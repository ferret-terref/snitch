from __future__ import annotations

import re
from urllib.parse import urlparse

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".avif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def extract_filename_from_url(url: str, default: str = "downloaded_file") -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    filename = path.rstrip("/").split("/")[-1]
    if filename:
        return filename
    return default


def parse_domain(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower() if parsed.netloc else None
    except Exception:
        match = re.match(r"https?://([^/]+)", url)
        return match.group(1).lower() if match else None


def is_direct_media_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    is_supported = any(path.endswith(ext) for ext in MEDIA_EXTENSIONS)
    return is_supported


def is_image_url(url: str) -> bool:
    """Return True if the URL path looks like an image file by extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def is_video_url(url: str) -> bool:
    """Return True if the URL path looks like a video file by extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in VIDEO_EXTENSIONS)
