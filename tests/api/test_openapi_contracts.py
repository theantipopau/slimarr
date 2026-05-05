import unittest
from fastapi.routing import APIRoute

from backend.main import app


class OpenAPIContractTests(unittest.TestCase):
    def _route_map(self) -> dict[tuple[str, str], APIRoute]:
        route_map: dict[tuple[str, str], APIRoute] = {}
        for route in app.routes:
            if isinstance(route, APIRoute):
                for method in route.methods or []:
                    route_map[(method.upper(), route.path)] = route
        return route_map

    def test_core_routes_have_response_models(self) -> None:
        routes = self._route_map()
        expected = [
            ("GET", "/api/v1/system/health"),
            ("GET", "/api/v1/system/info"),
            ("GET", "/api/v1/system/preflight"),
            ("GET", "/api/v1/system/decision-audit"),
            ("POST", "/api/v1/system/cycle/start"),
            ("GET", "/api/v1/settings"),
            ("POST", "/api/v1/settings/test/{service}"),
            ("GET", "/api/v1/tv/shows"),
            ("DELETE", "/api/v1/tv/shows/{plex_rating_key}"),
            ("GET", "/api/v1/library/movies"),
            ("GET", "/api/v1/dashboard/stats"),
            ("GET", "/api/v1/queue/active"),
            ("GET", "/api/v1/activity"),
        ]

        missing = []
        for key in expected:
            route = routes.get(key)
            if route is None or route.response_model is None:
                missing.append(key)

        self.assertEqual([], missing, f"Routes missing response models: {missing}")


if __name__ == "__main__":
    unittest.main()
