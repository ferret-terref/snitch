"""Utility helper functions for Snitch."""

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ===== URL and File Type Detection =====

def is_direct_image_url(url: str) -> bool:
    """
    Check if URL points directly to an image or video file.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL ends with an image/video extension
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg', '.avif'}
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    
    valid_extensions = image_extensions.union(video_extensions)
    
    # Remove query parameters before checking extension
    path = url.split('?')[0].lower()
    return any(path.endswith(ext) for ext in valid_extensions)


def is_image_extension(filename: str) -> bool:
    """
    Check if filename has an image extension.
    
    Args:
        filename: Filename or path to check
        
    Returns:
        True if filename ends with an image extension
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg', '.avif'}
    ext = Path(filename).suffix.lower()
    return ext in image_extensions


def is_video_extension(filename: str) -> bool:
    """
    Check if filename has a video extension.
    
    Args:
        filename: Filename or path to check
        
    Returns:
        True if filename ends with a video extension
    """
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    ext = Path(filename).suffix.lower()
    return ext in video_extensions


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


def extract_filename_from_url(url: str, default: Optional[str] = None) -> str:
    """
    Extract filename from URL, removing query parameters.
    
    Args:
        url: URL to extract filename from
        default: Default filename if extraction fails
        
    Returns:
        Extracted filename or default value
        
    Examples:
        >>> extract_filename_from_url("https://example.com/path/image.jpg?param=value")
        'image.jpg'
    """
    try:
        # Parse URL and get the path component
        parsed = urlparse(url)
        path = parsed.path
        
        # Get the last component (filename)
        filename = path.split("/")[-1]
        
        # Remove any remaining query parameters (just in case)
        filename = filename.split("?")[0]
        
        if filename:
            return filename
    except Exception as e:
        logger.debug(f"Failed to extract filename from URL: {e}")
    
    # Return default or generate one
    return default or "downloaded_file"


# ===== Path Utilities =====

def clean_path(path: str) -> str:
    """
    Clean a path string by removing quotes and Windows extended-length prefix.
    
    Args:
        path: Path string to clean
        
    Returns:
        Cleaned path string
        
    Examples:
        >>> clean_path('"\\\\?\\C:\\Users\\file.txt"')
        'C:\\Users\\file.txt'
    """
    # Remove quotes
    cleaned = path.strip('"').strip("'")
    
    # Remove Windows extended-length prefix
    if cleaned.startswith('\\\\?\\'):
        cleaned = cleaned[4:]
    
    # Remove trailing slashes/backslashes
    cleaned = cleaned.rstrip('\\/')
    
    return cleaned


def ensure_directory(path: str | Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path as string or Path object
        
    Returns:
        Path object of the created/existing directory
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


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


# ===== String Utilities =====

def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    Sanitize a filename by removing/replacing invalid characters.
    
    Args:
        filename: Original filename
        replacement: Character to use for replacements
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, replacement)
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Trim spaces and dots from ends
    filename = filename.strip(' .')
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"
    
    return filename


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length, adding a suffix if truncated.
    
    Args:
        text: String to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


# ===== Format Conversion =====

def bytes_to_human_readable(size_bytes: int) -> str:
    """
    Convert bytes to human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def human_readable_to_bytes(size_str: str) -> Optional[int]:
    """
    Convert human-readable size to bytes.
    
    Args:
        size_str: Size string (e.g., "1.5 MB", "500KB")
        
    Returns:
        Size in bytes or None if parsing fails
    """
    units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
        'PB': 1024 ** 5
    }
    
    # Match number and unit
    match = re.match(r'^([\d.]+)\s*([A-Z]+)$', size_str.strip().upper())
    if not match:
        return None
    
    try:
        number = float(match.group(1))
        unit = match.group(2)
        
        if unit not in units:
            return None
        
        return int(number * units[unit])
    except (ValueError, OverflowError):
        return None


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


# ===== Content Type Detection =====

def is_image_content_type(content_type: str) -> bool:
    """
    Check if a Content-Type header indicates an image.
    
    Args:
        content_type: Content-Type header value
        
    Returns:
        True if content type is an image
    """
    return content_type.lower().startswith("image/")


def is_video_content_type(content_type: str) -> bool:
    """
    Check if a Content-Type header indicates a video.
    
    Args:
        content_type: Content-Type header value
        
    Returns:
        True if content type is a video
    """
    return content_type.lower().startswith("video/")


def is_media_content_type(content_type: str) -> bool:
    """
    Check if a Content-Type header indicates image or video media.
    
    Args:
        content_type: Content-Type header value
        
    Returns:
        True if content type is image or video
    """
    return is_image_content_type(content_type) or is_video_content_type(content_type)


# ===== Retry and Error Handling =====

def should_retry_download(attempt: int, max_retries: int, bytes_downloaded: int) -> bool:
    """
    Determine if a download should be retried.
    
    Args:
        attempt: Current attempt number (1-indexed)
        max_retries: Maximum number of retry attempts
        bytes_downloaded: Number of bytes successfully downloaded
        
    Returns:
        True if should retry, False otherwise
    """
    return attempt < max_retries


def calculate_retry_delay(attempt: int, base_delay: float = 2.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff retry delay.
    
    Args:
        attempt: Current attempt number (1-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Delay in seconds
    """
    delay = base_delay * (2 ** (attempt - 1))
    return min(delay, max_delay)


# ===== List/Collection Utilities =====

def chunk_list(items: list, chunk_size: int) -> list[list]:
    """
    Split a list into chunks of specified size.
    
    Args:
        items: List to chunk
        chunk_size: Maximum size of each chunk
        
    Returns:
        List of chunks (sublists)
        
    Examples:
        >>> chunk_list([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def deduplicate_preserve_order(items: list) -> list:
    """
    Remove duplicates from a list while preserving order.
    
    Args:
        items: List with potential duplicates
        
    Returns:
        List with duplicates removed, order preserved
    """
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
