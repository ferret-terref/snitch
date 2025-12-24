"""StashApp integration."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class StashClient:
    def __init__(self, url: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.api_key = api_key
    
    async def trigger_scan(self, paths: Optional[list[str]] = None) -> Optional[str]:
        """
        Trigger a selective library scan in StashApp.
        
        Args:
            paths: List of paths to scan. If None, scans all configured paths.
            
        Returns:
            Job ID if successful, None otherwise
        """
        mutation = """
        mutation MetadataScan($input: ScanMetadataInput!) {
            metadataScan(input: $input)
        }
        """
        
        # Build scan input
        scan_input = {
            "scanGenerateClipPreviews": True,
            "scanGenerateCovers": True,
            "scanGenerateImagePreviews": False,
            "scanGeneratePhashes": True,
            "scanGeneratePreviews": True,
            "scanGenerateSprites": True,
            "scanGenerateThumbnails": False,
        }
        
        # Add paths if provided
        if paths:
            scan_input["paths"] = paths
        
        payload = {
            "operationName": "MetadataScan",
            "variables": {
                "input": scan_input
            },
            "query": mutation
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                job_id = data.get("data", {}).get("metadataScan")
                
                if job_id:
                    logger.info(f"Triggered Stash scan (Job ID: {job_id})" + 
                              (f" for {len(paths)} path(s)" if paths else " (full scan)"))
                    return job_id
                else:
                    logger.error("Scan triggered but no job ID returned")
                    return None
        except Exception as e:
            logger.error(f"Failed to trigger StashApp scan: {e}")
            return None
    
    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get the status of a specific job by ID.
        
        Args:
            job_id: The job ID to query
            
        Returns:
            Job dict with status, progress, etc., or None if not found
        """
        query = """
        query JobQueue {
            jobQueue {
                id
                status
                subTasks
                description
                progress
                startTime
                endTime
                addTime
                error
            }
        }
        """
        
        payload = {
            "operationName": "JobQueue",
            "query": query
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                jobs = data.get("data", {}).get("jobQueue", [])
                if jobs is None:
                    jobs = []
                
                # Find the specific job by ID
                for job in jobs:
                    if job.get("id") == job_id:
                        return job
                
                # Job not found in queue - might have completed and been removed
                return None
                
        except Exception as e:
            logger.error(f"Failed to get job status: {e}", exc_info=True)
            return None
    
    async def wait_for_scan_completion(self, stash_job_id: Optional[str] = None, timeout: int = 30) -> bool:
        """
        Wait for a scan job to complete.
        
        Args:
            job_id: Specific job ID to wait for. If None, waits for any scan job.
            timeout: Maximum seconds to wait
            
        Returns:
            True if scan completed successfully, False if timeout or error
        """
        import asyncio
        start_time = asyncio.get_event_loop().time()
        
        # If we have a job ID, use the more reliable job status polling
        if stash_job_id:
            try:
                job_seen = False
                while True:
                    job = await self.get_job_status(stash_job_id)
                    
                    if job:
                        job_seen = True
                        status = job.get("status")
                        
                        if status == "FINISHED":
                            logger.info(f"Scan job {stash_job_id} completed successfully")
                            return True
                        elif status == "CANCELLED" or job.get("error"):
                            logger.error(f"Scan job {stash_job_id} failed: {job.get('error', 'cancelled')}")
                            return False
                        # Status is READY, RUNNING, etc. - continue waiting
                    else:
                        # Job not in queue
                        if job_seen:
                            # We saw it before, now it's gone - it completed
                            logger.info(f"Scan job {stash_job_id} completed (removed from queue)")
                            return True
                        # Otherwise, job hasn't appeared yet - keep waiting
                    
                    # Check timeout
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        logger.warning(f"Scan wait timeout after {timeout}s for job {stash_job_id}")
                        return False
                    
                    # Wait before checking again
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"Failed to check job {stash_job_id} status: {e}")
                return False
        
        # Fallback to old method if no job ID
        else:
            query = """
            query JobQueue {
                jobQueue {
                    id
                    status
                    description
                }
            }
            """
            
            payload = {
                "operationName": "JobQueue",
                "query": query
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            if self.api_key:
                headers["ApiKey"] = self.api_key
            
            try:
                while True:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.url}/graphql",
                            json=payload,
                            headers=headers,
                            timeout=10.0
                        )
                        response.raise_for_status()
                        data = response.json()
                        
                        jobs = data.get("data", {}).get("jobQueue")
                        if jobs is None:
                            jobs = []
                        
                        # Check if there are any scan jobs running
                        scan_jobs = [j for j in jobs if "scan" in j.get("description", "").lower() 
                                     and j.get("status") in ["RUNNING", "READY"]]
                        
                        if not scan_jobs:
                            logger.info("Scan completed")
                            return True
                        
                        # Check timeout
                        if asyncio.get_event_loop().time() - start_time > timeout:
                            logger.warning(f"Scan wait timeout after {timeout}s")
                            return False
                        
                        # Wait before checking again
                        await asyncio.sleep(3)
                        
            except Exception as e:
                logger.error(f"Failed to check scan status: {e}")
                return False
    
    async def find_galleries_by_path(self, path: str, per_page: int = -1) -> list[dict]:
        """
        Find galleries in Stash by folder path.
        
        Args:
            path: The folder path to search for
            per_page: Number of results to return (-1 for all, default)
            
        Returns:
            List of gallery dicts with id, path, title, urls
        """
        query = """
        query FindGalleries($filter: FindFilterType, $gallery_filter: GalleryFilterType) {
            findGalleries(gallery_filter: $gallery_filter, filter: $filter) {
                count
                galleries {
                    id
                    title
                    urls
                    folder {
                        id
                        path
                    }
                }
            }
        }
        """
        
        # Convert forward slashes to backslashes for Windows paths
        search_path = path.replace("/", "\\")
        
        payload = {
            "operationName": "FindGalleries",
            "variables": {
                "filter": {
                    "q": "",
                    "page": 1,
                    "per_page": per_page,
                    "sort": "created_at",
                    "direction": "DESC"
                },
                "gallery_filter": {
                    "path": {
                        "value": search_path,
                        "modifier": "EQUALS"
                    }
                }
            },
            "query": query
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                galleries = data.get("data", {}).get("findGalleries", {}).get("galleries", [])
                return galleries
        except Exception as e:
            logger.error(f"Failed to find galleries by path: {e}")
            return []
    
    async def update_gallery_url(self, gallery_id: str, url: str, title: str = None) -> bool:
        """
        Update a gallery's URL and optionally title in Stash.
        
        Args:
            gallery_id: The Stash gallery ID
            url: The URL to set
            title: Optional title to set
            
        Returns:
            True if successful
        """
        mutation = """
        mutation GalleryUpdate($input: GalleryUpdateInput!) {
            galleryUpdate(input: $input) {
                id
                urls
                title
            }
        }
        """
        
        update_input = {
            "id": gallery_id,
            "urls": [url]
        }
        
        if title:
            update_input["title"] = title
        
        payload = {
            "operationName": "GalleryUpdate",
            "variables": {
                "input": update_input
            },
            "query": mutation
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"Updated gallery {gallery_id} with URL: {url}")
                return True
        except Exception as e:
            logger.error(f"Failed to update gallery URL: {e}")
            return False
    
    async def get_all_tags(self) -> dict[str, str]:
        """
        Fetch all tags from Stash.
        
        Returns:
            Dictionary mapping tag name (lowercase) to tag ID
        """
        query = """
        query FindTags {
            findTags(
                filter: { q: "", page: 1, per_page: 10000, sort: "name", direction: ASC }
                tag_filter: {}
            ) {
                tags { id name }
            }
        }
        """
        
        payload = {
            "operationName": "FindTags",
            "query": query
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                tags = data.get("data", {}).get("findTags", {}).get("tags", [])
                tag_map = {tag["name"].lower(): tag["id"] for tag in tags}
                logger.info(f"Fetched {len(tag_map)} tags from Stash")
                return tag_map
                
        except Exception as e:
            logger.error(f"Failed to fetch tags: {e}")
            return {}
    
    async def create_tag(self, name: str) -> Optional[str]:
        """
        Create a new tag in Stash.
        
        Args:
            name: Tag name
            
        Returns:
            Tag ID if successful, None otherwise
        """
        mutation = """
        mutation TagCreate($input: TagCreateInput!) {
            tagCreate(input: $input) {
                id
                name
            }
        }
        """
        
        payload = {
            "operationName": "TagCreate",
            "variables": {
                "input": {
                    "name": name,
                    "aliases": [],
                    "ignore_auto_tag": False
                }
            },
            "query": mutation
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("errors"):
                    # Check if tag already exists
                    error_msg = str(data["errors"])
                    if "already exists" in error_msg:
                        logger.debug(f"Tag '{name}' already exists, fetching ID")
                        tag_map = await self.get_all_tags()
                        return tag_map.get(name.lower())
                    logger.error(f"Failed to create tag: {data['errors']}")
                    return None
                
                tag_id = data.get("data", {}).get("tagCreate", {}).get("id")
                if tag_id:
                    logger.info(f"Created tag: {name} (ID: {tag_id})")
                return tag_id
                
        except Exception as e:
            logger.error(f"Failed to create tag '{name}': {e}")
            return None
    
    async def get_or_create_tags(self, tag_names: list[str]) -> list[str]:
        """
        Get or create multiple tags, returning their IDs.
        
        Args:
            tag_names: List of tag names
            
        Returns:
            List of tag IDs
        """
        if not tag_names:
            return []
        
        # Fetch all existing tags
        tag_map = await self.get_all_tags()
        tag_ids = []
        
        for tag_name in tag_names:
            key = tag_name.lower()
            
            # Check if tag exists
            if key in tag_map:
                tag_ids.append(tag_map[key])
            else:
                # Create new tag
                tag_id = await self.create_tag(tag_name)
                if tag_id:
                    tag_ids.append(tag_id)
                    tag_map[key] = tag_id
        
        return tag_ids
    
    async def update_gallery_with_tags(
        self,
        gallery_id: str,
        url: str,
        title: Optional[str] = None,
        tag_ids: Optional[list[str]] = None
    ) -> bool:
        """
        Update a gallery with URL, title, and tags.
        
        Args:
            gallery_id: Stash gallery ID
            url: Gallery URL
            title: Optional title to set
            tag_ids: Optional list of tag IDs
            
        Returns:
            True if successful
        """
        mutation = """
        mutation GalleryUpdate($input: GalleryUpdateInput!) {
            galleryUpdate(input: $input) {
                id
                urls
                title
                tags {
                    id
                    name
                }
            }
        }
        """
        
        update_input = {
            "id": gallery_id,
            "urls": [url]
        }
        
        if title:
            update_input["title"] = title
        
        if tag_ids:
            update_input["tag_ids"] = tag_ids
        
        payload = {
            "operationName": "GalleryUpdate",
            "variables": {
                "input": update_input
            },
            "query": mutation
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/graphql",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to update gallery: {e}")
            return False

