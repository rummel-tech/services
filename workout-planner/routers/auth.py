"""Authentication router with registration, login, and token management."""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from datetime import datetime
import uuid
from core.database import get_db, get_cursor
from core.logging_config import get_logger
from core import metrics
from slowapi import Limiter
from slowapi.util import get_remote_address
from core.settings import get_settings

log = get_logger("api.auth")

# Use environment-aware rate limiting - high limits for dev/test, strict for production
settings = get_settings()
if settings.environment == "production":
    limiter = Limiter(key_func=get_remote_address)
    REGISTER_LIMIT = "5/minute"
    LOGIN_LIMIT = "10/minute"
    REFRESH_LIMIT = "10/minute"
    LOGOUT_LIMIT = "20/minute"
else:
    # Very high limits for development/testing to avoid interference
    limiter = Limiter(key_func=get_remote_address, default_limits=["10000 per minute"])
    REGISTER_LIMIT = "10000/minute"
    LOGIN_LIMIT = "10000/minute"
    REFRESH_LIMIT = "10000/minute"
    LOGOUT_LIMIT = "10000/minute"
from core.auth_service import (
    UserCreate, UserLogin, User, Token, TokenData,
    get_password_hash, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from core.redis_client import is_token_blacklisted, blacklist_token
import time

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)  # Don't auto-error so we can handle dev mode


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> TokenData:
    """Dependency to extract and validate current user from JWT token.

    In development mode with DISABLE_AUTH=true, returns a stub user without authentication.
    """
    settings = get_settings()

    # Development mode bypass
    if settings.disable_auth and settings.environment == "development":
        log.info("auth_bypassed_dev_mode", extra={"stub_user": "user-123"})
        return TokenData(
            user_id="user-123",
            email="dev@example.com",
            jti="dev-stub-token",
            exp=None
        )

    # Production mode - require authentication
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    token_data = decode_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is blacklisted
    if token_data.jti and is_token_blacklisted(token_data.jti):
        log.warning("auth_token_blacklisted", extra={"jti": token_data.jti, "user_id": token_data.user_id})
        metrics.record_domain_event("auth_token_blacklisted")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data


def get_admin_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Dependency to check if current user is an admin.

    In development mode, allows all users to be admins.
    """
    settings = get_settings()

    # Development mode bypass
    if settings.disable_auth and settings.environment == "development":
        return current_user

    # Check if user is admin
    user = get_user_by_id(current_user.user_id)
    if not user or not user.get("is_admin"):
        log.warning("auth_admin_access_denied", extra={"user_id": current_user.user_id})
        metrics.record_domain_event("auth_admin_access_denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


def get_user_by_email(email: str):
    """Fetch user from database by email (case-insensitive)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def get_user_by_id(user_id: str):
    """Fetch user from database by ID."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def create_user(user: UserCreate, registration_code: str) -> dict:
    """Create new user in database."""
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user.password)
    # Normalize email to lowercase for consistent storage
    normalized_email = user.email.lower()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO users (id, email, hashed_password, full_name, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (user_id, normalized_email, hashed_password, user.full_name)
        )
        cur.execute("UPDATE registration_codes SET is_used = 1, used_by_user_id = ? WHERE code = ?", (user_id, registration_code))
        conn.commit()

    return get_user_by_id(user_id)


@router.post("/validate-code")
@limiter.limit(LOGIN_LIMIT)
async def validate_registration_code(request: Request, code: str):
    """Validate a registration code without using it.

    Returns whether the code is valid and can be used for registration.
    """
    if not code or len(code) < 4:
        return {"valid": False, "message": "Invalid code format"}

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT code, expires_at FROM registration_codes
            WHERE code = ? AND is_used = 0
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """, (code.upper(),))
        code_row = cur.fetchone()

        if code_row:
            log.info("auth_code_validated", extra={"code": code})
            return {"valid": True, "message": "Code is valid"}
        else:
            log.info("auth_code_invalid", extra={"code": code})
            return {"valid": False, "message": "Invalid or expired code"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, user: UserCreate):
    """Register a new user account or add to waitlist if no valid code."""
    # Check if user already exists
    existing_user = get_user_by_email(user.email)
    if existing_user:
        log.warning("auth_register_email_exists", extra={"email": user.email})
        metrics.record_domain_event("auth_register_email_exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check for valid registration code
    if not user.registration_code:
        # No code provided - add to waitlist
        with get_db() as conn:
            cur = get_cursor(conn)
            try:
                cur.execute("INSERT INTO waitlist (email) VALUES (?)", (user.email,))
                conn.commit()
                log.info("auth_register_waitlist_added", extra={"email": user.email})
                metrics.record_domain_event("auth_register_waitlist_added")
                return {
                    "status": "waitlisted",
                    "message": "You have been added to the waiting list. We'll notify you when registration opens."
                }
            except Exception as e:
                # Email might already be on waitlist
                log.warning("auth_register_waitlist_duplicate", extra={"email": user.email})
                return {
                    "status": "waitlisted",
                    "message": "You are already on the waiting list."
                }

    # Verify registration code
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT * FROM registration_codes
            WHERE code = ? AND is_used = 0
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """, (user.registration_code,))
        code_row = cur.fetchone()
        if not code_row:
            # Invalid or used code - add to waitlist
            try:
                cur.execute("INSERT INTO waitlist (email) VALUES (?)", (user.email,))
                conn.commit()
                log.warning("auth_register_invalid_code", extra={"email": user.email, "code": user.registration_code})
                metrics.record_domain_event("auth_register_invalid_code_waitlisted")
                return {
                    "status": "waitlisted",
                    "message": "Invalid or used registration code. You have been added to the waiting list."
                }
            except Exception:
                # Already on waitlist
                log.warning("auth_register_invalid_code_already_waitlisted", extra={"email": user.email})
                return {
                    "status": "waitlisted",
                    "message": "Invalid or used registration code. You are already on the waiting list."
                }

    # Valid code - create user
    db_user = create_user(user, user.registration_code)

    # Generate tokens
    access_token = create_access_token(data={"sub": db_user["id"], "email": db_user["email"]})
    refresh_token = create_refresh_token(data={"sub": db_user["id"], "email": db_user["email"]})

    log.info("auth_register_success", extra={"user_id": db_user["id"], "email": db_user["email"]})
    metrics.record_domain_event("auth_register_success")
    return {
        "status": "registered",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/login", response_model=Token)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, credentials: UserLogin):
    """Authenticate user and return JWT tokens."""
    # Find user
    user = get_user_by_email(credentials.email)
    if not user:
        log.warning("auth_login_invalid_email", extra={"email": credentials.email})
        metrics.record_domain_event("auth_login_invalid_email")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Verify password
    if not verify_password(credentials.password, user["hashed_password"]):
        log.warning("auth_login_bad_password", extra={"email": credentials.email})
        metrics.record_domain_event("auth_login_bad_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if user is active
    if not user["is_active"]:
        log.warning("auth_login_inactive", extra={"user_id": user["id"]})
        metrics.record_domain_event("auth_login_inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Generate tokens
    access_token = create_access_token(data={"sub": user["id"], "email": user["email"]})
    refresh_token = create_refresh_token(data={"sub": user["id"], "email": user["email"]})
    
    log.info("auth_login_success", extra={"user_id": user["id"], "email": user["email"]})
    metrics.record_domain_event("auth_login_success")
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
@limiter.limit(REFRESH_LIMIT)
async def refresh_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Refresh access token using refresh token."""
    token = credentials.credentials
    token_data = decode_token(token)
    
    if token_data is None:
        log.warning("auth_refresh_invalid_token")
        metrics.record_domain_event("auth_refresh_invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Verify user still exists and is active
    user = get_user_by_id(token_data.user_id)
    if not user or not user["is_active"]:
        log.warning("auth_refresh_user_invalid", extra={"user_id": token_data.user_id})
        metrics.record_domain_event("auth_refresh_user_invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Generate new tokens
    access_token = create_access_token(data={"sub": user["id"], "email": user["email"]})
    refresh_token = create_refresh_token(data={"sub": user["id"], "email": user["email"]})
    
    log.info("auth_refresh_success", extra={"user_id": user["id"]})
    metrics.record_domain_event("auth_refresh_success")
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """Get current authenticated user information."""
    user = get_user_by_id(current_user.user_id)
    if not user:
        log.warning("auth_me_not_found", extra={"user_id": current_user.user_id})
        metrics.record_domain_event("auth_me_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return User(
        id=user["id"],
        email=user["email"],
        full_name=user.get("full_name"),
        is_active=bool(user["is_active"]),
        created_at=user["created_at"]
    )


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """Logout user and blacklist the current token."""
    # Blacklist the token using its JTI
    if current_user.jti and current_user.exp:
        # Calculate TTL (time until token naturally expires)
        now = int(time.time())
        ttl_seconds = max(current_user.exp - now, 60)  # Minimum 60 seconds

        # Add token to blacklist
        blacklist_success = blacklist_token(current_user.jti, ttl_seconds)

        if blacklist_success:
            log.info("auth_logout_blacklisted", extra={
                "user_id": current_user.user_id,
                "jti": current_user.jti,
                "ttl": ttl_seconds
            })
        else:
            log.warning("auth_logout_blacklist_failed", extra={
                "user_id": current_user.user_id,
                "jti": current_user.jti
            })

    log.info("auth_logout", extra={"user_id": current_user.user_id})
    metrics.record_domain_event("auth_logout")
    return {"message": "Successfully logged out"}


@router.get("/admin/codes")
async def list_registration_codes(
    current_user: TokenData = Depends(get_admin_user),
    limit: int = 100,
    show_used: bool = False
):
    """List registration codes (admin only)."""
    with get_db() as conn:
        cur = get_cursor(conn)

        if show_used:
            cur.execute("""
                SELECT code, is_used, used_by_user_id, expires_at,
                       distributed_to, distributed_at, distributed_by_user_id, created_at
                FROM registration_codes
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
        else:
            cur.execute("""
                SELECT code, is_used, used_by_user_id, expires_at,
                       distributed_to, distributed_at, distributed_by_user_id, created_at
                FROM registration_codes
                WHERE is_used = 0
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

        codes = [dict(row) for row in cur.fetchall()]

    log.info("admin_codes_listed", extra={"user_id": current_user.user_id, "count": len(codes)})
    return {
        "codes": codes,
        "total": len(codes)
    }


@router.get("/admin/waitlist")
async def list_waitlist(
    current_user: TokenData = Depends(get_admin_user),
    limit: int = 100
):
    """List users on the waitlist (admin only)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT email, created_at
            FROM waitlist
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))

        waitlist = [dict(row) for row in cur.fetchall()]

    log.info("admin_waitlist_listed", extra={"user_id": current_user.user_id, "count": len(waitlist)})
    return {
        "waitlist": waitlist,
        "total": len(waitlist)
    }


@router.post("/admin/codes/generate")
async def generate_codes(
    current_user: TokenData = Depends(get_admin_user),
    count: int = 10,
    expires_in_days: Optional[int] = 30
):
    """Generate new registration codes (admin only).

    Args:
        count: Number of codes to generate (1-100)
        expires_in_days: Number of days until codes expire (default 30, null for no expiration)
    """
    import secrets
    import string
    from datetime import datetime, timedelta

    if count < 1 or count > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Count must be between 1 and 100"
        )

    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace('0', '').replace('O', '').replace('1', '').replace('I', '').replace('L', '')

    # Calculate expiration date if specified
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        expires_at_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
    else:
        expires_at_str = None

    codes_generated = []

    with get_db() as conn:
        cur = get_cursor(conn)

        for _ in range(count):
            while True:
                code = ''.join(secrets.choice(alphabet) for _ in range(8))
                try:
                    if expires_at_str:
                        cur.execute(
                            "INSERT INTO registration_codes (code, expires_at) VALUES (?, ?)",
                            (code, expires_at_str)
                        )
                    else:
                        cur.execute("INSERT INTO registration_codes (code) VALUES (?)", (code,))
                    codes_generated.append(code)
                    break
                except Exception:
                    continue

        conn.commit()

    log.info("admin_codes_generated", extra={
        "user_id": current_user.user_id,
        "count": len(codes_generated),
        "expires_at": expires_at_str
    })
    metrics.record_domain_event("admin_codes_generated")
    return {
        "codes": codes_generated,
        "count": len(codes_generated),
        "expires_at": expires_at_str
    }


@router.post("/admin/waitlist/invite")
async def invite_from_waitlist(
    current_user: TokenData = Depends(get_admin_user),
    email: str = None,
    expires_in_days: Optional[int] = 30
):
    """Invite a user from the waitlist by generating a code and removing them.

    Args:
        email: Email address to invite
        expires_in_days: Number of days until code expires (default 30)
    """
    import secrets
    import string
    from datetime import datetime, timedelta

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )

    with get_db() as conn:
        cur = get_cursor(conn)

        # Check if user is on waitlist
        cur.execute("SELECT email FROM waitlist WHERE email = ?", (email,))
        waitlist_entry = cur.fetchone()

        if not waitlist_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Email '{email}' not found on waitlist"
            )

        # Generate a registration code
        alphabet = string.ascii_uppercase + string.digits
        alphabet = alphabet.replace('0', '').replace('O', '').replace('1', '').replace('I', '').replace('L', '')

        # Calculate expiration date
        expires_at = None
        if expires_in_days is not None:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            expires_at_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
        else:
            expires_at_str = None

        # Generate unique code with distribution tracking
        while True:
            code = ''.join(secrets.choice(alphabet) for _ in range(8))
            try:
                now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                if expires_at_str:
                    cur.execute(
                        """INSERT INTO registration_codes
                           (code, expires_at, distributed_to, distributed_at, distributed_by_user_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (code, expires_at_str, email, now_str, current_user.user_id)
                    )
                else:
                    cur.execute(
                        """INSERT INTO registration_codes
                           (code, distributed_to, distributed_at, distributed_by_user_id)
                           VALUES (?, ?, ?, ?)""",
                        (code, email, now_str, current_user.user_id)
                    )
                break
            except Exception:
                continue

        # Remove from waitlist
        cur.execute("DELETE FROM waitlist WHERE email = ?", (email,))
        conn.commit()

    log.info("admin_waitlist_invited", extra={
        "user_id": current_user.user_id,
        "email": email,
        "code": code,
        "expires_at": expires_at_str
    })
    metrics.record_domain_event("admin_waitlist_invited")

    return {
        "email": email,
        "code": code,
        "expires_at": expires_at_str,
        "message": f"Generated code '{code}' for {email} and removed from waitlist"
    }


@router.delete("/admin/waitlist/{email}")
async def remove_from_waitlist(
    email: str,
    current_user: TokenData = Depends(get_admin_user)
):
    """Remove a user from the waitlist without sending them a code."""
    with get_db() as conn:
        cur = get_cursor(conn)

        # Check if user is on waitlist
        cur.execute("SELECT email FROM waitlist WHERE email = ?", (email,))
        waitlist_entry = cur.fetchone()

        if not waitlist_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Email '{email}' not found on waitlist"
            )

        # Remove from waitlist
        cur.execute("DELETE FROM waitlist WHERE email = ?", (email,))
        conn.commit()

    log.info("admin_waitlist_removed", extra={
        "user_id": current_user.user_id,
        "email": email
    })
    metrics.record_domain_event("admin_waitlist_removed")

    return {
        "email": email,
        "message": f"Removed {email} from waitlist"
    }
