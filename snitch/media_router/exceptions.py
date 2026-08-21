class MediaRouterError(Exception):
    """Base exception for media router errors."""


class NoSupportedDownloaderError(MediaRouterError):
    """Raised when no downloader can handle a URL."""


class DownloadError(MediaRouterError):
    """Raised when a download fails."""


class ProbeTimeoutError(MediaRouterError):
    """Raised when a downloader probe times out."""
