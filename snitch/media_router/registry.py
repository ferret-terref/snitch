from __future__ import annotations

from typing import Type

from .downloaders.base import Downloader


class DownloaderRegistry:
    _downloaders: list[Type[Downloader]] = []

    @classmethod
    def register(cls, downloader: Type[Downloader]) -> Type[Downloader]:
        if downloader not in cls._downloaders:
            cls._downloaders.append(downloader)
        return downloader

    @classmethod
    def get_downloaders(cls) -> tuple[Type[Downloader], ...]:
        return tuple(cls._downloaders)

    @classmethod
    def clear(cls) -> None:
        cls._downloaders.clear()
