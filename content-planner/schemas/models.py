from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Pillar ────────────────────────────────────────────────────────────────────

class PillarCreate(BaseModel):
    name: str
    color: int = 4280391411
    priority_weight: float = 1.0
    is_quarterly_focus: bool = False


class PillarUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[int] = None
    priority_weight: Optional[float] = None
    is_quarterly_focus: Optional[bool] = None


class PillarResponse(BaseModel):
    id: str
    user_id: str
    name: str
    color: int
    priority_weight: float
    is_quarterly_focus: bool
    created_at: str


# ── Source ────────────────────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    title: str
    url: Optional[str] = None
    type: str = "podcast"  # podcast | youtube | book | custom
    trust_level: str = "neutral"  # trusted | neutral | low
    blocked: bool = False


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    trust_level: Optional[str] = None
    blocked: Optional[bool] = None


class SourceResponse(BaseModel):
    id: str
    user_id: str
    title: str
    url: Optional[str]
    type: str
    trust_level: str
    blocked: bool
    created_at: str


# ── Content Item ──────────────────────────────────────────────────────────────

class PlayStateResponse(BaseModel):
    position_ms: int
    completed_at: Optional[str]


class FeedbackResponse(BaseModel):
    skip_count: int
    redundant_flag: bool
    last_skipped_at: Optional[str]


class ContentItemCreate(BaseModel):
    source_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    type: str = "episode"  # episode | clip | bookLink
    duration_ms: int = 0
    published_at: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    pillar_id: Optional[str] = None
    mode: str = "tactical"  # deep | tactical | recovery
    status: str = "inbox"  # inbox | queued | archived | completed
    similarity_key: Optional[str] = None


class ContentItemUpdate(BaseModel):
    source_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    duration_ms: Optional[int] = None
    published_at: Optional[str] = None
    topics: Optional[List[str]] = None
    pillar_id: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    queue_position: Optional[int] = None
    similarity_key: Optional[str] = None


class ContentItemResponse(BaseModel):
    id: str
    user_id: str
    source_id: Optional[str]
    title: str
    url: Optional[str]
    type: str
    duration_ms: int
    published_at: Optional[str]
    topics: List[str]
    pillar_id: Optional[str]
    mode: str
    status: str
    play_state: PlayStateResponse
    feedback: FeedbackResponse
    similarity_key: Optional[str]
    queue_position: int
    created_at: str


# ── Session ───────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    context: str = "idle"  # commute | workout | idle | evening
    mode: str = "tactical"
    content_item_id: Optional[str] = None


class SessionEnd(BaseModel):
    outcome: str  # completed | skipped | paused | abandoned
    listened_duration_ms: int = 0


class SessionResponse(BaseModel):
    id: str
    user_id: str
    started_at: str
    ended_at: Optional[str]
    context: str
    mode: str
    content_item_id: Optional[str]
    outcome: Optional[str]
    listened_duration_ms: int


# ── Summary ───────────────────────────────────────────────────────────────────

class SummaryCreate(BaseModel):
    content_item_id: str
    pillar_id: Optional[str] = None
    title: str
    insights: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    behavior_change: Optional[str] = None


class SummaryUpdate(BaseModel):
    pillar_id: Optional[str] = None
    title: Optional[str] = None
    insights: Optional[List[str]] = None
    applications: Optional[List[str]] = None
    behavior_change: Optional[str] = None


class SummaryResponse(BaseModel):
    id: str
    user_id: str
    content_item_id: str
    pillar_id: Optional[str]
    title: str
    insights: List[str]
    applications: List[str]
    behavior_change: Optional[str]
    created_at: str
    updated_at: Optional[str]


# ── Queue ─────────────────────────────────────────────────────────────────────

class QueueReorder(BaseModel):
    item_ids: List[str]  # ordered list of content item IDs


class QueueStats(BaseModel):
    total: int
    total_cap: int
    total_fill_pct: float
    by_pillar: dict
    by_mode: dict
    total_duration_ms: int


# ── User Settings ─────────────────────────────────────────────────────────────

class QueueCapsUpdate(BaseModel):
    total_cap: int = 10
    per_pillar_cap: int = 5
    per_mode_cap: int = 5


class NotificationSettingsUpdate(BaseModel):
    weekly_review_reminder: bool = True
    queue_empty_alert: bool = True
    inbox_overflow_alert: bool = False
    inbox_overflow_threshold: int = 20


class UserSettingsUpdate(BaseModel):
    pillar_ids: Optional[List[str]] = None
    trusted_source_ids: Optional[List[str]] = None
    blocked_source_ids: Optional[List[str]] = None
    context_mode_map: Optional[dict] = None
    queue_caps: Optional[QueueCapsUpdate] = None
    start_behavior: Optional[str] = None
    notifications: Optional[NotificationSettingsUpdate] = None
    quarterly_focus_pillar_id: Optional[str] = None


class UserSettingsResponse(BaseModel):
    user_id: str
    pillar_ids: List[str]
    trusted_source_ids: List[str]
    blocked_source_ids: List[str]
    context_mode_map: dict
    queue_caps: QueueCapsUpdate
    start_behavior: str
    notifications: NotificationSettingsUpdate
    quarterly_focus_pillar_id: Optional[str]
    updated_at: str


# ── Playlist ──────────────────────────────────────────────────────────────────

class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    # context presets: commute | quick_trip | workout | evening | custom
    context: str = "custom"
    # target duration in milliseconds (e.g. 2700000 = 45 min)
    target_duration_ms: int = 0
    # provider: youtube | podcast | mixed
    provider: str = "mixed"


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    context: Optional[str] = None
    target_duration_ms: Optional[int] = None
    provider: Optional[str] = None
    youtube_playlist_id: Optional[str] = None


class PlaylistItemAdd(BaseModel):
    # Supply either a content_item_id (already in the library) or raw YouTube fields
    content_item_id: Optional[str] = None
    youtube_video_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    duration_ms: int = 0
    thumbnail_url: Optional[str] = None
    channel_name: Optional[str] = None


class PlaylistItemReorder(BaseModel):
    item_ids: List[str]  # playlist_items.id in desired order


class PlaylistItemResponse(BaseModel):
    id: str
    playlist_id: str
    content_item_id: Optional[str]
    youtube_video_id: Optional[str]
    title: str
    url: Optional[str]
    duration_ms: int
    thumbnail_url: Optional[str]
    channel_name: Optional[str]
    position: int
    added_at: str


class PlaylistResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    context: str
    target_duration_ms: int
    provider: str
    youtube_playlist_id: Optional[str]
    total_duration_ms: int
    item_count: int
    items: List[PlaylistItemResponse]
    created_at: str
    updated_at: str


# ── YouTube suggestion returned by the suggestions endpoint ───────────────────

class YouTubeSuggestion(BaseModel):
    youtube_video_id: str
    title: str
    channel_name: str
    duration_ms: int
    thumbnail_url: str
    url: str
    fits_remaining_ms: bool  # True if adding this fills ≤ remaining time


# ── YouTube export result ─────────────────────────────────────────────────────

class YouTubeExportResult(BaseModel):
    youtube_playlist_id: str
    youtube_playlist_url: str
    videos_added: int
    skipped: int  # items without youtube_video_id
