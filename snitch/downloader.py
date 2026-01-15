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
async def download_image_direct(url: str, folder: str = None, tags: list[str] = None, page_url: str = None) -> dict:
    """
    Download a single image from a direct URL, save to folder, and optionally send tags to Stash.
    Returns dict with file path and tags.
    """

    import re
    from datetime import datetime

    from .api import database, stash_client
    from .tagging import StashTagger

    logger.info(f"Starting image download: url={url}, folder={folder}, tags={tags}")
    base_dir = Path(folder) if folder else Path.cwd() / "downloads"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0] or f"image_{datetime.now().timestamp()}.jpg"
    file_path = base_dir / filename

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Accept": "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Referer": url,
        "Priority": "u=0, i",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache"
    }

    # --- Cookie handling ---
    # Extract domain from URL
    domain_match = re.match(r"https?://([^/]+)", url)
    domain = domain_match.group(1) if domain_match else None
    cookies = {}
    if domain and database:
        cookies = await database.get_cookies_for_domain(domain)
        if cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers["Cookie"] = cookie_header
            logger.info(f"Using cookies for {domain}: {cookie_header}")

    logger.debug(f"Request headers: {headers}")

    try:
        # Set timeouts to prevent hanging on stalled connections
        # total=600 (10 min), sock_read=30 (30 sec between chunks)
        timeout = aiohttp.ClientTimeout(total=600, sock_read=10)
        
        max_retries = 3
        bytes_downloaded = 0
        
        for retry in range(max_retries):
            try:
                # Create fresh headers for each attempt
                request_headers = headers.copy()
                
                # Set Range header if resuming
                if bytes_downloaded > 0:
                    request_headers["Range"] = f"bytes={bytes_downloaded}-"
                    logger.info(f"Resuming download from byte {bytes_downloaded}")
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=request_headers) as resp:
                        logger.info(f"Retry {retry + 1}: HTTP {resp.status}, Content-Range: {resp.headers.get('Content-Range', 'N/A')}")
                        
                        # Accept both 200 (full) and 206 (partial) responses
                        if resp.status not in [200, 206]:
                            text = await resp.text()
                            # Detect Cloudflare block (simple heuristic)
                            if resp.status == 403 and ("cloudflare" in text.lower() or "cf-ray" in resp.headers or "cf_clearance" in text.lower()):
                                logger.warning(f"Cloudflare block detected for {url} (domain: {domain})")
                                logger.error(f"Response text: {text}")
                                raise Exception(f"Cloudflare block detected. Please provide the 'cf_clearance' cookie for {domain} via the UI.")
                            logger.error(f"Failed to download image: HTTP {resp.status}, response: {text}")
                            raise Exception(f"Failed to download image: HTTP {resp.status}")

                        content_type = resp.headers.get("Content-Type", "").lower()
                        content_length = resp.headers.get("Content-Length")
                        
                        if retry == 0:
                            logger.info(f"Image GET {url} status: {resp.status}")
                            logger.info(f"Response Content-Type: {content_type}, Content-Length: {content_length}")
                            
                            if not (content_type.startswith("image/") or content_type.startswith("video/")):
                                # Read a small preview of the response for logging
                                preview = await resp.content.read(256)
                                logger.error(f"URL did not return an image. Content-Type: {content_type}, preview: {preview[:100]!r}")
                                raise Exception(f"URL did not return an image. Content-Type: {content_type}")

                        # Open file in append mode if resuming, write mode otherwise
                        mode = "ab" if bytes_downloaded > 0 else "wb"
                        with open(file_path, mode) as f:
                            chunk_size = 1024 * 8  # 8KB chunks
                            
                            chunk_count = 0
                            # Use iter_chunked for better streaming handling
                            async for chunk in resp.content.iter_chunked(chunk_size):
                                if not chunk:
                                    logger.info(f"Received empty chunk at {bytes_downloaded} bytes")
                                    break
                                f.write(chunk)
                                bytes_downloaded += len(chunk)
                                chunk_count += 1
                                
                                # Log progress every 1MB
                                if bytes_downloaded % (1024 * 1024) < chunk_size:
                                    logger.info(f"Downloaded {bytes_downloaded / (1024 * 1024):.1f} MB")
                            
                            logger.info(f"Retry {retry + 1} received {chunk_count} chunks")
                        
                        # Check if download completed
                        if content_length:
                            expected_size = int(content_length)
                            # For 206 responses, content_length is the partial size
                            if resp.status == 206:
                                # Parse Content-Range header to get total size
                                content_range = resp.headers.get("Content-Range", "")
                                if "/" in content_range:
                                    expected_size = int(content_range.split("/")[-1])
                            
                            if expected_size != bytes_downloaded:
                                logger.warning(f"Download incomplete! Expected {expected_size} bytes but got {bytes_downloaded} bytes")
                                # Will retry with Range header
                                continue
                        
                        # Success!
                        break
                        
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Download attempt {retry + 1}/{max_retries} failed at {bytes_downloaded} bytes: {e}")
                if retry < max_retries - 1:
                    await asyncio.sleep(2)  # Wait 2 seconds before retry
                else:
                    # If we got some data but not all, save what we have
                    if bytes_downloaded > 0:
                        logger.error(f"Download failed after {max_retries} retries. Saved partial file: {bytes_downloaded} bytes")
                        # File is already saved, just return with what we have
                        break
                    raise Exception(f"Download failed after {max_retries} retries at {bytes_downloaded} bytes")
                            
        logger.info(f"Image downloaded successfully: {file_path} ({bytes_downloaded} bytes)")
    except Exception as e:
        logger.exception(f"Exception during image download: {e}")
        raise

    # Send tags to Stash if available and tags provided
    if tags and stash_client:
        tagger = StashTagger(stash_client)
        try:
            job_id = await stash_client.trigger_scan([str(base_dir)])
            await stash_client.wait_for_scan_completion(job_id, timeout=300)
            # Determine file type
            ext = filename.split('.')[-1].lower()
            if ext in ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "svg", "avif"]:
                await tagger.tag_image_by_filename(filename, tags, page_url)
                logger.info(f"Tagged image in Stash: {filename} with tags: {tags}")
            else:
                await tagger.tag_scene_by_filename(filename, tags, page_url)
                logger.info(f"Tagged scene in Stash: {filename} with tags: {tags}")
        except Exception as e:
            logger.error(f"Failed to tag image/scene in Stash: {e}")

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
        import sys
        if sys.platform == "win32":
            write_path_wrapper = Path(__file__).parent / "write_path_wrapper.bat"
            # NO quotes - will be passed as single argument
            exec_cmd = f"{write_path_wrapper} {{_directory}} {path_file}"
        else:
            write_path_script = Path(__file__).parent / "write_path.py"
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
                )
            else:
                # Unix systems can use exec directly
                logger.debug(f"Executing command string on unix: {cmd}")

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
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
                error_msg = stderr_text or stdout_text
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
