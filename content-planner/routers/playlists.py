"""
Playlist management router.

Supports:
- CRUD for named playlists with a target duration and context preset
  (commute / quick_trip / workout / evening / custom)
- Items drawn from the user's content library OR added directly as YouTube videos
- YouTube Data API v3 for video search and duration lookup
- Suggestions: find YouTube videos that fill the remaining playlist time
- YouTube playlist export via OAuth access token
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from core.settings import get_settings
from routers.auth import require_token
from schemas.models import (
    PlaylistCreate,
    PlaylistUpdate,
    PlaylistItemAdd,
    PlaylistItemReorder,
    PlaylistItemResponse,
    PlaylistResponse,
    YouTubeSuggestion,
    YouTubeExportResult,
)

router = APIRouter(prefix="/playlists", tags=["playlists"])
logger = logging.getLogger(__name__)

# ── Context duration presets (ms) ─────────────────────────────────────────────
CONTEXT_PRESETS: dict[str, int] = {
    "commute":     45 * 60 * 1000,   # 45 min
    "quick_trip":  15 * 60 * 1000,   # 15 min
    "workout":     60 * 60 * 1000,   # 60 min
    "evening":     90 * 60 * 1000,   # 90 min
    "custom":       0,
}

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso8601_duration_to_ms(iso: str) -> int:
    """Convert ISO 8601 duration (e.g. PT1H4M33S) to milliseconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match:
        return 0
    h, m, s = (int(x) if x else 0 for x in match.groups())
    return (h * 3600 + m * 60 + s) * 1000


def _row_to_item(row: dict) -> dict:
    return {
        "id": row["id"],
        "playlist_id": row["playlist_id"],
        "content_item_id": row.get("content_item_id"),
        "youtube_video_id": row.get("youtube_video_id"),
        "title": row["title"],
        "url": row.get("url"),
        "duration_ms": row.get("duration_ms", 0),
        "thumbnail_url": row.get("thumbnail_url"),
        "channel_name": row.get("channel_name"),
        "position": row.get("position", 0),
        "added_at": row["added_at"],
    }


def _build_playlist_response(pl: dict, items: list[dict]) -> dict:
    total_ms = sum(i.get("duration_ms", 0) for i in items)
    return {
        **pl,
        "total_duration_ms": total_ms,
        "item_count": len(items),
        "items": sorted(items, key=lambda x: x.get("position", 0)),
    }


def _fetch_playlist_with_items(playlist_id: str, user_id: str) -> dict:
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM playlists WHERE id = %s AND user_id = %s", USE_SQLITE
            ),
            (playlist_id, user_id),
        )
        pl_row = cur.fetchone()
        if not pl_row:
            raise HTTPException(status_code=404, detail="Playlist not found")
        pl = dict_from_row(pl_row, USE_SQLITE)

        cur.execute(
            adapt_query(
                "SELECT * FROM playlist_items WHERE playlist_id = %s ORDER BY position",
                USE_SQLITE,
            ),
            (playlist_id,),
        )
        item_rows = cur.fetchall()
    items = [_row_to_item(dict_from_row(r, USE_SQLITE)) for r in item_rows]
    return _build_playlist_response(pl, items)


async def _youtube_search(api_key: str, query: str, max_results: int = 10) -> list[dict]:
    """Search YouTube and return video metadata including duration."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        search_resp = await client.get(
            f"{YOUTUBE_API_BASE}/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": max_results,
                "key": api_key,
            },
        )
        if search_resp.status_code != 200:
            logger.error("YouTube search error: %s", search_resp.text)
            return []

        video_ids = [
            item["id"]["videoId"]
            for item in search_resp.json().get("items", [])
        ]
        if not video_ids:
            return []

        details_resp = await client.get(
            f"{YOUTUBE_API_BASE}/videos",
            params={
                "part": "contentDetails,snippet",
                "id": ",".join(video_ids),
                "key": api_key,
            },
        )
        if details_resp.status_code != 200:
            return []

        results = []
        for item in details_resp.json().get("items", []):
            vid_id = item["id"]
            snippet = item.get("snippet", {})
            duration_iso = item.get("contentDetails", {}).get("duration", "")
            duration_ms = _iso8601_duration_to_ms(duration_iso)
            thumbnails = snippet.get("thumbnails", {})
            thumb = (
                thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
                or ""
            )
            results.append({
                "youtube_video_id": vid_id,
                "title": snippet.get("title", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "duration_ms": duration_ms,
                "thumbnail_url": thumb,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
            })
        return results


# ── List playlists ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[PlaylistResponse])
async def list_playlists(
    context: Optional[str] = None,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if context:
        conditions.append("context = %s")
        params.append(context)
    where = " AND ".join(conditions)

    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"SELECT * FROM playlists WHERE {where} ORDER BY created_at DESC",
                USE_SQLITE,
            ),
            params,
        )
        pl_rows = cur.fetchall()
        playlists_raw = [dict_from_row(r, USE_SQLITE) for r in pl_rows]

        results = []
        for pl in playlists_raw:
            cur.execute(
                adapt_query(
                    "SELECT * FROM playlist_items WHERE playlist_id = %s ORDER BY position",
                    USE_SQLITE,
                ),
                (pl["id"],),
            )
            item_rows = cur.fetchall()
            items = [_row_to_item(dict_from_row(r, USE_SQLITE)) for r in item_rows]
            results.append(_build_playlist_response(pl, items))
    return results


# ── Create playlist ────────────────────────────────────────────────────────────

@router.post("", response_model=PlaylistResponse, status_code=201)
async def create_playlist(body: PlaylistCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    pl_id = str(uuid.uuid4())
    now = _now()

    # If target_duration_ms is 0 and context has a preset, apply it
    target_ms = body.target_duration_ms
    if target_ms == 0 and body.context in CONTEXT_PRESETS:
        target_ms = CONTEXT_PRESETS[body.context]

    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO playlists (id, user_id, name, description, context, "
                "target_duration_ms, provider, youtube_playlist_id, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)",
                USE_SQLITE,
            ),
            (pl_id, user_id, body.name, body.description, body.context,
             target_ms, body.provider, now, now),
        )
        conn.commit()

    return _fetch_playlist_with_items(pl_id, user_id)


# ── Get playlist ───────────────────────────────────────────────────────────────

@router.get("/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(playlist_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    return _fetch_playlist_with_items(playlist_id, user_id)


# ── Update playlist ────────────────────────────────────────────────────────────

@router.patch("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: str,
    body: PlaylistUpdate,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [playlist_id, user_id]
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"UPDATE playlists SET {set_clause} WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Playlist not found")
        conn.commit()
    return _fetch_playlist_with_items(playlist_id, user_id)


# ── Delete playlist ────────────────────────────────────────────────────────────

@router.delete("/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT id FROM playlists WHERE id = %s AND user_id = %s", USE_SQLITE),
            (playlist_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Playlist not found")
        # ON DELETE CASCADE handles playlist_items
        cur.execute(
            adapt_query("DELETE FROM playlists WHERE id = %s", USE_SQLITE),
            (playlist_id,),
        )
        conn.commit()


# ── Add item to playlist ───────────────────────────────────────────────────────

@router.post("/{playlist_id}/items", response_model=PlaylistResponse, status_code=201)
async def add_playlist_item(
    playlist_id: str,
    body: PlaylistItemAdd,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT id FROM playlists WHERE id = %s AND user_id = %s", USE_SQLITE),
            (playlist_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Resolve content_item duration if not provided
        duration_ms = body.duration_ms
        if body.content_item_id and duration_ms == 0:
            cur.execute(
                adapt_query("SELECT duration_ms FROM content_items WHERE id = %s", USE_SQLITE),
                (body.content_item_id,),
            )
            ci_row = cur.fetchone()
            if ci_row:
                duration_ms = dict_from_row(ci_row, USE_SQLITE).get("duration_ms", 0)

        # Append at end
        cur.execute(
            adapt_query(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM playlist_items WHERE playlist_id = %s",
                USE_SQLITE,
            ),
            (playlist_id,),
        )
        next_pos = dict_from_row(cur.fetchone(), USE_SQLITE)["next_pos"]

        item_id = str(uuid.uuid4())
        now = _now()
        cur.execute(
            adapt_query(
                "INSERT INTO playlist_items (id, playlist_id, content_item_id, youtube_video_id, "
                "title, url, duration_ms, thumbnail_url, channel_name, position, added_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                USE_SQLITE,
            ),
            (item_id, playlist_id, body.content_item_id, body.youtube_video_id,
             body.title, body.url, duration_ms, body.thumbnail_url,
             body.channel_name, next_pos, now),
        )
        cur.execute(
            adapt_query("UPDATE playlists SET updated_at = %s WHERE id = %s", USE_SQLITE),
            (now, playlist_id),
        )
        conn.commit()

    return _fetch_playlist_with_items(playlist_id, user_id)


# ── Remove item from playlist ──────────────────────────────────────────────────

@router.delete("/{playlist_id}/items/{item_id}", response_model=PlaylistResponse)
async def remove_playlist_item(
    playlist_id: str,
    item_id: str,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT id FROM playlists WHERE id = %s AND user_id = %s", USE_SQLITE),
            (playlist_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Playlist not found")
        cur.execute(
            adapt_query(
                "DELETE FROM playlist_items WHERE id = %s AND playlist_id = %s",
                USE_SQLITE,
            ),
            (item_id, playlist_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        # Re-number positions sequentially
        cur.execute(
            adapt_query(
                "SELECT id FROM playlist_items WHERE playlist_id = %s ORDER BY position",
                USE_SQLITE,
            ),
            (playlist_id,),
        )
        remaining = [dict_from_row(r, USE_SQLITE)["id"] for r in cur.fetchall()]
        for pos, rid in enumerate(remaining):
            cur.execute(
                adapt_query("UPDATE playlist_items SET position = %s WHERE id = %s", USE_SQLITE),
                (pos, rid),
            )
        now = _now()
        cur.execute(
            adapt_query("UPDATE playlists SET updated_at = %s WHERE id = %s", USE_SQLITE),
            (now, playlist_id),
        )
        conn.commit()

    return _fetch_playlist_with_items(playlist_id, user_id)


# ── Reorder items ──────────────────────────────────────────────────────────────

@router.put("/{playlist_id}/items/reorder", response_model=PlaylistResponse)
async def reorder_playlist_items(
    playlist_id: str,
    body: PlaylistItemReorder,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT id FROM playlists WHERE id = %s AND user_id = %s", USE_SQLITE),
            (playlist_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Playlist not found")
        for pos, item_id in enumerate(body.item_ids):
            cur.execute(
                adapt_query(
                    "UPDATE playlist_items SET position = %s WHERE id = %s AND playlist_id = %s",
                    USE_SQLITE,
                ),
                (pos, item_id, playlist_id),
            )
        now = _now()
        cur.execute(
            adapt_query("UPDATE playlists SET updated_at = %s WHERE id = %s", USE_SQLITE),
            (now, playlist_id),
        )
        conn.commit()

    return _fetch_playlist_with_items(playlist_id, user_id)


# ── YouTube video search ───────────────────────────────────────────────────────

@router.get("/youtube/search", response_model=List[YouTubeSuggestion])
async def youtube_search(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(10, ge=1, le=25),
    max_duration_ms: Optional[int] = Query(None, description="Filter videos shorter than this"),
    token: dict = Depends(require_token),
):
    """Search YouTube for videos. Optionally filter to videos shorter than max_duration_ms."""
    settings = get_settings()
    api_key = getattr(settings, "youtube_api_key", None) or os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="YouTube API key not configured")

    videos = await _youtube_search(api_key, q, max_results)
    results = []
    for v in videos:
        if max_duration_ms is not None and v["duration_ms"] > max_duration_ms:
            continue
        results.append(YouTubeSuggestion(
            fits_remaining_ms=True,
            **v,
        ))
    return results


# ── Suggestions: fill remaining playlist time ──────────────────────────────────

@router.get("/{playlist_id}/suggestions", response_model=List[YouTubeSuggestion])
async def get_suggestions(
    playlist_id: str,
    q: Optional[str] = Query(None, description="Topic hint for search"),
    max_results: int = Query(10, ge=1, le=25),
    token: dict = Depends(require_token),
):
    """
    Suggest YouTube videos to fill the remaining time in a playlist.

    Remaining = target_duration_ms - total_duration_ms.
    Falls back to the playlist name as query if q is not provided.
    """
    user_id = token.get("user_id") or token.get("sub")
    settings = get_settings()
    api_key = getattr(settings, "youtube_api_key", None) or os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="YouTube API key not configured")

    playlist_data = _fetch_playlist_with_items(playlist_id, user_id)
    remaining_ms = max(
        0, playlist_data["target_duration_ms"] - playlist_data["total_duration_ms"]
    )

    query = q or playlist_data["name"]
    videos = await _youtube_search(api_key, query, max_results)

    results = []
    for v in videos:
        fits = v["duration_ms"] <= remaining_ms if remaining_ms > 0 else True
        results.append(YouTubeSuggestion(fits_remaining_ms=fits, **v))

    # Sort: videos that fit remaining time first
    results.sort(key=lambda x: (not x.fits_remaining_ms, x.duration_ms))
    return results


# ── Export to YouTube playlist ─────────────────────────────────────────────────

@router.post("/{playlist_id}/export/youtube", response_model=YouTubeExportResult)
async def export_to_youtube(
    playlist_id: str,
    youtube_access_token: str = Query(..., description="OAuth 2.0 access token with youtube.force-ssl scope"),
    token: dict = Depends(require_token),
):
    """
    Create a YouTube playlist from this playlist's items using the user's OAuth token.

    Requires the user to have authorised the app with the
    https://www.googleapis.com/auth/youtube.force-ssl scope.
    Items without a youtube_video_id are skipped.
    """
    user_id = token.get("user_id") or token.get("sub")
    playlist_data = _fetch_playlist_with_items(playlist_id, user_id)

    headers = {
        "Authorization": f"Bearer {youtube_access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Create the YouTube playlist
        create_resp = await client.post(
            f"{YOUTUBE_API_BASE}/playlists",
            headers=headers,
            params={"part": "snippet,status"},
            json={
                "snippet": {
                    "title": playlist_data["name"],
                    "description": playlist_data.get("description") or "",
                },
                "status": {"privacyStatus": "private"},
            },
        )
        if create_resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"YouTube playlist creation failed: {create_resp.text}",
            )
        yt_playlist_id = create_resp.json()["id"]

        # 2. Insert each item that has a YouTube video ID
        added = 0
        skipped = 0
        for item in playlist_data["items"]:
            vid_id = item.get("youtube_video_id")
            if not vid_id:
                skipped += 1
                continue
            insert_resp = await client.post(
                f"{YOUTUBE_API_BASE}/playlistItems",
                headers=headers,
                params={"part": "snippet"},
                json={
                    "snippet": {
                        "playlistId": yt_playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": vid_id},
                    }
                },
            )
            if insert_resp.status_code in (200, 201):
                added += 1
            else:
                logger.warning("Failed to insert video %s: %s", vid_id, insert_resp.text)
                skipped += 1

    # 3. Store the YouTube playlist ID back on our record
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE playlists SET youtube_playlist_id = %s, updated_at = %s WHERE id = %s",
                USE_SQLITE,
            ),
            (yt_playlist_id, _now(), playlist_id),
        )
        conn.commit()

    return YouTubeExportResult(
        youtube_playlist_id=yt_playlist_id,
        youtube_playlist_url=f"https://www.youtube.com/playlist?list={yt_playlist_id}",
        videos_added=added,
        skipped=skipped,
    )
