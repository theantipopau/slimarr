# Slimarr v1.1 Implementation Plan

## Current State

Slimarr already has the core Plex -> search -> compare -> download -> replace workflow, SABnzbd/NZBGet adapters, Prowlarr/Newznab search, TMDB enrichment, Radarr/Sonarr touch points, queue recovery, failed-download cleanup, blacklist memory, health matrix, decision audit logs, and automation preflight checks.

The main gaps for v1.1 are polish and safety depth rather than basic plumbing. The live `logs3.md` run shows several high-priority risks: loose title/year matching can accept wrong releases, "multi"/foreign-language releases are sometimes trusted too easily, upscaled releases are not clearly penalized, recycle-bin space pressure needs clearer blocking, and users need better decision visibility before downloads start.

## Already Implemented

- Plex movie scanning with TMDB/Radarr image enrichment.
- Prowlarr and direct Newznab search paths.
- SABnzbd and NZBGet submit/monitor/purge support.
- Comparison rules for smaller size, minimum savings, minimum size, resolution downgrade, language tags, stale NZBs, preferred codecs, and uploader health.
- Persistent search results and decision audit logs.
- Queue, failed-download, orphan-download, blacklist, TV stale-media, system health, and settings pages.
- Basic preflight checks for cycle state, queue saturation, failed cleanup, downloader capabilities, required integrations, search source availability, and disk headroom.
- Radarr rescan after movie replacement and Sonarr unmonitor for TV-show deletion.

## Duplicated, Half-Finished, or Fragile Areas

- Dashboard and System duplicate integration/status concepts; Dashboard lacks the requested single command-center view.
- Settings uses unsaved values only for Radarr, Sonarr, and direct indexers. Plex, TMDB, SABnzbd, NZBGet, and Prowlarr still test saved config.
- Health matrix exists but is system-oriented, not an integration matrix with user-facing service purposes and dependency links.
- Comparison scoring is a single numeric blend and does not expose component scores for size, codec, resolution, source, language, match certainty, and indexer/uploader reliability.
- Title/year matching is too weak. Search results are compared by file attributes, not by release identity certainty.
- Dry-run and review-required modes are not present.
- Exclusions are limited to download blacklist entries, not media/folder/codec/resolution/size/age rules.
- Search result details are shown inline only; there is no candidate details drawer/modal.
- Queue/recent/failed/orphan pages have basic filtering but no unified table/search/sort model.
- API errors are inconsistent: some endpoints return `{success:false}`, some return plain status objects, and some raise FastAPI defaults.
- No dedicated test suite exists in the repository.
- `build-installer.ps1` rewrites a reduced `config.yaml.example`, which risks dropping newer config keys during packaging.

## v1.1 Scope

### 1. GUI Command Center

- Redesign Dashboard around operational cards:
  - Library size
  - Total savings
  - Pending candidates
  - Active downloads
  - Failed items
  - Last successful scan
  - Integration health
- Add an Integration Matrix panel with Plex, Radarr, Sonarr, Prowlarr, SABnzbd/NZBGet, TMDB, and indexers.
- Add clear badges for connected, degraded, disabled, and unavailable states.
- Improve Queue, Failed Downloads, Orphaned Downloads, Activity, and Movie Detail result tables with search, filtering, sorting, compact status badges, and better empty states.
- Add a candidate details modal/drawer showing accepted/rejected status, confidence score, component factors, savings, metadata, and rejection reasons.
- Keep the desktop app dense, modern, responsive, and operational rather than marketing-like.

### 2. Integration Interconnection

- Extend service health responses with purpose text, active/optional flags, and degradation causes.
- Make every settings test button prefer current unsaved form values where practical.
- Add explicit path mapping validation:
  - Missing Plex prefix
  - Missing local path
  - Local path does not exist
  - Mapping would not affect known Plex paths
- Strengthen preflight to block path-mapping failures, missing local file paths, invalid selected downloader config, no usable search source, and dangerous recycle/target disk pressure.
- Document how Plex, Radarr, Sonarr, Prowlarr, download clients, TMDB, and local file paths cooperate.

### 3. Accuracy and Safety

- Preserve the hard rule: never replace with a larger file.
- Add candidate confidence scoring components:
  - Size reduction
  - Codec improvement
  - Resolution match or upgrade/downgrade
  - Source quality
  - Preferred language match
  - Movie title/year certainty
  - Indexer/uploader reliability
- Add hard rejection reasons for title/year mismatch, suspicious year mismatch, obvious upscales when downgrades are disallowed, too-large candidates, missing size, too-small candidates, stale posts, bad uploader health, wrong language, and missing local source file.
- Add dry-run mode so scan/search/compare can run without download, move, delete, replace, cleanup, or Plex/Radarr refresh side effects.
- Add review-required mode that stores accepted candidates as pending approval instead of downloading automatically.
- Add more decision logging to make every accept/reject explainable in the UI.

### 4. Additional Functionality

- Add manual Analyse Item and Search Replacement Now actions for movies first; extend to episodes later.
- Add exclusion rules for movies/shows, folders, codecs, resolutions, minimum file size, and maximum age.
- Add savings reports by movie, show, library, and date range.
- Add CSV/JSON export for history and savings.
- Add notification hooks if practical, starting with generic webhook and Discord webhook.
- Add config/database backup and restore if time permits.

### 5. Code Quality and Tests

- Introduce shared API response/error helpers for consistent errors.
- Keep backend service boundaries clear: routers orchestrate, services decide, integrations only call remote systems.
- Strengthen TypeScript types for settings, health, search results, and dashboard summaries.
- Add focused backend tests for:
  - Comparison and confidence scoring
  - Title/year match rejection
  - Path mapping and path validation
  - Dry-run non-mutating behavior
  - Preflight blocking logic
- Add frontend build verification and packaging smoke checks.

## First Implementation Slice

1. Add v1.1 config fields and migrations for dry-run/review/exclusion/confidence metadata.
2. Strengthen comparison with title/year certainty, source quality, component scoring, and clearer rejection reasons.
3. Add backend dashboard summary and integration matrix endpoints.
4. Add path mapping validation endpoint and include it in preflight.
5. Redesign Dashboard and improve Movie Detail candidate visibility.
6. Make settings test buttons use unsaved values for all integrations.
7. Update README, CHANGELOG, config example, installer metadata, and frontend package version.
8. Add focused tests where practical and run frontend/backend verification.

## Slice 1 Progress

- Added confidence metadata fields and startup migrations for search results and decision audit rows.
- Started hardening comparison with title/year certainty, upscaled-release rejection, confidence scoring, and component breakdowns.
- Added dry-run and review-required gates before automatic downloads/replacements.
- Added dashboard summary fields and a user-facing integration matrix endpoint.
- Started exposing candidate confidence details in the Movie Detail UI.
- Made Settings connection tests send unsaved Plex, TMDB, SABnzbd, NZBGet, and Prowlarr form values.

## Known v1.2 Follow-Ups

- Episode-level replacement workflow and confidence scoring.
- Health history over time rather than latest-only snapshots.
- Notification templates and per-event routing.
- Advanced retry backoff using indexer/uploader failure weights.
- Full backup/restore UI with scheduled backup retention.
- Broader frontend table abstraction to remove repeated list/table code.
