# Changelog

All notable changes to Slimarr are documented here.

---

## [1.2.0.0] - 2026-05-04

### Release focus

Eliminated the only C-compiled Python dependency (`lxml`) and tightened Python version
guards to make source installs seamless on any supported Python version.

**lxml dependency removed**
- `backend/integrations/newznab.py` now uses `xml.etree.ElementTree` (Python stdlib) instead
  of `lxml` to parse Newznab RSS/Atom responses. The API is identical, so behaviour is
  unchanged. This removes the last dependency that required a C++ compiler or prebuilt wheel.
- `lxml==5.3.0` removed from `requirements.txt`.
- Source installs now require **zero** native compilers — all remaining packages have
  prebuilt wheels for Python 3.11, 3.12, and 3.13 on Windows.

**Tightened Python 3.14 guard in install.ps1**
- Added a post-venv-creation version check: even if the venv somehow ends up on Python 3.14
  (e.g. leftover venv from an old install), the script now aborts with a clear error message
  before attempting `pip install`, rather than letting pip fail with cryptic build errors.
- Updated pip-failure message to reflect that pydantic-core (not lxml) is the remaining
  reason Python 3.14 is unsupported.

**Milestone A safety hardening**
- Added centralized API error envelopes with `code`, `message`, `details`, and
  `correlation_id` fields, plus global exception mapping in `backend/main.py`.
- Added correlation ID middleware (`X-Correlation-ID`) so API errors and server logs can be
  traced per request.
- Updated core API routes to use shared error helpers instead of mixed ad-hoc `HTTPException`
  responses.

**Milestone A backend tests**
- Added focused backend unit tests for comparison decisions, Radarr post-replace policy
  behavior, and replacer-to-Radarr policy bridge dispatch.
- New test files:
  - `tests/backend/test_comparer.py`
  - `tests/backend/test_radarr_policy.py`
  - `tests/backend/test_replacer_policy_bridge.py`

**Audit and observability improvements**
- Added system audit events for auth and settings actions:
  - login success/failure
  - active lockout checks
  - first-user registration
  - settings update writes and integration enabled/disabled toggles
- Extended `activity_log` with `actor` and `details` fields (additive migration) and exposed
  them in the Activity API output.
- Added correlation-id-enriched logging format and request lifecycle logs with method, path,
  response status, and latency.

**Task idempotency safeguards**
- Added guarded background-task start logic for manual task triggers to prevent duplicate starts
  while a matching task key is already running.
- Applied guards to scheduler task runs, full scan trigger, cleanup trigger, and full cycle start.

**Diagnostics bundle**
- Added a one-click diagnostics export endpoint at `/api/v1/system/diagnostics/bundle` that
  packages redacted config, system/integration health snapshots, and recent log tail into a zip
  for easier support troubleshooting.

**API contract improvements**
- Added shared Pydantic response models and wired them into core API routes for clearer OpenAPI
  docs and safer frontend type expectations.
- Covered auth check, dashboard stats/history/activity, library movie/search/action endpoints,
  queue endpoints, and activity list responses.
- Aligned auth dependency failures (API key/JWT/auth required) with centralized error envelopes
  for consistent unauthorized response payloads.
- Expanded response-model coverage to `system`, `settings`, and `tv` routers for health,
  preflight, matrix, update/task actions, blacklist, settings test, and TV cleanup endpoints.
- Added API contract test coverage to assert key routes keep declared response models.

---

## [1.1.2.0] - 2026-05-04

### Release focus

Installer reliability, Python version guardrails, and one-click launcher improvements.

**Critical installer fix**
- Fixed a silent bug in `build-installer.ps1` where the generated `dist/Slimarr/start.bat` had
  a broken health-check loop — PowerShell variables (`$deadline`, `$resp`) were being expanded
  to empty strings by the double-quoted here-string, causing the health-check to silently fail
  and the browser to open before the backend was ready. Changed to single-quote here-string
  (`@'...'@`) so the embedded PowerShell script is written literally and evaluated correctly.

**Python 3.14 guardrails**
- `install.ps1` now rejects Python 3.14 with a clear explanation: `lxml` and `pydantic-core`
  have no prebuilt wheels for 3.14 yet and require Visual C++ Build Tools / Rust to compile
- Candidate order is now explicit: 3.13 → 3.12 → 3.11; uses `py -3.13`, `py -3.12`, `py -3.11`
  launcher args instead of `py -3` (which would resolve to 3.14 if installed)
- Existing venv is deleted and recreated if it was built on Python 3.14
- Python version is printed after venv creation to make diagnostics easier
- `requirements.txt` has a comment block explaining the 3.11–3.13 constraint

**Launcher improvements**
- `start.bat` (source install) now polls `/api/v1/system/health` for up to 60 seconds before
  opening the browser — prevents opening to a blank page while the backend is still starting
- `install.ps1 -Start` (`Start-SlimarrUi`) does the same health-check polling before browser open
- `tray.py` health-check deadline extended from 30 seconds to 60 seconds (consistent with launchers)

**Updater improvements**
- `update.bat` now rebuilds the React frontend after `git pull` so UI changes are reflected
  immediately without a separate `npm run build` step; skips gracefully if node_modules is absent

**Installer data directories**
- `installer/slimarr.iss` now pre-creates `{userappdata}\Slimarr\data\recycling` at install time
  so recycling-bin moves succeed on first replacement without requiring a manual folder creation

**README / documentation**
- Requirements table updated: Python 3.11–3.13 only (3.14 not yet supported)
- New Troubleshooting section covering lxml/pydantic-core build failures and WinError 10013
  (firewall blocking PyPI) with step-by-step fixes

---

## [1.1.0.0] - 2026-04-30

### Release focus

Dashboard command-center polish, safer replacement decisions, and clearer integration state.

**Implemented so far**
- Added `docs/VERSION_1_1_PLAN.md` with the v1.1 implementation audit and phased plan
- Added confidence scoring metadata for replacement candidates, including size, codec, resolution, source, language, title/year certainty, and reliability components
- Persisted confidence scores and breakdowns on search results and decision audit logs with additive SQLite migrations
- Strengthened candidate matching with title/year certainty checks and upscaled-release rejection
- Added dry-run and review-required automation gates so accepted candidates can be inspected without automatic downloads/replacements
- Expanded Dashboard stats with library size, pending candidates, failed items, last successful scan, and active download counts
- Added a user-facing Integration Matrix for Plex, Radarr, Sonarr, Prowlarr, SABnzbd, NZBGet, TMDB, and direct indexers
- Added a Movie Detail candidate drawer showing confidence breakdowns and rejection reasons
- Made Settings connection tests use unsaved form values for Plex, TMDB, SABnzbd, NZBGet, and Prowlarr
- Updated config examples with v1.1 safety and automation settings

---

## [1.0.0.5] - 2026-04-28

### Release focus

Manual download recovery, stale NZB visibility, and stuck queue repair.

**Search and candidate quality**
- Added resolution and NZB age columns to manual movie search results so old/stale posts are visible before downloading
- Persisted NZB age from indexer publish dates into search results and API responses
- Added age-aware comparison scoring and max-age rejection using `comparison.max_candidate_age_days`
- Penalized stale candidates using `quality.stale_release_days` while lightly favoring fresh posts

**Download recovery**
- Added a safer downloader submission handoff that creates a Slimarr tracking row before submitting to SABnzbd/NZBGet
- Added startup resume for downloads left in `downloading` after restarts or crashed background tasks
- Added `POST /queue/resume` and a Queue page "Resume Stuck" action to manually restart stuck monitor tasks
- Added a configurable active-download timeout (`schedule.max_active_download_hours`, default 24h) so old `downloading`/`submitting` rows fail cleanly and can retry
- Added an hourly stale-download recovery scheduler to catch silent stuck rows while Slimarr is still running
- Treated SABnzbd post-processing states such as `extracting`, `verifying`, `repairing`, and `queued` as in-progress instead of terminal failures
- Hardened SABnzbd queue parsing when progress percentage is missing or null

**Replacement reliability**
- Added fallback same-folder backup handling when recycling-bin moves fail, so replacements can proceed safely when the recycle disk is full
- Restores the backed-up original file if moving the completed download into place fails
- Added preflight free-space checks for recycle-bin and target-drive moves before replacement

**Upgrade safety**
- Added an additive SQLite migration for `search_results.age_days` so upgraded installs can use NZB age columns without resetting data

---

## [1.0.0.4] — 2026-04-28

### Planned focus

Usability polish, ecosystem expansion, and higher-confidence automation workflows.

**Implemented so far**
- Optimized System health checks:
  * Parallelize integration probes instead of checking services one by one
  * Cache health probe results briefly so the System page and Health Matrix do not duplicate network checks
  * Refresh the Integration Status panel on an interval to match the Health Matrix freshness
- Added production frontend chunk splitting for charts, sockets, icons, and remaining vendor code to reduce oversized main bundle risk
- Added route-level lazy loading so major pages are loaded on demand instead of bundled into the initial app payload
- Added automation preflight checks before full-cycle start:
  * Blocks cycles when critical services/search sources are unavailable
  * Warns about queue saturation, pending failed-download cleanup, optional integration issues, and low disk headroom
  * Adds a System page preflight panel with per-check status details
- Improved Queue page UX:
  * Unified active/recent refresh path with manual refresh and 15-second fallback polling
  * Added active/completed/failed summary counters
  * Added recent-download status filters and timestamps
  * Improved responsive row layout for long release names and error messages
- Added service-health cache invalidation after settings saves so connection status reflects configuration changes quickly
- Improved Settings page review workflow:
  * Added inline validation for malformed URLs, invalid numeric ranges, incomplete active downloader config, and missing search sources
  * Added quick-jump section navigation for long Settings pages on smaller windows
  * Added downloader capability display for SABnzbd/NZBGet support coverage
- Added a download-client capability matrix and API so future clients can declare support for submit, queue/history status, purge, categories, pause/resume, and storage-path lookup
- Added active-downloader capability checks to automation preflight
- Added installer frontend asset-manifest smoke test so packaging fails early if `frontend/dist/index.html` references missing built assets
- Added additive SQLite startup migrations for existing installs so failed-download retry/cleanup metadata columns are created without resetting user data
- Hardened SABnzbd failure recovery:
  * Capture SAB failure messages and storage paths for incomplete/aborted jobs
  * Purge failed jobs from both SAB queue and history
  * Clean failed download folders automatically before retrying alternatives
  * Route manual and scheduled downloads through a shared monitor/replace/cleanup/retry workflow
- Improved retry behavior:
  * Retry only accepted replacement candidates
  * Skip every release already attempted for the movie
  * Avoid retrying generic blacklisted releases even if they came from a different indexer
  * Mark movies as failed when all retry/replacement paths are exhausted instead of leaving them stuck as downloading
- Improved orphan cleanup:
  * Match downloader jobs against both raw and client-prefixed Slimarr job IDs
  * Capture SAB orphan storage paths correctly
  * Make the Orphaned Downloads cleanup action purge downloader history and delete orphaned files/folders immediately

**UI and usability (planned)**
- Sidebar resilience on smaller windows:
  * Ensure navigation remains reachable when viewport height is constrained
  * Keep footer actions visible while allowing menu items to scroll
- Additional responsive polish pass across pages with long action stacks beyond System/Settings/Queue

**Integration opportunities under investigation**
- Bazarr companion integration:
  * Trigger subtitle refresh/search after successful replacements
  * Surface missing subtitle counts per media item in Slimarr UI
- Lidarr integration (music):
  * Evaluate extending Slimarr's scoring/replacement model to albums/tracks
  * Reuse existing downloader/indexer plumbing for audio workflows
- Whisparr parity integration:
  * Reuse Sonarr-like API patterns for monitor/unmonitor and post-import sync
  * Keep feature toggled/optional like current Radarr/Sonarr integration approach
- Readarr status note:
  * Readarr is currently retired by the Servarr team, so direct integration is lower priority unless ecosystem support stabilizes

**Reliability and automation candidates**
- Smarter retry windows (time-based backoff + indexer/uploader failure weighting)
- Integration health history (not just latest state) for trend-based diagnostics
- Persist preflight and health snapshots for trend views instead of keeping only the latest result

**Packaging and performance candidates**
- Installer/package footprint audit (exclude unnecessary test modules from packaged runtime where safe)

## [1.0.0.3] — 2026-04-27

### Release focus

Failed download recovery, retry automation, and downloader hygiene. This release adds comprehensive tooling to detect, diagnose, recover, and prevent repeated failed downloads, including cleanup workflows, retry ladder logic, blacklist memory, orphan discovery, and richer quality/comparison rules.

**Failed download handling**
- Added `cleanup_status` field to download records to track cleanup attempts (`"pending"` | `"cleaned"` | `"error"`)
- Implemented `purge_job()` on both SABnzbd and NZBGet clients to remove jobs from downloader history via native APIs
- Added `cleanup_failed_download()` async function to orchestrate cleanup:
  * Calls client API to purge job from history
  * Deletes local storage folder (tree deletion for incomplete paths)
  * Records cleanup outcome in database
  * Emits `download:cleanup` event for real-time UI updates
  * Handles edge cases: missing folders, API errors, permission issues

**Failed downloads UI page**
- New "Failed Downloads" navigation link in sidebar (AlertCircle icon)
- Dedicated page listing all failed downloads with:
  * Release title and error reason
  * Storage folder path (formatted for readability)
  * Cleanup status indicator (pending | cleaned | error)
  * "Clean Folder" button — manually trigger cleanup for any failed download
  * "Retry Search" button wired to retry ladder API
  * Real-time updates via `download:cleanup` socket events
- Pagination ready (initial: 50 failed downloads per page)

**Retry ladder and failure recovery (Phase 2A)**
- Added retry metadata to downloads:
  * `retry_count`
  * `grabbed_at`
  * `last_error_at`
  * `blacklist_reason`
- Added retry endpoint: `POST /queue/{id}/retry`
- Implemented retry selection flow that:
  * Verifies retry eligibility and max retry count
  * Selects next candidate by score while skipping failed/blacklisted options
  * Starts replacement download and schedules monitor flow
  * Carries retry metadata forward for diagnostics
- Failed Downloads page "Retry Search" action is now fully wired to backend retry flow

**Blacklist memory and management**
- Added persistent blacklist table and logic to prevent repeated attempts of bad releases
- Added blacklist CRUD endpoints:
  * `GET /settings/blacklist`
  * `POST /settings/blacklist`
  * `DELETE /settings/blacklist/{release_hash}`
- Added dedicated Blacklist management page in UI with add/remove workflows
- Added blacklist expiry/cleanup support for temporary and timed entries

**Orphan scanner and cleanup tooling (Phase 2B)**
- Added orphan tracking table for downloader jobs/folders not represented in Slimarr DB
- Added orphan scanner service for SABnzbd and NZBGet history reconciliation
- Added orphan endpoints:
  * `GET /queue/orphaned`
  * `POST /queue/orphaned/{id}/cleanup`
- Added dedicated Orphaned Downloads page for review and manual cleanup scheduling
- Scheduler now includes:
  * Daily orphan scan job (04:00 UTC)
  * Periodic downloader health pulse (every 30 minutes)

**Quality and comparison enhancements**
- Parser now extracts additional metadata:
  * uploader/group (`uploader`)
  * release freshness (`release_age_days`)
- Comparison engine now applies stricter and richer decision rules:
  * Strong preference for higher resolution (including smaller 4K upgrades)
  * Preferred-language enforcement with safer handling for untagged releases
  * Staleness penalties for older releases
  * Uploader health scoring and low-health rejection thresholds

**Uploader health tracking**
- Added uploader statistics table with success/failure/corruption counters and computed health score
- Download monitor now updates uploader health stats on completion/failure paths
- Comparison pipeline uses uploader health data to reduce repeat failures

**API additions**
- `GET /queue/failed?limit=50` — fetch failed downloads with cleanup metadata
- `POST /queue/{id}/cleanup` — manually trigger cleanup for a download
- Updated `/queue/active` and `/queue/recent` responses to include `storage_path` and `cleanup_status`
- Updated queue payloads to include retry metadata fields for diagnostics and UI state

**Diagnostics**
- Download model now tracks:
  * `storage_path` — downloader's folder location (captured from job metadata)
  * `cleanup_status` — cleanup attempt outcome
- Added explicit retry/failure timing metadata in API output for supportability
- Logs now include full storage paths for failed jobs, making it easy to diagnose orphaned folders
- Failed downloads are queryable by status, making audit and recovery workflows simpler

**Download client improvements**
- Download client protocol now defines `purge_job()` contract — all downloader adapters must implement it
- SABnzbd client now uses `queue?action=delete` API for clean history removal
- NZBGet client now uses `editqueue` RPC with `GroupDelete` operation for job removal
- Client purge failures are non-fatal and logged as warnings (cleanup continues with folder deletion)

**System and UX quick wins**
- Added quick stats block in System page for active downloads, total movies, and improved items
- Added navigation links/routes for Orphaned Downloads and Blacklist pages
- Extended frontend API/types for retry/orphan/blacklist workflows

**Post-merge improvements (same 1.0.0.3 release)**
- Added end-to-end health matrix API (`GET /system/health/matrix`) covering API, DB, queue, scheduler, orchestrator, recycling bin, and integration summaries
- Added release decision audit logging with persistent decision rationale and endpoint (`GET /system/decision-audit`)
- System page now includes a live Health Matrix panel and recent Release Decision Audit feed
- Orphan auto-cleanup now deletes orphaned storage paths from disk before removing stale orphan records

---

## [1.0.0.2] — 2026-04-23

### Release focus

This release hardens replacement reliability and adds final UX polish for production rollout.

**Settings and file management**
- Added live recycling bin usage in Settings (file count + total size)
- Added one-click "Empty Recycling Bin" action in Settings with confirmation and freed-space feedback
- Recycling bin stats now auto-refresh in the UI for live monitoring

**Reliability**
- Hardened SAB completion flow so replacement only proceeds when SAB history provides a valid storage path
- Improved logging for failed replacement outcomes to make diagnostics clearer

**UI and polish**
- Updated browser favicon to use the dedicated square app icon
- Added backend favicon routes so icon loads correctly in packaged and source deployments

**Release packaging**
- Version bump to `1.0.0.2` across backend API/app, frontend package metadata, and installer
- Windows installer output updated to `SlimarrSetup-1.0.0.2.exe`
- Installer build script now reports the newest generated installer artifact correctly when multiple versions exist in `dist/installer`

## [1.0.0.1] — 2026-04-22

### Initial release

**Core features**
- Movie library management via Plex + Radarr integration
- TV series management via Sonarr integration
- SABnzbd download queue integration — trigger, monitor, and complete downloads
- TMDB metadata lookup for movies and shows
- Prowlarr + custom indexer support

**System**
- System health page showing live status of all connected services (Plex, SABnzbd, Radarr, Sonarr, Prowlarr, TMDB, indexers)
- GitHub update checker — badge shown in System page when a new release is available
- Nightly scheduler: library sync at 01:00 UTC, recycling bin cleanup at 03:00 UTC
- Real-time event feed via WebSocket (Socket.IO)

**File management**
- Automatic file relocation after download completes — moves file to Plex library folder, removes old copy
- Plex path mapping — translate Plex-reported paths to locally accessible paths when Slimarr runs on a different machine
- Recycling bin support (optional) — deleted files moved to a holding folder before permanent removal
- Download folder cleanup on all exit paths (success and failure) to prevent disk bloat

**Settings**
- Full settings UI: Plex, SABnzbd, Radarr, Sonarr, Prowlarr, TMDB, indexers, files, path mappings
- Test connection buttons for Radarr and Sonarr (reads live form values, not just saved config)
- SSL verify disabled for local HTTPS endpoints

**Windows installer**
- All-in-one `SlimarrSetup-1.0.0.1.exe` — no Python or prerequisites required
- Embeds full Python runtime, all dependencies, and the React frontend
- System tray icon with Open / Restart / Quit options
- Optional desktop shortcut and Windows startup entry
- Config and database stored in `%AppData%\Slimarr`

---
