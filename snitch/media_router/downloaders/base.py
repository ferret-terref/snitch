from __future__ import annotations

import abc
from typing import ClassVar

from snitch.config import FolderType

from ..models import ProbeResult


class Downloader(abc.ABC):
    name: ClassVar[str] = "base"
    priority: ClassVar[int] = 0
    timeout: ClassVar[float] = 5.0
    # Preferred folder type for downloads handled by this downloader.
    # DownloadManager / API may use this to choose destination folders.
    # This is kept private; probes should pass the value into ProbeResult.
    _preferred_folder_type: ClassVar[FolderType] = FolderType.Gallery

    @classmethod
    @abc.abstractmethod
    async def probe(cls, url: str) -> ProbeResult:
        """Return a ProbeResult describing support for the URL."""

    @classmethod
    @abc.abstractmethod
    async def download(cls, url: str, output_dir: str, scan_only: bool) -> str:
        """
        Download media from the URL into the output directory.
        
        :return: Filename or output directory
        """
