"""Tagging utility for Stash integration (galleries and images)."""

from typing import List, Optional


class StashTagger:
    def __init__(self, stash_client):
        self.stash = stash_client

    async def ensure_tags(self, tag_names: List[str]) -> List[str]:
        """
        Ensure all tags exist in Stash, creating them if needed. Returns tag IDs.
        """
        return await self.stash.get_or_create_tags(tag_names)

    async def tag_gallery(self, gallery_id: str, tag_names: List[str], url: Optional[str] = None, title: Optional[str] = None):
        tag_ids = await self.ensure_tags(tag_names)
        await self.stash.update_gallery_with_tags(gallery_id, url or "", title, tag_ids)

    async def tag_image_by_filename(self, filename: str, tag_names: List[str], page_url: Optional[str] = None, title: Optional[str] = None) -> Optional[int]:
        """
        Find image by filename and tag it with the given tags.
        """
        tag_ids = await self.ensure_tags(tag_names)
        image = await self.stash.find_image_by_filename(filename)
        
        print(f"StashTagger.tag_image_by_filename: filename={filename}, found image={image}")
        
        if image:
            image_id = image["id"]
            success = await self.stash.tag_image(image_id, tag_ids, page_url, title)
            return image_id if success else None
        return None
    
    async def tag_scene_by_filename(self, filename: str, tag_names: List[str], page_url: Optional[str] = None) -> Optional[int]:
        """
        Tag a scene in Stash by filename. Stub implementation.
        """
        
        tag_ids = await self.ensure_tags(tag_names)
        scene = await self.stash.find_scene_by_filename(filename)
        
        print(f"StashTagger.tag_scene_by_filename: filename={filename}, found scene={scene}")
        
        
        if scene:
            scene_id = scene["id"]
            success = await self.stash.tag_scene(scene_id, tag_ids, page_url)
            return scene_id if success else None
        return None
        pass
