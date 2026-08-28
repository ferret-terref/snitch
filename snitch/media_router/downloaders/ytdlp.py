from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

from snitch.config import FolderType

from ..exceptions import MediaRouterError
from ..models import (ModuleNotInstalled, ProbeError, ProbeResult,
                      SupportedDomain, UnsupportedDomain)
from ..registry import DownloaderRegistry
from ..utils.urls import is_direct_media_url, parse_domain
from .base import Downloader

try:
    from yt_dlp import YoutubeDL  # type: ignore
except ImportError:  # pragma: no cover
    YoutubeDL = None

@DownloaderRegistry.register
class YtDlpDownloader(Downloader):
    name: ClassVar[str] = "yt-dlp"
    priority: ClassVar[int] = 90
    timeout: ClassVar[float] = 10.0
    _preferred_folder_type: ClassVar[FolderType] = FolderType.Scenes

    @classmethod
    async def probe(cls, url: str) -> ProbeResult:
        if YoutubeDL is None:
            return ModuleNotInstalled(cls.name, url)

        if is_direct_media_url(url):
            return UnsupportedDomain(cls.name, url)

        try:
            ydl_probe_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "simulate": True,
            }

            # prefer a cookiefile at the repo root if present
            cookiefile = Path.cwd() / "cookiefile.txt"
            if cookiefile.exists() and cookiefile.stat().st_size > 0:
                ydl_probe_opts["cookiefile"] = str(cookiefile)
            else:
                ydl_probe_opts["http_headers"] = cls._build_http_headers(url)

            await asyncio.to_thread(
                lambda: YoutubeDL(ydl_probe_opts).extract_info(url, download=False)
            )

            # Suggest the class-level preferred folder for yt-dlp
            return SupportedDomain(cls.name, url, preferred_folder=getattr(cls, "_preferred_folder_type", None))
        except Exception as exc:
            return ProbeError(cls.name, url, exc)
    
    @classmethod
    async def download(cls, url: str, output_dir: str, scan_only: bool) -> str:
        if YoutubeDL is None:
            raise MediaRouterError("yt-dlp is not installed")

        ydl_opts = {
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "writeinfojson": True,
            "no_warnings": True,
            "quiet": True,
        }

        cookiefile = Path.cwd() / "cookiefile.txt"
        if cookiefile.exists() and cookiefile.stat().st_size > 0:
            ydl_opts["cookiefile"] = str(cookiefile)
        else:
            ydl_opts["http_headers"] = cls._build_http_headers(url)

        def run_download() -> str:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                downloads = info.get("requested_downloads")
                if downloads:
                    return downloads[0]["filepath"]

                return ydl.prepare_filename(info)

        return await asyncio.to_thread(run_download)

    @classmethod
    def _build_http_headers(cls, url: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        cookie_header = cls._get_cookie_header(url)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    @classmethod
    def _get_cookie_header(cls, url: str) -> str | None:
        host = parse_domain(url)
        if not host:
            return None

        # exact = YTDLP_COOKIES_BY_DOMAIN.get(host)
        # if exact:
        #     return exact
# 
        # if host.startswith("."):
        #     host = host[1:]
# 
        # parts = host.split('.')
        # if len(parts) > 2:
        #     root = '.'.join(parts[-2:])
        #     return YTDLP_COOKIES_BY_DOMAIN.get(root)

        return None
