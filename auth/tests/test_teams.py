"""Tests for team management endpoints."""
import os
import uuid

os.environ["DATABASE_URL"] = "sqlite:///test_teams.db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["ENABLE_METRICS"] = "false"

import pytest
from fastapi.testclient import TestClient

from auth.api.main import app

TEST_DB = "test_teams.db"


@pytest.fixture(scope="module")
def client():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with TestClient(app) as c:
        yield c
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def _register(client, suffix: str) -> tuple[str, str]:
    """Register a user and return (user_id, access_token)."""
    email = f"teams_{suffix}_{uuid.uuid4().hex[:6]}@test.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me.json()["id"], token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------

def test_create_team(client):
    _, token = _register(client, "creator")
    r = client.post(
        "/teams",
        json={"name": "Dream Team", "slug": "dream-team"},
        headers=_headers(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Dream Team"
    assert data["slug"] == "dream-team"
    assert "id" in data


def test_owner_is_member_with_owner_role(client):
    owner_id, token = _register(client, "owner_check")
    r = client.post(
        "/teams",
        json={"name": "Owner Check", "slug": f"owner-check-{uuid.uuid4().hex[:6]}"},
        headers=_headers(token),
    )
    team_id = r.json()["id"]
    detail = client.get(f"/teams/{team_id}", headers=_headers(token))
    assert detail.status_code == 200
    members = detail.json()["members"]
    owner_entry = next((m for m in members if m["id"] == owner_id), None)
    assert owner_entry is not None
    assert owner_entry is not None and owner_entry["role"] == "owner"


def test_list_teams_returns_user_teams(client):
    _, token = _register(client, "lister")
    slug = f"list-team-{uuid.uuid4().hex[:6]}"
    client.post("/teams", json={"name": "List Team", "slug": slug}, headers=_headers(token))
    r = client.get("/teams", headers=_headers(token))
    assert r.status_code == 200
    slugs = [t["slug"] for t in r.json()]
    assert slug in slugs


def test_get_team_includes_members(client):
    _, token = _register(client, "detail")
    slug = f"detail-{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/teams", json={"name": "Detail Team", "slug": slug}, headers=_headers(token)
    ).json()
    r = client.get(f"/teams/{created['id']}", headers=_headers(token))
    assert r.status_code == 200
    assert "members" in r.json()
    assert len(r.json()["members"]) >= 1


def test_duplicate_slug_rejected(client):
    _, token = _register(client, "dup")
    slug = f"dup-slug-{uuid.uuid4().hex[:6]}"
    client.post("/teams", json={"name": "First", "slug": slug}, headers=_headers(token))
    r = client.post("/teams", json={"name": "Second", "slug": slug}, headers=_headers(token))
    assert r.status_code == 409


def test_non_member_cannot_view_team(client):
    _, owner_token = _register(client, "priv_owner")
    _, stranger_token = _register(client, "priv_stranger")
    slug = f"private-{uuid.uuid4().hex[:6]}"
    team = client.post(
        "/teams", json={"name": "Private", "slug": slug}, headers=_headers(owner_token)
    ).json()
    r = client.get(f"/teams/{team['id']}", headers=_headers(stranger_token))
    assert r.status_code == 403


def test_invite_and_accept(client):
    owner_id, owner_token = _register(client, "inv_owner")
    invitee_id, invitee_token = _register(client, "inv_invitee")

    # Get invitee email
    invitee_email = client.get("/auth/me", headers=_headers(invitee_token)).json()["email"]

    slug = f"invite-team-{uuid.uuid4().hex[:6]}"
    team = client.post(
        "/teams", json={"name": "Invite Team", "slug": slug}, headers=_headers(owner_token)
    ).json()
    team_id = team["id"]

    invite_r = client.post(
        f"/teams/{team_id}/invite",
        json={"email": invitee_email, "role": "member"},
        headers=_headers(owner_token),
    )
    assert invite_r.status_code == 201
    token = invite_r.json()["token"]

    accept_r = client.post(
        "/teams/invitations/accept",
        json={"token": token},
        headers=_headers(invitee_token),
    )
    assert accept_r.status_code == 200

    detail = client.get(f"/teams/{team_id}", headers=_headers(invitee_token)).json()
    member_ids = [m["id"] for m in detail["members"]]
    assert invitee_id in member_ids


def test_remove_member(client):
    _, owner_token = _register(client, "rem_owner")
    member_id, member_token = _register(client, "rem_member")
    member_email = client.get("/auth/me", headers=_headers(member_token)).json()["email"]

    slug = f"remove-{uuid.uuid4().hex[:6]}"
    team = client.post(
        "/teams", json={"name": "Remove Test", "slug": slug}, headers=_headers(owner_token)
    ).json()
    team_id = team["id"]

    inv = client.post(
        f"/teams/{team_id}/invite",
        json={"email": member_email, "role": "member"},
        headers=_headers(owner_token),
    ).json()
    client.post(
        "/teams/invitations/accept",
        json={"token": inv["token"]},
        headers=_headers(member_token),
    )

    r = client.delete(f"/teams/{team_id}/members/{member_id}", headers=_headers(owner_token))
    assert r.status_code == 204

    detail = client.get(f"/teams/{team_id}", headers=_headers(owner_token)).json()
    member_ids = [m["id"] for m in detail["members"]]
    assert member_id not in member_ids


def test_non_owner_cannot_delete_team(client):
    _, owner_token = _register(client, "del_owner")
    _, member_token = _register(client, "del_member")
    member_email = client.get("/auth/me", headers=_headers(member_token)).json()["email"]

    slug = f"del-team-{uuid.uuid4().hex[:6]}"
    team = client.post(
        "/teams", json={"name": "Del Team", "slug": slug}, headers=_headers(owner_token)
    ).json()
    team_id = team["id"]

    inv = client.post(
        f"/teams/{team_id}/invite",
        json={"email": member_email, "role": "member"},
        headers=_headers(owner_token),
    ).json()
    client.post(
        "/teams/invitations/accept",
        json={"token": inv["token"]},
        headers=_headers(member_token),
    )

    r = client.delete(f"/teams/{team_id}", headers=_headers(member_token))
    assert r.status_code == 403


def test_delete_team_owner_succeeds(client):
    _, owner_token = _register(client, "del_ok")
    slug = f"del-ok-{uuid.uuid4().hex[:6]}"
    team = client.post(
        "/teams", json={"name": "Delete OK", "slug": slug}, headers=_headers(owner_token)
    ).json()
    r = client.delete(f"/teams/{team['id']}", headers=_headers(owner_token))
    assert r.status_code == 204
