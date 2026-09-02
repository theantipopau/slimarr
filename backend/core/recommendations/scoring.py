"""Deterministic recommendation scoring — pure, no I/O, no AI.

score_candidate() takes pre-fetched signals (already-in-Plex checks, TMDB
relationship data, streaming availability, etc. — all gathered elsewhere by
core/recommendations/{sourcing,correlation,streaming}.py) and returns a score
plus the structured reasons that produced it. Score and reasons are kept as
separate fields on ScoredResult so a caller never has to re-derive "why does
this have this score" — the brief requires this explicitly.

Hard exclusions (already owned, already managed, previously dismissed,
permanently hidden, blocked keyword/person, unsupported media type) short
-circuit to a zero score and a single terminal reason, mirroring the
_reject()-early-return style already used in backend/core/comparer.py for the
same "stop and say why" clarity.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReasonInput:
    reason_code: str
    explanation: str
    weight: float = 0.0
    source_movie_id: int | None = None
    source_provider: str | None = None


@dataclass(frozen=True)
class CandidateSignals:
    media_type: str = "movie"
    popularity: float | None = None       # TMDB popularity, unbounded positive float
    vote_average: float | None = None     # TMDB vote_average, 0-10
    release_year: int | None = None

    # Deterministic relationship signals
    collection_name: str | None = None
    collection_owned_count: int = 0
    collection_total_count: int = 0
    is_sequel_or_prequel: bool = False
    sequel_source_title: str | None = None
    sequel_source_movie_id: int | None = None
    related_source_titles: tuple[str, ...] = ()
    genre_matches: tuple[str, ...] = ()
    creator_affinity_names: tuple[str, ...] = ()

    # Personalization (opt-in signals only — engine.py is responsible for
    # never populating these unless the corresponding config opt-in is on)
    on_watchlist: bool = False
    recent_source_activity: bool = False

    # Streaming availability
    available_on_subscribed_provider: bool = False
    available_provider_names: tuple[str, ...] = ()

    # Hard-exclusion / negative signals
    already_in_plex: bool = False
    already_managed_radarr: bool = False
    already_managed_sonarr: bool = False
    previously_dismissed: bool = False
    permanently_hidden: bool = False
    blocked_keyword_match: str | None = None
    blocked_person_match: str | None = None
    excluded_genre_match: str | None = None
    outside_year_range: bool = False
    outside_language_preference: bool = False
    unavailable_in_configured_region: bool = False
    unsupported_media_type: bool = False


@dataclass(frozen=True)
class ScoredResult:
    score: float
    state: str  # "active" | "already_available" | "already_managed" | "excluded"
    reasons: list[ReasonInput] = field(default_factory=list)


# Weights are deliberately simple and named so they can be tuned without
# touching the scoring logic itself.
_WEIGHT_MISSING_COLLECTION_MEMBER = 35.0
_WEIGHT_PER_OWNED_SIBLING = 6.0          # scales with how "complete" the collection already is
_WEIGHT_SEQUEL_PREQUEL = 30.0
_WEIGHT_RELATED_TITLE = 12.0
_WEIGHT_PER_GENRE_MATCH = 4.0
_WEIGHT_PER_CREATOR_MATCH = 8.0
_WEIGHT_WATCHLIST = 20.0
_WEIGHT_RECENT_ACTIVITY = 10.0
_WEIGHT_STREAMING_AVAILABLE = 15.0
_WEIGHT_POPULARITY_MAX = 10.0            # capped contribution regardless of how popular
_WEIGHT_RATING_MAX = 8.0                 # capped contribution from vote_average

_PENALTY_OUTSIDE_YEAR_RANGE = 25.0
_PENALTY_OUTSIDE_LANGUAGE = 15.0
_PENALTY_UNAVAILABLE_IN_REGION = 5.0     # informational, not exclusionary on its own


def score_candidate(signals: CandidateSignals) -> ScoredResult:
    # --- Hard exclusions: short-circuit, matching comparer.py's _reject() style ---
    if signals.unsupported_media_type:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput("unsupported_media_type", "This media type is not enabled.")],
        )
    if signals.already_in_plex:
        return ScoredResult(
            score=0.0,
            state="already_available",
            reasons=[ReasonInput("already_in_plex", "Already in your Plex library.")],
        )
    if signals.already_managed_radarr:
        return ScoredResult(
            score=0.0,
            state="already_managed",
            reasons=[ReasonInput("already_managed_radarr", "Already monitored in Radarr.")],
        )
    if signals.already_managed_sonarr:
        return ScoredResult(
            score=0.0,
            state="already_managed",
            reasons=[ReasonInput("already_managed_sonarr", "Already monitored in Sonarr.")],
        )
    if signals.permanently_hidden:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput("permanently_hidden", "You hid this recommendation permanently.")],
        )
    if signals.previously_dismissed:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput("previously_dismissed", "You previously dismissed this recommendation.")],
        )
    if signals.blocked_keyword_match:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput(
                "blocked_keyword",
                f"Matches an excluded keyword: {signals.blocked_keyword_match}.",
            )],
        )
    if signals.blocked_person_match:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput(
                "blocked_person",
                f"Associated with an excluded person: {signals.blocked_person_match}.",
            )],
        )
    if signals.excluded_genre_match:
        return ScoredResult(
            score=0.0,
            state="excluded",
            reasons=[ReasonInput(
                "excluded_genre",
                f"Matches an excluded genre: {signals.excluded_genre_match}.",
            )],
        )

    score = 0.0
    reasons: list[ReasonInput] = []

    if signals.collection_name and signals.collection_total_count > 0:
        score += _WEIGHT_MISSING_COLLECTION_MEMBER
        score += _WEIGHT_PER_OWNED_SIBLING * signals.collection_owned_count
        reasons.append(ReasonInput(
            "missing_collection_member",
            f"Missing from {signals.collection_name}, which you have "
            f"{signals.collection_owned_count} of {signals.collection_total_count} titles from already.",
            weight=_WEIGHT_MISSING_COLLECTION_MEMBER + _WEIGHT_PER_OWNED_SIBLING * signals.collection_owned_count,
            source_provider="tmdb",
        ))

    if signals.is_sequel_or_prequel and signals.sequel_source_title:
        score += _WEIGHT_SEQUEL_PREQUEL
        reasons.append(ReasonInput(
            "direct_sequel",
            f"Sequel or prequel to {signals.sequel_source_title}, which is in your library.",
            weight=_WEIGHT_SEQUEL_PREQUEL,
            source_movie_id=signals.sequel_source_movie_id,
            source_provider="tmdb",
        ))

    for title in signals.related_source_titles:
        score += _WEIGHT_RELATED_TITLE
        reasons.append(ReasonInput(
            "related_to_library_title",
            f"Related to {title}, which is in your library.",
            weight=_WEIGHT_RELATED_TITLE,
            source_provider="tmdb",
        ))

    if signals.genre_matches:
        weight = _WEIGHT_PER_GENRE_MATCH * len(signals.genre_matches)
        score += weight
        reasons.append(ReasonInput(
            "genre_affinity",
            f"Matches your preferred genres: {', '.join(signals.genre_matches)}.",
            weight=weight,
        ))

    if signals.creator_affinity_names:
        weight = _WEIGHT_PER_CREATOR_MATCH * len(signals.creator_affinity_names)
        score += weight
        reasons.append(ReasonInput(
            "creator_affinity",
            f"From {', '.join(signals.creator_affinity_names)}, featured elsewhere in your library.",
            weight=weight,
            source_provider="tmdb",
        ))

    if signals.on_watchlist:
        score += _WEIGHT_WATCHLIST
        reasons.append(ReasonInput(
            "on_watchlist",
            "On your watchlist.",
            weight=_WEIGHT_WATCHLIST,
        ))

    if signals.recent_source_activity:
        score += _WEIGHT_RECENT_ACTIVITY
        reasons.append(ReasonInput(
            "related_to_recent_activity",
            "Related to titles you've recently watched.",
            weight=_WEIGHT_RECENT_ACTIVITY,
            source_provider="plex",
        ))

    if signals.available_on_subscribed_provider and signals.available_provider_names:
        score += _WEIGHT_STREAMING_AVAILABLE
        providers = ", ".join(signals.available_provider_names)
        reasons.append(ReasonInput(
            "streaming_available",
            f"Available on {providers} in your configured region.",
            weight=_WEIGHT_STREAMING_AVAILABLE,
            source_provider="tmdb",
        ))

    if signals.popularity is not None and signals.popularity > 0:
        # Diminishing-returns cap so popularity never dominates a deterministic
        # relationship signal — popularity is not personal preference.
        popularity_contribution = min(_WEIGHT_POPULARITY_MAX, signals.popularity / 20.0)
        if popularity_contribution > 0:
            score += popularity_contribution
            reasons.append(ReasonInput(
                "popular_on_provider",
                "Popular on TMDB right now.",
                weight=popularity_contribution,
                source_provider="tmdb",
            ))

    if signals.vote_average is not None and signals.vote_average > 0:
        rating_contribution = min(_WEIGHT_RATING_MAX, (signals.vote_average / 10.0) * _WEIGHT_RATING_MAX)
        if rating_contribution > 0:
            score += rating_contribution
            reasons.append(ReasonInput(
                "highly_rated",
                f"Highly rated ({signals.vote_average:.1f}/10 on TMDB).",
                weight=rating_contribution,
                source_provider="tmdb",
            ))

    if signals.outside_year_range:
        score -= _PENALTY_OUTSIDE_YEAR_RANGE
    if signals.outside_language_preference:
        score -= _PENALTY_OUTSIDE_LANGUAGE
    if signals.unavailable_in_configured_region:
        score -= _PENALTY_UNAVAILABLE_IN_REGION

    return ScoredResult(score=max(0.0, round(score, 2)), state="active", reasons=reasons)
