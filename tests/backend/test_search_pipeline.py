import unittest
import tempfile
from unittest.mock import patch

import httpx

from backend.config import IndexerConfig, SlimarrConfig
from backend.core import search_diagnostics
from backend.integrations.newznab import NewznabClient, NewznabParserError, NewznabSearchError
from backend.integrations.prowlarr import ProwlarrClient


def _response(status_code: int, content: str, request: httpx.Request) -> httpx.Response:
    return httpx.Response(status_code, content=content.encode("utf-8"), request=request)


class SearchPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        search_diagnostics.reset()

    def _indexer(self, categories: list[int] | None = None) -> IndexerConfig:
        return IndexerConfig(
            name="TestIndexer",
            url="https://indexer.test",
            api_key="secret",
            categories=categories or [2000],
        )

    async def test_newznab_parses_empty_result_payload(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(200, "<rss><channel></channel></rss>", request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))
        results = await client.search_by_query("The Matrix 1999")

        self.assertEqual([], results)
        snapshot = search_diagnostics.snapshot()
        self.assertEqual(1, snapshot["indexer_reliability"]["TestIndexer"]["empty"])

    async def test_newznab_parses_categories_and_size_attrs(self) -> None:
        xml = """
        <rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
          <channel>
            <item>
              <title>The.Matrix.1999.1080p.WEB-DL.x265-GRP</title>
              <link>https://indexer.test/get/1</link>
              <pubDate>Tue, 12 May 2026 10:00:00 GMT</pubDate>
              <newznab:attr name="size" value="1234567890" />
              <newznab:attr name="category" value="2000" />
              <newznab:attr name="grabs" value="7" />
            </item>
          </channel>
        </rss>
        """

        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(200, xml, request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))
        results = await client.search_by_query("The Matrix 1999")

        self.assertEqual(1, len(results))
        self.assertEqual([2000], results[0]["categories"])
        self.assertEqual(1234567890, results[0]["size"])
        self.assertEqual(7, results[0]["grabs"])

    async def test_newznab_auth_failure_is_not_silent_empty(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(200, '<error code="100" description="Invalid API key" />', request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))

        with self.assertRaises(NewznabSearchError):
            await client.search_by_query("The Matrix 1999")

        snapshot = search_diagnostics.snapshot()
        self.assertIn("Invalid API key", snapshot["indexer_reliability"]["TestIndexer"]["last_error"])

    async def test_newznab_quota_error_warns_user(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(200, '<error code="500" description="Daily API request limit reached" />', request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))

        with self.assertRaises(NewznabSearchError):
            await client.search_by_query("The Matrix 1999")

        snapshot = search_diagnostics.snapshot()
        self.assertEqual(1, snapshot["indexer_reliability"]["TestIndexer"]["rate_limited"])
        self.assertTrue(snapshot["recent_events"][0]["rate_limited"])
        self.assertEqual("Indexer API quota or rate limit reached.", snapshot["warnings"][0]["message"])
        self.assertEqual("TestIndexer", snapshot["warnings"][0]["detail"]["indexer"])

    async def test_newznab_namespaced_error_is_not_silent_empty(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(
                200,
                '<newznab:error xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/" '
                'code="100" description="Invalid API key" />',
                request,
            )

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))

        with self.assertRaises(NewznabSearchError):
            await client.search_by_query("The Matrix 1999")

    async def test_newznab_malformed_payload_is_not_silent_empty(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(200, "<rss><channel>", request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))

        with self.assertRaises(NewznabParserError):
            await client.search_by_query("The Matrix 1999")

        snapshot = search_diagnostics.snapshot()
        self.assertEqual(1, snapshot["indexer_reliability"]["TestIndexer"]["malformed"])

    async def test_newznab_timeout_has_actionable_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("", request=request)

        client = NewznabClient(self._indexer(), transport=httpx.MockTransport(handler))

        with self.assertRaises(httpx.ReadTimeout):
            await client.search_by_query("The Matrix 1999")

        snapshot = search_diagnostics.snapshot()
        self.assertEqual(1, snapshot["indexer_reliability"]["TestIndexer"]["timeouts"])
        self.assertIn("timed out", snapshot["indexer_reliability"]["TestIndexer"]["last_error"])

    async def test_prowlarr_search_uses_redacted_movie_request(self) -> None:
        cfg = SlimarrConfig()
        cfg.prowlarr.enabled = True
        cfg.prowlarr.url = "https://prowlarr.test"
        cfg.prowlarr.api_key = "top-secret"

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("/api/v1/search", request.url.path)
            self.assertEqual("movie", request.url.params.get("type"))
            self.assertEqual("The Matrix 1999", request.url.params.get("query"))
            body = """
            [
              {
                "indexer": "NZB.su",
                "title": "The.Matrix.1999.1080p.WEB-DL.x265-GRP",
                "downloadUrl": "https://prowlarr.test/download/1",
                "size": 1234567890,
                "categories": [{"id": 2000}]
              }
            ]
            """
            return _response(200, body, request)

        with patch("backend.integrations.prowlarr.get_config", return_value=cfg):
            client = ProwlarrClient(transport=httpx.MockTransport(handler))
            results = await client.search("The Matrix 1999")

        self.assertEqual(1, len(results))
        self.assertEqual([2000], results[0]["categories"])
        event = search_diagnostics.snapshot()["recent_events"][0]
        self.assertNotIn("top-secret", event["request_url"])

    async def test_prowlarr_http_429_warns_user(self) -> None:
        cfg = SlimarrConfig()
        cfg.prowlarr.enabled = True
        cfg.prowlarr.url = "https://prowlarr.test"
        cfg.prowlarr.api_key = "top-secret"

        async def handler(request: httpx.Request) -> httpx.Response:
            return _response(429, "Too Many Requests", request)

        with patch("backend.integrations.prowlarr.get_config", return_value=cfg):
            client = ProwlarrClient(transport=httpx.MockTransport(handler))
            with self.assertRaises(httpx.HTTPStatusError):
                await client.search("The Matrix 1999")

        snapshot = search_diagnostics.snapshot()
        self.assertEqual(1, snapshot["indexer_reliability"]["Prowlarr"]["rate_limited"])
        self.assertTrue(snapshot["recent_events"][0]["rate_limited"])
        self.assertEqual("Indexer API quota or rate limit reached.", snapshot["warnings"][0]["message"])

    async def test_diagnostics_redacts_text_and_raw_previews(self) -> None:
        preview = search_diagnostics.raw_preview(
            '{"apikey":"secret","token":"token-secret","Authorization":"Bearer bearer-secret"}'
        )
        url = search_diagnostics.redact_url("https://user:pass@indexer.test/api?apikey=secret&q=movie")

        self.assertNotIn("secret", preview)
        self.assertIn("***", preview)
        self.assertNotIn("user:pass", url)
        self.assertNotIn("secret", url)
        self.assertIn("q=movie", url)

    async def test_diagnostics_retention_is_bounded(self) -> None:
        for idx in range(search_diagnostics.MAX_EVENTS + 25):
            search_diagnostics.record_filter_summary(
                movie_id=idx,
                title=f"Movie {idx}",
                raw_count=0,
                unique_count=0,
                stored_count=0,
                accepted_count=0,
                rejected_count=0,
                rejection_reasons={},
            )

        snapshot = search_diagnostics.snapshot()
        self.assertLessEqual(len(snapshot["recent_events"]), search_diagnostics.MAX_EVENTS)

    async def test_consecutive_zero_results_mark_pipeline_degraded(self) -> None:
        for idx in range(100):
            await search_diagnostics.record_movie_search_completed(
                movie_id=idx,
                title=f"Movie {idx}",
                raw_count=0,
                accepted_count=0,
                indexer_attempts=1,
                indexer_failures=0,
                configured_sources=1,
            )

        status = search_diagnostics.degradation_status()
        self.assertTrue(status["degraded"])
        self.assertFalse(status["blocking"])
        self.assertIn("100+ consecutive zero-result searches", status["reasons"])
        search_diagnostics.raise_if_degraded()

    async def test_repeated_all_provider_failures_block_automation(self) -> None:
        for idx in range(10):
            await search_diagnostics.record_movie_search_completed(
                movie_id=idx,
                title=f"Movie {idx}",
                raw_count=0,
                accepted_count=0,
                indexer_attempts=2,
                indexer_failures=2,
                configured_sources=2,
            )

        status = search_diagnostics.degradation_status()
        self.assertTrue(status["degraded"])
        self.assertTrue(status["blocking"])
        self.assertIn("all configured search providers failing", status["blocking_reasons"])
        with self.assertRaises(search_diagnostics.SearchPipelineDegraded):
            search_diagnostics.raise_if_degraded()

    async def test_history_supports_pagination_and_filtering(self) -> None:
        original_history_file = search_diagnostics.HISTORY_FILE
        with tempfile.TemporaryDirectory() as tmpdir:
            search_diagnostics.HISTORY_FILE = f"{tmpdir}/history.jsonl"
            try:
                for idx in range(5):
                    search_diagnostics.record_filter_summary(
                        movie_id=idx,
                        title=f"Alpha Movie {idx}" if idx % 2 == 0 else f"Beta Movie {idx}",
                        raw_count=idx + 1,
                        unique_count=idx + 1,
                        stored_count=idx + 1,
                        accepted_count=1,
                        rejected_count=0,
                        rejection_reasons={},
                    )

                page_1 = search_diagnostics.history(page=1, per_page=2)
                page_2 = search_diagnostics.history(page=2, per_page=2)
                alpha_only = search_diagnostics.history(page=1, per_page=10, event_type="filter_summary", query="Alpha")

                self.assertEqual(2, page_1["per_page"])
                self.assertEqual(1, page_1["page"])
                self.assertEqual(2, len(page_1["items"]))
                self.assertEqual(2, page_2["page"])
                self.assertEqual(2, len(page_2["items"]))

                self.assertGreaterEqual(alpha_only["total"], 3)
                self.assertTrue(all(item.get("type") == "filter_summary" for item in alpha_only["items"]))
                self.assertTrue(all("alpha" in str(item).lower() for item in alpha_only["items"]))
            finally:
                search_diagnostics.HISTORY_FILE = original_history_file


if __name__ == "__main__":
    unittest.main()
