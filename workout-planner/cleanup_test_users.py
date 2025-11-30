#!/usr/bin/env python3
"""Clean up test users and waitlist entries."""
from database import get_db, get_cursor

def cleanup():
    """Remove test users and waitlist entries."""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Delete test users (keeping the admin user)
        cur.execute("DELETE FROM users WHERE email LIKE '%example.com' AND email != 'valid@example.com'")
        deleted_users = cur.rowcount
        
        # Clear waitlist
        cur.execute("DELETE FROM waitlist")
        deleted_waitlist = cur.rowcount
        
        conn.commit()
        
        print(f"Cleaned up {deleted_users} test user(s)")
        print(f"Cleared {deleted_waitlist} waitlist entry(ies)")
        print("\nDatabase reset complete!")

if __name__ == "__main__":
    cleanup()
