"""FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# New: Single image download endpoint
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Config, DownloadFolder
from .database import Database
from .downloader import GalleryDownloader
from .models import (BulkImageDownloadRequest, DownloadJob, DownloadRequest,
                     DownloadResponse, HistoryResponse, QueueResponse,
                     SingleImageDownloadRequest)
from .queue_manager import QueueManager
from .stash import StashClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await database.initialize()
    await queue_manager.start()
    logger.info("Snitch started")
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

# Place the endpoint after app is created
@app.post("/api/image/download")
async def download_single_image(request: SingleImageDownloadRequest = Body(...)):
    """Download a single image from a direct URL, with optional tags."""
    from .downloader import download_image_direct
    try:
        result = await download_image_direct(
            url=request.url,
            folder=request.folder,
            tags=request.tags
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Single image download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"
    
    if index_file.exists():
        return FileResponse(index_file)
    else:
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
    
    for url in request.urls:
        # Check if already exists
        existing = await database.check_existing_download(url)
        if existing:
            skipped += 1
            duplicates.append({
                "url": url,
                "status": existing.status,
                "downloaded_at": existing.completed_at.isoformat() if existing.completed_at else None
            })
            logger.info(f"Skipping duplicate URL: {url} (status: {existing.status})")
        else:
            job_id = await database.add_download(url, folder.name, folder.path)
            added += 1
            logger.info(f"Added download job {job_id} for {url}")
    
    return DownloadResponse(
        added=added,
        skipped=skipped,
        duplicates=duplicates
    )


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
