"""Tests for URL utilities."""

from mcp_webgate.utils.url import dedup_urls, is_binary_url, is_domain_allowed, sanitize_url


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


class TestIsDomainAllowed:
    def test_empty_lists_allow_everything(self):
        assert is_domain_allowed("https://example.com/page", [], []) is True

    def test_blocklist_rejects_exact_match(self):
        assert is_domain_allowed("https://reddit.com/r/python", ["reddit.com"], []) is False

    def test_blocklist_rejects_subdomain(self):
        assert is_domain_allowed("https://www.reddit.com/r/python", ["reddit.com"], []) is False

    def test_blocklist_allows_unrelated(self):
        assert is_domain_allowed("https://github.com/user/repo", ["reddit.com"], []) is True

    def test_allowlist_accepts_match(self):
        assert is_domain_allowed("https://docs.python.org/3/", [], ["python.org"]) is True

    def test_allowlist_accepts_subdomain(self):
        assert is_domain_allowed("https://docs.python.org/3/", [], ["python.org"]) is True

    def test_allowlist_rejects_non_match(self):
        assert is_domain_allowed("https://reddit.com/r/python", [], ["python.org"]) is False

    def test_allowlist_takes_precedence_over_blocklist(self):
        # When allowed is set, only it matters — blocked is ignored
        assert is_domain_allowed("https://python.org", ["python.org"], ["python.org"]) is True
