"""Probe utilities for yt-dlp."""


def is_ytdlp_url(url: str) -> bool:
    return "youtu" in url or "vimeo" in url or "twitch" in url or "tiktok" in url
