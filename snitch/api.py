"""FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from snitch.media_router.utils.urls import extract_filename_from_url

from . import helpers
from .config import Config, DownloadFolder, FolderType
from .database import Database
from .media_router import DownloadManager
from .models import (CookieSetRequest, DownloadRequest, DownloadResponse,
                     DownloadTestResponse, HistoryResponse, QueueResponse,
                     StashScanRequest, StashUpdateRequest, StashUpdateResponse)
from .stash_manager.stashmananger import StashManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await database.initialize()
    stash_manager.start()
    logger.info("Snitch started on port %s", config.server.port)
    
    yield
    
    stash_manager.stop()
    logger.info("Snitch stopped")

logger = logging.getLogger(__name__)

# Global instances
config: Optional[Config] = None
database: Optional[Database] = None

stash_manager: Optional[StashManager] = None

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

@app.get("/favicon.ico")
async def get_favicon():
    """Serve the favicon."""
    base_dir = helpers.get_base_dir_for_executable()
    favicon_file = base_dir / "static" / "favicon.ico"
    if favicon_file.exists():
        return FileResponse(str(favicon_file))
    else:
        raise HTTPException(status_code=404, detail="Favicon not found")

@app.post("/api/v2/download", response_model=Union[DownloadResponse, DownloadTestResponse])
async def submit_download_v2(
    request: DownloadRequest,
    test_mode: bool = Query(False, description="If true, resolve downloaders without executing downloads."),
    scan_only: bool = Query(False, description="If true, scan selected folders only")
):
    """Unified download endpoint using the new media router."""
    # If a folder override was provided, resolve it once; otherwise we'll select per-item.
    folder_override = None
    if request.folder:
        folder_override = _resolve_folder(request.folder)

    manager = DownloadManager()
    added = 0
    skipped = 0
    duplicates = []
    errors = []
    test_results = []

    for item in request.items:
        try:
            existing = await database.check_existing_download(item.url)
            if existing:
                skipped += 1
                duplicates.append({
                    "url": item.url,
                    "status": existing.status,
                    "downloaded_at": existing.completed_at.isoformat() if existing.completed_at else None,
                })
                logger.info(f"Skipping duplicate URL: {item.url} (status: {existing.status})")
                continue

            downloader_cls, probe_result = await manager.resolve(item.url)

            # choose folder: use override if provided, otherwise pick by downloader preference
            if folder_override:
                target_folder = folder_override
            else:
                # Prefer a folder suggested by the probe (downloaders can set this)
                preferred = getattr(probe_result, "preferred_folder", None) or getattr(downloader_cls, "_preferred_folder_type", None) or FolderType.Gallery

                # find a matching configured folder
                target_folder: DownloadFolder | None = next((f for f in config.download_folders if getattr(f, "type", None) == preferred), None)
                if not target_folder:
                    logger.debug("No configured folder found for preferred type %s, falling back to default", preferred)
                    # fallback to existing default resolution
                    target_folder = _resolve_folder(None)

            if test_mode:
                test_results.append({
                    "url": item.url,
                    "downloader": downloader_cls.name,
                    "reason": probe_result.reason,
                    "folder": target_folder.name,
                })
            else:
                identifier = await downloader_cls.download(item.url, target_folder.path, scan_only)
                                
                # Filename or output directory
                if (scan_only):
                    logger.info(f"Found {identifier}: {target_folder.path}")
                else:
                    logger.info(f"Downloaded {item.url} with {downloader_cls.name}: {probe_result.reason} -> {target_folder.path}")
                    
                added += 1
                
                # Trigger stash import
                logger.info(f"Identifier is {identifier}, located in {target_folder.path} ({target_folder.type})")
                
                source_url = item.page_url or item.url ## Use one or the other
                if target_folder.type == FolderType.Gallery:
                    gallery_folder = target_folder.path # Get the folder galleries are saved in
                    gallery_name = Path(identifier).resolve().name ## Get the name of the gallery
                    gallery_tags = item.tags or helpers.get_tags_from_gallery_json(identifier)
                    asyncio.create_task(stash_manager.import_gallery(identifier, gallery_folder, gallery_tags, source_url, item.title))
                
                elif target_folder.type == FolderType.Images:
                    asyncio.create_task(stash_manager.import_image(identifier, target_folder.path, item.tags, source_url, item.title))
                    
                elif (target_folder.type == FolderType.Scenes):
                    asyncio.create_task(stash_manager.import_scene(identifier, target_folder.path, item.tags, source_url, item.title))
                
        except Exception as exc:
            skipped += 1
            logger.error(f"Failed to process {item.url} via media router: {exc}")
            errors.append({
                "url": item.url,
                "error": str(exc),
            })

    if test_mode:
        return DownloadTestResponse(
            results=test_results,
            duplicates=duplicates,
            errors=errors if errors else None,
        )

    return DownloadResponse(
        added=added,
        skipped=skipped,
        duplicates=duplicates,
        errors=errors if errors else None,
    )

#   TODO: Implement stash update in new code base
#@app.post("/api/stash/update", response_model=StashUpdateResponse)
#async def update_stash_metadata(
#    request: StashUpdateRequest = Body(...),
#    scan_first: bool = False
#):
#    """
#    Update image metadata in Stash (tags, URL) without downloading.
#    Optionally trigger a scan first to ensure the image is indexed.
#    """
#    if not stash_client:
#        raise HTTPException(status_code=400, detail="StashApp integration not enabled")
#
#    # Optionally scan first
#    if scan_first:
#        scan_paths = _get_scan_paths(request.folder)
#        job_id = await stash_client.trigger_scan(paths=scan_paths)
#        if job_id:
#            await stash_client.wait_for_scan_completion(job_id, timeout=300)
#
#    # Extract filename from URL
#    item = request.items[0]  # Assuming single item for update
#    filename = item.url.split("/")[-1].split("?")[0]
#    if not filename:
#        raise HTTPException(status_code=400, detail="Could not extract filename from URL")
#
#    logger.info(f"Updating Stash image metadata for filename: {filename}")
#
#    # Find and update image in Stash
#    try:
#        image = await stash_client.find_image_by_filename(filename)
#        if not image:
#            raise HTTPException(status_code=404, detail=f"Image not found in Stash: {filename}")
#        
#        image_id = image["id"]
#        logger.info(f"Found Stash image ID: {image_id}")
#        
#        tag_ids = await stash_client.get_or_create_tags(item.tags or [])
#        
#        # Update image with tags and url (page_url)
#        success = await stash_client.tag_image(image_id, tag_ids, item.page_url, item.title)
#        if not success:
#            raise HTTPException(status_code=500, detail="Failed to update image in Stash")
#        
#        return StashUpdateResponse(
#            success=True,
#            image_id=image_id,
#            tags=item.tags or [],
#            page_url=item.page_url
#        )
#    except HTTPException:
#        raise
#    except Exception as ex:
#        logger.error(f"Failed to update Stash image: {ex}")
#        raise HTTPException(status_code=500, detail=str(ex))

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
                "path": f.path,
                "type": getattr(f, "type", None),
                "default": f.default
            }
            for f in config.download_folders
        ]
    }

#   TODO: Implement stash scan in new code base
#@app.post("/api/stash/scan")
#async def trigger_stash_scan(request: StashScanRequest = Body(...)):
#    """
#    Manually trigger a StashApp library scan.
#    
#    Args:
#        request: Scan configuration with paths and scan_all flag.
#    """
#    if not stash_client:
#        raise HTTPException(
#            status_code=400,
#            detail="StashApp integration not enabled"
#        )
#    
#    # Determine which paths to scan
#    scan_paths = request.paths
#    if not scan_paths and not request.scan_all:
#        # Default to configured download folders
#        scan_paths = [f.path for f in config.download_folders]
#    
#    stash_job_id = await stash_client.trigger_scan(paths=scan_paths if not request.scan_all else None)
#    
#    if stash_job_id:
#        if request.scan_all:
#            return {"message": "StashApp full scan triggered (all paths)", "job_id": stash_job_id}
#        elif scan_paths:
#            return {"message": f"StashApp selective scan triggered for {len(scan_paths)} path(s)", "job_id": stash_job_id}
#        else:
#            return {"message": "StashApp scan triggered", "job_id": stash_job_id}
#    else:
#        raise HTTPException(
#            status_code=500,
#            detail="Failed to trigger StashApp scan"
#        )

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
    global config, database, stash_manager
    
    config = cfg
    database = Database(config.database.path)
    stash_manager = StashManager(config.stashapp.url, config.stashapp.api_key)
    
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
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename=cfg.logging.file
        )
    except Exception as e:
        logger.error(f"Failed to initialize app: {e}")
        raise
