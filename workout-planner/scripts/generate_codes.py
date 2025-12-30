#!/usr/bin/env python3
"""
Generate random registration codes for the workout planner app.
"""
import secrets
import string
from database import get_db, get_cursor

def generate_code(length=8):
    """Generate a random alphanumeric code."""
    # Use uppercase letters and digits for easier typing
    alphabet = string.ascii_uppercase + string.digits
    # Exclude easily confused characters: 0, O, 1, I, L
    alphabet = alphabet.replace('0', '').replace('O', '').replace('1', '').replace('I', '').replace('L', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def insert_codes(num_codes=50):
    """Generate and insert registration codes into the database."""
    codes_generated = []

    with get_db() as conn:
        cur = get_cursor(conn)

        for _ in range(num_codes):
            # Keep trying until we get a unique code
            while True:
                code = generate_code()
                try:
                    cur.execute(
                        "INSERT INTO registration_codes (code) VALUES (?)" if "sqlite" in str(type(conn))
                        else "INSERT INTO registration_codes (code) VALUES (%s)",
                        (code,)
                    )
                    codes_generated.append(code)
                    break
                except Exception:
                    # Code already exists, try again
                    continue

        conn.commit()

    return codes_generated

if __name__ == "__main__":
    print("Generating 50 registration codes...")
    codes = insert_codes(50)

    print(f"\nSuccessfully generated {len(codes)} codes:")
    print("-" * 40)
    for i, code in enumerate(codes, 1):
        print(f"{i:2d}. {code}")

    print("\nCodes have been inserted into the database.")
