import asyncio

from snitch.media_router.downloaders.base import Downloader
from snitch.media_router.manager import DownloadManager
from snitch.media_router.models import ProbeResult
from snitch.media_router.registry import DownloaderRegistry


class DummyDownloader(Downloader):
    name = "dummy"
    priority = 0
    timeout = 1.0

    @classmethod
    async def probe(cls, url: str) -> ProbeResult:
        return ProbeResult(supported=True, score=10, reason="dummy support")

    @classmethod
    async def download(cls, url: str, output_dir: str) -> str:
        return None


def test_registry_registers_downloader():
    DownloaderRegistry.clear()
    DownloaderRegistry.register(DummyDownloader)
    assert DummyDownloader in DownloaderRegistry.get_downloaders()


def test_manager_resolves_best_downloader():
    DownloaderRegistry.clear()
    DownloaderRegistry.register(DummyDownloader)
    manager = DownloadManager()

    downloader_cls, probe_result = asyncio.run(manager.resolve("https://example.com/test"))

    assert downloader_cls is DummyDownloader
    assert probe_result.supported is True
    assert probe_result.score == 10
