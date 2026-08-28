"""Utility helper functions for Snitch."""

import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def extract_domain(url: str) -> Optional[str]:
    """
    Extract the domain (host) from a URL.
    
    Args:
        url: Full URL
        
    Returns:
        Domain string or None if invalid
        
    Examples:
        >>> extract_domain("https://example.com/path/file.jpg")
        'example.com'
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        # Fallback to regex
        match = re.match(r"https?://([^/]+)", url)
        return match.group(1) if match else None

# ===== Path Utilities =====

def get_base_dir_for_executable() -> Path:
    """
    Get the base directory for the application.
    Works for both frozen (PyInstaller) and normal Python execution.
    
    Returns:
        Path to the base directory
    """
    import sys
    
    if getattr(sys, 'frozen', False):
        # Running as a bundled EXE
        return Path(sys.executable).parent
    else:
        # Running as normal Python script
        # Assumes this file is in snitch/ subdirectory
        return Path(__file__).parent.parent

# ===== HTTP Request Utilities =====

def build_default_headers(referer: Optional[str] = None) -> dict:
    """
    Build default HTTP headers for requests.
    
    Args:
        referer: Optional referer URL to include
        
    Returns:
        Dictionary of HTTP headers
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Accept": "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Priority": "u=0, i",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache"
    }
    
    if referer:
        headers["Referer"] = referer
    
    return headers


def format_cookies_header(cookies: dict) -> str:
    """
    Format a cookies dictionary into a Cookie header string.
    
    Args:
        cookies: Dictionary of cookie name-value pairs
        
    Returns:
        Cookie header string
        
    Examples:
        >>> format_cookies_header({"session": "abc123", "token": "xyz"})
        'session=abc123; token=xyz'
    """
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def is_cloudflare_block(status_code: int, response_text: str, headers: dict) -> bool:
    """
    Detect if a response is a Cloudflare block.
    
    Args:
        status_code: HTTP status code
        response_text: Response body text
        headers: Response headers dict
        
    Returns:
        True if Cloudflare block detected
    """
    if status_code != 403:
        return False
    
    # Check for Cloudflare indicators
    text_lower = response_text.lower()
    return (
        "cloudflare" in text_lower or
        "cf-ray" in headers or
        "cf_clearance" in text_lower
    )
    
def get_tags_from_gallery_json(identifier: str) -> list[str]:
    folder = Path(identifier)

    for filename in ("metadata.json", "info.json"):
        path = folder / filename

        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = json.load(f)

            tags = data.get("tags") or data.get("tag_string") or ""

            if isinstance(tags, list):
                return tags

            return tags.split()

    return []