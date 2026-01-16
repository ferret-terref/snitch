
"""Database models and schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# === ENUMS ===
class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    AWAITING_SCAN = "awaiting_scan"
    SCANNING = "scanning"
    UPDATING = "updating"
    COMPLETED = "completed"
    FAILED = "failed"
    
    
# === Request Models ===
class DownloadItem(BaseModel):
    """Individual item to download (gallery or image)."""
    url: str
    tags: Optional[list[str]] = None
    page_url: Optional[str] = None  # Source page URL for context

class DownloadRequest(BaseModel):
    """Unified request for downloading galleries or images."""
    items: list[DownloadItem]
    folder: Optional[str] = None  # Folder name or path; uses default if None

class StashUpdateRequest(BaseModel):
    """Request to update metadata in Stash without downloading."""
    url: str  # Image URL (for filename extraction)
    tags: Optional[list[str]] = None
    page_url: Optional[str] = None
    folder: Optional[str] = None  # For determining scan path


class CookieSetRequest(BaseModel):
    """Request to set a cookie for a domain."""
    domain: str
    cookie_name: str
    cookie_value: str


class StashScanRequest(BaseModel):
    """Request to trigger a Stash library scan."""
    paths: Optional[list[str]] = None  # Specific paths to scan
    scan_all: bool = False  # If True, scans all Stash paths

# ===== Response Models =====

class DownloadResponse(BaseModel):
    """Response for download submission."""
    added: int
    skipped: int
    duplicates: list[dict] = Field(default_factory=list)
    errors: Optional[list[dict]] = None

class DownloadJob(BaseModel):
    """Download job record from database."""
    id: int
    url: str
    folder_name: str
    gallery_path: str
    folder_path: str
    status: DownloadStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

class QueueResponse(BaseModel):
    """Response for queue status."""
    pending: list[DownloadJob]
    downloading: list[DownloadJob]
    total: int

class HistoryResponse(BaseModel):
    """Response for download history."""
    jobs: list[DownloadJob]
    total: int
    limit: int
    offset: int

class StashUpdateResponse(BaseModel):
    """Response for Stash metadata update."""
    success: bool
    image_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    page_url: Optional[str] = None
    error: Optional[str] = None
