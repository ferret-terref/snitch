"""Built-in downloader implementations for the media router."""

from .base import Downloader
from .gallerydl import GalleryDlDownloader
from .manual import ManualDownloader
from .ytdlp import YtDlpDownloader

__all__ = ["Downloader", "GalleryDlDownloader", "ManualDownloader", "YtDlpDownloader"]
