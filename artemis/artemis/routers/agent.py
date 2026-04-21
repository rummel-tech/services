"""AI agent endpoints — HTTP chat and WebSocket."""
import json
import logging
import sys
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from common.tasks import enqueue, get_job, task

from artemis.core.agent import run_agent, stream_agent
from artemis.core.auth import validate_token
from artemis.core.registry import registry

log = logging.getLogger("artemis.agent_router")
router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None
    async_mode: bool = False  # if True, dispatches as background job and returns job_id immediately


class ChatResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []


class AsyncChatResponse(BaseModel):
    job_id: str
    status: str = "pending"


@task("agent_chat")
async def _run_agent_task(message: str, token_payload: dict, token: str, history: list) -> dict:
    return await run_agent(
        user_message=message,
        token_payload=token_payload,
        token=token,
        conversation_history=history or [],
    )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Send a message to the Artemis AI agent.

    - Synchronous (default): waits for the full response (use WebSocket for streaming).
    - Async (async_mode=true): dispatches immediately, returns job_id. Poll GET /agent/jobs/{job_id}.
    """
    token = authorization.split(" ", 1)[1] if authorization else ""

    if body.async_mode:
        job_id = enqueue(
            background_tasks,
            _run_agent_task,
            message=body.message,
            token_payload=token_payload,
            token=token,
            history=body.history or [],
        )
        return AsyncChatResponse(job_id=job_id)

    result = await run_agent(
        user_message=body.message,
        token_payload=token_payload,
        token=token,
        conversation_history=body.history,
    )
    return ChatResponse(response=result["response"], tool_calls=result["tool_calls"])


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    token_payload: dict = Depends(validate_token),
):
    """Poll the status of an async agent chat job."""
    job = get_job(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
