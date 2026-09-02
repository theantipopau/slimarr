"""Optional AI abstraction for recommendation explanations — disabled by
default, provider-neutral, and never load-bearing for the base engine.

The deterministic engine (sourcing + correlation + scoring) produces a
complete, explainable recommendation set with zero AI involvement. AI, when
enabled, may only:
  - rerank an already-generated candidate set;
  - produce a short natural-language explanation from supplied metadata;
  - build a themed discovery list from an existing candidate pool.

AI must never invent titles, franchise relationships, or streaming
availability, and never receives Plex tokens, file paths, service
credentials, or more viewing history than the user has explicitly opted to
share (see docs/RECOMMENDATION_PRIVACY.md). Every AI-returned TMDB ID is
re-validated against TMDB by the caller before it can reach a
RecommendationCandidate row — that validation lives in engine.py, not here,
so it can never be skipped by a provider implementation.

Only NoOpExplanationProvider ships in this release. Real adapters
(OpenAI-compatible, Anthropic, Ollama) are documented as the intended shape
in docs/RECOMMENDATION_ARCHITECTURE.md but are not implemented — per the
brief's own instruction to implement an interface and disabled capability
state rather than guess at an external API's behavior without verifying it
against live documentation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RerankContext:
    """Deliberately minimal — no Plex tokens, file paths, or credentials can
    be expressed by this type, so a provider implementation cannot receive
    them even by accident."""
    library_genre_summary: tuple[str, ...] = ()
    recent_watch_titles: tuple[str, ...] = ()  # only populated when both
    # recommendations.use_plex_watch_history AND ai.share_watch_history are true


@dataclass(frozen=True)
class ScoredCandidateSummary:
    """The subset of a scored candidate an AI provider is allowed to see —
    title/year/genres/overview/score/reasons, nothing else."""
    tmdb_id: int
    media_type: str
    title: str
    year: int | None
    genres: tuple[str, ...]
    overview: str | None
    score: float
    reason_summaries: tuple[str, ...]


@runtime_checkable
class RecommendationExplanationProvider(Protocol):
    async def rerank(
        self, candidates: list[ScoredCandidateSummary], context: RerankContext
    ) -> list[ScoredCandidateSummary]:
        ...

    async def explain(
        self, candidate: ScoredCandidateSummary, context: RerankContext
    ) -> str | None:
        ...

    async def themed_discovery(
        self, prompt: str, candidate_pool: list[ScoredCandidateSummary]
    ) -> list[ScoredCandidateSummary]:
        ...

    async def test_connection(self) -> dict:
        ...


class NoOpExplanationProvider:
    """The default and only shipped provider. Every method is a pure
    pass-through — the engine's output is byte-identical whether this
    provider or no provider at all is wired in. This is what "AI disabled by
    default" means concretely, not just a config flag that happens to be
    false."""

    async def rerank(
        self, candidates: list[ScoredCandidateSummary], context: RerankContext
    ) -> list[ScoredCandidateSummary]:
        return candidates

    async def explain(
        self, candidate: ScoredCandidateSummary, context: RerankContext
    ) -> str | None:
        return None

    async def themed_discovery(
        self, prompt: str, candidate_pool: list[ScoredCandidateSummary]
    ) -> list[ScoredCandidateSummary]:
        return []

    async def test_connection(self) -> dict:
        return {"success": True, "provider": "none"}


def get_explanation_provider(config) -> RecommendationExplanationProvider:
    """Factory. Returns NoOpExplanationProvider whenever AI is disabled or an
    unrecognized/unimplemented provider is configured — never raises, never
    silently falls back to a partially-working state."""
    ai_config = getattr(config.recommendations, "ai", None)
    if not ai_config or not ai_config.enabled or ai_config.provider == "none":
        return NoOpExplanationProvider()

    # openai_compatible / anthropic / ollama adapters are documented in
    # docs/RECOMMENDATION_ARCHITECTURE.md but not implemented in this
    # release — falling back to the no-op provider is a safe degrade, not a
    # silent failure, since the base engine never depends on AI succeeding.
    return NoOpExplanationProvider()
