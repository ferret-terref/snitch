from __future__ import annotations

import asyncio
import io
import re
import sys
from pathlib import Path
from typing import ClassVar

from snitch.config import FolderType
from snitch.media_router.probes.gallerydl import (is_booru_collection,
                                                  is_gallerydl_url)

from ..exceptions import MediaRouterError
from ..models import (ModuleNotInstalled, ProbeResult, SupportedDomain,
                      UnsupportedDomain)
from ..registry import DownloaderRegistry
from ..utils.urls import parse_domain
from .base import Downloader

try:
    import gallery_dl  # type: ignore
    from gallery_dl import config as gallery_config  # type: ignore
    from gallery_dl import job as gallery_job  # type: ignore
except ImportError:  # pragma: no cover
    gallery_dl = None
    gallery_config = None
    gallery_job = None

import logging

logger = logging.getLogger(__name__)

FILE_RE = re.compile(r"#\s(.+\.(jpg|png|mp4|gif|webm))")


@DownloaderRegistry.register
class GalleryDlDownloader(Downloader):
    name: ClassVar[str] = "gallery-dl"
    priority: ClassVar[int] = 80
    timeout: ClassVar[float] = 10.0
    _preferred_folder_type: ClassVar[FolderType] = FolderType.Gallery

    @classmethod
    async def probe(cls, url: str) -> ProbeResult:
        if gallery_dl is None:
            return ModuleNotInstalled(cls.name, url)

        if not parse_domain(url):
            return UnsupportedDomain(cls.name, url)

        if is_gallerydl_url(url):
            return SupportedDomain(cls.name, url, preferred_folder=getattr(cls, "_preferred_folder_type", None))

        if is_booru_collection(url):
            return SupportedDomain(cls.name, url, preferred_folder=getattr(cls, "_preferred_folder_type", None))
        
        if cls.simulateDownload(url, "./temp"):
            return SupportedDomain(cls.name, url, preferred_folder=getattr(cls, "_preferred_folder_type", None))
        
        return UnsupportedDomain(cls.name, url)
    
    @classmethod
    async def simulateDownload(cls, url: str, output_dir: str) -> str:
        
        gallery_config.load()
        gallery_config.default()
        gallery_config.set((), "base-directory", output_dir)
        gallery_config.set((), "cookies", "cookiefile.txt")
        gallery_config.set((), "simulate", True)
        gallery_config.set((), "range", 1)
        gallery_config.set((), "sleep-request", 0)
        gallery_config.set(("extractor",), "postprocessors", [{
            "name": "metadata",
            "event": "prepare",
        }])
        
    
        buffer = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = buffer
        sys.stderr = buffer

        try:
            job = gallery_job.DownloadJob(url)
            job.run()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
    
        output = buffer.getvalue()
        if ("error" not in output):
            return True
        
        return False

    
    @classmethod
    async def download(cls, url: str, output_dir: str, scan_only: bool) -> str:
        if gallery_job is None or gallery_config is None:
            raise MediaRouterError("gallery-dl is not installed")

        def run_job() -> str:
            import io
            import sys
            from pathlib import Path

            gallery_config.load()
            gallery_config.default()
            gallery_config.set((), "base-directory", output_dir)
            gallery_config.set((), "cookies", "cookiefile.txt")
            gallery_config.set(("extractor",), "postprocessors", [{
                "name": "metadata",
                "event": "prepare",
            }])
            
            buffer = io.StringIO()
            old_stdout = sys.stdout
            old_stderr = sys.stderr

            sys.stdout = buffer
            sys.stderr = buffer

            try:
                job = gallery_job.DownloadJob(url)
                job.run()
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            output = buffer.getvalue()

            logger.info("gallery-dl raw output:\n%s", output)

            # -----------------------------
            # FIX: normalize correctly
            # -----------------------------
            lines = []

            for line in output.splitlines():
                line = line.strip()

                if line.startswith("# ") or line.startswith("* "):
                    path = line[2:].strip()

                    # IMPORTANT FIX: remove leading "./"
                    path = path.lstrip("./")

                    logger.info("parsed file: %s", path)

                    lines.append(path)

            logger.info("parsed files=%s", lines)
            
            if not lines:
                logger.error("No file paths found in gallery-dl output")
                raise MediaRouterError("gallery-dl produced no file paths")

            final_path = lines[-1]

            final_dir = Path(final_path).resolve().parent

            logger.info("final dir=%s", final_dir)

            return str(final_dir)

        return await asyncio.to_thread(run_job)