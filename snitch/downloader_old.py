"""Backup of the old subprocess-based GalleryDownloader.download method."""

import asyncio
import subprocess
import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp

from . import helpers
from .config import GalleryDlConfig, get_executable_dir

logger = logging.getLogger(__name__)

class GalleryDownloaderOld:
    def __init__(self, config: GalleryDlConfig):
        self.config = config
    
    async def download(
        self, url: str, destination: str, job_id: int
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Download a gallery using gallery-dl subprocess.
        
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
        import sys
        if sys.platform == "win32":
            write_path_wrapper = get_executable_dir() / "write_path_wrapper.bat"
            if not (write_path_wrapper).exists():
                logger.error(f"Executable not found: {write_path_wrapper}")
                raise FileNotFoundError(f"Executable not found: {write_path_wrapper}")
            
            # NO quotes - will be passed as single argument
            exec_cmd = f"{write_path_wrapper} {{_directory}} {path_file}"
        else:
            write_path_script = get_executable_dir() / "write_path.py"
            exec_cmd = f'python "{write_path_script}" "{{_directory}}" "{path_file}"'
        
        # Build command list
        cmd = [self.config.executable]
        
        # Add config file if specified
        if self.config.config_file:
            logger.info(f"Using config file: {self.config.config_file}")
            cmd.extend(["--config", self.config.config_file])
        else:
            logger.info("No config file specified, using gallery-dl defaults")
        
        # Add default arguments
        if self.config.default_args:
            logger.info(f"Using default args: {self.config.default_args}")
            cmd.extend(self.config.default_args)
        
        # Add destination, exec-after, and URL
        cmd.extend([
            "--destination", destination,
            "--exec-after", exec_cmd,
            url
        ])
        
        cmd_str = ' '.join(cmd)
        logger.info(f"Running gallery-dl: {cmd_str}")
        logger.info(f"Command list (raw): {cmd}")
        
        try:
            # Use exec on Windows for better compatibility
            if sys.platform == "win32":
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                
                logger.info(f"Executing command with create_subprocess_exec: {cmd}")

                # Use exec directly - pass arguments as list (no shell interpretation)
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Unix systems can use exec directly
                logger.debug(f"Executing command string on unix: {cmd}")

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, 
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            
            # Read and log output live
            async def log_stream(stream, name):
                """Read from stream line by line and log it."""
                lines = []
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    if decoded:
                        logger.info(f"[gallery-dl {name}] {decoded}")
                        lines.append(decoded)
                return '\n'.join(lines)
            
            # Run both stdout and stderr readers concurrently
            stdout_text, stderr_text = await asyncio.gather(
                log_stream(process.stdout, "stdout"),
                log_stream(process.stderr, "stderr")
            )
            
            # Wait for process to complete
            await process.wait()
            
            if process.returncode == 0:
                # Read the folder path from the temp file
                downloaded_folder = None
                try:
                    if path_file.exists():
                        downloaded_folder = path_file.read_text(encoding='utf-8').strip()
                        # Clean up the path
                        downloaded_folder = helpers.clean_path(downloaded_folder)
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
                error_msg = stderr_text or stdout_text
                logger.error(f"Failed to download {url}: {error_msg}")
                return False, error_msg, None
                
        except Exception as e:
            error_msg = f"Exception during download: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None