import unittest
from types import SimpleNamespace

from backend.core.recommendations.ai_provider import (
    NoOpExplanationProvider,
    RecommendationExplanationProvider,
    RerankContext,
    ScoredCandidateSummary,
    get_explanation_provider,
)


def _summary(**overrides) -> ScoredCandidateSummary:
    base = dict(
        tmdb_id=1, media_type="movie", title="A Movie", year=2000,
        genres=("Animation",), overview="An overview.", score=50.0, reason_summaries=("x",),
    )
    base.update(overrides)
    return ScoredCandidateSummary(**base)


class NoOpProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_rerank_returns_input_order_unchanged(self):
        provider = NoOpExplanationProvider()
        candidates = [_summary(tmdb_id=1), _summary(tmdb_id=2), _summary(tmdb_id=3)]
        result = await provider.rerank(candidates, RerankContext())
        self.assertEqual(result, candidates)
        self.assertIs(result, candidates)  # genuinely a pass-through, not a re-sorted copy

    async def test_explain_returns_none(self):
        provider = NoOpExplanationProvider()
        result = await provider.explain(_summary(), RerankContext())
        self.assertIsNone(result)

    async def test_themed_discovery_returns_empty_list(self):
        provider = NoOpExplanationProvider()
        result = await provider.themed_discovery("cozy animated films", [_summary()])
        self.assertEqual(result, [])

    async def test_test_connection_reports_success_with_no_provider(self):
        provider = NoOpExplanationProvider()
        result = await provider.test_connection()
        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "none")

    async def test_conforms_to_the_protocol(self):
        self.assertIsInstance(NoOpExplanationProvider(), RecommendationExplanationProvider)


class ProviderFactoryTests(unittest.TestCase):
    def _config(self, **ai_overrides):
        defaults = {"enabled": False, "provider": "none"}
        defaults.update(ai_overrides)
        return SimpleNamespace(recommendations=SimpleNamespace(ai=SimpleNamespace(**defaults)))

    def test_ai_disabled_returns_noop(self):
        provider = get_explanation_provider(self._config(enabled=False))
        self.assertIsInstance(provider, NoOpExplanationProvider)

    def test_provider_none_returns_noop_even_if_enabled_flag_is_true(self):
        provider = get_explanation_provider(self._config(enabled=True, provider="none"))
        self.assertIsInstance(provider, NoOpExplanationProvider)

    def test_unimplemented_real_provider_degrades_to_noop_not_an_exception(self):
        """openai_compatible/anthropic/ollama adapters aren't implemented in
        this release — requesting one must degrade safely, never raise,
        since the base engine's correctness never depends on AI succeeding."""
        for provider_name in ("openai_compatible", "anthropic", "ollama"):
            provider = get_explanation_provider(self._config(enabled=True, provider=provider_name))
            self.assertIsInstance(provider, NoOpExplanationProvider)

    def test_missing_ai_config_section_returns_noop(self):
        config = SimpleNamespace(recommendations=SimpleNamespace())
        provider = get_explanation_provider(config)
        self.assertIsInstance(provider, NoOpExplanationProvider)


class SignalTypesCannotCarrySensitiveDataTests(unittest.TestCase):
    """Defensive/documentation tests: these dataclasses must never grow a
    field capable of carrying a Plex token, file path, or credential —
    verified here by checking their declared fields stay within the
    documented allow-list, so an accidental future addition fails a test
    instead of silently expanding what an AI provider can see."""

    def test_rerank_context_fields_are_the_documented_allow_list(self):
        fields = set(RerankContext.__dataclass_fields__.keys())
        self.assertEqual(fields, {"library_genre_summary", "recent_watch_titles"})

    def test_scored_candidate_summary_fields_are_the_documented_allow_list(self):
        fields = set(ScoredCandidateSummary.__dataclass_fields__.keys())
        self.assertEqual(
            fields,
            {"tmdb_id", "media_type", "title", "year", "genres", "overview", "score", "reason_summaries"},
        )


if __name__ == "__main__":
    unittest.main()
