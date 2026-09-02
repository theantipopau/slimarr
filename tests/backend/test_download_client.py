import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.integrations.download_client import (
    decode_job_id,
    encode_job_id,
    get_active_download_client_name,
    get_download_client_capabilities,
    list_download_client_capabilities,
)


class DownloadClientHelpersTests(unittest.TestCase):
    def test_get_active_download_client_name_defaults_to_sabnzbd(self):
        with patch(
            "backend.integrations.download_client.get_config",
            return_value=SimpleNamespace(download_client=""),
        ):
            self.assertEqual("sabnzbd", get_active_download_client_name())

    def test_get_active_download_client_name_normalizes_case(self):
        with patch(
            "backend.integrations.download_client.get_config",
            return_value=SimpleNamespace(download_client="NZBGet"),
        ):
            self.assertEqual("nzbget", get_active_download_client_name())

    def test_get_download_client_capabilities_known_clients(self):
        sabnzbd = get_download_client_capabilities("sabnzbd")
        nzbget = get_download_client_capabilities("nzbget")
        self.assertTrue(sabnzbd.submit_url)
        self.assertTrue(nzbget.submit_url)

    def test_get_download_client_capabilities_unknown_client_raises(self):
        with self.assertRaises(ValueError):
            get_download_client_capabilities("qbittorrent")

    def test_list_download_client_capabilities_includes_both_clients(self):
        result = list_download_client_capabilities()
        self.assertEqual({"nzbget", "sabnzbd"}, set(result.keys()))
        self.assertIn("submit_url", result["sabnzbd"])

    def test_encode_decode_job_id_round_trip(self):
        encoded = encode_job_id("sabnzbd", "abc123")
        self.assertEqual(("sabnzbd", "abc123"), decode_job_id(encoded))

    def test_decode_job_id_without_prefix_uses_fallback_client(self):
        self.assertEqual(("nzbget", "abc123"), decode_job_id("abc123", fallback_client="nzbget"))

    def test_decode_job_id_empty_returns_fallback_and_empty_id(self):
        self.assertEqual(("sabnzbd", ""), decode_job_id(None, fallback_client="sabnzbd"))


if __name__ == "__main__":
    unittest.main()
