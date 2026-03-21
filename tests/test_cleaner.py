"""Tests for HTML cleaning pipeline."""

from mcp_xsearch.scraper.cleaner import clean_html, clean_text, extract_title, process_page


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

    def test_truncation(self):
        html = "<html><body><p>" + "a" * 10000 + "</p></body></html>"
        text, _, truncated = process_page(html, max_chars=100)
        assert len(text) == 100
        assert truncated

    def test_snippet_fallback(self):
        html = "<html><body></body></html>"
        text, _, _ = process_page(html, snippet="Good snippet content", max_chars=5000)
        assert "snippet" in text.lower()
