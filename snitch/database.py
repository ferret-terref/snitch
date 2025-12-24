"""Database operations."""

import logging
from datetime import datetime
from typing import Optional

import aiosqlite

from .models import DownloadJob, DownloadStatus

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def initialize(self):
        """Create database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    gallery_path TEXT,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON downloads(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON downloads(created_at DESC)
            """)
            
            # Migration: Add gallery_path column if it doesn't exist
            try:
                await db.execute("SELECT gallery_path FROM downloads LIMIT 1")
            except:
                logger.info("Adding gallery_path column to existing database")
                await db.execute("ALTER TABLE downloads ADD COLUMN gallery_path TEXT")
            
            await db.commit()
    
    async def check_existing_download(self, url: str) -> Optional[DownloadJob]:
        """Check if a URL has already been downloaded."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM downloads WHERE url = ? ORDER BY created_at DESC LIMIT 1",
                (url,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_job(row) if row else None
    
    async def add_download(
        self, url: str, folder_name: str, folder_path: str
    ) -> int:
        """Add a new download to the queue."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO downloads 
                   (url, folder_name, folder_path, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (url, folder_name, folder_path, DownloadStatus.PENDING, datetime.now())
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_pending_jobs(self) -> list[DownloadJob]:
        """Get all pending download jobs."""
        return await self._get_jobs_by_status(DownloadStatus.PENDING)
    
    async def get_downloading_jobs(self) -> list[DownloadJob]:
        """Get all currently downloading jobs."""
        return await self._get_jobs_by_status(DownloadStatus.DOWNLOADING)
    
    async def get_awaiting_scan_jobs(self) -> list[DownloadJob]:
        """Get all jobs awaiting scan."""
        return await self._get_jobs_by_status(DownloadStatus.AWAITING_SCAN)
    
    async def get_scanning_jobs(self) -> list[DownloadJob]:
        """Get all currently scanning jobs."""
        return await self._get_jobs_by_status(DownloadStatus.SCANNING)
    
    async def get_updating_jobs(self) -> list[DownloadJob]:
        """Get all currently updating jobs."""
        return await self._get_jobs_by_status(DownloadStatus.UPDATING)
    
    async def get_history(self, limit: int = 50, offset: int = 0) -> list[DownloadJob]:
        """Get download history."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM downloads 
                   WHERE status IN (?, ?)
                   ORDER BY created_at DESC 
                   LIMIT ? OFFSET ?""",
                (DownloadStatus.COMPLETED, DownloadStatus.FAILED, limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_job(row) for row in rows]
    
    async def delete_job(self, job_id: int) -> bool:
        """Delete a job from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM downloads WHERE id = ?",
                (job_id,)
            )
            await db.commit()
            return cursor.rowcount > 0
    
    async def clear_history(self) -> int:
        """Delete all completed and failed jobs."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM downloads WHERE status IN (?, ?)",
                (DownloadStatus.COMPLETED, DownloadStatus.FAILED)
            )
            await db.commit()
            return cursor.rowcount
    
    async def update_gallery_path(self, job_id: int, gallery_path: str):
        """Update the gallery_path for a job."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE downloads SET gallery_path = ? WHERE id = ?",
                (gallery_path, job_id)
            )
            await db.commit()
    
    async def update_status(
        self,
        job_id: int,
        status: DownloadStatus,
        error_message: Optional[str] = None
    ):
        """Update job status."""
        now = datetime.now()
        
        if status == DownloadStatus.DOWNLOADING:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE downloads SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, job_id)
                )
                await db.commit()
        elif status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """UPDATE downloads 
                       SET status = ?, completed_at = ?, error_message = ? 
                       WHERE id = ?""",
                    (status, now, error_message, job_id)
                )
                await db.commit()
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE downloads SET status = ? WHERE id = ?",
                    (status, job_id)
                )
                await db.commit()
    
    async def _get_jobs_by_status(self, status: DownloadStatus) -> list[DownloadJob]:
        """Get jobs by status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM downloads WHERE status = ? ORDER BY created_at ASC",
                (status,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_job(row) for row in rows]
    
    def _row_to_job(self, row: aiosqlite.Row) -> DownloadJob:
        """Convert database row to DownloadJob."""
        return DownloadJob(
            id=row["id"],
            url=row["url"],
            folder_name=row["folder_name"],
            folder_path=row["folder_path"],
            gallery_path=row["gallery_path"] if row["gallery_path"] else "",
            status=DownloadStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"]
        )
