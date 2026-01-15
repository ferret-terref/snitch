
"""Database models and schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class DownloadRequestItem(BaseModel):
    url: str
    tags: Optional[list[str]] = None
    
class DownloadRequest(BaseModel):
    """Request model for submitting downloads."""
    items: list[DownloadRequestItem]
    folder: Optional[str] = None  # If None, uses default folder


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    AWAITING_SCAN = "awaiting_scan"
    SCANNING = "scanning"
    UPDATING = "updating"
    COMPLETED = "completed"
    FAILED = "failed"

class SingleImageDownloadRequest(BaseModel):
    """Request model for single image download."""
    url: str
    tags: Optional[list[str]] = None
    folder: Optional[str] = None
    page_url: Optional[str] = None

class BulkImageDownloadRequest(BaseModel):
    """Request model for bulk image download."""
    urls: list[str]
    tags: Optional[list[str]] = None
    folder: Optional[str] = None
    subfolder: Optional[str] = None
    rename: Optional[bool] = False


class DownloadResponse(BaseModel):
    """Response model for download submission."""
    added: int
    skipped: int
    duplicates: list[dict]


class DownloadJob(BaseModel):
    """Download job record."""
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

class CookieSetRequest(BaseModel):
    domain: str
    cookie_name: str
    cookie_value: str