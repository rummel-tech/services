"""Teams router: create, list, manage teams and memberships."""
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from auth.core.database import get_cursor, get_db
from auth.routers.auth import get_current_user

router = APIRouter(prefix="/teams", tags=["teams"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,38}[a-z0-9]$")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
    name: str
    slug: str

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Slug must be 3-40 characters, lowercase alphanumeric and hyphens only, "
                "and must not start or end with a hyphen."
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class InviteRequest(BaseModel):
    email: str
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("owner", "admin", "member"):
            raise ValueError("role must be 'owner', 'admin', or 'member'")
        return v


class AcceptInviteRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_team(team_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_membership(team_id: str, user_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT * FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _require_member(team_id: str, user_id: str) -> dict:
    membership = _get_membership(team_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    return membership


def _require_owner_or_admin(team_id: str, user_id: str) -> dict:
    membership = _get_membership(team_id, user_id)
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owner or admin can perform this action",
        )
    return membership


def _team_member_count(team_id: str) -> int:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,))
        row = cur.fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new team. The caller automatically becomes the owner."""
    # Check slug uniqueness
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT id FROM teams WHERE slug = ?", (body.slug,))
        if cur.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")

    team_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO teams (id, name, slug, owner_id, plan, max_members, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'team', 10, ?, ?)""",
            (team_id, body.name, body.slug, current_user["id"], now, now),
        )
        cur.execute(
            """INSERT INTO team_members (id, team_id, user_id, role, joined_at)
               VALUES (?, ?, ?, 'owner', ?)""",
            (member_id, team_id, current_user["id"], now),
        )
        conn.commit()

    return _get_team(team_id)


@router.get("")
async def list_teams(current_user: dict = Depends(get_current_user)):
    """Return all teams the authenticated user belongs to, with their role."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT t.*, tm.role
               FROM teams t
               JOIN team_members tm ON tm.team_id = t.id
               WHERE tm.user_id = ?
               ORDER BY t.created_at DESC""",
            (current_user["id"],),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{team_id}")
async def get_team(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return team details with member list. Only accessible to team members."""
    team = _get_team(team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    _require_member(team_id, current_user["id"])

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT u.id, u.email, u.full_name, tm.role, tm.joined_at
               FROM team_members tm
               JOIN users u ON u.id = tm.user_id
               WHERE tm.team_id = ?
               ORDER BY tm.joined_at ASC""",
            (team_id,),
        )
        members = [dict(r) for r in cur.fetchall()]

    return {**team, "members": members}


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a team. Only the owner can do this."""
    team = _get_team(team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    if team["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can delete this team")

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        conn.commit()


@router.post("/{team_id}/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    team_id: str,
    body: InviteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Invite a user by email. Returns the invitation token (would be emailed in production)."""
    team = _get_team(team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    _require_owner_or_admin(team_id, current_user["id"])

    member_count = _team_member_count(team_id)
    if member_count >= team["max_members"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team has reached max members ({team['max_members']})",
        )

    invitation_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=7)).isoformat()
    now_iso = now.isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO team_invitations
                   (id, team_id, email, role, invited_by, token, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invitation_id,
                team_id,
                body.email.lower(),
                body.role,
                current_user["id"],
                token,
                expires_at,
                now_iso,
            ),
        )
        conn.commit()

    return {
        "invitation_id": invitation_id,
        "token": token,
        "expires_at": expires_at,
    }


@router.post("/invitations/accept")
async def accept_invitation(
    body: AcceptInviteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Accept a team invitation by token. Adds the current user to the team."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM team_invitations WHERE token = ?", (body.token,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation = dict(row)

    if invitation["accepted_at"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation already accepted")

    # Parse expires_at — stored as ISO string
    expires_raw = invitation["expires_at"]
    try:
        if isinstance(expires_raw, str):
            # Handle both offset-aware and naive strings
            if expires_raw.endswith("+00:00") or expires_raw.endswith("Z"):
                expires_dt = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
            else:
                expires_dt = datetime.fromisoformat(expires_raw).replace(tzinfo=timezone.utc)
        else:
            expires_dt = expires_raw.replace(tzinfo=timezone.utc) if expires_raw.tzinfo is None else expires_raw
    except (ValueError, AttributeError):
        expires_dt = datetime.now(timezone.utc) - timedelta(seconds=1)  # treat as expired

    if datetime.now(timezone.utc) > expires_dt:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invitation has expired")

    # Check team is not already full
    team = _get_team(invitation["team_id"])
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team no longer exists")

    # Check user is not already a member
    existing = _get_membership(invitation["team_id"], current_user["id"])
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a team member")

    member_count = _team_member_count(invitation["team_id"])
    if member_count >= team["max_members"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team has reached max members ({team['max_members']})",
        )

    member_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO team_members (id, team_id, user_id, role, invited_by, joined_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                member_id,
                invitation["team_id"],
                current_user["id"],
                invitation["role"],
                invitation["invited_by"],
                now,
            ),
        )
        cur.execute(
            "UPDATE team_invitations SET accepted_at = ? WHERE id = ?",
            (now, invitation["id"]),
        )
        conn.commit()

    return _get_team(invitation["team_id"])


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a member from the team. Only owner/admin can do this. Cannot remove the owner."""
    team = _get_team(team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    _require_owner_or_admin(team_id, current_user["id"])

    # Cannot remove the team owner
    if user_id == team["owner_id"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the team owner",
        )

    membership = _get_membership(team_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id),
        )
        conn.commit()
