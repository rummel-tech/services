#!/usr/bin/env python3
"""
AI Chat Demo Script
Demonstrates the chat integration without starting the full server
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ai_chat_service import AIChatService
from database import get_db, get_cursor, init_sqlite
import asyncio

print("🤖 AI Coach Chat Demo\n")
print("=" * 60)

# Initialize database
print("📊 Initializing database...")
init_sqlite()

# Create service
print("🧠 Creating AI service (mock mode)...")
service = AIChatService()

# Test user context retrieval
print("\n📋 User Context:")
print("-" * 60)
context = service.get_user_context("demo-user", days=7)
print(f"Summary: {context['summary']}")
print(f"Goals: {len(context['goals'])} active")
print(f"Health Metrics: {len(context['recent_health'])} types")
print(f"Readiness: {context.get('readiness', 'Not calculated')}")

# Test system prompt generation
print("\n📝 System Prompt Generated:")
print("-" * 60)
system_prompt = service.build_system_prompt(context)
print(system_prompt[:300] + "..." if len(system_prompt) > 300 else system_prompt)

# Test mock responses
print("\n💬 Testing Mock Responses:")
print("-" * 60)

async def demo_chat():
    test_messages_list = [
        "What should I train today?",
        "How is my recovery?",
        "Help me set a marathon goal",
        "What does HRV mean?",
    ]
    for msg in test_messages_list:
        print(f"\n👤 User: {msg}")
        result = await service.generate_response(
            user_id="demo-user",
            message=msg,
            session_id=None,
            chat_history=[]
        )
        print(f"🤖 AI: {result['response']}")
        if result.get('metadata'):
            print(f"   └─ Context: {result['metadata'].get('context', 'N/A')}")

asyncio.run(demo_chat())

# Test database operations
print("\n\n🗄️  Testing Database Operations:")
print("-" * 60)

with get_db() as conn:
    cur = get_cursor(conn)
    
    # Create session
    cur.execute("""
        INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
        VALUES (?, ?, datetime('now'), datetime('now'))
    """, ("demo-user", "Demo Chat"))
    session_id = cur.lastrowid
    print(f"✅ Created session: {session_id}")
    
    # Add messages
    cur.execute("""
        INSERT INTO chat_messages (session_id, user_id, role, content, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (session_id, "demo-user", "user", "Hello!"))
    
    cur.execute("""
        INSERT INTO chat_messages (session_id, user_id, role, content, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (session_id, "demo-user", "assistant", "Hi! How can I help you today?"))
    
    print("✅ Added 2 messages")
    
    # Query messages
    cur.execute("""
        SELECT role, content FROM chat_messages WHERE session_id = ?
    """, (session_id,))
    
    messages = cur.fetchall()
    print(f"\n📨 Messages in session {session_id}:")
    for msg in messages:
        role = msg[0] if isinstance(msg, tuple) else msg['role']
        content = msg[1] if isinstance(msg, tuple) else msg['content']
        print(f"   {role}: {content}")
    
    conn.commit()

print("\n" + "=" * 60)
print("✅ Demo Complete!")
print("\nNext Steps:")
print("1. Run backend: uvicorn main:app --reload")
print("2. Test API: curl -X POST http://localhost:8000/chat/messages \\")
print("     -H 'Content-Type: application/json' \\")
print("     -d '{\"user_id\": \"test\", \"message\": \"Hello!\"}'")
print("3. Run Flutter app and tap chat icon")
print("\n📚 See AI_COACH_CHAT.md for full documentation")
