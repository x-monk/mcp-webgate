"""Tests for URL utilities."""

from mcp_xsearch.utils.url import dedup_urls, is_binary_url, sanitize_url


class TestSanitizeUrl:
    def test_removes_tracking_params(self):
        url = "https://example.com/page?utm_source=google&utm_medium=cpc&id=42"
        result = sanitize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=42" in result

    def test_removes_fragment(self):
        url = "https://example.com/page#section"
        result = sanitize_url(url)
        assert "#" not in result

    def test_preserves_valid_params(self):
        url = "https://example.com/search?q=test&page=2"
        result = sanitize_url(url)
        assert "q=test" in result
        assert "page=2" in result

    def test_handles_malformed_url(self):
        url = "not-a-url"
        result = sanitize_url(url)
        assert result == "not-a-url"


class TestIsBinaryUrl:
    def test_pdf(self):
        assert is_binary_url("https://example.com/doc.pdf")

    def test_zip(self):
        assert is_binary_url("https://example.com/archive.zip")

    def test_html(self):
        assert not is_binary_url("https://example.com/page.html")

    def test_no_extension(self):
        assert not is_binary_url("https://example.com/page")

    def test_case_insensitive(self):
        assert is_binary_url("https://example.com/FILE.PDF")


class TestDedupUrls:
    def test_removes_duplicates(self):
        urls = [
            "https://example.com/page",
            "https://example.com/page",
        ]
        assert len(dedup_urls(urls)) == 1

    def test_tracking_param_dedup(self):
        urls = [
            "https://example.com/page?utm_source=a",
            "https://example.com/page?utm_source=b",
        ]
        assert len(dedup_urls(urls)) == 1

    def test_preserves_order(self):
        urls = [
            "https://a.com",
            "https://b.com",
            "https://a.com",
        ]
        result = dedup_urls(urls)
        assert result == ["https://a.com", "https://b.com"]

    def test_trailing_slash_dedup(self):
        urls = [
            "https://example.com/page",
            "https://example.com/page/",
        ]
        assert len(dedup_urls(urls)) == 1
