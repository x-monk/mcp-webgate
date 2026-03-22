"""Tests for HTML cleaning pipeline."""

from mcp_webgate.scraper.cleaner import (
    _apply_window,
    clean_html,
    clean_text,
    extract_title,
    normalize_typography,
    process_page,
)


class TestCleanHtml:
    def test_strips_script_and_style(self):
        html = "<html><head><style>body{}</style></head><body><script>alert(1)</script><p>Hello</p></body></html>"
        result = clean_html(html)
        assert "Hello" in result
        assert "alert" not in result
        assert "body{}" not in result

    def test_strips_nav_footer(self):
        html = "<html><body><nav>Menu</nav><main><p>Content</p></main><footer>Copyright</footer></body></html>"
        result = clean_html(html)
        assert "Content" in result
        assert "Menu" not in result

    def test_empty_input(self):
        assert clean_html("") == ""

    def test_malformed_html(self):
        result = clean_html("<p>Unclosed paragraph")
        assert "Unclosed paragraph" in result


class TestCleanText:
    def test_removes_unicode_junk(self):
        text = "Hello\u200bWorld\u202aTest"
        result = clean_text(text)
        assert "\u200b" not in result
        assert "\u202a" not in result
        assert "Hello" in result

    def test_removes_noise_lines(self):
        text = "Sign In\nActual content here\nFollow us"
        result = clean_text(text)
        assert "Actual content here" in result
        assert "Sign In" not in result
        assert "Follow us" not in result

    def test_deduplicates_consecutive_lines(self):
        text = "Same line\nSame line\nSame line"
        result = clean_text(text)
        assert result.count("Same line") == 1

    def test_collapses_newlines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = clean_text(text)
        assert "\n\n\n" not in result

    def test_empty_input(self):
        assert clean_text("") == ""


class TestNormalizeTypography:
    def test_smart_quotes_to_ascii(self):
        text = "\u201cHello\u201d and \u2018world\u2019"
        result = normalize_typography(text)
        assert '"Hello"' in result
        assert "'world'" in result

    def test_em_dash_to_hyphen(self):
        result = normalize_typography("before\u2014after")
        assert " - " in result
        assert "\u2014" not in result

    def test_en_dash_to_hyphen(self):
        result = normalize_typography("2020\u20132021")
        assert " - " in result

    def test_ellipsis_to_dots(self):
        result = normalize_typography("and so\u2026")
        assert "..." in result
        assert "\u2026" not in result

    def test_ligatures_expanded(self):
        result = normalize_typography("\ufb01le\ufb02ow")  # ﬁleﬂow
        assert "fi" in result
        assert "fl" in result
        assert "\ufb01" not in result
        assert "\ufb02" not in result

    def test_soft_hyphen_dropped(self):
        result = normalize_typography("word\u00adbreak")
        assert "\u00ad" not in result
        assert "wordbreak" in result

    def test_clean_text_applies_typography(self):
        """clean_text() must run typography normalization."""
        text = "React\u2019s new features\u2014what\u2019s new"
        result = clean_text(text)
        assert "\u2019" not in result
        assert "\u2014" not in result
        assert "React's" in result


class TestExtractTitle:
    def test_extracts_title(self):
        html = "<html><head><title>My Page</title></head><body></body></html>"
        assert extract_title(html) == "My Page"

    def test_no_title(self):
        html = "<html><body>No title here</body></html>"
        assert extract_title(html) == ""

    def test_empty_input(self):
        assert extract_title("") == ""


class TestProcessPage:
    def test_full_pipeline(self):
        html = "<html><head><title>Test</title></head><body><nav>Nav</nav><p>Real content here</p></body></html>"
        text, title, truncated = process_page(html, max_chars=5000)
        assert title == "Test"
        assert "Real content" in text
        assert "Nav" not in text
        assert not truncated

    def test_truncation_single_long_line(self):
        """Single-line content beyond budget is hard-truncated to max_chars."""
        html = "<html><body><p>" + "a" * 10000 + "</p></body></html>"
        text, _, truncated = process_page(html, max_chars=100)
        assert len(text) == 100
        assert truncated

    def test_snippet_fallback(self):
        html = "<html><body></body></html>"
        text, _, _ = process_page(html, snippet="Good snippet content", max_chars=5000)
        assert "snippet" in text.lower()


class TestApplyWindow:
    def test_no_truncation_when_within_budget(self):
        text = "Line one\nLine two\nLine three"
        result, truncated = _apply_window(text, max_chars=1000)
        assert result == text
        assert not truncated

    def test_cuts_on_line_boundary(self):
        text = "First line\nSecond line\nThird line"
        # Budget fits first two lines (10 + 1 + 11 = 22) but not the third
        result, truncated = _apply_window(text, max_chars=22)
        assert "First line" in result
        assert "Second line" in result
        assert "Third line" not in result
        assert truncated

    def test_result_never_exceeds_budget(self):
        lines = [f"Line number {i:04d}" for i in range(200)]
        text = "\n".join(lines)
        result, _ = _apply_window(text, max_chars=100)
        assert len(result) <= 100

    def test_first_line_hard_truncated_when_exceeds_budget(self):
        """If even the first line is too long, hard-truncate it."""
        text = "x" * 500
        result, truncated = _apply_window(text, max_chars=100)
        assert result == "x" * 100
        assert truncated

    def test_empty_text(self):
        result, truncated = _apply_window("", max_chars=100)
        assert result == ""
        assert not truncated
