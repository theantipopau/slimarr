import unittest

from backend.integrations.shared_http import get_shared_client


class SharedHttpClientTests(unittest.TestCase):
    def test_tls_verify_false_never_uses_the_shared_client(self):
        self.assertIsNone(get_shared_client(tls_verify=False))

    def test_tls_verify_true_falls_back_gracefully_outside_the_app_lifespan(self):
        # get_http_client() raises RuntimeError until FastAPI's lifespan has
        # started it (as in this unit test) - must degrade to None, not raise.
        self.assertIsNone(get_shared_client(tls_verify=True))

    def test_default_behaves_as_tls_verify_true(self):
        self.assertIsNone(get_shared_client())


if __name__ == "__main__":
    unittest.main()
