"""Media router framework for selecting and downloading media from URLs."""

# Import built-in downloaders so they register automatically.
from . import downloaders  # noqa: F401
from .manager import DownloadManager
from .registry import DownloaderRegistry

__all__ = ["DownloadManager", "DownloaderRegistry"]
