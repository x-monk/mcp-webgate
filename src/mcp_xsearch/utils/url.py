"""URL sanitization, deduplication, and binary extension filtering."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}

BINARY_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dmg",
    ".iso",
    ".rar",
    ".7z",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".svg",
    ".webp",
)


def sanitize_url(url: str) -> str:
    """Remove tracking parameters and fragments from a URL."""
    try:
        parsed = urlparse(url)
        query_dict = dict(parse_qsl(parsed.query))
        filtered = {k: v for k, v in query_dict.items() if k.lower() not in TRACKING_PARAMS}
        return urlunparse(parsed._replace(query=urlencode(filtered), fragment=""))
    except Exception:
        return url


def is_binary_url(url: str) -> bool:
    """Check if a URL points to a binary file based on extension."""
    path = urlparse(url).path.lower().split("?")[0]
    return path.endswith(BINARY_EXTENSIONS)


def dedup_urls(urls: list[str]) -> list[str]:
    """Deduplicate URLs after sanitization, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        clean = sanitize_url(url).lower().rstrip("/")
        if clean not in seen:
            seen.add(clean)
            result.append(url)
    return result
