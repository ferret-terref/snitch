from fastapi import Body, FastAPI, HTTPException, Query, Request, status

"""FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# New: Single image download endpoint
from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config, DownloadFolder
from .database import Database
from .downloader import GalleryDownloader
from .models import (BulkImageDownloadRequest, CookieSetRequest, DownloadJob,
                     DownloadRequest, DownloadResponse, HistoryResponse,
                     QueueResponse, SingleImageDownloadRequest)
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Serve the web UI."""
    import sys
    if getattr(sys, 'frozen', False):
        # Running as a bundled EXE
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent.parent
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

@app.post("/api/download")
async def submit_download(request: DownloadRequest):
    """Submit URL(s) for download."""
    # Determine which folder to use
    if request.folder:
        folder = next(
            (f for f in config.download_folders if f.name == request.folder),
            None
        )
        if not folder:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown folder: {request.folder}"
            )
    else:
        # Use default folder
        folder = next(
            (f for f in config.download_folders if f.default),
            None
        )
        if not folder:
            if config.download_folders:
                folder = config.download_folders[0]
            else:
                raise HTTPException(
                    status_code=500,
                    detail="No download folders configured"
                )
    
    # Add jobs to queue
    added = 0
    skipped = 0
    duplicates = []
    
    for item in request.items:
        # Check if already exists
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
    
    return DownloadResponse(
        added=added,
        skipped=skipped,
        duplicates=duplicates
    )

@app.post("/api/image/download")
async def download_single_image(request: SingleImageDownloadRequest = Body(...)):
    """Download a single image from a direct URL, with optional tags."""
    from .downloader import download_image_direct

    # Support both folder name and direct path
    folder_path = None
    if request.folder:
        folder_obj = next((f for f in config.download_folders if f.name == request.folder), None)
        if folder_obj:
            folder_path = folder_obj.path
        else:
            folder_path = request.folder  # treat as direct path
    else:
        # Use default folder
        folder_obj = next((f for f in config.download_folders if f.default), None)
        if not folder_obj:
            if config.download_folders:
                folder_obj = config.download_folders[0]
            else:
                raise HTTPException(status_code=500, detail="No download folders configured")
        folder_path = folder_obj.path

    try:
        result = await download_image_direct(
            url=request.url,
            folder=folder_path,
            tags=request.tags,
            page_url=request.page_url,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Single image download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from typing import Annotated

# New: allow triggering a Stash scan before lookup
from fastapi import Query


@app.post("/api/image/stash-update")
async def update_stash_image_metadata(
    request: SingleImageDownloadRequest = Body(...),
    scan_first: bool = False
):
    """Update an image in Stash with tags and url, given a SingleImageDownloadRequest (no download). Optionally trigger a Stash scan first."""
    print(f"Received Stash image update request: {request}, scan_first={scan_first}")

    import re
    from pathlib import Path

    from .tagging import StashTagger

    if not stash_client:
        raise HTTPException(status_code=400, detail="StashApp integration not enabled")

    # Optionally trigger a scan
    if scan_first:
        # Scan only the relevant folder if possible
        scan_paths = None
        if request.folder:
            folder_obj = next((f for f in config.download_folders if f.name == request.folder), None)
            if folder_obj:
                scan_paths = [folder_obj.path]
            else:
                scan_paths = [request.folder]
        else:
            # Default: scan all download folders
            scan_paths = [f.path for f in config.download_folders]
        job_id = await stash_client.trigger_scan(paths=scan_paths)
        if job_id:
            await stash_client.wait_for_scan_completion(job_id, timeout=300)

    # Extract filename from URL (same as download_image_direct)
    filename = request.url.split("/")[-1].split("?")[0]
    if not filename:
        raise HTTPException(status_code=400, detail="Could not extract filename from URL")

    print(f"Updating Stash image metadata for filename: {filename}")

    # Ensure tags exist and update image in Stash
    try:
        image = await stash_client.find_image_by_filename(filename)
        
        if not image:
            raise HTTPException(status_code=404, detail=f"Image not found in Stash for filename: {filename}")
        
        print(f"Found Stash image: {image}")
        
        image_id = image["id"]
        
        print(f"Preparing to update Stash image ID: {image_id} with tags")
        tag_ids = await stash_client.get_or_create_tags(request.tags or [])
        
        # Update image with tags and url (page_url)
        success = await stash_client.tag_image(image_id, tag_ids, request.page_url)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update image in Stash")
        return {"success": True, "image_id": image_id, "tags": request.tags or [], "page_url": request.page_url}
    except HTTPException as httpEx:
        logger.error(f"Failed to update Stash image: {httpEx}")
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
async def trigger_stash_scan(paths: Optional[list[str]] = None, scan_all: bool = False):
    """
    Manually trigger a StashApp library scan.
    
    Args:
        paths: Optional list of specific paths to scan.
        scan_all: If True, scans ALL paths in Stash. If False and no paths provided, scans configured download folders.
    """
    if not stash_client:
        raise HTTPException(
            status_code=400,
            detail="StashApp integration not enabled"
        )
    
    # Determine which paths to scan
    scan_paths = paths
    if not scan_paths and not scan_all:
        # Default to configured download folders
        scan_paths = [f.path for f in config.download_folders]
    
    stash_job_id = await stash_client.trigger_scan(paths=scan_paths if not scan_all else None)
    
    if stash_job_id:
        if scan_all:
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

# --- Cookie API endpoints ---
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
