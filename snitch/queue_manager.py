"""Download queue manager."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from .database import Database
from .downloader import GalleryDownloader
from .models import DownloadJob, DownloadStatus
from .stash import StashClient

logger = logging.getLogger(__name__)


class QueueManager:
    def __init__(
        self,
        database: Database,
        downloader: GalleryDownloader,
        stash_client: Optional[StashClient] = None,
        max_concurrent: int = 3,
        scan_batch_size: int = 5,
        scan_batch_timeout: int = 60
    ):
        self.database = database
        self.downloader = downloader
        self.stash_client = stash_client
        self.max_concurrent = max_concurrent
        self.scan_batch_size = scan_batch_size
        self.scan_batch_timeout = scan_batch_timeout
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._download_semaphore = asyncio.Semaphore(max_concurrent)
        self._last_scan_time: float = 0
        self._job_folders: dict[int, str] = {}  # Map job_id -> downloaded_folder
    
    async def start(self):
        """Start processing the queue."""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("Queue manager started")
    
    async def stop(self):
        """Stop processing the queue."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Queue manager stopped")
    
    async def _process_queue(self):
        """Main queue processing loop."""
        while self.running:
            try:
                # Phase 1: Start downloads for pending jobs (up to max_concurrent)
                pending_jobs = await self.database.get_pending_jobs()
                downloading_jobs = await self.database.get_downloading_jobs()
                
                # Start new downloads if we have capacity
                available_slots = self.max_concurrent - len(downloading_jobs)
                if available_slots > 0 and pending_jobs:
                    jobs_to_start = pending_jobs[:available_slots]
                    tasks = [self._download_job(job) for job in jobs_to_start]
                    if tasks:
                        # Start downloads without waiting for them to complete
                        for task in tasks:
                            asyncio.create_task(task)
                
                # Phase 2: Check if we should trigger a scan batch
                awaiting_scan = await self.database.get_awaiting_scan_jobs()
                time_since_last_scan = time.time() - self._last_scan_time
                
                should_scan = (
                    len(awaiting_scan) >= self.scan_batch_size or
                    (len(awaiting_scan) > 0 and time_since_last_scan >= self.scan_batch_timeout)
                )
                
                if should_scan and self.stash_client:
                    await self._process_scan_batch(awaiting_scan)
                    self._last_scan_time = time.time()
                
                # Wait before next iteration
                await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"Error processing queue: {e}")
                await asyncio.sleep(5)
    
    async def _download_job(self, job: DownloadJob):
        """Download a single job with semaphore limiting."""
        async with self._download_semaphore:
            try:
                logger.info(f"[Job {job.id}] Starting download: {job.url}")
                
                # Update status to downloading
                await self.database.update_status(job.id, DownloadStatus.DOWNLOADING)
                
                # Download
                success, error_msg, downloaded_folder = await self.downloader.download(
                    job.url, job.folder_path, job.id
                )
                
                if success:
                    # Store the downloaded folder path for later matching
                    if downloaded_folder:
                        self._job_folders[job.id] = downloaded_folder
                        await self.database.update_gallery_path(job.id, downloaded_folder)
                    
                    # Move to awaiting_scan status
                    await self.database.update_status(job.id, DownloadStatus.AWAITING_SCAN)
                    logger.info(f"[Job {job.id}] Download complete, awaiting scan")
                else:
                    await self.database.update_status(
                        job.id, DownloadStatus.FAILED, error_msg
                    )
                    logger.error(f"Job {job.id} failed: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Error downloading job {job.id}: {e}")
                await self.database.update_status(
                    job.id, DownloadStatus.FAILED, str(e)
                )
    
    async def _process_scan_batch(self, jobs: list[DownloadJob]):
        """Process a batch of completed downloads with Stash scanning."""
        if not jobs:
            return
        
        logger.info(f"Processing scan batch of {len(jobs)} jobs")
        
        try:
            # Mark all as scanning
            for job in jobs:
                await self.database.update_status(job.id, DownloadStatus.SCANNING)
            
            # Collect all paths
            paths = list(set(job.gallery_path for job in jobs))
            
            logger.info(f"Triggering Stash scan for {len(paths)} path(s)")
            logger.info('Directories to scan:\n\t' + '\n\t'.join(paths))
            
            # Trigger single scan for all paths
            stash_job_id = await self.stash_client.trigger_scan(paths=paths)
            
            if stash_job_id:
                logger.info("Waiting for Stash scan to complete...")
                scan_completed = await self.stash_client.wait_for_scan_completion(stash_job_id, timeout=120)
                
                if scan_completed:
                    # Mark all as updating
                    for job in jobs:
                        await self.database.update_status(job.id, DownloadStatus.UPDATING)
                    
                    # Process each job individually
                    for job in jobs:
                        job_folder = self._job_folders.get(job.id)
                        if not job_folder:
                            logger.warning(f"[Job {job.id}] No downloaded folder found, skipping")
                            continue
                        
                        # Find galleries in this specific folder (limit to 10)
                        galleries = await self.stash_client.find_galleries_by_path(job_folder, per_page=10)
                        
                        if not galleries:
                            logger.warning(f"[Job {job.id}] No galleries found in {job_folder}")
                            continue
                        
                        logger.info(f"[Job {job.id}] Found {len(galleries)} gallery(ies):")
                        for idx, gal in enumerate(galleries, 1):
                            gal_title = gal.get("title", "Untitled")
                            gal_path = gal.get("folder", {}).get("path", "No path")
                            logger.info(f"  > {idx}. Gallery {gal['id']}: '{gal_title}' @ {gal_path}")
                        
                        # Match by exact path
                        matched_gallery = None
                        for gallery in galleries:
                            folder_info = gallery.get("folder", {})
                            gallery_folder = folder_info.get("path")
                            
                            if not gallery_folder:
                                continue
                            
                            # Normalize paths for comparison
                            gallery_path_normalized = gallery_folder.replace('\\', '/').rstrip('/')
                            job_path_normalized = job_folder.replace('\\', '/').rstrip('/')
                            
                            if gallery_path_normalized == job_path_normalized:
                                matched_gallery = gallery
                                break
                        
                        if matched_gallery:
                            gallery_title = matched_gallery.get("title", "Untitled")
                            logger.info(f"[Job {job.id}] Matched to gallery {matched_gallery['id']} ('{gallery_title}')")
                            
                            # Load metadata and update
                            metadata = self.downloader.find_gallery_metadata(job_folder)
                            await self._update_gallery_with_metadata(job, matched_gallery, metadata)
                            
                            # Clean up the folder mapping
                            self._job_folders.pop(job.id, None)
                        else:
                            logger.warning(f"[Job {job.id}] No exact path match found in {len(galleries)} galleries")
                    
                    # Mark all jobs as completed
                    for job in jobs:
                        await self.database.update_status(job.id, DownloadStatus.COMPLETED)
                        
                else:
                    logger.warning("Scan did not complete in time")
                    for job in jobs:
                        await self.database.update_status(job.id, DownloadStatus.COMPLETED)
            else:
                logger.error("Failed to trigger scan")
                for job in jobs:
                    await self.database.update_status(job.id, DownloadStatus.COMPLETED)
                    
        except Exception as e:
            logger.error(f"Error processing scan batch: {e}")
            for job in jobs:
                try:
                    await self.database.update_status(job.id, DownloadStatus.COMPLETED)
                except:
                    pass
    
    async def _update_gallery_with_metadata(self, job: DownloadJob, gallery: dict, metadata: dict):
        """Update a Stash gallery with metadata from info.json."""
        try:
            await self.database.update_status(job.id, DownloadStatus.UPDATING)
            
            gallery_title = metadata.get("title") if metadata else None
            gallery_tags = metadata.get("tags", []) if metadata else []
            
            # Get or create tags
            tag_ids = []
            if gallery_tags:
                tag_ids = await self.stash_client.get_or_create_tags(gallery_tags)
            
            # Update gallery with URL, title, and tags
            await self.stash_client.update_gallery_with_tags(
                gallery["id"], 
                job.url,
                title=gallery_title,
                tag_ids=tag_ids if tag_ids else None
            )
            
            tags_msg = f", {len(tag_ids)} tags" if tag_ids else ""
            logger.info(f"[Job {job.id}] Updated gallery {gallery['id']}{tags_msg}")
            
        except Exception as e:
            logger.error(f"Error updating gallery for job {job.id}: {e}")
