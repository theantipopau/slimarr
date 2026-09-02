# Recommendation & Collection Completion — Privacy

This document describes exactly what data the recommendation feature reads,
stores, and (optionally) shares — and what it never does. It complements
`docs/RECOMMENDATION_ARCHITECTURE.md` (data model) and
`docs/RECOMMENDATION_INTEGRATIONS.md` (hand-off actions).

## The feature is off by default

Nothing in this document applies until `recommendations.enabled: true` is set
in config. With it unset, the recommendation engine makes zero network calls
beyond what TMDB poster enrichment already made in prior Slimarr releases,
and no new database rows are ever created.

## What is read

- **Your own Plex-derived library data already in Slimarr's database**
  (`movies.tmdb_id`, `movies.imdb_id`, `movies.title`, `movies.year`) — no
  new Plex API calls are made for the deterministic recommendation engine
  itself; it reads what the existing scanner already stored.
- **TMDB metadata** for your owned movies and any candidate titles
  (collections, recommendations, similar titles, watch-provider listings) —
  the same provider Slimarr already uses for posters and backdrops.
- **Radarr's and Sonarr's movie/series lists**, if those integrations are
  configured, fetched once per refresh run to determine what you already
  manage there (see the audit's N+1 finding this design specifically avoids
  — `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md` §4).
- **Plex watch history** — **only if** `recommendations.use_plex_watch_history`
  is explicitly set to `true`. This is off by default. When on, only
  aggregate signals (which titles were recently watched) are used for
  scoring; no viewing history is stored verbatim in the recommendation
  tables beyond a title reference already visible elsewhere in Slimarr.

## What is stored

Exactly the tables in `docs/RECOMMENDATION_ARCHITECTURE.md`:
`RecommendationCandidate`, `Recommendation`, `RecommendationReason`,
`StreamingAvailability`, `RecommendationFeedback`. All are metadata about
*titles you don't have*, plus your own actions on those recommendations
(dismiss, hide, watchlist, sent-to-Radarr, etc.). No Plex tokens, API keys,
or credentials are ever written to these tables.

## What is never done

- Recommendations are never used to trigger a download or file replacement.
  The recommendation tables have no foreign-key or code path into
  `Movie`/`Download`/the replacement pipeline at all — see the audit's
  explicit verification of this boundary.
- No streaming service is scraped, and no streaming-service credentials are
  ever requested or stored. Availability comes exclusively from TMDB's own
  `/watch/providers` endpoint (itself sourced from JustWatch data under
  TMDB's API terms), which is why every `StreamingAvailability` row carries
  a `source_url` attribution link back to TMDB, as their terms require.
- No telemetry about your recommendations, feedback, or watch history is
  sent anywhere outside your own Slimarr instance. There is no analytics or
  phone-home in this feature.

## Deletion controls

- Dismissing or hiding a recommendation is immediate and local — no
  confirmation round-trip to any external service.
- An operator can delete all recommendation history and feedback by clearing
  the five tables listed above (a future release may add a one-click "clear
  all recommendation data" action in Settings; in this release it's a direct
  database operation, documented here rather than silently omitted).

## Optional AI — a stricter, separate opt-in

AI is disabled by default (`recommendations.ai.enabled: false`) and, even
when enabled, is a **second, independent** opt-in from watch-history sharing:

- `recommendations.use_plex_watch_history` controls whether watch history
  informs *scoring* at all.
- `recommendations.ai.share_watch_history` controls whether that
  already-opted-in watch history signal is *additionally* passed to a
  configured AI provider. Turning on the first does not turn on the second.

When both are enabled, the only watch-history-derived data an AI provider
ever receives is a short list of recently-watched **titles** (see
`RerankContext.recent_watch_titles` in
`backend/core/recommendations/ai_provider.py`) — never Plex tokens, file
paths, timestamps, device info, or any other viewing metadata. The
`RerankContext` and `ScoredCandidateSummary` types passed to a provider are
deliberately minimal dataclasses that cannot structurally carry more than
that (see the "cannot carry sensitive data" tests in
`tests/backend/test_recommendation_ai_provider.py`) — this is enforced by
the type shape itself, not just by convention.

AI is never given:
- Plex tokens, server URLs, or any service credentials;
- file paths (recommendation data has no file paths to give it in the first
  place — the whole feature never touches the filesystem);
- more viewing history than the two opt-ins above explicitly allow;
- the ability to bypass scoring filters, invent titles, or trigger a
  download/replacement directly (the base engine's output is fully
  determined before AI ever runs, and every AI-returned TMDB ID is
  re-validated against TMDB before use — see
  `docs/RECOMMENDATION_ARCHITECTURE.md`'s AI section).

Only `NoOpExplanationProvider` ships in this release — no data leaves your
instance for AI purposes today regardless of configuration, since no real
provider adapter is implemented yet (see Known Limitations in
`docs/RECOMMENDATION_ARCHITECTURE.md`).
