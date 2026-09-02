# Recommendation & Collection Completion — Architecture

**Status:** Stage 2 design, first-increment scope. This document is the data-model and service-boundary proposal referenced by `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md` §4 and `docs/ARR_PLATFORM_GAP_ANALYSIS.md`'s "Implement now" bucket.

## Goals and non-goals

Slimarr's job is deciding *whether an existing file should be replaced*. The recommendation engine's job is answering an entirely different question — *what's missing* — and must never let the two blur together. Concretely:

- `RecommendationCandidate` rows are never `Movie` rows. There is no shared primary-key space, no shared status vocabulary, and no code path by which `orchestrator.process_single_movie()` (gated on `Movie.status in {pending, failed}`) could ever pick up a recommendation candidate.
- Nothing in this feature downloads anything. Every acquisition path (Radarr, Sonarr, Seerr) is a hand-off to a system that already owns that decision; Slimarr never calls a download client directly for a recommended title.
- Personalization must remain explainable without an LLM. The scorer runs, and every recommendation carries reasons, whether or not the optional AI layer is ever enabled.

## Service boundaries

New code lives in two places, mirroring the existing `core/` + `api/` split rather than inventing a new layout:

```
backend/core/recommendations/
    __init__.py
    models_support.py      # small helpers shared by the modules below (dedup keys, state transitions)
    sourcing.py             # deterministic candidate generation (collections, sequels/prequels, related titles)
    correlation.py          # "is this already in Plex / already in Radarr / already in Sonarr" checks
    streaming.py            # TMDB /watch/providers integration + caching
    scoring.py               # pure, decomposable, unit-testable scorer (no I/O)
    ai_provider.py          # RecommendationExplanationProvider interface + NoOpProvider (Stage 10)
    engine.py                # orchestrates sourcing → correlation → streaming → scoring → persistence

backend/api/recommendations.py   # REST endpoints, mirrors the style of backend/api/library.py
```

`backend/core/jobs.py` (the existing durable job runtime — see audit §1/§4) gets two new job kinds registered in `_execute_job_kind`: `recommendation_refresh` and `streaming_availability_refresh`. No new job/queue mechanism is introduced. This is a direct application of the gap analysis's "Implement now: reuse existing durable jobs" line.

The existing health matrix (`api/system.py: /health/matrix`) gets a new component entry for recommendation-provider state (TMDB reachable, streaming-availability cache freshness, AI provider reachable if enabled) — extending an existing pattern rather than adding a parallel health endpoint.

## Data model

All new tables. No existing table is altered except a new `movies` correlation is done by **query**, not by foreign key (a `RecommendationCandidate` should not hard-link to a specific `Movie.id`, since a candidate title might not be in the library — correlation is computed at read/scoring time by matching `external_ids` against `Movie.imdb_id`/`Movie.tmdb_id`).

```python
class RecommendationCandidate(Base):
    """A specific title the engine has identified as potentially relevant.
    One row per distinct real-world title, deduplicated by external ID —
    NOT per-recommendation-event. Many Recommendation rows (different
    categories, re-surfaced after expiry) can point at the same candidate.
    """
    __tablename__ = "recommendation_candidates"
    __table_args__ = (
        UniqueConstraint("media_type", "tmdb_id", name="uq_candidate_media_tmdb"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # "movie" | "tv"
    title: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # External IDs — tmdb_id is the required join key (TMDB is the only metadata
    # provider this release integrates); imdb_id/tvdb_id are opportunistic extras
    # used for Radarr/Sonarr/Plex correlation, which key on those IDs, not TMDB's.
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    poster_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backdrop_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    popularity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vote_average: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    genres: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON array, matches Movie.genres convention

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    availability: Mapped[list["StreamingAvailability"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    """One surfaced recommendation event for a candidate. A candidate can have
    multiple Recommendation rows over time (e.g. dismissed once, re-surfaced
    months later under a different category) but only one *active* row per
    (candidate, category) pair — enforced below.
    """
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("candidate_id", "category", name="uq_recommendation_candidate_category"),
        Index("ix_recommendations_state_score", "state", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("recommendation_candidates.id"), index=True)

    # Single-user app today (see audit §1) — this column exists so a future
    # multi-user migration doesn't require a schema rewrite, but it always
    # holds the one implicit scope value ("default") in this release and is
    # not exposed anywhere in the API or UI as a selectable dimension.
    user_scope: Mapped[str] = mapped_column(String, default="default", index=True)

    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # "collection_completion" | "sequel_prequel" | "related_title" | "franchise_affinity"
    # | "genre_affinity" | "watchlist" | "trending" | "streaming_available"

    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    state: Mapped[str] = mapped_column(String, default="active", index=True)
    # active | dismissed | hidden | watchlisted | actioned | already_available
    # | already_managed | expired

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    candidate: Mapped["RecommendationCandidate"] = relationship(back_populates="recommendations")
    reasons: Mapped[list["RecommendationReason"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["RecommendationFeedback"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )


class RecommendationReason(Base):
    """Structured explanation. A stable reason_code (never the free-text
    alone) is what the frontend uses to render a reason chip/icon, and what
    tests assert against — the human-readable text can be reworded without
    breaking anything that keys off the code, matching the convention already
    used for search:warning's `code` field (see 1.9.0.0 changelog)."""
    __tablename__ = "recommendation_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    reason_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    explanation: Mapped[str] = mapped_column(String, nullable=False)
    source_movie_id: Mapped[Optional[int]] = mapped_column(ForeignKey("movies.id"), nullable=True)
    source_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "tmdb" | "plex" | "ai"
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="reasons")


class StreamingAvailability(Base):
    """Region-scoped, time-stamped, explicitly-expiring. Never presented as
    current if checked_at is older than the configured TTL — the API layer
    computes and returns a `stale` flag rather than silently serving old data
    as current (brief requirement)."""
    __tablename__ = "streaming_availability"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "region", "provider_id", "availability_type",
            name="uq_availability_candidate_region_provider_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("recommendation_candidates.id"), index=True)
    region: Mapped[str] = mapped_column(String, nullable=False, index=True)  # ISO 3166-1 alpha-2, e.g. "AU"
    provider_id: Mapped[int] = mapped_column(Integer, nullable=False)         # TMDB provider_id
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    display_priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    availability_type: Mapped[str] = mapped_column(String, nullable=False)    # "flatrate" | "rent" | "buy" | "ads" | "free"
    source: Mapped[str] = mapped_column(String, default="tmdb")
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # TMDB attribution link, required by their ToS
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    candidate: Mapped["RecommendationCandidate"] = relationship(back_populates="availability")


class RecommendationFeedback(Base):
    """Append-only event log — every user action on a recommendation, not
    just its current state (Recommendation.state is the derived "latest"
    view; this table is the audit trail, mirroring the existing
    DecisionAuditLog / ActivityLog pattern already used elsewhere)."""
    __tablename__ = "recommendation_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # shown | opened | dismissed | hidden | watchlisted | sent_to_radarr
    # | sent_to_sonarr | sent_to_seerr | marked_owned | availability_refreshed
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON, e.g. {"radarr_movie_id": 123}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="feedback")
```

**Why a candidate/recommendation split instead of one flat table:** a collection-completion scan and a "trending on TMDB" scan can both independently surface the same title. Without the split, the second scan either creates a duplicate row (violates the brief's "add unique constraints to prevent duplicate recommendations") or has to do a fragile upsert against a single wide table. With the split, `RecommendationCandidate` is the deduplicated identity (unique on `media_type` + `tmdb_id`), and `Recommendation` is the per-category surfaced event (unique on `candidate_id` + `category`), so both scans naturally converge on the same candidate row and each contributes at most one `Recommendation` row per category.

**Config additions** (new `recommendations:` section in `config.yaml`, following the existing flat-config-object convention — see gap analysis "Prepare now" table re: profile-style config being unnecessary for this release):

```yaml
recommendations:
  enabled: false                       # opt-in; the whole feature is inert until this is true
  region: ""                           # ISO 3166-1 alpha-2; empty = streaming availability disabled until set (brief: "explicit, not silently assumed")
  subscribed_providers: []             # TMDB provider_ids the user actually subscribes to
  enabled_categories: ["collection_completion", "sequel_prequel", "related_title"]
  media_types: ["movie"]               # "tv" support gated on Sonarr correlation, see Known Limitations
  minimum_score: 40.0
  max_candidate_age_days: 0            # 0 = no ceiling on a title's own release age
  languages: []                        # empty = no language filter
  genres_include: []
  genres_exclude: []
  excluded_keywords: []
  use_plex_watch_history: false        # opt-in; brief requires this explicit
  refresh_interval_hours: 24
  max_recommendations_retained: 500
  ai:
    enabled: false                     # disabled by default; see docs/RECOMMENDATION_ARCHITECTURE.md §AI
    provider: "none"                   # "none" | "openai_compatible" | "anthropic" | "ollama"
    base_url: ""
    model: ""
    api_key: ""
    timeout_seconds: 20
    share_watch_history: false         # separate, more restrictive opt-in than use_plex_watch_history
```

## Scoring (deterministic, no I/O)

`core/recommendations/scoring.py` exposes one pure function:

```python
def score_candidate(signals: CandidateSignals) -> ScoredResult:
    """No network/DB access. Takes pre-fetched signals, returns (score, [ReasonInput]).
    Fully unit-testable with plain dataclasses — no mocks needed."""
```

Positive/negative signal handling matches the brief's list exactly (missing-collection-member, sequel/prequel, genre/creator affinity, watchlist presence, popularity, streaming availability, already-in-Plex, already-managed, previously-dismissed/hidden, blocked lists, region/language mismatch, duplicate). Score and reasons are computed together but returned as separate fields — `ScoredResult.score: float` and `ScoredResult.reasons: list[ReasonInput]` — so the API layer can always answer "why does this have this score" without re-deriving it, per the brief's explicit "keep score and reasons separate" requirement.

## AI abstraction (interface only in this increment; see Known Limitations)

```python
class RecommendationExplanationProvider(Protocol):
    async def rerank(self, candidates: list[ScoredCandidate], context: RerankContext) -> list[ScoredCandidate]: ...
    async def explain(self, candidate: ScoredCandidate, signals: CandidateSignals) -> str | None: ...
    async def themed_discovery(self, prompt: str, candidate_pool: list[ScoredCandidate]) -> list[ScoredCandidate]: ...

class NoOpExplanationProvider:
    """Default. Every method is a pass-through/no-op — reranking returns the
    input order unchanged, explain() returns None (caller falls back to the
    deterministic reason chips), themed_discovery() returns an empty list.
    This is what 'disabled by default' means concretely: the engine's output
    is byte-identical whether this provider or no provider is wired in."""
```

Every AI-returned `tmdb_id` is re-validated against `TMDBClient.get_movie()`/`get_tv()` before ever reaching a `RecommendationCandidate` row — the brief's "validate every AI-returned media identifier against the metadata provider before displaying it" is enforced in `engine.py`, not left to the provider to self-police. AI never receives file paths, Plex tokens, or service credentials (its interface signature has no parameter capable of carrying them — `CandidateSignals`/`ScoredCandidate` are plain metadata dataclasses).

## Known limitations of this increment

- **TV support is deferred.** `media_types` defaults to `["movie"]`. Sonarr correlation ("already managed") requires a working title/TVDB-ID matching strategy at least as robust as the existing `SonarrClient.unmonitor_series_by_title()`'s exact-then-ambiguous-prefix logic — extending that safely is worth its own focused pass rather than rushing it alongside the first recommendation-engine release.
- **The AI provider interface ships with only the no-op implementation.** Real adapters (OpenAI-compatible, Anthropic, Ollama) are documented here as the intended shape but not implemented in this increment, per the brief's own instruction: "If an external API is insufficiently documented, implement an interface and disabled capability state rather than guessing its behaviour." Nothing about the interface needs to change to add them later.
- **Seerr hand-off ships with capability detection but is disabled until a live Seerr instance is verified against it** — see `docs/RECOMMENDATION_INTEGRATIONS.md` for the specific detection strategy and why guessing Overseerr-vs-Seerr endpoint compatibility was rejected.
