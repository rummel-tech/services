"""
Test AI Chat Integration
Run: pytest test_chat.py -v
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import app
from database import get_db, get_cursor

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    """Clean chat tables before each test"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM chat_messages")
        cur.execute("DELETE FROM chat_sessions")
        conn.commit()
    yield

class TestChatSessions:
    """Test chat session management"""
    
    def test_create_session(self):
        """Test creating a new chat session"""
        response = client.post(
            "/chat/sessions",
            json={"user_id": "test-user", "title": "Test Chat"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user"
        assert data["title"] == "Test Chat"
        assert "id" in data
    
    def test_list_sessions(self):
        """Test listing user sessions"""
        # Create two sessions
        client.post("/chat/sessions", json={"user_id": "user-1", "title": "Chat 1"})
        client.post("/chat/sessions", json={"user_id": "user-1", "title": "Chat 2"})
        client.post("/chat/sessions", json={"user_id": "user-2", "title": "Other User"})
        
        response = client.get("/chat/sessions?user_id=user-1")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 2
        assert all(s["user_id"] == "user-1" for s in sessions)
    
    def test_get_session(self):
        """Test getting session details"""
        create_resp = client.post(
            "/chat/sessions",
            json={"user_id": "test-user", "title": "My Chat"}
        )
        session_id = create_resp.json()["id"]
        
        response = client.get(f"/chat/sessions/{session_id}?user_id=test-user")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["title"] == "My Chat"
    
    def test_delete_session(self):
        """Test deleting a session"""
        create_resp = client.post(
            "/chat/sessions",
            json={"user_id": "test-user"}
        )
        session_id = create_resp.json()["id"]
        
        response = client.delete(f"/chat/sessions/{session_id}?user_id=test-user")
        assert response.status_code == 200
        
        # Verify it's gone
        get_resp = client.get(f"/chat/sessions/{session_id}?user_id=test-user")
        assert get_resp.status_code == 404

class TestChatMessages:
    """Test chat messaging functionality"""
    
    def test_send_message_creates_session(self):
        """Test sending message without session_id creates new session"""
        response = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "Hello coach!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["user_message"]["content"] == "Hello coach!"
        assert data["assistant_message"]["role"] == "assistant"
        assert len(data["assistant_message"]["content"]) > 0
    
    def test_send_message_with_existing_session(self):
        """Test sending message to existing session"""
        # Create session
        session_resp = client.post(
            "/chat/sessions",
            json={"user_id": "test-user"}
        )
        session_id = session_resp.json()["id"]
        
        # Send message
        response = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "What should I train today?",
                "session_id": session_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
    
    def test_get_messages(self):
        """Test retrieving messages from session"""
        # Send a message (creates session)
        send_resp = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "Hello"
            }
        )
        session_id = send_resp.json()["session_id"]
        
        # Get messages
        response = client.get(f"/chat/messages/{session_id}?user_id=test-user")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 2  # User message + assistant response
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
    
    def test_message_with_context(self):
        """Test that AI response includes context metadata"""
        response = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "How is my recovery?"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data["assistant_message"]
        metadata = data["assistant_message"]["metadata"]
        assert "context" in metadata

class TestUserContext:
    """Test user context retrieval"""
    
    def test_get_user_context(self):
        """Test fetching user context for AI prompts"""
        response = client.get("/chat/context/test-user")
        assert response.status_code == 200
        context = response.json()
        assert "goals" in context
        assert "recent_health" in context
        assert "summary" in context

class TestChatIntegration:
    """Test full chat conversation flow"""
    
    def test_multi_message_conversation(self):
        """Test multiple messages in same session preserve context"""
        # First message
        resp1 = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "I want to run a marathon"
            }
        )
        session_id = resp1.json()["session_id"]
        
        # Second message in same session
        resp2 = client.post(
            "/chat/messages",
            json={
                "user_id": "test-user",
                "message": "When should I start training?",
                "session_id": session_id
            }
        )
        assert resp2.status_code == 200
        assert resp2.json()["session_id"] == session_id
        
        # Check messages in order
        messages_resp = client.get(f"/chat/messages/{session_id}?user_id=test-user")
        messages = messages_resp.json()
        assert len(messages) == 4  # 2 user + 2 assistant
        assert messages[0]["content"] == "I want to run a marathon"
        assert messages[2]["content"] == "When should I start training?"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
