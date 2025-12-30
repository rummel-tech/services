from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from core.database import get_db, get_cursor
from core.logging_config import get_logger
import metrics
from slowapi import Limiter
from slowapi.util import get_remote_address
from core.settings import get_settings

log = get_logger("api.waitlist")

# Use environment-aware rate limiting
settings = get_settings()
if settings.environment == "production":
    limiter = Limiter(key_func=get_remote_address)
    WAITLIST_LIMIT = "5/minute"
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=["10000 per minute"])
    WAITLIST_LIMIT = "10000/minute"
router = APIRouter(tags=["waitlist"])

class WaitlistCreate(BaseModel):
    email: EmailStr

@router.post("/waitlist", status_code=status.HTTP_201_CREATED)
@limiter.limit(WAITLIST_LIMIT)
async def join_waitlist(request: Request, data: WaitlistCreate):
    """Add a user to the waitlist."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM waitlist WHERE email = ?", (data.email,))
        if cur.fetchone():
            log.warning("waitlist_email_exists", extra={"email": data.email})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address already on the waitlist."
            )
        
        cur.execute("INSERT INTO waitlist (email) VALUES (?)", (data.email,))
        conn.commit()
    
    log.info("waitlist_email_added", extra={"email": data.email})
    metrics.record_domain_event("waitlist_joined")
    return {"message": "You have been added to the waitlist."}
