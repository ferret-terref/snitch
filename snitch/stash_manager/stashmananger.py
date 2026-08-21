""" Stash Scan Manager, queues scan requests so as to not overload the server """

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .stashclient import StashClient

logger = logging.getLogger(__name__)

class ImportRequestType(Enum):
    Scene = 1
    Image = 2
    Gallery = 3
    Tag = 4

class ImportRequestStatus(Enum):
    Pending = 1
    Active = 2
    Completed = 3
    Error = 999

@dataclass
class ImportJob:
    type: ImportRequestType
    query: str  # Filename or path
    folder_path: str # Folder to scan
    tag_names: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None

    status: ImportRequestStatus = ImportRequestStatus.Pending
    future: asyncio.Future = field(default_factory=asyncio.Future)

class StashManager:
    def __init__(self, stash_url, stash_api_key):       
        self.stash_client = StashClient(
            stash_url,
            stash_api_key
        )
        
        self._jobs: asyncio.Queue[ImportJob] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
    
    def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())
    
    def stop(self):
        self._worker_task.cancel()

    async def import_scene(self, 
                           scene_filename: str,
                           folder_path: str,
                           tag_names: Optional[str] = None,
                           source_url: Optional[str] = None,
                           title: Optional[str] = None):
        import_request = ImportJob(ImportRequestType.Scene, scene_filename, folder_path, tag_names, source_url, title)
        await self._jobs.put(import_request)
        
        result = await import_request.future
        return result
        
    async def import_image(self, 
                           image_filename: str,
                           folder_path: str,
                           tag_names: Optional[str] = None,
                           source_url: Optional[str] = None,
                           title: Optional[str] = None):
        import_request = ImportJob(ImportRequestType.Image, image_filename, folder_path, tag_names, source_url, title)
        await self._jobs.put(import_request)        
        
        logger.info(f"Adding {image_filename} to queue")
        result = await import_request.future
        return result
        
    async def import_gallery(self, 
                        gallery_path: str,
                        folder_path: str,
                        tag_names: Optional[str] = None,
                        source_url: Optional[str] = None,
                        title: Optional[str] = None):
        import_request = ImportJob(ImportRequestType.Gallery, gallery_path, folder_path, tag_names, source_url, title)
        await self._jobs.put(import_request) 
        
        result = await import_request.future
        return result
    
    async def _worker_loop(self):        
        while True:
            logger.info("Worker loop start")
            job = await self._jobs.get()
            
            logger.info(F"Starting Job, {job.query}")
            job.status = ImportRequestStatus.Active
            
            try:
                result = await self._handler(job)
                
                if result is True:
                    job.status = ImportRequestStatus.Completed
                    
                job.future.set_result(result)
                
            except Exception as e:
                job.status = ImportRequestStatus.Error
                job.future.set_exception(e)

            finally:
                self._jobs.task_done()
                
    # Handlers
    
    async def _handler(self, job: ImportJob):
        if job.type == ImportRequestType.Scene:
            return await self._scene_handler(job)

        elif job.type == ImportRequestType.Image:
            return await self._image_handler(job)

        elif job.type == ImportRequestType.Gallery:
            return await self._gallery_handler(job)

        else:
            raise ValueError(f"Unknown job type: {job.type}")
    
    async def _scene_handler(self, job: ImportJob):
        scene = await self._resolve_with_scan(
            search_fn=self.stash_client.search_for_scene,
            query=job.query,
            folder_path=job.folder_path
        )

        if not scene:
            raise Exception(f"Scene not found: {job.query}")

        scene_id = scene["id"]

        tag_ids = await self.stash_client.get_or_create_tags(job.tag_names)

        await self.stash_client.update_scene_metadata(
            scene_id,
            tag_ids,
            job.source_url,
            job.title
        )

        return True
    
    async def _image_handler(self, job: ImportJob):
        image = await self._resolve_with_scan(
            search_fn=self.stash_client.search_for_image,
            query=job.query,
            folder_path=job.folder_path
        )

        if not image:
            raise Exception(f"Image not found: {job.query}")

        image_id = image["id"]

        logger.info(f"Creating tags, {job.tag_names}")
        tag_ids = await self.stash_client.get_or_create_tags(job.tag_names)
        
        print(f"Tag count is {len(tag_ids)}")

        return await self.stash_client.update_image_metadata(
            image_id,
            tag_ids,
            job.source_url,
            job.title
        )
    
    async def _gallery_handler(self, job: ImportJob):
        gallery = await self._resolve_with_scan(
            search_fn=self.stash_client.search_for_gallery,
            query=job.query,
            folder_path=job.folder_path
        )

        if not gallery:
            raise Exception(f"Gallery not found: {job.query}")

        gallery_id = gallery["id"]

        tag_ids = await self.stash_client.get_or_create_tags(job.tag_names)

        await self.stash_client.update_gallery_metadata(
            gallery_id,
            tag_ids,
            job.source_url,
            job.title
        )

        return True
    
    async def _resolve_with_scan(
        self,
        *,
        search_fn,
        query: str,
        folder_path: str | None = None
    ):
        # 1. try direct lookup
        entity = await search_fn(query)
        if entity:
            return entity

        # 2. trigger scan (for ALL types now)
        if folder_path:
            scan_task = await self.stash_client.request_scan(folder_path)
            await scan_task

            # 3. retry once after scan
            entity = await search_fn(query)
            if entity:
                return entity

        return None
