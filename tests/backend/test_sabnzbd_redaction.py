import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.integrations.sabnzbd import SABnzbdClient

SECRET_KEY = "sk-super-secret-value-12345"


def _http_status_error_with_embedded_key() -> httpx.HTTPStatusError:
    """Build the exact kind of exception httpx raises from resp.raise_for_status()
    when the request URL (as SABnzbd's client always builds it) carries the API
    key as a query parameter — this is the real leak vector being fixed. httpx
    generates its own message text (embedding the URL) inside raise_for_status()
    itself, so it must actually be called rather than hand-constructed, or the
    test would just be checking a message we made up."""
    request = httpx.Request(
        "GET",
        f"http://sabnzbd.local:8080/api?mode=queue&apikey={SECRET_KEY}&output=json",
    )
    response = httpx.Response(500, request=request, text="Internal Server Error")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("raise_for_status() did not raise")


class SABnzbdRedactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.sabnzbd.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.sabnzbd.url = "http://sabnzbd.local:8080"
        mock_get_config.return_value.sabnzbd.api_key = SECRET_KEY
        mock_get_config.return_value.sabnzbd.category = "slimarr"
        self.client = SABnzbdClient()

    def _assert_key_not_leaked(self, text: str) -> None:
        self.assertNotIn(SECRET_KEY, text)
        self.assertIn("***", text)

    async def test_test_connection_redacts_the_api_key_on_failure(self):
        """Regression test: httpx's exception message embeds the full request
        URL, and SABnzbd's API key travels as a query param on every request
        (unlike NZBGet, which uses HTTP Basic auth) — a raw str(exc) here used
        to leak the key into the /health/services and /integrations/matrix
        API responses."""
        with patch.object(
            self.client, "_api", AsyncMock(side_effect=_http_status_error_with_embedded_key())
        ):
            result = await self.client.test_connection()

        self.assertFalse(result["success"])
        self._assert_key_not_leaked(result["error"])

    async def test_purge_job_redacts_the_api_key_in_logs(self):
        logged: list[str] = []

        def fake_warning(fmt, *args):
            logged.append(fmt.format(*args))

        with patch.object(
            self.client, "_api", AsyncMock(side_effect=_http_status_error_with_embedded_key())
        ), patch("backend.integrations.sabnzbd.logger.warning", side_effect=fake_warning), patch(
            "backend.integrations.sabnzbd.logger.debug"
        ):
            purged = await self.client.purge_job("nzo123")

        self.assertFalse(purged)
        self.assertTrue(logged, "expected the history-purge failure to be logged")
        for line in logged:
            self._assert_key_not_leaked(line)


if __name__ == "__main__":
    unittest.main()
