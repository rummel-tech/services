"""AI agent endpoints — HTTP chat and WebSocket."""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from artemis.core.agent import run_agent, stream_agent
from artemis.core.auth import validate_token
from artemis.core.registry import registry

log = logging.getLogger("artemis.agent_router")
router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
) -> ChatResponse:
    """Send a message to the Artemis AI agent and get a response."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    result = await run_agent(
        user_message=body.message,
        token_payload=token_payload,
        token=token,
        conversation_history=body.history,
    )
    return ChatResponse(response=result["response"], tool_calls=result["tool_calls"])


@router.get("/tools")
async def list_tools(token: dict = Depends(validate_token)) -> List[Dict[str, Any]]:
    """List all Claude tool definitions currently available from registered modules."""
    return registry.build_claude_tools()


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming agent interactions.

    Protocol:
      Client sends: {"message": "...", "token": "Bearer ..."}
      Server sends: {"type": "text", "content": "..."} chunks
                    {"type": "tool_call", "tool": "...", "result": {...}}
                    {"type": "done"}
                    {"type": "error", "detail": "..."}
    """
    await websocket.accept()
    token_payload: Optional[dict] = None
    token: str = ""

    try:
        # First message must contain the auth token
        auth_msg = await websocket.receive_text()
        try:
            auth_data = json.loads(auth_msg)
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
            await websocket.close(code=1003)
            return

        raw_token = auth_data.get("token", "")
        if raw_token.startswith("Bearer "):
            token = raw_token.split(" ", 1)[1]
        else:
            token = raw_token

        # Validate token
        from artemis.core.auth import fetch_public_key
        from jose import JWTError, jwt as jose_jwt
        pub_key = await fetch_public_key()
        if pub_key:
            try:
                token_payload = jose_jwt.decode(token, pub_key, algorithms=["RS256"], issuer="artemis-auth")
            except JWTError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid token"}))
                await websocket.close(code=1008)
                return
        else:
            # Dev fallback
            try:
                token_payload = jose_jwt.get_unverified_claims(token)
            except Exception:
                token_payload = {"sub": "unknown", "name": "User", "modules": []}

        await websocket.send_text(json.dumps({"type": "connected", "user": token_payload.get("name")}))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
                continue

            user_message = msg.get("message", "")
            if not user_message:
                continue

            # Run agent and stream results
            result = await run_agent(
                user_message=user_message,
                token_payload=token_payload,
                token=token,
                conversation_history=msg.get("history"),
            )

            # Send tool calls as events
            for tc in result.get("tool_calls", []):
                await websocket.send_text(json.dumps({
                    "type": "tool_call",
                    "tool": tc["tool"],
                    "result": tc.get("result"),
                }))

            # Stream the final response in chunks
            text = result["response"]
            chunk_size = 80
            for i in range(0, len(text), chunk_size):
                await websocket.send_text(json.dumps({
                    "type": "text",
                    "content": text[i:i+chunk_size],
                }))

            await websocket.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        log.info("agent websocket disconnected")
    except Exception as e:
        log.error(f"agent websocket error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "detail": str(e)}))
        except Exception:
            pass
