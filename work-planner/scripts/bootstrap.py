#!/usr/bin/env python3
"""
Bootstrap script — creates the first admin user and initial registration codes.

Run this once after deploying to a fresh database. Safe to re-run; it checks
for existing data before inserting.

Usage:
    python scripts/bootstrap.py
    python scripts/bootstrap.py --codes 10
    python scripts/bootstrap.py --email admin@example.com --codes 20

Environment variables (or .env file):
    DATABASE_URL  — defaults to sqlite:///work_dev.db
    BOOTSTRAP_EMAIL    — admin email (overridden by --email flag)
    BOOTSTRAP_PASSWORD — admin password (prompted if not set)
"""

import sys
import os
import uuid
import argparse
import getpass
import sqlite3
import random
import string
from pathlib import Path
from datetime import datetime, timezone

# Add project root and common to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.settings import get_settings
from core.auth_service import get_password_hash

settings = get_settings()
DATABASE_URL = settings.database_url
USE_SQLITE = DATABASE_URL.startswith('sqlite')


def get_conn():
    if USE_SQLITE:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    else:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(dsn=DATABASE_URL)
            return conn
        except ImportError:
            print('ERROR: psycopg2 not installed. Run: pip install psycopg2-binary')
            sys.exit(1)


def placeholder(n: int = 1) -> str:
    """Return SQL placeholder(s) compatible with both SQLite (?) and Postgres (%s)."""
    ph = '%s' if not USE_SQLITE else '?'
    return ', '.join([ph] * n)


def generate_code(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def bootstrap(email: str, password: str, num_codes: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    ph = '?' if USE_SQLITE else '%s'

    # -------------------------------------------------------------------------
    # Ensure schema exists (runs the same CREATE IF NOT EXISTS as database.py)
    # -------------------------------------------------------------------------
    if USE_SQLITE:
        from core.database import _init_sqlite
        _init_sqlite()
        # Re-open after init
        conn.close()
        conn = get_conn()
        cur = conn.cursor()

    # -------------------------------------------------------------------------
    # Create admin user (idempotent)
    # -------------------------------------------------------------------------
    cur.execute(f'SELECT id, is_admin FROM users WHERE LOWER(email) = LOWER({ph})', (email,))
    existing = cur.fetchone()

    if existing:
        user_id = existing['id'] if USE_SQLITE else existing[0]
        is_admin = existing['is_admin'] if USE_SQLITE else existing[1]
        if is_admin:
            print(f'  Admin already exists: {email}')
        else:
            cur.execute(
                f'UPDATE users SET is_admin = 1 WHERE id = {ph}',
                (user_id,),
            )
            conn.commit()
            print(f'  Promoted existing user to admin: {email}')
    else:
        user_id = str(uuid.uuid4())
        hashed = get_password_hash(password)
        cur.execute(
            f'''INSERT INTO users (id, email, hashed_password, is_active, is_admin, created_at, updated_at)
                VALUES ({placeholder(7)})''',
            (user_id, email.lower(), hashed, 1, 1,
             datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        print(f'  Created admin user: {email}  (id: {user_id})')

    # -------------------------------------------------------------------------
    # Generate registration codes
    # -------------------------------------------------------------------------
    codes_created = 0
    for _ in range(num_codes):
        code = generate_code()
        try:
            cur.execute(
                f'INSERT INTO registration_codes (code, is_used) VALUES ({placeholder(2)})',
                (code, 0),
            )
            conn.commit()
            codes_created += 1
            print(f'  Registration code: {code}')
        except Exception:
            # Collision — skip
            pass

    conn.close()
    print(f'\nDone. Created {codes_created} registration code(s).')
    print('Share codes with beta users. Each code can be used once.')


def main() -> None:
    parser = argparse.ArgumentParser(description='Bootstrap work-planner admin + registration codes')
    parser.add_argument('--email', default=os.getenv('BOOTSTRAP_EMAIL', ''), help='Admin email address')
    parser.add_argument('--codes', type=int, default=5, help='Number of registration codes to generate (default: 5)')
    args = parser.parse_args()

    print(f'Work Planner Bootstrap')
    print(f'Database: {DATABASE_URL}\n')

    email = args.email or input('Admin email: ').strip()
    if not email or '@' not in email:
        print('ERROR: Invalid email address')
        sys.exit(1)

    password = os.getenv('BOOTSTRAP_PASSWORD') or getpass.getpass('Admin password (min 8 chars): ')
    if len(password) < 8:
        print('ERROR: Password must be at least 8 characters')
        sys.exit(1)

    bootstrap(email=email, password=password, num_codes=args.codes)


if __name__ == '__main__':
    main()
