"""Stash Integration"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

class StashClient:
    def __init__(self, stash_server_url: str, stash_server_api_key: str):
        if not stash_server_url:
            raise ValueError("Stash server URL is required.")
        
        if not stash_server_api_key:
            raise ValueError("Stash server API key is required for authentication.")
        
        self.stash_server_url = stash_server_url.rstrip("/")  # Remove trailing slash if present
        self.stash_server_api_key = stash_server_api_key
        
        self._tags_cache: dict[str, str] | None = None
        self._tags_lock = asyncio.Lock()
        
        # Scan Tasks Keyed by Folder name
        self._scan_tasks: dict[str, asyncio.Task] = {}
        self._scan_lock = asyncio.Lock()

        self._scan_pending: set[str] = set()
        self._current_scan_batch: asyncio.Task | None = None
        self._batch_lock = asyncio.Lock()

    ### Tasks
    
    ## Request a new file scan for a folder
    async def request_scan(self, folder: str) -> asyncio.Task:
        async with self._batch_lock:
            self._scan_pending.add(folder)

            # Start batch only once per burst window
            if self._current_scan_batch is None or self._current_scan_batch.done():
                self._current_scan_batch = asyncio.create_task(self._flush_scan_batch())

            # Always return the batch task representing "eventual scan completion"
            return self._current_scan_batch

    async def _flush_scan_batch(self):
        await asyncio.sleep(0.5)  # debounce window (prevents spam bursts)

        async with self._batch_lock:
            folders = list(self._scan_pending)
            self._scan_pending.clear()

        if not folders:
            return None

        logger.info(f"Triggering stash scan for {len(folders)} folders")

        job_id = await self._trigger_scan_now(folders)

        if not job_id:
            raise RuntimeError("Failed to trigger stash scan")

        # Wait for completion
        while True:
            job = await self._get_job_status(job_id)

            if job is None:
                # Stash sometimes drops completed jobs from queue
                break

            status = job.get("status", "").lower()
            logger.info(f"Job ({job_id}) status is {status}")
            if status in {"finished", "complete", "completed"}:
                break

            await asyncio.sleep(2)

        logger.info("Stash scan batch completed")
        return True
    
    # Trigger a scan Now
    async def _trigger_scan_now(self, paths_to_scan: Optional[list[str]] = None) -> Optional[str]:
        from .constants import GRAPHQL_METADATA_SCAN
        
        """
        Trigger a scan on the Stash server.

        :param paths_to_scan: Optional list of paths to scan. If None, scans all paths.
        :return: Stash Job ID if successful, None otherwise
        """
        
        logger.info("Scanning db")
        
        # Construct the GraphQL mutation payload
        payload = {
            "operationName": "MetadataScan",
            "variables": {
                "input": {
                    "paths": paths_to_scan or [],
                    "scanGenerateCovers": True,
                    "scanGeneratePhashes": True
                }
            },
            "query": GRAPHQL_METADATA_SCAN
        }
        
        # Perform the GraphQL request
        response = await self.__do_graphql_request(payload)
        job_id = response.get("data", {}).get("metadataScan") if response else None
        
        if job_id is None:
            logger.error("Failed to trigger scan. Stash returned no Job ID.")
        
        return job_id

    # Get the current status of a given stash scan task
    async def _get_job_status(self, stash_job_id: str) -> Optional[dict]:
        from .constants import GRAPHQL_STASH_TASKS_QUERY
        """
        Get the status of a specific stash task by Id
        
        :param stash_job_id: The task ID to check for
        :return Dict containing status, progress etc., or None if no job found
        """
        
        # Construct the GraphQL query payload
        payload = {
            "operationName": "JobQueue",
            "query": GRAPHQL_STASH_TASKS_QUERY
        }
        
        response = await self.__do_graphql_request(payload)
        jobs = response.get("data", {}).get("jobQueue", {})
        
        if jobs is None:
            logger.error(f"Failed to find information for Job Id ({stash_job_id}), it may have been completed")
            jobs = [] # Set to empty array
        
        # Check the stash job list for our specific ask
        for job in jobs:
            if job.get("id") == stash_job_id:
                return job
        
        # Job not found, either completed or removed before check
        return None
    
    ### Scene Methods
    async def search_for_scene(self, filename: str) -> Optional[dict]:
        # Create payload
        from .constants import GRAPHQL_SCENES_QUERY
        payload = {
            "operationName": "FindScenes",
            "query": GRAPHQL_SCENES_QUERY,
            "variables": {
                "filter": {
                        "q": filename,
                        "page": 1,
                        "per_page": 40,
                        "sort": "file_mod_time",
                        "direction": "DESC"
                },
                "scene_filter": {}
            }
        }
        
        response = await self.__do_graphql_request(payload)
        scenes = response.get("data", {}).get("findScenes", {}).get("scenes", [])
        
        for scene in scenes:
            for files in scene.get("files", []):
                if (filename in files.get("path", "")):
                    return scene
        
        return None
    
    async def update_scene_metadata(self, scene_id: str,
                                    tag_ids: Optional[list[str]] = [], 
                                    scene_source_url: Optional[str] = None,
                                    scene_title: Optional[str] = None) -> bool:
        # Create payload
        from .constants import GRAPHQL_UPDATE_SCENE
        payload = {
            "operationName": "SceneUpdate",
            "query": GRAPHQL_UPDATE_SCENE,
            "variables": {
                "input": {
                    "id": scene_id,
                    "tag_ids": tag_ids,
                    "url": scene_source_url,
                    "title": scene_title
                }
            }
        }
        
        from pprint import pprint
        pprint(payload, indent=2)
        
        response = await self.__do_graphql_request(payload)
        if response.get("errors"):
            logger.error(f"Failed to tag image: {response['errors']}")
            return False
        
        logger.info(f"Updated scene {scene_id} with {len(tag_ids)} tag(s)")
        return True
    
    ### Image Methods
    async def search_for_image(self, filename: str) -> Optional[dict]:
        # Create payload
        from .constants import GRAPHQL_IMAGES_QUERY
        payload = {
            "operationName": "FindImages",
            "query": GRAPHQL_IMAGES_QUERY,
            "variables": {
                "filter": {
                    "q": filename,
                    "page": 1,
                    "per_page": 40,
                    "sort": "file_mod_time",
                    "direction": "DESC"
                },
                "image_filter": {}
            }
        }
        
        response = await self.__do_graphql_request(payload)
        images = response.get("data", {}).get("findImages", {}).get("images", [])
        for img in images:
            for vf in img.get("visual_files", []):
                if filename in vf.get("path", ""):
                    logger.info(f"Found image, {img}")
                    return img
                
        return None
    
    async def update_image_metadata(self, image_id: str, 
                                    tag_ids: Optional[list[str]] = [], 
                                    image_source_url: Optional[str] = None, 
                                    image_title: Optional[str] = None,) -> bool:
        logger.info(f"Updating image id ({image_id})")
        
        # Create payload
        from .constants import GRAPHQL_UPDATE_IMAGE
        payload = {
            "operationName": "ImageUpdate",
            "query": GRAPHQL_UPDATE_IMAGE,
            "variables": {
                "input": {
                    "id": image_id,
                    "tag_ids": tag_ids,
                    "url": image_source_url or "",
                    "title": image_title or ""
                }
            }
        }
        
        print(payload)
        response = await self.__do_graphql_request(payload)
        if response.get("errors"):
                logger.error(f"Failed to tag image: {response['errors']}")
                return False
        
        logger.info(f"Updated image {image_id} with {len(tag_ids)} tag(s)")
        return True
    
    ### Gallery Methods
    async def search_for_gallery(self, gallery_path: str) -> dict:
        
        logger.info(f'looking for {gallery_path}')
        
        # Create payload
        from .constants import GRAPHQL_GALLERIES_QUERY
        payload = {
            "operationName": "FindGalleries",
            "query": GRAPHQL_GALLERIES_QUERY,
            "variables": {
                "filter": {
                    "q": "", # Maybe i should use the name for this?
                    "page": 1,
                    "per_page": 10,
                    "sort": "created_at",
                    "direction": "DESC"
                },
                "gallery_filter": {
                    "path": {
                        "value": gallery_path,
                        "modifier": "EQUALS"
                    }
                }
            }
        }
        
        response = await self.__do_graphql_request(payload)
        galleries = response.get("data", {}).get("findGalleries", {}).get("galleries", [])
        
        # log all the results
        for idx, gal in enumerate(galleries, 1):
            gal_title = gal.get("title", "Untitled")
            gal_path = gal.get("folder", {}).get("path", "No path")
            logger.debug(f"  > {idx}. Gallery {gal['id']}: '{gal_title}' @ {gal_path}")
        
         # Match by exact path
        matched_gallery: dict = None
        for gallery in galleries:
            
            folder_info = gallery.get("folder", {})
            gallery_folder = folder_info.get("path")
            
            logger.info(f"found gallery -> {gallery_folder}")
            
            if not gallery_folder:
                continue
            
            # Normalize paths for comparison
            gallery_path_normalized = gallery_folder.replace('\\', '/').rstrip('/')
            job_path_normalized = gallery_path.replace('\\', '/').rstrip('/')
            
            if gallery_path_normalized == job_path_normalized:
                matched_gallery = gallery
                break
        
        if matched_gallery:
            return matched_gallery
        else:
            logger.warning(f"No exact path match found in {len(galleries)} galleries")
            return None
    
    async def update_gallery_metadata(self, gallery_id: str,
                                      tag_ids: Optional[list[str]] = [],
                                      gallery_source_url: Optional[str] = None,
                                      gallery_title: Optional[str] = None) -> bool:
        # Create payload
        from .constants import GRAPHQL_UPDATE_GALLERY
        
        payload = {
            "operationName": "GalleryUpdate",
            "query": GRAPHQL_UPDATE_GALLERY,
            "variables": {
                "input": {
                    "id": gallery_id,
                    "tag_ids": tag_ids or [],
                    "urls": [gallery_source_url] or [],
                    "title": gallery_title or ""
                }
            }
        }
        from pprint import pprint
        pprint(payload)
        response = await self.__do_graphql_request(payload)
        
        return True
    
    ### Tag Methods
    async def get_or_create_tags(self, request_tag_names: list[str]) -> list[str]:
        if not request_tag_names:
            return []
        
        all_tags = await self.__get_all_tags()
        tag_ids = []
        
        print(f"all tags count is {len(all_tags)}")
        
        for tag in request_tag_names:
            key = tag.lower() # Normalise for search
            
            if key in all_tags:
                # tag exists, return its Id
                tag_ids.append(all_tags[key])
            else:
                # tag doesn't exist, create it
                tag_id = await self.create_tag(tag)
                if (tag_id):
                    tag_ids.append(tag_id)
                    all_tags[key] = tag_id
                
        return tag_ids
            
    async def create_tag(self, tag_name: str) -> Optional[str]:
        # Create payload
        from .constants import GRAPHQL_CREATE_TAG
        payload = {
            "operationName": "TagCreate",
            "variables": {
                "input": {
                    "name": tag_name,
                    "aliases": []
                }
            },
            "query": GRAPHQL_CREATE_TAG
        }
        
        response = await self.__do_graphql_request(payload)
        
        if response.get("errors"):
            # An error occurred, tag may already exist
            error_msg = str(response["errors"])
            if "already exist" in error_msg:
                logger.debug(f"Tag '{tag_name}' already exists")
                tag_map = await self.__get_all_tags()
                return tag_map.get(tag_name.lower())
            
            logger.error(f"Failed to create tag: {response['errors']}")
            return None
        
        tag_id = response.get("data", {}).get("tagCreate", {}).get("id")
        
        if tag_id:
            logger.info(f"Added new tag: {tag_name} (Id = {tag_id})")    
            # Invalidate cache on successful creation
            self._tags_cache = None
            
        return tag_id
    
    # private methods
    
    async def __do_graphql_request(self, payload: dict) -> Optional[dict]:
        """
        Perform a GraphQL request to the Stash server.

        :param payload: The GraphQL payload to send
        :return: The response data if successful, None otherwise
        """
        headers = self.__get_headers()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.stash_server_url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error during GraphQL request: {e}")
        
        return None
    
    def __get_headers(self) -> dict[str, str]:
        """
        Get the headers for the Stash API requests.

        :return: Dictionary containing the headers
        """
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ApiKey": self.stash_server_api_key
        }
    
    async def __get_all_tags(self) -> dict[str, str]:
        # Return cached result if available
        if self._tags_cache is not None:
            return self._tags_cache
        
        async with self._tags_lock:
            # Another coroutine may have populated the cache, check again
            if self._tags_cache is not None:
                return self._tags_cache
            
            # Construct the query payload
            from .constants import GRAPHQL_TAGS_QUERY
            payload = {
                "operationName": "FindTags",
                "query": GRAPHQL_TAGS_QUERY
            }
            
            response = await self.__do_graphql_request(payload)
            tags = response.get("data", {}).get("findTags", {}).get("tags", {})
            
            tag_map = {tag["name"].lower(): tag["id"] for tag in tags}
            
            # Save to internal cache
            self._tags_cache = tag_map
            return tag_map