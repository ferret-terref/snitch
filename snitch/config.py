"""Configuration management."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class DownloadFolder(BaseModel):
    name: str
    path: str
    default: bool = False


class GalleryDlConfig(BaseModel):
    executable: str = "gallery-dl"
    config_file: str = ""
    default_args: list[str] = Field(default_factory=list)


class StashAppConfig(BaseModel):
    enabled: bool = False
    url: str = "http://localhost:9999"
    api_key: str = ""


class DatabaseConfig(BaseModel):
    path: str = "snitch.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "snitch.log"


class QueueConfig(BaseModel):
    max_concurrent_downloads: int = 3
    scan_batch_size: int = 5
    scan_batch_timeout: int = 60  # seconds


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    download_folders: list[DownloadFolder] = Field(default_factory=list)
    gallery_dl: GalleryDlConfig = Field(default_factory=GalleryDlConfig)
    stashapp: StashAppConfig = Field(default_factory=StashAppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    
    return Config(**data)
