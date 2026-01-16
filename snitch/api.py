"""FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import helpers
from .config import Config, DownloadFolder
from .database import Database
from .downloader import GalleryDownloader
from .models import (CookieSetRequest, DownloadRequest, DownloadResponse,
                     HistoryResponse, QueueResponse, StashScanRequest,
                     StashUpdateRequest, StashUpdateResponse)
from .queue_manager import QueueManager
from .stash import StashClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await database.initialize()
    await queue_manager.start()
    logger.info("Snitch started on port %s", config.server.port)
    yield
    # Shutdown
    await queue_manager.stop()
    logger.info("Snitch stopped")

logger = logging.getLogger(__name__)

# Global instances
config: Optional[Config] = None
database: Optional[Database] = None
downloader: Optional[GalleryDownloader] = None
queue_manager: Optional[QueueManager] = None
stash_client: Optional[StashClient] = None

app = FastAPI(
    title="Snitch",
    description="An *arr-style application for downloading image galleries",
    version="0.1.0",
    lifespan=lifespan
)

# Enable CORS for browser extensions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Serve the web UI."""
    base_dir = helpers.get_base_dir_for_executable()
    index_file = base_dir / "static" / "index.html"
    logger.info(f"[Snitch] Checking for index.html at: {index_file} (exists: {index_file.exists()})")
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        logger.warning(f"[Snitch] index.html not found at: {index_file}")
        return {
            "name": "Snitch",
            "version": "0.1.0",
            "status": "running",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        }

@app.post("/api/download", response_model=DownloadResponse)
async def submit_download(request: DownloadRequest):
    """
    Unified download endpoint supporting:
    - Gallery URLs (gallery-dl)
    - Single image URLs (direct download)
    - Bulk operations
    """
    # Determine which folder to use
    folder = _resolve_folder(request.folder)
    
    # Add jobs to queue
    added = 0
    skipped = 0
    duplicates = []
    errors = []
    
    for item in request.items:
        try:
            # Detect if this is a direct image URL or gallery URL
            if helpers.is_direct_image_url(item.url):
                # Handle as single image download
                result = await _handle_single_image(
                    url=item.url,
                    folder=folder,
                    tags=item.tags,
                    page_url=item.page_url
                )
                if result["success"]:
                    added += 1
                    logger.info(f"Downloaded image: {item.url}")
                else:
                    skipped += 1
                    errors.append({
                        "url": item.url,
                        "error": result.get("error", "Unknown error")
                    })
            else:
                # Handle as gallery download
                existing = await database.check_existing_download(item.url)
                if existing:
                    skipped += 1
                    duplicates.append({
                        "url": item.url,
                        "status": existing.status,
                        "downloaded_at": existing.completed_at.isoformat() if existing.completed_at else None
                    })
                    logger.info(f"Skipping duplicate URL: {item.url} (status: {existing.status})")
                else:
                    job_id = await database.add_download(item.url, folder.name, folder.path)
                    added += 1
                    logger.info(f"Added download job {job_id} for {item.url}")
        except Exception as e:
            logger.error(f"Failed to process {item.url}: {e}")
            errors.append({
                "url": item.url,
                "error": str(e)
            })
    
    return DownloadResponse(
        added=added,
        skipped=skipped,
        duplicates=duplicates,
        errors=errors if errors else None
    )

@app.post("/api/stash/update", response_model=StashUpdateResponse)
async def update_stash_metadata(
    request: StashUpdateRequest = Body(...),
    scan_first: bool = False
):
    """
    Update image metadata in Stash (tags, URL) without downloading.
    Optionally trigger a scan first to ensure the image is indexed.
    """
    if not stash_client:
        raise HTTPException(status_code=400, detail="StashApp integration not enabled")

    # Optionally scan first
    if scan_first:
        scan_paths = _get_scan_paths(request.folder)
        job_id = await stash_client.trigger_scan(paths=scan_paths)
        if job_id:
            await stash_client.wait_for_scan_completion(job_id, timeout=300)

    # Extract filename from URL
    filename = request.url.split("/")[-1].split("?")[0]
    if not filename:
        raise HTTPException(status_code=400, detail="Could not extract filename from URL")

    logger.info(f"Updating Stash image metadata for filename: {filename}")

    # Find and update image in Stash
    try:
        image = await stash_client.find_image_by_filename(filename)
        if not image:
            raise HTTPException(status_code=404, detail=f"Image not found in Stash: {filename}")
        
        image_id = image["id"]
        logger.info(f"Found Stash image ID: {image_id}")
        
        tag_ids = await stash_client.get_or_create_tags(request.tags or [])
        
        # Update image with tags and url (page_url)
        success = await stash_client.tag_image(image_id, tag_ids, request.page_url)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update image in Stash")
        
        return StashUpdateResponse(
            success=True,
            image_id=image_id,
            tags=request.tags or [],
            page_url=request.page_url
        )
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Failed to update Stash image: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/api/queue", response_model=QueueResponse)
async def get_queue():
    """Get current download queue status."""
    pending = await database.get_pending_jobs()
    downloading = await database.get_downloading_jobs()
    awaiting_scan = await database.get_awaiting_scan_jobs()
    scanning = await database.get_scanning_jobs()
    updating = await database.get_updating_jobs()
    
    # Combine all active jobs
    active_jobs = downloading + awaiting_scan + scanning + updating
    
    return QueueResponse(
        pending=pending,
        downloading=active_jobs,
        total=len(pending) + len(active_jobs)
    )

@app.get("/api/history", response_model=HistoryResponse)
async def get_history(limit: int = 50, offset: int = 0):
    """Get download history."""
    jobs = await database.get_history(limit, offset)
    
    return HistoryResponse(
        jobs=jobs,
        total=len(jobs),
        limit=limit,
        offset=offset
    )

@app.delete("/api/history/{job_id}")
async def delete_history_item(job_id: int):
    """Delete a history item."""
    deleted = await database.delete_job(job_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {"success": True, "message": "Job deleted"}

@app.delete("/api/history")
async def clear_history():
    """Clear all history items."""
    deleted_count = await database.clear_history()
    
    return {"success": True, "message": f"Deleted {deleted_count} job(s)"}

@app.post("/api/queue/fail-all")
async def fail_all_pending():
    """Force all non-completed jobs to failed status."""
    from .models import DownloadStatus

    # Get all non-completed jobs
    pending = await database.get_pending_jobs()
    downloading = await database.get_downloading_jobs()
    awaiting_scan = await database.get_awaiting_scan_jobs()
    scanning = await database.get_scanning_jobs()
    updating = await database.get_updating_jobs()
    
    all_active = pending + downloading + awaiting_scan + scanning + updating
    
    # Mark all as failed
    for job in all_active:
        await database.update_status(job.id, DownloadStatus.FAILED, "Manually failed via API")
    
    return {"success": True, "message": f"Failed {len(all_active)} job(s)"}

@app.get("/api/folders")
async def get_folders():
    """Get configured download folders."""
    return {
        "folders": [
            {
                "name": f.name,
                "path": f.path,
                "default": f.default
            }
            for f in config.download_folders
        ]
    }

@app.post("/api/stash/scan")
async def trigger_stash_scan(request: StashScanRequest = Body(...)):
    """
    Manually trigger a StashApp library scan.
    
    Args:
        request: Scan configuration with paths and scan_all flag.
    """
    if not stash_client:
        raise HTTPException(
            status_code=400,
            detail="StashApp integration not enabled"
        )
    
    # Determine which paths to scan
    scan_paths = request.paths
    if not scan_paths and not request.scan_all:
        # Default to configured download folders
        scan_paths = [f.path for f in config.download_folders]
    
    stash_job_id = await stash_client.trigger_scan(paths=scan_paths if not request.scan_all else None)
    
    if stash_job_id:
        if request.scan_all:
            return {"message": "StashApp full scan triggered (all paths)", "job_id": stash_job_id}
        elif scan_paths:
            return {"message": f"StashApp selective scan triggered for {len(scan_paths)} path(s)", "job_id": stash_job_id}
        else:
            return {"message": "StashApp scan triggered", "job_id": stash_job_id}
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to trigger StashApp scan"
        )

# ===== Helper Functions =====

def _resolve_folder(folder_name: Optional[str]) -> DownloadFolder:
    """Resolve folder name to DownloadFolder object."""
    if folder_name:
        folder = next(
            (f for f in config.download_folders if f.name == folder_name),
            None
        )
        if not folder:
            raise HTTPException(status_code=400, detail=f"Unknown folder: {folder_name}")
        return folder
    
    # Use default folder
    folder = next((f for f in config.download_folders if f.default), None)
    if not folder:
        if config.download_folders:
            folder = config.download_folders[0]
        else:
            raise HTTPException(status_code=500, detail="No download folders configured")
    return folder

async def _handle_single_image(
    url: str,
    folder: DownloadFolder,
    tags: Optional[list[str]] = None,
    page_url: Optional[str] = None
) -> dict:
    """Handle single image download."""
    from .downloader import download_image_direct
    
    try:
        result = await download_image_direct(
            url=url,
            folder=folder.path,
            tags=tags,
            page_url=page_url,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Single image download failed: {e}")
        return {"success": False, "error": str(e)}


def _get_scan_paths(folder_name: Optional[str]) -> Optional[list[str]]:
    """Get scan paths for Stash based on folder name."""
    if folder_name:
        folder_obj = next((f for f in config.download_folders if f.name == folder_name), None)
        if folder_obj:
            return [folder_obj.path]
        return [folder_name]  # Treat as direct path
    # Default: all download folders
    return [f.path for f in config.download_folders]


# ===== Cookie API endpoints =====

@app.get("/api/cookies")
async def get_cookies(domain: str = Query(..., description="Domain to fetch cookies for")):
    """Get all cookies for a domain as a dict."""
    cookies = await database.get_cookies_for_domain(domain)
    return {"domain": domain, "cookies": cookies}

@app.post("/api/cookies", status_code=status.HTTP_204_NO_CONTENT)
async def set_cookie(req: CookieSetRequest):
    """Set or update a cookie for a domain."""
    await database.set_cookie(req.domain, req.cookie_name, req.cookie_value)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

# New: Delete a cookie for a domain and name
@app.delete("/api/cookies", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cookie(domain: str = Query(...), cookie_name: str = Query(...)):
    """Delete a cookie for a domain and name."""
    deleted = await database.delete_cookie(domain, cookie_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

def create_app(cfg: Config) -> FastAPI:
    """Create and configure the FastAPI app."""
    global config, database, downloader, queue_manager, stash_client
    
    config = cfg
    database = Database(config.database.path)
    downloader = GalleryDownloader(config.gallery_dl)
    
    if config.stashapp.enabled:
        stash_client = StashClient(config.stashapp.url, config.stashapp.api_key)
    
    queue_manager = QueueManager(
        database, 
        downloader, 
        stash_client,
        max_concurrent=config.queue.max_concurrent_downloads,
        scan_batch_size=config.queue.scan_batch_size,
        scan_batch_timeout=config.queue.scan_batch_timeout
    )
    
    return app

# Initialize the app when module is loaded
if config is None:
    try:
        # Load config and initialize app
        from .config import load_config
        cfg = load_config()
        create_app(cfg)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    except Exception as e:
        logger.error(f"Failed to initialize app: {e}")
        raise
