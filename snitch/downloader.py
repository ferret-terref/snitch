import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp

from .config import GalleryDlConfig

logger = logging.getLogger(__name__)

# Async function to download a single image from a direct URL
async def download_image_direct(url: str, folder: str = None, tags: list[str] = None) -> dict:
    """
    Download a single image from a direct URL, save to folder, and optionally store tags.
    Returns dict with file path and tags.
    """
    from datetime import datetime
    base_dir = Path(folder) if folder else Path.cwd() / "downloads"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0] or f"image_{datetime.now().timestamp()}.jpg"
    file_path = base_dir / filename

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download image: HTTP {resp.status}")
            with open(file_path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1024 * 32)
                    if not chunk:
                        break
                    f.write(chunk)

    # Optionally, save tags as a sidecar file
    if tags:
        tag_path = file_path.with_suffix(file_path.suffix + ".tags.json")
        import json
        with open(tag_path, "w", encoding="utf-8") as tf:
            json.dump({"tags": tags}, tf)

    return {"file": str(file_path), "tags": tags or []}


"""Gallery downloader using gallery-dl."""
class GalleryDownloader:
    def __init__(self, config: GalleryDlConfig):
        self.config = config
    
    async def download(
        self, url: str, destination: str, job_id: int
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Download a gallery using gallery-dl.
        
        Args:
            url: Gallery URL to download
            destination: Base destination folder
            job_id: Job ID for tracking
        
        Returns:
            (success: bool, error_message: Optional[str], downloaded_folder: Optional[str])
        """
        # Create temp directory for path output
        temp_dir = Path("C:/Temp/gallery-dl")
        temp_dir.mkdir(parents=True, exist_ok=True)
        path_file = temp_dir / f"{job_id}-path.txt"
        
        # Remove old path file if it exists
        if path_file.exists():
            path_file.unlink()
        
        # Build gallery-dl command
        cmd = [self.config.executable]
        
        # Add config file if specified
        if self.config.config_file:
            cmd.extend(["--config", self.config.config_file])
        
        # Add default arguments
        if self.config.default_args:
            cmd.extend(self.config.default_args)
        
        # Set destination directory
        cmd.extend(["--destination", destination])
        
        import sys
        if sys.platform == "win32":
            # Use batch file wrapper to handle Windows argument edge cases
            write_path_wrapper = Path(__file__).parent / "write_path_wrapper.bat"
            exec_cmd = f'"{write_path_wrapper}" {{_directory}} {path_file}'
        else:
            write_path_script = Path(__file__).parent / "write_path.py"
            exec_cmd = f'python "{write_path_script}" "{{_directory}}" "{path_file}"'
            
        cmd.extend(["--exec-after", exec_cmd])
        
        # Add URL
        cmd.append(url)
        
        logger.info(f"Running gallery-dl: {' '.join(cmd)}")
        
        try:
            # Use shell on Windows for better compatibility
            import sys
            if sys.platform == "win32":
                # Build command string with proper quoting for Windows
                cmd_parts = []
                for i, part in enumerate(cmd):
                    # Special handling for --exec-after value
                    if i > 0 and cmd[i-1] == "--exec-after":
                        # Already has internal quotes, just wrap in outer quotes
                        cmd_parts.append(f'"{part}"')
                    elif ' ' in part or '/' in part:
                        cmd_parts.append(f'"{part}"')
                    else:
                        cmd_parts.append(part)
                cmd_str = ' '.join(cmd_parts)
                
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"

                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                
            else:
                # Unix systems can use exec directly
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Read the folder path from the temp file
                downloaded_folder = None
                try:
                    if path_file.exists():
                        downloaded_folder = path_file.read_text(encoding='utf-8').strip()
                        # Clean up the path - remove quotes and extended-length prefix
                        downloaded_folder = downloaded_folder.strip('"').strip("'")
                        if downloaded_folder.startswith('\\\\?\\'):
                            downloaded_folder = downloaded_folder[4:]
                        # Remove trailing backslash/slash
                        downloaded_folder = downloaded_folder.rstrip('\\/')
                        logger.info(f"Read folder path from temp file: {downloaded_folder}")
                        # Clean up the temp file
                        path_file.unlink()
                    else:
                        logger.warning(f"Temp path file not found: {path_file}")
                except Exception as e:
                    logger.error(f"Failed to read temp path file: {e}")
                
                logger.info(f"Downloaded: {url} → {downloaded_folder}")
                return True, None, downloaded_folder
            else:
                error_msg = stderr.decode('utf-8', errors='replace').strip() or stdout.decode('utf-8', errors='replace').strip()
                logger.error(f"Failed to download {url}: {error_msg}")
                return False, error_msg, None
                
        except Exception as e:
            error_msg = f"Exception during download: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def find_gallery_metadata(self, destination: str) -> Optional[dict]:
        """
        Find and read the info.json file created by gallery-dl.
        Also adds the actual download folder path to the metadata.
        
        Args:
            destination: The download destination folder
            
        Returns:
            Dictionary with metadata (title, site, etc.) plus 'folder_path' or None
        """
        try:
            dest_path = Path(destination)
            # Find the most recently modified info.json file
            info_files = list(dest_path.rglob("info.json"))
            
            if not info_files:
                logger.warning(f"No info.json found in {destination}")
                return None
            
            # Get the most recently modified one
            latest_info = max(info_files, key=lambda p: p.stat().st_mtime)
            
            with open(latest_info, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                # Add the actual folder path (parent of info.json)
                metadata['folder_path'] = str(latest_info.parent)
                logger.info(f"Read metadata from {latest_info}: {metadata.get('title')}")
                return metadata
                
        except Exception as e:
            logger.error(f"Failed to read gallery metadata: {e}")
            return None
