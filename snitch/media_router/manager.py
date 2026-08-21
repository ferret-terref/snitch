from __future__ import annotations

import asyncio
from typing import Type

from snitch.media_router.downloaders.base import Downloader

from .exceptions import NoSupportedDownloaderError
from .models import ProbeResult, ProbeTimeout, UnsupportedDomain
from .registry import DownloaderRegistry


class DownloadManager:
    async def resolve(self, url: str) -> tuple[Type["Downloader"], ProbeResult]:
        downloaders = DownloaderRegistry.get_downloaders()
        if not downloaders:
            raise NoSupportedDownloaderError("No downloaders are registered")

        tasks = [self._probe_downloader(downloader, url) for downloader in downloaders]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        print(f"Probe results for URL: {url}")
        for downloader, result in zip(downloaders, results):
            print(f"  {downloader.name} [{result.supported}]")
            
        supported_candidates = [
            (downloader, result)
            for downloader, result in zip(downloaders, results)
            if isinstance(result, ProbeResult) and result.supported
        ]
        if not supported_candidates:
            raise NoSupportedDownloaderError(
                f"No supported downloader found for URL: {url}"
            )

        downloader_cls, probe_result = max(
            supported_candidates,
            key=lambda item: (item[1].score, item[0].priority),
        )
        return downloader_cls, probe_result

    async def download(
        self,
        url: str,
        output_dir: str,
        downloader_cls: Type["Downloader"] | None = None,
    ) -> tuple[Type["Downloader"], ProbeResult]:
        if downloader_cls is None:
            downloader_cls, probe_result = await self.resolve(url)
        else:
            probe_result = ProbeResult(
                supported=True,
                score=0,
                reason=f"Manual download with {downloader_cls.name}",
            )

        await downloader_cls.download(url, output_dir)
        return downloader_cls, probe_result

    async def _probe_downloader(
        self, downloader: Type["Downloader"], url: str
    ) -> ProbeResult:
        timeout = getattr(downloader, "timeout", 5.0)
        try:
            result = await asyncio.wait_for(downloader.probe(url), timeout=timeout)
            if not isinstance(result, ProbeResult):
                return UnsupportedDomain(downloader.name, url)
            return result
        except asyncio.TimeoutError:
            return ProbeTimeout(downloader.name, url, timeout)
        except Exception:
            return UnsupportedDomain(downloader.name, url)
