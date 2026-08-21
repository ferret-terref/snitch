"""Configuration management."""

import os
import sys
from enum import Enum as _Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default="8080")


class FolderType(_Enum):
    Images = "Images"
    Scenes = "Scenes"
    Gallery = "Gallery"


class DownloadFolder(BaseModel):
    name: str
    path: str
    type: FolderType = FolderType.Images
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


def get_executable_dir() -> Path:
    """Get the directory where the executable or script is located."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent.parent


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    # If relative path, make it relative to executable directory
    path = Path(config_path)
    if not path.is_absolute():
        path = get_executable_dir() / config_path
    
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    
    # Make relative database path absolute relative to executable
    config = Config(**data)
    if not Path(config.database.path).is_absolute():
        config.database.path = str(get_executable_dir() / config.database.path)
    
    if not Path(config.logging.file).is_absolute():
        config.logging.file = str(get_executable_dir() / config.logging.file)
    
    return config
