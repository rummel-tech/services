"""
Chat Router
Handles chat sessions and messages with AI coach
"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
from database import get_db, get_cursor
from logging_config import get_logger
import metrics
from auth_service import TokenData
from routers.auth import get_current_user

log = get_logger("api.chat")
from ai_chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatMessage(BaseModel):
    session_id: Optional[int] = None
    user_id: str
    message: str

class ChatSession(BaseModel):
    user_id: str
    title: Optional[str] = None

class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    metadata: Optional[dict] = None
    created_at: str

class SessionResponse(BaseModel):
    id: int
    user_id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    message_count: int

@router.post("/sessions")
async def create_session(session: ChatSession, current_user: TokenData = Depends(get_current_user)):
    """Create a new chat session"""
    if current_user.user_id != session.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        
        title = session.title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        cur.execute("""
            INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (session.user_id, title, datetime.now().isoformat(), datetime.now().isoformat()))
        
        session_id = cur.lastrowid
        
        response = {
            "id": session_id,
            "user_id": session.user_id,
            "title": title,
            "created_at": datetime.now().isoformat()
        }
        log.info("chat_session_created", extra={"session_id": session_id, "user_id": session.user_id})
        metrics.record_domain_event("chat_session_created")
        return response

@router.get("/sessions")
async def list_sessions(user_id: str, limit: int = 20, current_user: TokenData = Depends(get_current_user)):
    """List user's chat sessions"""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        
        cur.execute("""
            SELECT s.id, s.user_id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) as message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            WHERE s.user_id = ?
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        sessions = [dict(s) for s in cur.fetchall()]
        log.info("chat_sessions_list", extra={"user_id": user_id, "count": len(sessions)})
        metrics.record_domain_event("chat_sessions_list")
        return sessions

@router.get("/sessions/{session_id}")
async def get_session(session_id: int, user_id: str):
    """Get session details"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        cur.execute("""
            SELECT s.id, s.user_id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) as message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            WHERE s.id = ? AND s.user_id = ?
            GROUP BY s.id
        """, (session_id, user_id))
        
        session = cur.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        result = dict(session)
        log.info("chat_session_retrieved", extra={"session_id": session_id, "user_id": user_id})
        metrics.record_domain_event("chat_session_retrieved")
        return result

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, user_id: str):
    """Delete a chat session and its messages"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Verify ownership
        cur.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?", 
                   (session_id, user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Delete messages first
        cur.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        
        # Delete session
        cur.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        
        log.info("chat_session_deleted", extra={"session_id": session_id, "user_id": user_id})
        metrics.record_domain_event("chat_session_deleted")
        return {"status": "deleted", "session_id": session_id}

@router.post("/messages")
async def send_message(chat: ChatMessage):
    """Send a message and get AI response"""
    session_id = chat.session_id
    
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Create session if not provided
        if not session_id:
            title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            cur.execute("""
                INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (chat.user_id, title, datetime.now().isoformat(), datetime.now().isoformat()))
            session_id = cur.lastrowid
            log.info("chat_session_auto_created", extra={"session_id": session_id, "user_id": chat.user_id})
            metrics.record_domain_event("chat_session_auto_created")
        else:
            # Verify session exists and belongs to user
            cur.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
                       (session_id, chat.user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Session not found")
        
        # Get recent chat history for context
        cur.execute("""
            SELECT role, content
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (session_id,))
        history = [dict(row) for row in cur.fetchall()]
        history.reverse()  # Chronological order
        
        # Save user message
        cur.execute("""
            INSERT INTO chat_messages (session_id, user_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, chat.user_id, "user", chat.message, datetime.now().isoformat()))
        user_message_id = cur.lastrowid
        log.info("chat_user_message_saved", extra={"session_id": session_id, "message_id": user_message_id, "user_id": chat.user_id})
        metrics.record_domain_event("chat_user_message_saved")
        
        # Generate AI response
        ai_result = await chat_service.generate_response(
            user_id=chat.user_id,
            message=chat.message,
            session_id=session_id,
            chat_history=history
        )
        
        # Save AI response
        metadata_json = json.dumps(ai_result.get("metadata", {}))
        cur.execute("""
            INSERT INTO chat_messages (session_id, user_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, chat.user_id, "assistant", ai_result["response"], 
              metadata_json, datetime.now().isoformat()))
        assistant_message_id = cur.lastrowid
        log.info("chat_assistant_message_saved", extra={"session_id": session_id, "message_id": assistant_message_id, "user_id": chat.user_id})
        metrics.record_domain_event("chat_assistant_message_saved")
        
        # Update session timestamp
        cur.execute("""
            UPDATE chat_sessions SET updated_at = ? WHERE id = ?
        """, (datetime.now().isoformat(), session_id))
        
        conn.commit()
        
        response = {
            "session_id": session_id,
            "user_message": {
                "id": user_message_id,
                "role": "user",
                "content": chat.message,
                "created_at": datetime.now().isoformat()
            },
            "assistant_message": {
                "id": assistant_message_id,
                "role": "assistant",
                "content": ai_result["response"],
                "metadata": ai_result.get("metadata"),
                "created_at": datetime.now().isoformat()
            }
        }
        log.info("chat_exchange_complete", extra={"session_id": session_id, "user_id": chat.user_id})
        metrics.record_domain_event("chat_exchange_complete")
        return response

@router.get("/messages/{session_id}")
async def get_messages(session_id: int, user_id: str, limit: int = 50):
    """Get messages for a session"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Verify session belongs to user
        cur.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
                   (session_id, user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get messages
        cur.execute("""
            SELECT id, session_id, role, content, metadata, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (session_id, limit))
        
        messages = cur.fetchall()
        result = []
        for msg in messages:
            msg_dict = dict(msg)
            if msg_dict.get("metadata"):
                try:
                    msg_dict["metadata"] = json.loads(msg_dict["metadata"])
                except:
                    pass
            result.append(msg_dict)
        
        log.info("chat_messages_list", extra={"session_id": session_id, "user_id": user_id, "count": len(result)})
        metrics.record_domain_event("chat_messages_list")
        return result

@router.get("/context/{user_id}")
async def get_user_context(user_id: str):
    """Get user's health context for debugging/display"""
    context = chat_service.get_user_context(user_id)
    return context
