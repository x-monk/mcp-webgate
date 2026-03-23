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

# Typography normalization table — smart quotes, dashes, ellipsis, ligatures.
# Built as a str.translate() table for a single O(n) pass instead of 40+ sequential scans.
_TYPOGRAPHY_TRANS: dict[int, str | None] = {
    # Smart / curly quotes → ASCII
    ord("\u2018"): "'",   # '  left single quotation mark
    ord("\u2019"): "'",   # '  right single quotation mark (apostrophe)
    ord("\u201a"): "'",   # ‚  single low-9 quotation mark
    ord("\u201b"): "'",   # ‛  single high-reversed-9 quotation mark
    ord("\u201c"): '"',   # "  left double quotation mark
    ord("\u201d"): '"',   # "  right double quotation mark
    ord("\u201e"): '"',   # „  double low-9 quotation mark
    ord("\u201f"): '"',   # ‟  double high-reversed-9 quotation mark
    ord("\u2039"): "'",   # ‹  single left-pointing angle quotation mark
    ord("\u203a"): "'",   # ›  single right-pointing angle quotation mark
    ord("\u00ab"): '"',   # «  left-pointing double angle quotation mark
    ord("\u00bb"): '"',   # »  right-pointing double angle quotation mark
    # Dashes → ASCII hyphen (with spaces to avoid word-gluing)
    ord("\u2014"): " - ", # —  em dash
    ord("\u2013"): " - ", # –  en dash
    ord("\u2012"): " - ", # ‒  figure dash
    ord("\u2015"): " - ", # ―  horizontal bar
    ord("\u2011"): "-",   # ‑  non-breaking hyphen
    ord("\u00ad"): "",    # soft hyphen (invisible, drop it)
    # Ellipsis
    ord("\u2026"): "...", # …  horizontal ellipsis
    # Typographic spaces → regular space
    ord("\u2002"): " ",   # en space
    ord("\u2003"): " ",   # em space
    ord("\u2004"): " ",   # three-per-em space
    ord("\u2005"): " ",   # four-per-em space
    ord("\u2007"): " ",   # figure space
    ord("\u2009"): " ",   # thin space
    ord("\u200a"): " ",   # hair space
    ord("\u202f"): " ",   # narrow no-break space
    # Ligatures → component letters
    ord("\ufb00"): "ff",  # ﬀ
    ord("\ufb01"): "fi",  # ﬁ
    ord("\ufb02"): "fl",  # ﬂ
    ord("\ufb03"): "ffi", # ﬃ
    ord("\ufb04"): "ffl", # ﬄ
    ord("\ufb05"): "st",  # ﬅ
    ord("\ufb06"): "st",  # ﬆ
    ord("\u0132"): "IJ",  # Ĳ  Dutch digraph
    ord("\u0133"): "ij",  # ĳ
    ord("\u0152"): "OE",  # Œ
    ord("\u0153"): "oe",  # œ
}


def normalize_typography(text: str) -> str:
    """Replace typographic characters with their plain ASCII equivalents."""
    return text.translate(_TYPOGRAPHY_TRANS)


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
    """Sterilize extracted text: unicode junk, typography, noise lines, duplicates."""
    if not text:
        return ""

    # Unicode / BiDi sterilization
    text = _UNICODE_JUNK.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)

    # Typographic normalization
    text = normalize_typography(text)

    # Collapse whitespace again (em-dash replacements may have added spaces)
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
            return normalize_typography(title_el.text.strip())
    except Exception:
        pass
    return ""


def _apply_window(text: str, max_chars: int) -> tuple[str, bool]:
    """Collect whole lines until the character budget is exhausted.

    Returns (windowed_text, truncated). The output is always cut on a line
    boundary — never mid-sentence — so the LLM receives coherent paragraphs.

    Edge case: if the very first line already exceeds the budget (e.g. a
    single-paragraph wall of text), it is hard-truncated to max_chars so
    the caller always receives something rather than an empty string.
    """
    if len(text) <= max_chars:
        return text, False

    lines = text.splitlines()
    buf: list[str] = []
    total = 0
    for line in lines:
        # Account for the newline separator between lines
        needed = len(line) + (1 if buf else 0)
        if total + needed > max_chars:
            # Hard-truncate the first line if nothing fits yet
            if not buf:
                return line[:max_chars], True
            break
        buf.append(line)
        total += needed

    return "\n".join(buf), True


def process_page(raw_html: str, snippet: str = "", max_chars: int = 4000) -> tuple[str, str, bool]:
    """Full cleaning pipeline for a single page.

    Returns (text, title, truncated).
    """
    title = extract_title(raw_html)
    text = clean_text(clean_html(raw_html))

    # Heuristic: if scraping produced low-quality content, fall back to snippet
    if not text or (snippet and len(text) < len(snippet)) or text.count("\ufffd") > 10:
        if snippet:
            text = f"[Using search snippet - page content was low quality] {snippet}"

    text, truncated = _apply_window(text, max_chars)
    return text, title, truncated
