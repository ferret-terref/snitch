from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar

import aiohttp

from snitch.config import FolderType
from snitch.helpers import (build_default_headers, extract_domain,
                            format_cookies_header, is_cloudflare_block)

from ..exceptions import MediaRouterError
from ..models import ProbeResult, SupportedDomain, UnsupportedDomain
from ..registry import DownloaderRegistry
from ..utils.urls import extract_filename_from_url, is_direct_media_url
from .base import Downloader

logger = logging.getLogger(__name__)

@DownloaderRegistry.register
class ManualDownloader(Downloader):
    name: ClassVar[str] = "manual"
    priority: ClassVar[int] = 10
    timeout: ClassVar[float] = 5.0
    _preferred_folder_type: ClassVar[FolderType] = FolderType.Images

    @classmethod
    async def probe(cls, url: str) -> ProbeResult:
        if is_direct_media_url(url):
            # For manual (direct) downloads, suggest Images or Scenes based on extension
            from snitch.config import FolderType
            from snitch.media_router.utils.urls import (is_image_url,
                                                        is_video_url)
            preferred = None
            if is_image_url(url):
                preferred = FolderType.Images
            elif is_video_url(url):
                preferred = FolderType.Scenes
            # If probe didn't determine preferred, fall back to class-level hint
            if preferred is None:
                preferred = getattr(cls, "_preferred_folder_type", None)
            return SupportedDomain(cls.name, url, preferred_folder=preferred)
        return UnsupportedDomain(cls.name, url)

    @classmethod
    async def download(cls, url: str, output_dir: str, scan_only: bool) -> str:
        if not is_direct_media_url(url):
            raise MediaRouterError("Manual downloader only supports direct media URLs")

        output_path = cls._resolve_output_path(output_dir, url)
        if (scan_only == False):
            headers = await cls._build_headers(url)
            await cls._download_with_retries(url, headers, output_path)
            
        return extract_filename_from_url(url, default="downloaded_file")

    @classmethod
    def _resolve_output_path(cls, output_dir: str, url: str) -> Path:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        filename = extract_filename_from_url(url, default="downloaded_file")
        return destination / filename

    @classmethod
    async def _build_headers(cls, url: str) -> dict[str, str]:
        headers = build_default_headers(referer=url)
        cookies = await cls._get_cookies(url)
        if cookies:
            logger.info("Found cookies - using")
            logger.info(cookies)
            headers["Cookie"] = format_cookies_header(cookies)
        return headers

    @classmethod
    async def _get_cookies(cls, url: str) -> dict[str, str]:
        domain = extract_domain(url)
        logger.info(f"Extracted domain: {domain} from URL: {url}")
        if not domain:
            return {}

        # Try to load cookies from the database first
        db_cookies: dict[str, str] = {}
        try:
            import snitch.api as api

            db = getattr(api, "database", None)
            if db:
                db_cookies = await db.get_cookies_for_domain(domain) or {}
        except Exception:
            db_cookies = {}

        # Also load cookies from a cookiefile (Netscape format) at repo root
        file_cookies: dict[str, str] = {}
        try:
            cookiefile = Path.cwd() / "cookiefile.txt"
            if cookiefile.exists() and cookiefile.stat().st_size > 0:
                with open(cookiefile, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split('\t')
                        if len(parts) < 7:
                            continue
                        domain_field = parts[0]
                        name = parts[5]
                        value = parts[6]
                        dom = domain_field.lstrip('.').lower()
                        host = domain.split(':', 1)[0].lower()
                        # Match exact host or subdomains (e.g. host == dom or host endswith '.dom')
                        if host == dom or host.endswith('.' + dom):
                            file_cookies[name] = value
        except Exception:
            file_cookies = {}

        # Merge cookies, preferring cookiefile entries (like yt-dlp)
        merged = {**db_cookies, **file_cookies}
        return merged

    @classmethod
    async def _download_with_retries(
        cls,
        url: str,
        headers: dict[str, str],
        output_path: Path,
        max_retries: int = 3,
    ) -> None:
        timeout = aiohttp.ClientTimeout(total=600, sock_read=10)

        for attempt in range(1, max_retries + 1):
            try:
                await cls._download_once(url, headers, output_path, timeout, attempt)
                return
            except (aiohttp.ClientError, asyncio.TimeoutError, MediaRouterError) as exc:
                if attempt >= max_retries:
                    raise MediaRouterError(f"Failed to download URL: {url}") from exc
                await asyncio.sleep(2)

    @classmethod
    async def _download_once(
        cls,
        url: str,
        headers: dict[str, str],
        output_path: Path,
        timeout: aiohttp.ClientTimeout,
        attempt: int,
    ) -> None:
        async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.get(url, headers=headers) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                content_length = resp.headers.get("Content-Length")
                
                if (content_length is None or content_length == 0):
                    logger.info("Failed to download - content_length was %s", content_length)
                    raise MediaRouterError(f"Content Length was {content_length}")
                    
                if resp.status not in {200, 206}:
                    text = await resp.text()
                    if is_cloudflare_block(resp.status, text, resp.headers):
                        raise MediaRouterError(
                            f"Cloudflare block detected for {url}."
                        )
                    raise MediaRouterError(
                        f"Failed to download URL: HTTP {resp.status}"
                    )

                if attempt == 1 and "html" in content_type:
                    preview = await resp.content.read(256)
                    raise MediaRouterError(
                        f"URL returned HTML instead of media: {preview[:100]!r}"
                    )

                bytes_downloaded = await cls._write_response(resp, output_path)

                if content_length and resp.status == 200:
                    expected_size = int(content_length)
                    if bytes_downloaded != expected_size:
                        raise MediaRouterError(
                            f"Incomplete download: expected {expected_size} bytes, got {bytes_downloaded}"
                        )

    @classmethod
    async def _write_response(cls, resp: aiohttp.ClientResponse, output_path: Path) -> int:
        bytes_downloaded = 0
        with open(output_path, "wb") as f:
            async for chunk in resp.content.iter_chunked(8192):
                if not chunk:
                    break
                f.write(chunk)
                bytes_downloaded += len(chunk)
        return bytes_downloaded
