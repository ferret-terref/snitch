"""Probe utilities for gallery-dl."""


def is_gallerydl_url(url: str) -> bool:
    known_domains = [
            "pixiv.net",
            "flickr.com",
            "reddit.com",
            "deviantart.com",
            "twitter.com",
            "x.com",
        ]
    return any(domain in url.lower() for domain in known_domains)
