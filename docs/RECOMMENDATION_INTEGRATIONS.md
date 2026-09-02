# Recommendation & Collection Completion — Integrations

Covers every external system the recommendation feature touches: what it
calls, what it never calls, and — for the Radarr/Sonarr/Seerr hand-off
actions specifically — the capability-detection model the brief this release
was built against required explicitly.

## TMDB

The sole metadata source for deterministic sourcing, correlation enrichment,
and streaming availability. New `TMDBClient` methods added for this feature
(`backend/integrations/tmdb.py`):

- `get_movie_full(tmdb_id)` — movie details plus `belongs_to_collection`,
  `credits`, `recommendations`, and `similar` in one request via TMDB's
  `append_to_response`, rather than four separate round-trips per candidate.
- `get_collection(collection_id)` — full collection membership.
- `get_external_ids(tmdb_id)` — IMDb/TVDB IDs for a sourced candidate (needed
  for Radarr/Sonarr correlation, since those key on IMDb/TVDB, not TMDB IDs).
- `get_watch_providers(tmdb_id, media_type)` — TMDB's own aggregated,
  region-keyed provider listing (itself sourced from JustWatch under TMDB's
  API terms — see `docs/RECOMMENDATION_PRIVACY.md` for the attribution
  requirement this imposes).

These methods use the app's shared pooled `httpx.AsyncClient`
(`backend.main.get_http_client()`) rather than opening a new connection per
call, and retry transient 429/5xx responses with jitter (respecting
`Retry-After`) while failing permanent 4xx responses immediately — see
`docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md` finding A5. The original,
pre-existing TMDB methods (`search_movie`, `get_movie`, `find_by_imdb`,
`download_image`) are unchanged in this release.

## Radarr / Sonarr — correlation (read-only)

`backend/core/recommendations/correlation.py` fetches each configured
service's full movie/series list **once per refresh run** (not once per
candidate — see the audit's N+1 finding this specifically addresses) to
determine what's already managed, so recommendations for
already-managed titles are surfaced as `already_managed` rather than
`active`. A fetch failure degrades to "nothing is managed" rather than
aborting the whole refresh.

## Radarr / Sonarr — hand-off (write, explicit user action only)

`POST /api/v1/recommendations/{id}/send-to-radarr` and `.../send-to-sonarr`:

- Require the user to supply `root_folder_path` and `quality_profile_id`
  explicitly in the request body — Slimarr never guesses these. The
  frontend is expected to populate pickers from `RadarrClient.get_root_folders()`
  / `get_quality_profiles()` (added alongside `add_movie()`/`add_series()`
  in this release) before offering the action.
- Re-check "already managed" immediately before adding (not just relying on
  the correlation snapshot, which may be a few minutes stale) — a genuine
  duplicate-prevention check at the moment of action, not just at scoring
  time.
- Reject a mismatched media type (a TV candidate can't be sent to Radarr,
  and vice versa) and a TV candidate missing a TVDB ID (Sonarr requires one).
- On success, mark the `Recommendation` row `actioned` and append a
  `RecommendationFeedback` row recording the resulting Radarr/Sonarr ID —
  Radarr/Sonarr remain the system of record after hand-off; Slimarr does not
  track the movie/series further once sent.
- Never run automatically. There is no code path that calls `add_movie()`
  or `add_series()` except this explicit, user-clicked endpoint.

## Seerr (Overseerr / Jellyseerr) — capability detection only, not implemented

`GET /api/v1/recommendations/capabilities` reports Seerr hand-off as
**unavailable** unconditionally in this release:

```json
{"seerr": {"available": false, "reason": "Seerr hand-off requires verifying the configured instance's actual API version against live capability detection, which this release does not yet implement..."}}
```

This is a deliberate scoping decision, not an oversight. The brief this
release was built against explicitly requires, before implementing Seerr
submission:

> inspect current, authoritative API documentation or the local configured
> service's API schema; do not assume legacy Overseerr and current Seerr
> endpoints are identical; perform capability detection

No live Seerr/Overseerr instance was available to verify against during
this implementation, and the brief is equally explicit that guessing is
worse than not implementing:

> If an external API is insufficiently documented, implement an interface
> and disabled capability state rather than guessing its behaviour.

**What exists today:** the capability-detection response shape above, which
a frontend can check before offering the action at all (matching the
"disable the action gracefully" requirement) — and the `sent_to_seerr`
action code already reserved in `RecommendationFeedback.action`'s
vocabulary, so adding real submission later doesn't require a schema change.

**What a future implementation needs to do**, concretely:
1. Fetch `{seerr_url}/api/v1/status` (or the equivalent for the configured
   instance) and compare against known Overseerr vs. Seerr version markers
   — do not assume based on user-entered URL or product name alone.
2. Only report `available: true` once that check has run successfully
   against the user's actual configured instance, not merely because a URL
   and API key are present (the way Radarr/Sonarr's simpler check above
   works, since those two products don't have Seerr's fork-divergence risk).
3. Submit a request through whatever the detected version's actual endpoint
   and payload shape is, and never bypass Seerr's own approval/permission
   rules (the brief is explicit that Slimarr must not go around Seerr's own
   configured approval workflow).

## Plex

No new Plex API calls are added by the deterministic engine — it reads
`Movie` rows Slimarr's existing scanner already populated. Plex watch
history integration (opt-in, `use_plex_watch_history`) is a **future**
extension point documented here and in `docs/RECOMMENDATION_ARCHITECTURE.md`'s
Known Limitations — the `CandidateSignals.recent_source_activity` field
exists in the scorer today but nothing currently populates it, since wiring
real Plex watch-history reads is out of scope for this increment.

## What is explicitly never called

- No streaming service's own API or website (Netflix, Disney+, Prime Video,
  etc.) — TMDB's aggregated `/watch/providers` data is the only source, per
  the brief's explicit prohibition on scraping.
- No download client (SABnzbd/NZBGet) is ever invoked from any code path in
  `backend/core/recommendations/` — verified by the audit's boundary check
  in `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md` §4.
