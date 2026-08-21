
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
            "scanGenerateClipPreviews": False,
            "scanGenerateCovers": True,
            "scanGenerateImagePreviews": False,
            "scanGeneratePhashes": True,
            "scanGeneratePreviews": False,
            "scanGenerateSprites": False,
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

    async def find_image_by_filename(self, filename: str) -> dict:
        """
        Search for an image in Stash by filename (using FindImages with q=filename).
        Returns the first matching image dict, or None.
        """
        
        query = """
query FindImages($filter: FindFilterType, $image_filter: ImageFilterType, $image_ids: [Int!]) {
    findImages(filter: $filter, image_filter: $image_filter, image_ids: $image_ids) {
        count
        megapixels
        filesize
        images {
            ...SlimImageData
            __typename
        }
        __typename
    }
}

fragment SlimImageData on Image {
    id
    title
    code
    date
    urls
    details
    photographer
    rating100
    organized
    o_counter
    paths {
        thumbnail
        preview
        image
        __typename
    }
    galleries {
        id
        title
        files {
            path
            __typename
        }
        folder {
            path
            __typename
        }
        __typename
    }
    studio {
        id
        name
        image_path
        __typename
    }
    tags {
        id
        name
        __typename
    }
    performers {
        id
        name
        gender
        favorite
        image_path
        __typename
    }
    visual_files {
        ...VisualFileData
        __typename
    }
    __typename
}

fragment VisualFileData on VisualFile {
    ... on BaseFile {
        id
        path
        size
        mod_time
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    ... on ImageFile {
        id
        path
        size
        mod_time
        width
        height
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    ... on VideoFile {
        id
        path
        size
        mod_time
        duration
        video_codec
        audio_codec
        width
        height
        frame_rate
        bit_rate
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    __typename
}
"""
        variables = {
            "filter": {
                "q": filename,
                "page": 1,
                "per_page": 40,
                "sort": "file_mod_time",
                "direction": "DESC"
            },
            "image_filter": {}
        }
        payload = {
            "operationName": "FindImages",
            "variables": variables,
            "query": query
        }
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["ApiKey"] = self.api_key
        
        # Debug: log filename and payload
        logger.debug(f"find_image_by_filename: filename={filename}")
        logger.debug(f"find_image_by_filename: payload={payload}")
        
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
                
                logger.debug(f"find_image_by_filename: status={response.status_code}, response={response.text}")
                
                images = data.get("data", {}).get("findImages", {}).get("images", [])
                for img in images:
                    for vf in img.get("visual_files", []):
                        if filename in vf.get("path", ""):
                            return img
                return None
        except Exception as e:
            logger.error(f"Failed to find image by filename: {e}")
            return None

    async def tag_image(
            self,
            image_id: str,
            tag_ids: list[str],
            page_url: Optional[str] = None,
            title: Optional[str] = None
        ) -> bool:
            """
            Tag an image in Stash by image_id and tag_ids.
            Args:
                image_id: Stash image ID
                tag_ids: List of tag IDs to assign
            Returns:
                True if successful
            """
            
            mutation = """
            mutation ImageUpdate($input: ImageUpdateInput!) {
                imageUpdate(input: $input) {
                    id
                    tags { id name }
                    url
                    title
                }
            }
            """
            
            url = page_url
            if not url:
                url = ""

            update_input = {
                "id": image_id,
                "tag_ids": tag_ids,
                "url": url,
                "title": title
            }

            payload = {
                "operationName": "ImageUpdate",
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
                    data = response.json()
                    if data.get("errors"):
                        logger.error(f"Failed to tag image: {data['errors']}")
                        return False
                    logger.info(f"Tagged image {image_id} with {len(tag_ids)} tag(s)")
                    return True
            except Exception as e:
                logger.error(f"Failed to tag image: {e}")
                return False
                
    async def find_scene_by_filename(self, filename: str) -> Optional[dict]:
        """
        Search for a scene in Stash by filename (using FindScenes with q=filename).
        Returns the first matching scene dict, or None.
        """
        query = '''
query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType, $scene_ids: [Int!]) {
    findScenes(filter: $filter, scene_filter: $scene_filter, scene_ids: $scene_ids) {
        count
        filesize
        duration
        scenes {
            ...SlimSceneData
            __typename
        }
        __typename
    }
}

fragment SlimSceneData on Scene {
    id
    title
    code
    details
    director
    urls
    date
    rating100
    o_counter
    organized
    interactive
    interactive_speed
    resume_time
    play_duration
    play_count
    files {
        ...VideoFileData
        __typename
    }
    paths {
        screenshot
        preview
        stream
        webp
        vtt
        sprite
        funscript
        interactive_heatmap
        caption
        __typename
    }
    scene_markers {
        id
        title
        seconds
        primary_tag {
            id
            name
            __typename
        }
        __typename
    }
    galleries {
        id
        files {
            path
            __typename
        }
        folder {
            path
            __typename
        }
        title
        __typename
    }
    studio {
        id
        name
        image_path
        __typename
    }
    groups {
        group {
            id
            name
            front_image_path
            __typename
        }
        scene_index
        __typename
    }
    tags {
        id
        name
        __typename
    }
    performers {
        id
        name
        disambiguation
        gender
        favorite
        image_path
        __typename
    }
    stash_ids {
        endpoint
        stash_id
        updated_at
        __typename
    }
    __typename
}

fragment VideoFileData on VideoFile {
    id
    path
    size
    mod_time
    duration
    video_codec
    audio_codec
    width
    height
    frame_rate
    bit_rate
    fingerprints {
        type
        value
        __typename
    }
    __typename
}
    '''
        variables = {
                "filter": {
                        "q": filename,
                        "page": 1,
                        "per_page": 40,
                        "sort": "file_mod_time",
                        "direction": "DESC"
                },
                "scene_filter": {}
        }
        payload = {
                "operationName": "FindScenes",
                "variables": variables,
                "query": query
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
                headers["ApiKey"] = self.api_key
        logger.debug(f"find_scene_by_filename: filename={filename}")
        logger.debug(f"find_scene_by_filename: payload={payload}")
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
                    logger.debug(f"find_scene_by_filename: status={response.status_code}, response={response.text}")
                    scenes = data.get("data", {}).get("findScenes", {}).get("scenes", [])
                    for scene in scenes:
                            for vf in scene.get("files", []):
                                    if filename in vf.get("path", ""):
                                            return scene
                    return None
        except Exception as e:
                logger.error(f"Failed to find scene by filename: {e}")
                return None
            
    async def tag_scene(
            self,
            scene_id: str,
            tag_ids: list[str],
            page_url: Optional[str] = None
        ) -> bool:
            """
            Tag a scene in Stash by scene_id and tag_ids.
            Args:
                scene_id: Stash scene ID
                tag_ids: List of tag IDs to assign
                page_url: Optional URL to set
            Returns:
                True if successful
            """
            mutation = '''
            mutation SceneUpdate($input: SceneUpdateInput!) {
                sceneUpdate(input: $input) {
                    id
                    tags { id name }
                    url
                }
            }
            '''
            url = page_url if page_url else ""
            update_input = {
                "id": scene_id,
                "tag_ids": tag_ids,
                "url": url
            }
            payload = {
                "operationName": "SceneUpdate",
                "variables": {
                    "input": update_input
                },
                "query": mutation
            }
            headers = {"Content-Type": "application/json"}
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
                        logger.error(f"Failed to tag scene: {data['errors']}")
                        return False
                    logger.info(f"Tagged scene {scene_id} with {len(tag_ids)} tag(s)")
                    return True
            except Exception as e:
                logger.error(f"Failed to tag scene: {e}")
                return False