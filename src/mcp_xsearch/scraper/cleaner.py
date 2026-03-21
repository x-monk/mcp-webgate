"""HTML cleaning pipeline: lxml XPath + regex text sterilization."""

from __future__ import annotations

import re

from lxml import html as lxml_html

# XPath selector for noise elements to remove
_NOISE_XPATH = (
    "//script | //style | //nav | //footer | //header"
    " | //aside | //form | //iframe | //noscript"
    " | //svg | //button | //input | //select | //textarea"
)

# Regex: C0/C1 control codes, replacement char, zero-width and BiDi overrides
_UNICODE_JUNK = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd"
    r"\u200b-\u200f\u202a-\u202e\u2066-\u2069]+"
)

# Collapse whitespace (spaces, tabs, non-breaking spaces)
_WHITESPACE = re.compile(r"[ \t\u00A0]+")

# Noise lines: navigation / boilerplate text
_NOISE_LINE = re.compile(
    r"^(?:menu|home|search|sign in|log in|sign up|register|subscribe|newsletter"
    r"|account|profile|cart|checkout|buy now|shop|close|cancel|skip to content"
    r"|next|previous|back to top|privacy policy|terms|cookie|copyright"
    r"|all rights reserved|legal|contact us|help|support|faq|social|follow us"
    r"|share|facebook|twitter|instagram|linkedin|youtube|advertisement"
    r"|sponsored|promoted|related posts|read more|loading|posted by"
    r"|written by|author|category|tags)$",
    re.IGNORECASE,
)

# Short date-only lines
_DATE_ONLY = re.compile(
    r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w{3} \d{1,2},? \d{4}"
)


def clean_html(raw_html: str) -> str:
    """Strip HTML to clean text using lxml XPath removal."""
    if not raw_html:
        return ""
    try:
        tree = lxml_html.fromstring(raw_html)
        for element in tree.xpath(_NOISE_XPATH):
            element.drop_tree()
        text = tree.text_content()
        return text.strip()
    except Exception:
        return ""


def clean_text(text: str) -> str:
    """Sterilize extracted text: unicode junk, noise lines, duplicates."""
    if not text:
        return ""

    # Unicode / BiDi sterilization
    text = _UNICODE_JUNK.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)

    # Line-by-line noise filtering
    cleaned: list[str] = []
    prev = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _NOISE_LINE.match(line):
            continue
        if len(line) < 5 and not any(c.isalnum() for c in line):
            continue
        if len(line) < 20 and _DATE_ONLY.match(line):
            continue
        if line == prev:
            continue
        cleaned.append(line)
        prev = line

    result = "\n".join(cleaned)
    # Collapse 3+ newlines to double
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def extract_title(raw_html: str) -> str:
    """Extract <title> from raw HTML."""
    if not raw_html:
        return ""
    try:
        tree = lxml_html.fromstring(raw_html)
        title_el = tree.find(".//title")
        if title_el is not None and title_el.text:
            return title_el.text.strip()
    except Exception:
        pass
    return ""


def process_page(raw_html: str, snippet: str = "", max_chars: int = 4000) -> tuple[str, str, bool]:
    """Full cleaning pipeline for a single page.

    Returns (text, title, truncated).
    """
    title = extract_title(raw_html)
    text = clean_text(clean_html(raw_html))

    # Heuristic: if scraping produced low-quality content, fall back to snippet
    if not text or (snippet and len(text) < len(snippet)) or text.count("\ufffd") > 10:
        if snippet:
            text = f"[Using search snippet — page content was low quality] {snippet}"

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return text, title, truncated
