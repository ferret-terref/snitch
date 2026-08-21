from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from snitch.config import FolderType


@dataclass(frozen=True)
class ProbeResult:
    supported: bool
    score: int = 0
    reason: str = ""
    error: Optional[str] = None
    # Optional preferred folder type suggested by this probe
    preferred_folder: Optional[FolderType] = None

    def __post_init__(self):
        if self.score < 0:
            raise ValueError("score must be non-negative")

    @property
    def is_success(self) -> bool:
        return self.supported and self.score > 0

@dataclass(frozen=True, init=False)
class SupportedDomain(ProbeResult):
    name: str
    url: str

    def __init__(self, name: str, url: str, score: int = 100, preferred_folder: Optional[FolderType] = None):
        reason = f"{url} is recognized as a {name} supported domain"
        super().__init__(supported=True, score=score, reason=reason, error=None, preferred_folder=preferred_folder)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "preferred_folder", preferred_folder)

@dataclass(frozen=True, init=False)
class ModuleNotInstalled(ProbeResult):
    name: str
    url: Optional[str] = None

    def __init__(self, name: str, url: Optional[str] = None):
        reason = f"{name} is not installed"
        if url:
            reason = f"{reason} for {url}"
        super().__init__(supported=False, score=0, reason=reason, error=None)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)

@dataclass(frozen=True, init=False)
class UnsupportedDomain(ProbeResult):
    name: str
    url: str

    def __init__(self, name: str, url: str):
        reason = f"{url} is not recognized as a {name} supported domain"
        super().__init__(supported=False, score=0, reason=reason, error=None)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)

@dataclass(frozen=True, init=False)
class ProbeTimeout(ProbeResult):
    name: str
    url: str
    timeout: float

    def __init__(self, name: str, url: str, timeout: float):
        reason = f"{name} probe timed out after {timeout}s for {url}"
        super().__init__(supported=False, score=0, reason=reason, error=None)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "timeout", timeout)

@dataclass(frozen=True, init=False)
class ProbeError(ProbeResult):
    name: str
    url: str
    error: Exception

    def __init__(self, name: str, url: str, error: Exception):
        reason = f"{name} probe failed for {url}: {error}"
        super().__init__(supported=False, score=0, reason=reason, error=str(error))
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "error", error)