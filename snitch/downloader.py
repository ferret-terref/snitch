import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

import aiohttp
from gallery_dl import config, job

from . import helpers
from .config import GalleryDlConfig, get_executable_dir

logger = logging.getLogger(__name__)

# Async function to download a single image from a direct URL
async def download_image_direct(url: str, folder: str = None, tags: list[str] = None, page_url: str = None, title: str = None) -> dict:
    """
    Download a single image from a direct URL, save to folder, and optionally send tags to Stash.
    Returns dict with file path and tags.
    """

    from datetime import datetime

    from .api import database, stash_client
    from .tagging import StashTagger

    logger.info(f"Starting image download: url={url}, folder={folder}, tags={tags}")
    base_dir = Path(folder) if folder else Path.cwd() / "downloads"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = helpers.extract_filename_from_url(url, default=f"image_{datetime.now().timestamp()}.jpg")
    file_path = base_dir / filename

    headers = helpers.build_default_headers(referer=url)

    # --- Cookie handling ---
    # Extract domain from URL
    domain = helpers.extract_domain(url)
    cookies = {}
    if domain and database:
        cookies = await database.get_cookies_for_domain(domain)
        if cookies:
            headers["Cookie"] = helpers.format_cookies_header(cookies)
            logger.info(f"Using cookies for {domain}: {headers['Cookie']}")

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
                
                async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
                    async with session.get(url, headers=request_headers) as resp:
                        logger.info(f"Retry {retry + 1}: HTTP {resp.status}, Content-Range: {resp.headers.get('Content-Range', 'N/A')}")
                        
                        # Accept both 200 (full) and 206 (partial) responses
                        if resp.status not in [200, 206]:
                            text = await resp.text()
                            # Detect Cloudflare block
                            if helpers.is_cloudflare_block(resp.status, text, resp.headers):
                                logger.warning(f"Cloudflare block detected for {url} (domain: {domain})")
                                logger.error(f"Response text: {text}")
                                raise Exception(f"Cloudflare block detected. Please provide the 'cf_clearance' cookie for {domain} via the UI.")
                            # Special handling for 404 with HTML (expired/invalid auto-download link)
                            content_type = resp.headers.get("Content-Type", "").lower()
                            if resp.status == 404 and "html" in content_type:
                                preview = text[:200].replace('\n', ' ')
                                logger.error(f"Failed to download image: HTTP 404 (likely expired or invalid auto-download link). Preview: {preview!r}")
                                raise Exception("Download link returned 404 Not Found and HTML content. This usually means the link has expired or is invalid. For DeviantArt, try refreshing the page and getting a new download link.")
                            logger.error(f"Failed to download image: HTTP {resp.status}, response: {text[:200]!r}")
                            raise Exception(f"Failed to download image: HTTP {resp.status}")

                        content_type = resp.headers.get("Content-Type", "").lower()
                        content_length = resp.headers.get("Content-Length")
                        
                        if retry == 0:
                            logger.info(f"Image GET {url} status: {resp.status}")
                            logger.info(f"Response Content-Type: {content_type}, Content-Length: {content_length}")

                            # If the content type is HTML, it's likely an error page (expired link, etc.)
                            if "html" in content_type:
                                preview = await resp.content.read(256)
                                logger.error(f"URL returned HTML instead of an image. This may be an expired or invalid auto-download link. Content-Type: {content_type}, preview: {preview[:100]!r}")
                                raise Exception(f"URL returned HTML instead of an image. The link may have expired or require authentication. (Content-Type: {content_type})")

                            if not helpers.is_media_content_type(content_type):
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
    if stash_client:
        tagger = StashTagger(stash_client)
        try:
            job_id = await stash_client.trigger_scan([str(base_dir)])
            await stash_client.wait_for_scan_completion(job_id, timeout=300)
            # Determine file type using the full filename
            if helpers.is_image_extension(filename):
                await tagger.tag_image_by_filename(filename, tags, page_url, title)
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
        logger.info(f"Downloading gallery: {url} -> {destination}")
        
        try:
            
            from gallery_dl import config as gallery_config

            # Load gallery-dl config
            gallery_config.load()
            if self.config.config_file:
                gallery_config.load(self.config.config_file)
            
            # Set destination
            gallery_config.set((), 'base-directory', destination)
            logger.info(f"Set gallery-dl base-directory to: {gallery_config.get((), 'base-directory', destination)}")
            
            # Cookie handling for Twitter/X
            
            from .api import database
            domain = helpers.extract_domain(url)
            if domain in ('x.com', 'twitter.com') and database:
                print(f"Checking for cookies for domain: {domain}")
                cookies = await database.get_cookies_for_domain(domain)
                if cookies:
                    gallery_config.set(('extractor', 'twitter'), 'cookies', cookies)
                    logger.info(f"Using cookies for Twitter: {cookies}")
            
            # Create download job
            j = job.DownloadJob(url)
            
            # Hook to capture the download directory
            captured_dirs = []
            def capture_directory(pathfmt):
                captured_dirs.append(pathfmt.directory)
            j.hooks = {"post": [capture_directory]}
            
            await asyncio.to_thread(j.run)
            
            downloaded_folder = captured_dirs[0] if captured_dirs else destination
            logger.info(f"Downloaded: {url} → {downloaded_folder}")
            return True, None, downloaded_folder
            
        except Exception as e:
            error_msg = str(e)
            # Improve error messages for common cases
            if "'Unavailable'" in error_msg or "Unavailable" in error_msg:
                error_msg = "The content is not available. It may be private, deleted, or require authentication (e.g., login to Twitter/X)."
            elif "No video could be found" in error_msg or "No images found" in error_msg:
                error_msg = "No downloadable media found in this post. It may contain only text or unsupported content."
            logger.error(f"Failed to download {url}: {error_msg}")
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
                logger.info(f"Tags in metadata: {metadata.get('tags')}")
                return metadata
                
        except Exception as e:
            logger.error(f"Failed to read gallery metadata: {e}")
            return None
