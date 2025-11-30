#!/usr/bin/env python3
"""
Make a user an admin by email address.
"""
import sys
from database import get_db, get_cursor

def make_admin(email):
    """Promote a user to admin status."""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Check if user exists
        cur.execute("SELECT id, email, is_admin FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        
        if not user:
            print(f"Error: No user found with email '{email}'")
            return False
        
        if user['is_admin']:
            print(f"User '{email}' is already an admin")
            return True
        
        # Make user admin
        cur.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
        conn.commit()
        
        print(f"Success: User '{email}' (ID: {user['id']}) is now an admin")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
        print("Example: python make_admin.py valid@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    success = make_admin(email)
    sys.exit(0 if success else 1)
