"""Probe utilities for gallery-dl."""


def is_gallerydl_url(url: str) -> bool:
    known_domains = [
            "pixiv.net",
            "flickr.com",
            "reddit.com",
            "deviantart.com",
            "twitter.com",
            "x.com",
            "e-hentai.org",
            "exhentai.org"
        ]
    return any(domain in url.lower() for domain in known_domains)

def is_booru_collection(url: str) -> bool:
    import re
    from urllib.parse import parse_qs, unquote_plus, urlparse
    
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # Pool pages
    if qs.get("page", [""])[0] == "pool":
        return True

    # Parent searches
    tags = unquote_plus(qs.get("tags", [""])[0])
    if re.search(r"\bparent:\d+\b", tags):
        return True

    return False