# Changelog

All notable changes to Slimarr are documented here.

---

## [2.0.0.0] - 2026-09-03

Standalone release summary: `docs/UPGRADE_NOTES_2.0.0.md`

A full backend/frontend audit against the actual implementation (not README
claims), a competitive gap analysis against mature *arr platforms, two
confirmed correctness fixes, and a new deterministic **Discovery &
Recommendations** feature.

- **New: Discovery & Recommendations.** Slimarr can now suggest titles
  related to what you already own - missing collection entries, sequels/
  prequels, and related titles - scored deterministically with a
  transparent, human-readable reason for every suggestion. Off by default
  (`recommendations.enabled: false`). See `docs/RECOMMENDATION_ARCHITECTURE.md`.
- **New: region-specific streaming availability.** Looked up per-title via
  TMDB's own `/watch/providers` endpoint only - no streaming service is
  scraped or asked for credentials, and availability is timestamped and
  treated as stale after 24 hours rather than shown as current indefinitely.
- **New: explicit hand-off to Radarr/Sonarr from Discovery.** Sending a
  recommendation to Radarr or Sonarr requires you to confirm the root
  folder and quality profile; it's a separate, explicit action, never an
  automatic one, and duplicate-checked against the live instance first.
  Seerr hand-off is intentionally not implemented this release - see
  `docs/RECOMMENDATION_INTEGRATIONS.md` for the capability-detection
  rationale.
- **New: optional, provider-neutral AI reranking abstraction** (disabled by
  default, no provider shipped enabled). It can only rerank a candidate
  list Slimarr already sourced or produce short explanations - it cannot
  invent titles or availability, cannot see your Plex token, file paths, or
  more watch history than explicitly opted in, and cannot trigger a
  download. Every AI-returned ID is re-validated against TMDB before
  display.
- **Fixed:** `auto_cleanup_old_orphans()` deleted its tracking row before
  confirming the underlying file removal actually succeeded, so a failed
  cleanup could silently lose track of an orphaned download. It now checks
  the removal outcome first and only clears the row on confirmed success.
- **Fixed:** SABnzbd connection-test and job-purge error paths could log an
  API key embedded in a request URL inside an exception message. Errors are
  now redacted before logging, matching the existing redaction behavior
  used elsewhere in the codebase.
- **Fixed:** a storage path containing an embedded `..` segment (e.g.
  `/mnt/local/../nas/movies`) could evade NAS-prefix classification,
  skipping budget/throttle/cooldown protection entirely. Paths are now
  collapsed before classification.
- **Fixed:** on a case-sensitive filesystem (Linux/most Docker/NAS-via-NFS),
  path classification lowercased unconditionally, which could cause a false
  NAS match or a false miss depending on how `nas_path_prefixes` was cased.
  Case is now only folded on Windows.
- **Fixed:** if a cross-device NAS copy's final source-file cleanup failed
  after the copy itself had already succeeded, the whole move was reported
  as `failed` even though the target had a complete, correct copy - leaving
  a duplicate and a misleading status. It's now reported as completed with
  an explicit warning instead.
- **Fixed:** the image-proxy endpoint could leak a raw exception (including
  local filesystem paths) to any client on a cache-fetch failure; it's now
  logged server-side only.
- **Fixed:** a job's event timeline had no upper bound, so a job retried
  many times returned an ever-growing array from `GET /jobs/{id}`. Capped
  to the most recent 200 events.
- TMDB, Radarr, and Sonarr's original API methods now reuse the app's
  pooled HTTP client instead of opening a new connection per call (Radarr/
  Sonarr only when the instance's own TLS-verification setting agrees with
  the shared client's, so a self-signed-cert setup is never silently
  affected).
- Two low-severity silent-failure spots (`/metrics` DB query, diagnostics
  bundle NAS summary) now leave a debug-level trace instead of swallowing
  the exception entirely.
- **New: send a recommendation straight to Radarr/Sonarr from Discovery.**
  A hand-off modal fetches the target instance's root folders and quality
  profiles live, lets you pick monitored/search-now, and calls the
  existing (previously unreachable from the UI) send-to-radarr/sonarr
  endpoints - closing the biggest functional gap in the initial Discovery
  ship, where this control was a non-interactive placeholder.
- **New: pagination and a streaming-provider filter on the Discovery page.**
  The list endpoint always supported `page`/`per_page` and a `provider_id`
  filter, but the page fetched one fixed batch of 60 with no way to reach
  anything past it, and the provider filter had no UI at all. A "Load more"
  control and a provider dropdown (backed by a new
  `GET /recommendations/providers`) close both gaps.
- Discovery UI polish: an "Open on TMDB" link and TMDB-attributed
  availability chips on every card, a "Copy TMDB ID" action, and a full
  Discovery & Recommendations configuration section in Settings.
- **Fixed (GitHub issue #1):** the NAS write-budget reservation charged a
  same-directory rename (`backup_existing_target`'s metadata-only,
  zero-byte `os.rename()`) at full file size, since it only checked whether
  the *target* classified as NAS/network rather than whether source and
  target were on the same device. On the reporter's production instance
  this exhausted a 300GB/day budget on phantom writes alone, then blocked
  genuine replacements and discarded already-downloaded releases. Now
  skipped whenever `_same_storage_device()` is true.
- **Fixed:** a NAS failure cooldown was purely in-process, so a restart
  right after a failure silently dropped it and let the next replacement
  hit the same failing share immediately. Now restored from
  `StoragePathHealth` on startup.
- **Fixed:** the duplicate-cleanup recycle path `mkdir`'d onto its
  destination without preflighting it first; a misconfigured or
  unreachable recycling-bin share is now checked before use, falling back
  to skip-and-retry-next-scan instead of a permanent delete.
- **Fixed (GitHub issue #2):** GHCR images weren't publishing for `latest`
  or any tagged version - CI's lint and test jobs were failing outright
  (a missing `pytest.ini` plus 88 ruff findings), so the jobs that actually
  push to GHCR never ran. Also fixed a latent race in the multi-arch Docker
  build where the per-platform matrix job pushed directly to the same tags
  as the manifest-merge job, letting `linux/amd64` and `linux/arm64` builds
  overwrite each other under `latest`.
- **Fixed:** a cross-device directory move onto a NAS/network target fell
  through to a plain, unthrottled `shutil.move()` with no rate limit and no
  budget accounting - the one path that bypassed every NAS safety control
  this module exists to provide. Nothing in this release triggers it
  (movies are single-file), so it now refuses loudly instead of moving the
  bytes unsafely; a same-device directory move is unaffected.
- **Fixed:** marking a recommendation as already-owned could be silently
  reverted by the next refresh if the correlation check still couldn't see
  it as owned (physical media, an unscanned library) - that state is now
  protected the same way dismiss/hide/watchlist already were.
- **Fixed:** `genres_include`/`genres_exclude` filtering was permanently
  dead code - sourced candidates always got an empty genre tuple, since
  TMDB's collection/recommendations/similar payloads only carry numeric
  genre IDs, never names, and nothing resolved them against TMDB's genre
  list. Now resolved via a genre map fetched once per refresh.
- **Fixed:** a recommendation that dropped below `minimum_score` on a later
  refresh was left frozen at its old score forever instead of expiring.
- **Fixed:** `GET /recommendations`'s `provider_id` filter ran in Python
  after pagination and after `total` was computed from an unfiltered count,
  so a page could come back empty (or split matches across pages) while
  `total` still reported the unfiltered figure. Filtering now happens at
  the SQL level before pagination.
- **Fixed:** the same endpoint's Plex-ownership check ran two `SELECT
  count(*)` queries per returned row; replaced with one batched lookup.
- **Fixed:** a transient Windows file lock (e.g. Plex or an AV scanner
  briefly holding a just-created file) during post-replacement cleanup
  could permanently orphan the old file, since that cleanup step runs
  once and nothing else ever retries it. Given the same retry the
  move-into-place step already had.
- Full audit findings: `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md`.
  Competitive analysis: `docs/ARR_PLATFORM_GAP_ANALYSIS.md`.

---

## [1.9.0.0] - 2026-07-20

Standalone release summary: `docs/CHANGELOG_v1.9.0.0.md`

A full backend/frontend review pass, then a second pass working through the
findings: a database reliability fix, a config feature that was fully wired
but never actually did anything, and a batch of smaller correctness and
consistency fixes across both codebases.

- **Fixed the root cause of "database is locked" failures during downloads.**
  SQLite was running in its default rollback-journal mode, which takes an
  exclusive lock for the duration of any write — under concurrent access
  (a scan running while a download gets inserted) this surfaced as
  `OperationalError: database is locked`, visible repeatedly in production
  logs. WAL mode plus a 30s busy-timeout are now set on every connection.
- **Fixed `exclusions:` in config.yaml silently doing nothing.** The whole
  config section (movie IDs, title keywords, folders, codecs, resolutions,
  file-size floor, library-age ceiling) was defined and validated but never
  read anywhere — meaning personal footage living in the same Plex library
  as movies (home videos, wedding films) was being sent as search queries to
  public Usenet indexers every cycle. Exclusions are now checked before a
  search is ever issued, and there's a full Settings UI section to configure
  them.
- **Fixed `Movie.source_type` never being populated,** which silently
  weakened the comparer's source-quality upgrade checks for every movie.
  It's now set from the actual release title on replacement, and guessed
  from the filename during scans for movies not yet replaced.
- **Fixed uploader-health scoring blocking the event loop and always
  returning the default score on PostgreSQL.** It ran a synchronous SQLite
  query per candidate release (100+ times per movie search) and had no
  PostgreSQL path at all. Replaced with one batched async query per search
  that works on either database.
- Fixed the rate-limit toast never firing for indexer-pause events, because
  it matched on an exact prose string instead of the warning's actual
  category — a machine-readable `code` is now attached to every
  `search:warning` event.
- Fixed the same file size being displayed differently on different pages
  (some divided by 1e9, others by 2^30, both labeled "GB"). One shared
  formatter now backs every size shown in the UI.
- Sidebar navigation regrouped into labeled sections (Library, Activity,
  System, Settings) with live failed/orphaned/active download badge counts,
  instead of 13 links in a flat list.
- Self-hosted the UI font instead of pulling it from Google Fonts on every
  page load, replaced the last native `window.confirm` dialog with the
  app's own styled confirmation modal, and unified the brand accent color
  (the config had a stale, unused green that didn't match what the UI
  actually painted everywhere).

## [1.8.0.0] - 2026-07-12

Standalone release summary: `docs/CHANGELOG_v1.8.0.0.md`

Follow-up to 1.7.1.0 after reports that the replace-loop fix wasn't holding
for everyone. Root-caused two separate reasons it kept recurring, then did a
broader backend optimization/observability pass and a frontend UI-consistency
pass across most pages.

- Fixed the actual reason the 1.7.1.0 replace-loop fix didn't help everyone:
  `replace_file()`'s post-replacement probe was gated behind
  `files.enable_media_probe`, which defaults to off. It now always probes
  the single file it just placed, and the scanner no longer lets a possibly
  stale Plex read overwrite the corrected values on the next pass.
- Fixed a second, independently-discovered cause of the same symptom found
  in a user's live logs: a movie whose existing file was transiently locked
  by another process failed to replace every night, re-downloading the same
  release each time. The recycle-bin move and fallback backup-move now
  retry a few times before giving up.
- Performance: the Plex scan no longer blocks the event loop for its full
  duration; the retry ladder's blacklist check and the orphan scanner's
  history-item checks are now batched into single queries instead of one
  per candidate/item; the NAS-pressure panel counts in SQL instead of
  pulling every reject reason into Python.
- Observability: several silently-swallowed errors (Radarr rescan/unmonitor,
  uploader-health lookup) now log with context; a dead download client no
  longer floods the log with an identical warning every 5 seconds; a
  permanently-404ing TMDB lookup no longer retries every single scan.
- Frontend: fixed a sidebar nav bug that double-highlighted parent/child
  routes, a login-page bug that permanently locked the form behind a
  transient startup connectivity error, and unified inconsistent
  status-color palettes and loading/empty states across most pages.
  Deduplicated ~200 lines of copy-pasted NAS-preset logic between Dashboard
  and System into a shared hook, and memoized several list components.

## [1.7.1.0] - 2026-07-04

Standalone release summary: `docs/CHANGELOG_v1.7.1.0.md`

Patch release fixing a movie-stuck-in-an-endless-replace-loop bug found
while investigating matching reports from two users, plus a dashboard query
performance fix and three UI correctness bugs.

- Fixed `replace_file()` never persisting the re-probed resolution/codec/
  bitrate of a replacement file, which left a movie's tracked quality stuck
  at its previous file's values forever and made every future cycle treat
  the (accurately-replaced) local copy as still needing an upgrade.
- Added a `(decision, created_at)` composite index on `decision_audit_log`;
  the NAS storage-pressure dashboard query was taking up to 6.4s in
  production logs because SQLite's planner wasn't using the existing
  `(created_at, decision)` index for this query shape.
- Fixed a Movie Detail bug where a pending search/process/download response
  from a previously-viewed movie could overwrite a different movie's
  on-screen data after navigating away within a few seconds.
- Fixed a Library search race where a fast typist could end up seeing
  results for an earlier, superseded query.
- Fixed the System page "Run Now" button getting stuck on "Starting…"
  indefinitely when starting the automation cycle failed outright.

## [1.7.0.0] - 2026-06-23

Standalone release summary: `docs/CHANGELOG_v1.7.0.0.md`

Planning documents (history; not all tickets shipped in this release — see note below):

- `docs/VERSION_1_7_CHANGELOG_DRAFT.md`
- `docs/VERSION_1_7_ROADMAP.md`

Primary release theme: storage-safe automation, NAS resilience, persistent
jobs/recovery, and the start of a UI/visual fidelity refresh.

This release closes out the storage-safety and persistent-jobs foundation
(Phases 0-3 and 6-7 of the v1.7 roadmap) and the root cause of NAS
freeze/crash reports, and makes a first pass at UI consistency (Operations
page, confirm dialogs, empty/loading states, storage-state visual marks).
The deeper visual redesign of Dashboard/Library/Movie Detail/Settings and new
bitmap release assets (roadmap Phases 4-5) are still in progress and will
ship in a follow-up release rather than being backdated into this one.

### Phase 0 fixes

- Fixed scan-time media probe fallback so lightweight config/test harnesses
  without an explicit `files` section no longer fail during library scans.
- Changed duplicate cleanup preview behavior so the System page no longer
  refreshes Plex/NAS duplicate-preview scans every 45 seconds.
- Added server-side duplicate-preview caching and made maintenance insights read
  cached duplicate telemetry instead of triggering a fresh Plex/NAS scan.
- Added environment variable support for NAS/storage safety settings:
  `SLIMARR_ENABLE_MEDIA_PROBE`, `SLIMARR_NAS_PATH_PREFIXES`,
  `SLIMARR_NAS_MAX_WRITE_GB_PER_DAY`,
  `SLIMARR_NAS_MAX_REPLACEMENTS_PER_DAY`,
  `SLIMARR_NAS_MAX_CONCURRENT_OPERATIONS`,
  `SLIMARR_NAS_FAILURE_COOLDOWN_MINUTES`,
  `SLIMARR_MIN_SAVINGS_MB_FOR_NAS`, `SLIMARR_MIN_CYCLE_INTERVAL_MINUTES`,
  `SLIMARR_MAX_DOWNLOADS_PER_NIGHT`, `SLIMARR_THROTTLE_SECONDS`, and
  `SLIMARR_MAX_ACTIVE_DOWNLOAD_HOURS`.
- Added startup diagnostics warning when Slimarr runs outside the supported
  Python 3.11-3.13 range.
- Added shared storage path helpers for NAS prefix matching and storage path
  classification, with regression tests.
- Updated NAS pressure and comparison policy to share the same NAS path matching
  logic.
- Adjusted low-pressure NAS recommendations so configured NAS installs are not
  nudged toward aggressive mode by default.
- Fixed Plex post-replacement refresh so installs without explicit Plex library
  sections refresh all movie sections instead of doing nothing.
- Improved duplicate-preview cache reuse so a larger cached preview can satisfy
  lighter maintenance telemetry reads without another Plex/NAS scan.
- Added a non-mutating storage preflight helper and `/system/storage/preflight`
  endpoint for path classification, parent accessibility, free-space checks, and
  future replacement/cleanup safety gates.
- Routed replacement target preflight, recycle moves, fallback backups, restore
  moves, final placement, and old-file deletes through the shared async storage
  operation helpers instead of raw library-path `shutil.move`/`os.remove` calls.
- Added per-path storage operation locks and routed duplicate cleanup,
  failed-download cleanup, orphan cleanup, replacement staging cleanup, manual
  recycling purge, and scheduled recycling purge through the shared storage
  operation helpers.
- Added storage operation telemetry for recent move/delete outcomes and exposed
  it through diagnostics bundles and Prometheus metrics.
- Added optional in-memory NAS storage budgets for daily write volume, daily
  replacement count, concurrent NAS operations, and cooldown after failed NAS
  operations.
- Added a storage operations telemetry endpoint, health-matrix component, and
  System page readout for recent storage outcomes, NAS cooldown state, active
  NAS operations, and 24-hour NAS write/replacement counters.
- Changed storage-operation health warnings to use a bounded recent-failure
  window so old in-memory failures remain inspectable without degrading system
  health indefinitely.
- Added persisted storage operation telemetry and path-health tables so move,
  delete, skip, and failure history can survive process restarts and appear in
  diagnostics/support data.
- Added replacement recovery metadata tracking so risky replacement phases
  record original, target, recycle, backup, phase, and recovery-required state
  before and after library-file mutations.
- Refreshed the System page into a wider v1.7 operations surface and added a
  Storage Safety panel with live storage preflight status.
- Added a System page Replacement Recovery panel that surfaces active and
  recovery-required replacement records, latest risky phase, redacted target and
  backup paths, and manual refresh.
- Added the initial persistent job runtime with durable `jobs` and `job_events`
  tables, startup recovery for interrupted running jobs, job event timelines,
  cancellation/retry APIs, Prometheus job metrics, diagnostics bundle job
  timeline export, and job IDs attached to storage operation telemetry.
- Routed manual scans, full automation cycles, duplicate-preview refreshes,
  duplicate cleanup, and manual scheduled-task runs through persistent job
  records.
- Added a System page Persistent Jobs panel showing recent jobs, active work,
  failed/recovery-required counts, and latest job state.
- Added the first v1.7 visual asset and source notes:
  `images/releases/v1.7-storage-safe-banner.png` and
  `docs/assets/V1_7_VISUAL_ASSETS.md`.

### NAS freeze/crash fix and hardening pass

- **Fixed the root cause of NAS freezes/crashes during replacement.**
  `replace_file()` (the function that actually swaps a downloaded file into
  the Plex library) was calling `shutil.disk_usage()`, `os.makedirs()`,
  `os.path.exists()/getsize()/isdir()`, and a recursive `os.walk()` directly
  on the asyncio event loop instead of through `asyncio.to_thread()`. On a
  slow, busy, or sleeping NAS share these syscalls can block for seconds;
  because they ran on the event loop, that block stalled the *entire app* —
  API requests, the websocket, and the scheduler — for the duration, which
  presented as the whole instance freezing. Every blocking filesystem call in
  the replacement path is now offloaded to a worker thread, matching the
  pattern already used in `storage.py` and `scheduler.py`. The same blocking
  pattern was fixed in the duplicate-cleanup scan (`cleanup.py`), which ran
  `os.path.exists`/`os.path.getsize` against every Plex media part, and in the
  `/system/storage/preflight` diagnostics endpoint.
- Added regression tests (`tests/backend/test_replacer_event_loop.py`) that
  assert the offloaded filesystem helpers genuinely run off the event loop
  rather than just trusting the call site.
- Hardened the SQLite lightweight-migration helpers (`backend/database.py`)
  against unsafe table/column identifiers before they're interpolated into
  DDL strings, as defense-in-depth.
- Replaced several silent `except Exception: pass` blocks in the Plex
  integration and login-lockout audit path with logged warnings so
  connectivity/auth issues are diagnosable instead of invisible.
- Removed an accidentally committed 6MB log archive and diagnostics history
  file from `docs/logs-new/` and tightened `.gitignore` so log/`.jsonl`
  artifacts outside the canonical `logs/` directory are also excluded.

### Phase 3 / 4 / 6 enhancements

- Moved recycle-bin health and cleanup traversal off the async request loop and
  reused cached/single-pass directory snapshots to reduce NAS metadata storms.
- Changed storage moves and deletes to calculate directory size once per
  operation instead of repeatedly traversing the same tree.
- Made 24-hour NAS write and replacement budgets consult persisted operation
  history so limits survive process restarts, with in-flight budget reservation.
- Added chunked, rate-limited cross-device NAS file moves with temporary-target
  placement and conservative balanced defaults.
- Forwarded NAS safety environment variables through all Docker Compose variants.
- Added a responsive mobile navigation drawer, accessible notifications,
  reduced-motion support, and calmer System-page polling.

- Added `purge_old_jobs(keep_days)` to the job runtime so terminal job records
  (and their cascaded events) older than a configured window are automatically
  removed.
- Added `purge_old_storage_operations(keep_days)` to the storage module so
  persisted storage operation log entries are automatically trimmed.
- Added a daily `telemetry_retention_cleanup` scheduler job (05:00 UTC) that
  runs both purge functions with a 30-day default retention window.
- Added a `POST /system/telemetry/purge` endpoint so operators can trigger
  retention cleanup manually with an optional `keep_days` parameter.
- Added an explicit API response schema for manual telemetry purge results so
  OpenAPI contracts stay complete.
- Added NAS path classification summary (`system.nas.classification.json`) to
  the diagnostics bundle, including configured NAS prefixes, per-prefix
  classification, and NAS policy state.
- Added a dedicated Operations page (`/system/operations`) with active and
  historical job tables, per-job event timelines, cancel/retry actions, storage
  operation log (in-memory and persisted), NAS budget footer, and a guarded
  purge action.
- Added a reusable `ConfirmDialog` component for destructive-action confirmation
  with consistent visual treatment, keyboard dismiss, and loading state.
- Added a `Skeleton` component family (`Skeleton`, `SkeletonCard`, `SkeletonRow`,
  `SkeletonTable`) for consistent loading placeholder states.
- Added a reusable `EmptyState` component for empty list/table surfaces.
- Applied `ConfirmDialog` to the System page recycling-bin purge and duplicate
  cleanup triggers, replacing `window.confirm` native dialogs.
- Added "View all" link from the System page Persistent Jobs panel to the
  Operations page.
- Added Operations page to the sidebar navigation.

### GUI and code-health pass

- Implemented `files.verify_after_download` (previously a documented no-op
  that warned on every startup despite defaulting to `true`). Replacement now
  rejects empty/zero-byte downloads before they touch the library, and — when
  `files.enable_media_probe` is also enabled — logs a warning if a downloaded
  file has no detectable video stream, without hard-blocking on probe
  flakiness. Removed the now-stale "not yet implemented" startup warning.
- Unified destructive-action confirmation across the app: replaced the
  bespoke TV-show delete modal with the shared `ConfirmDialog`, and added
  confirmation prompts to two previously unconfirmed destructive actions —
  removing a blacklist entry and cleaning up an orphaned download — that
  could previously fire immediately on click.
- Added `Skeleton`/`EmptyState` treatment to the Blacklist page, matching the
  pattern already used on Library, Operations, Queue, and Orphaned Downloads.
- Added a small storage-state visual mark system (`StorageStateMark`) that
  maps replacement-recovery phase strings (preflight, recycling, backing up,
  placing, restoring, failed, recovery-required) to a consistent icon and
  color instead of raw phase text, and applied it to the System page
  Replacement Recovery panel.
- Added a startup warning when `server.allowed_origins` includes `*`. Risk is
  lower than typical wildcard-CORS because `allow_credentials=False` (no
  cookies are sent cross-origin), but it still allows any site to call the
  API with a leaked bearer token, so it's now surfaced instead of silent.
- Documented the full NAS-safety environment variable set and the new
  Prometheus metrics (`slimarr_jobs_active`, `slimarr_storage_operations_total`,
  etc.) in `docs/DOCKER.md`, which previously only covered the pre-1.6.1
  variables and metrics.
- Fixed `build-installer.ps1` overwriting the maintained `config.yaml.example`
  with a stale, hardcoded copy on every installer build — it had drifted to
  omit all NAS budget settings and flip `enable_media_probe` back to `true`
  (the unsafe default). The script now verifies the source-controlled file
  exists instead of regenerating it.
- Added `requirements-tray.txt` (pystray/pillow/pywin32) and wired it into
  `install.ps1`; these were required by `slimarr.spec`'s PyInstaller hidden
  imports but were never actually installed by the documented setup path,
  so the tray icon could be broken in a from-scratch build.
- Fixed `build-installer.ps1`'s Inno Setup detection to also find Inno Setup
  7 (it only looked for "Inno Setup 6" in its hardcoded paths).

## [1.6.1.0] - 2026-05-27

### NAS resilience and UI polish

#### NAS/load safety

- Added cycle cooldown enforcement (`schedule.min_cycle_interval_minutes`) so
  scheduler pulses can skip expensive full cycles when the previous cycle is too
  recent.
- Enforced `schedule.max_downloads_per_night` in the orchestrator and applied
  post-replacement `schedule.throttle_seconds` pacing between successful
  replacements to reduce back-to-back write pressure.
- Added `files.enable_media_probe` so operators can disable scan-time media
  probing for NAS-heavy environments where extra file reads may destabilize
  network-mounted storage.
- Added NAS path targeting (`files.nas_path_prefixes`) plus
  `comparison.min_savings_mb_for_nas` to block low-value replacements on
  network-mounted movie paths (for example `Z:\\Movies`) and reduce frequent
  write churn.
- Added recycle-bin stats caching in `/system/recycling-bin` to avoid repeated
  recursive folder walks on every UI poll when the recycle path is a network
  share.

#### UI polish

- Updated Settings and System recycle-bin status polling cadence from 15 seconds
  to 60 seconds and skipped polling while browser tabs are hidden.
- Added new Settings controls for media-probe fallback and minimum cycle
  interval tuning.
- Added a new System "NAS Pressure" panel with 24-hour NAS write activity,
  NAS-policy reject counters, tracked NAS paths visibility, and one-click
  stability presets (`gentle`, `balanced`, `aggressive`).
- Added a first-run Welcome Setup flow that asks for NAS path prefix and
  preferred stability profile, then applies safe schedule/NAS defaults
  automatically.
- Added a Dashboard NAS-pressure recommendation banner with one-click
  "Apply Gentle" and "Apply Balanced" actions when NAS activity risk rises.
- Added Dashboard "Quick Start Checklist" progress card with direct links to
  required setup areas (Plex, search provider, NAS path, first scan).
- Added Settings "Show Help" mode with contextual beginner guidance blocks for
  key sections (Plex, rules, files, schedule).
- Added compact Dashboard system-health summary strip for at-a-glance status of
  integrations, NAS pressure, and cycle readiness.
- Added "Restore Previous" action for NAS presets (Dashboard and System) so
  users can safely revert after testing profile changes.
- Added audio-quality pills to movie cards/detail headers so users can see
  resolution, video codec, and audio codec together at a glance.
- Added global audio preference ordering (`comparison.preferred_audio_codecs`) so
  users can set preferred audio formats once and apply that ranking across all
  movies.
- Added optional strict audio mode (`comparison.require_preferred_audio_match`)
  to reject candidates that do not match the configured preferred audio list.

## [1.6.0.0] - 2026-05-25

### Preference engine and live reliability

#### Quality priorities

- Added per-movie weighted quality priorities for 4K, HDR, Dolby Vision, Atmos,
  TrueHD, 5.1+, and 7.1.
- Added priority-aware compare scoring so matching candidates receive ranking
  boosts without hiding the existing safety policy.
- Added explicit Dolby Vision priority handling so users who choose DV can allow
  it intentionally even when the default compatibility safety mode is enabled.
- Added audio channel persistence for search results and exposed audio codec /
  channel badges in Movie Detail search results.
- Added candidate detail visibility for the priority-score contribution.

#### Live-system reliability

- Added direct Newznab indexer cooldowns after quota/rate-limit responses so an
  exhausted indexer is paused instead of hammered every movie.
- Added per-indexer enable toggles and configurable rate-limit cooldown minutes
  in Settings.
- Redacted sensitive API keys and tokens from normal runtime exception logs, TMDB
  lookup failures, downloader errors, and orphan scanner logs.
- Improved automation summaries so protected titles, no-candidate outcomes, dry
  runs, and review-required items are not counted as hard failures.

#### Windows launcher

- Fixed Windows startup registry entries and generated installer launcher scripts
  to start Slimarr with `--tray`, restoring the tray icon after restart/login.

#### Tests and build

- Added regression coverage for priority scoring and explicit Dolby Vision
  preference behavior.
- Rebuilt the bundled frontend assets for the v1.6 UI.

## [1.5.0.0] - 2026-05-15

### v1.5 foundation (architecture and quality-intent groundwork)

#### Database evolution groundwork

- Added optional PostgreSQL backend support through `SLIMARR_DB_URL` while keeping
  SQLite as the default backend.
- Added startup database connection retry/backoff to better tolerate transient
  startup races in containerized deployments.
- Added pool configuration support for PostgreSQL (`SLIMARR_DB_POOL_SIZE`,
  `SLIMARR_DB_MAX_OVERFLOW`, `SLIMARR_DB_POOL_TIMEOUT`, `SLIMARR_DB_POOL_RECYCLE`).
- Added slow-query timing instrumentation with warning logs for expensive queries.
- Added runtime database diagnostics exposure (`db_backend`, pool checked-out count)
  in system info.

#### Preferred Quality / Force-Keep foundation

- Added per-movie quality policy fields:
  `quality_intent`, `force_keep`, `allow_larger_replacements`, and
  `quality_profile_overrides`.
- Added new quality-intent API endpoint:
  `POST /api/v1/library/movies/{movie_id}/quality-intent`.
- Added compare-engine profile-aware decision logic for intents:
  `space_saver`, `balanced`, `premium`, `reference`, `locked`, and `pinned`.
- Added policy-level safeguards to block automated replacements for locked/pinned
  or force-kept movies.
- Added support for initial per-movie override hooks in compare decisions:
  preferred codec, preferred sources, resolution floor, release-group rejects,
  and max size increase policy.
- Added automation-cycle safeguards to skip force-kept titles entirely.
- Hardened protected-title automation so locked/pinned titles and force-kept
  titles are skipped consistently during single-movie processing.
- Hardened preferred-release automation so stored preferred releases only win
  when the compare engine still accepts them; rejected preferred candidates now
  fall back to normal scoring.
- Hardened quality override parsing so malformed numeric/list overrides fall
  back to policy defaults instead of aborting candidate comparison.
- Replaced raw Movie Detail quality override JSON editing with explicit controls
  for resolution floor, preferred codec, preferred sources, rejected groups, and
  max size increase.
- Added indexer/Prowlarr quota detection for HTTP 429, Newznab request-limit
  errors, and common API limit/quota response text. Quota events now emit
  actionable Search Diagnostics warnings, realtime user toasts, reliability
  counters, and failure-heatmap entries instead of looking like silent empty
  searches.

#### Documentation and roadmap

- Added `docs/V1_5_FOUNDATION_ROADMAP.md` containing:
  implementation plan, refactor roadmap, risk assessment, observability plan,
  worker architecture proposal, ffprobe roadmap, security recommendations,
  technical debt audit, performance analysis, migration guidance, and phased
  priorities for v1.5+.
- Added `docker-compose.postgres.yml` as an optional write-heavy deployment
  template.
- Expanded `docs/DOCKER.md` with PostgreSQL backend guidance.

#### Tests

- Added new regression tests for quality-intent compare behavior in
  `tests/backend/test_quality_intent.py`.

#### Installer reliability

- Improved `install.ps1` native-command logging so pip/network errors are written
  cleanly to `startup-error.log` without noisy PowerShell wrapper output.
- Added targeted install diagnostics for blocked package index access (for example
  `WinError 10013`) with explicit firewall/proxy remediation guidance.
- Added offline dependency fallback support in `install.ps1`:
  if online pip install fails due network restrictions, installer now tries local
  wheelhouse paths (`.\wheelhouse`, `.\dist\wheelhouse`, or `-WheelhousePath`).

#### Home theater and quality-lock planning

- Added v1.5 planning scope for a dedicated home-theater intent built on existing
  `quality_intent` + lock semantics so users can preserve premium reference copies
  (for example 4K HDR/DV high-bitrate with lossless/7.1 audio) instead of over-compressed
  alternatives.
- Added planning notes for optional curated title seeding (for example Oscar winners,
  IMDB Top lists, and operator-imported watchlists) so "media center" movies can be
  bulk-marked for premium retention policies.

#### Docker launch UX

- Added no-download launch path planning so operators can start Slimarr via shell
  directly from the official compose template without manually copying files first.
- Fixed Windows installer/start-menu launchers so first launch starts the tray app
  path instead of headless-only mode, making the tray icon appear immediately.

## [1.4.0.0] - 2026-05-15

### Slimarr v1.4 — "Containerised"

This release focuses on Linux-native operation, official Docker deployment, and
production-grade observability. Windows installs continue to work unchanged.

#### Full Linux & Docker Support

- Added official multi-stage `Dockerfile` targeting `linux/amd64` and `linux/arm64`.
- Added `docker-compose.yml` for basic self-hosted deployments and
  `docker-compose.traefik.yml` for Traefik reverse proxy setups.
- Added `.dockerignore` for lean images (no test artefacts, no secrets, no Windows
  packaging files).
- Added `.env.example` with a full reference of all supported environment variables.
- Container runs as a non-root user (`UID/GID 1000`) by default; `PUID`/`PGID`
  build args allow customisation.
- Built-in `HEALTHCHECK` hits the `/api/v1/system/health` endpoint every 30 s.
- Graceful shutdown is handled natively by uvicorn's SIGTERM/SIGINT handling.

#### Environment Variable Configuration

- Added `SLIMARR_*` environment variable override layer so the container can be
  configured entirely without a `config.yaml`.
- Supported variables cover all service connections: Plex, SABnzbd, NZBGet,
  Prowlarr, Radarr, Sonarr, TMDB, server port, log level/format, and timezone.
- Config precedence: `SLIMARR_*` env vars → `config.yaml` → built-in defaults.
- `TZ` and `SLIMARR_TZ` both map to `schedule.timezone`.
- Type coercion handles booleans, integers, and floats from string env values.

#### Cross-Platform Filesystem Utilities

- Added `backend/utils/platform.py` with:
  - OS and Docker container detection (`is_docker()`, `container_id()`, `os_info()`).
  - Cross-platform disk space helpers (`disk_free_bytes()`, `disk_total_bytes()`)
    using `statvfs` on Linux/macOS and `GetDiskFreeSpaceExW` on Windows.
  - `normalize_path()` for portable path expansion.
  - `is_writable()` permission check.
  - `safe_makedirs()` respecting container umask.
- System info endpoint now returns `arch`, `in_docker`, and `container_id`.

#### Startup Validation

- Added `backend/core/startup.py` that runs once at application startup:
  - Detects OS, architecture, Python version, Docker status.
  - Creates and validates all required data directories.
  - Checks disk space; emits `warn` (< 5 GB) or `critical` (< 1 GB) alerts.
  - Logs a structured startup banner with provider summary and active env overrides.
  - Exposes warnings via `GET /api/v1/system/startup` (authenticated) and reflects
    them in the `/health` response.
- Startup validation results are included in the diagnostics bundle.

#### Observability & Logging

- Logger now auto-detects runtime environment:
  - Docker / no-TTY → plain structured text (no ANSI codes), Docker-friendly.
  - `SLIMARR_LOG_FORMAT=json` → newline-delimited JSON to stderr (Loki, ELK, Splunk).
  - Interactive terminal → existing colourised output unchanged.
- Added `SLIMARR_LOG_LEVEL` and `SLIMARR_LOG_FILE` environment variable overrides.
- Added `GET /api/v1/system/metrics` (unauthenticated) Prometheus-compatible
  plain-text endpoint exposing:
  `slimarr_uptime_seconds`, `slimarr_movies_total`, `slimarr_downloads_active`,
  `slimarr_db_size_bytes`, `slimarr_disk_free_bytes`, `slimarr_cycle_running`,
  `slimarr_search_degraded`, `slimarr_info`.
- `/api/v1/system/health` now returns `{"status":"degraded","warnings":[…]}` when
  startup checks found actionable issues, instead of always returning `ok`.

#### Container Diagnostics UI

- Added **System → Container** page (`/system/container`) showing:
  - Runtime info: OS, architecture, Python version, Docker status, container ID.
  - Data directory validation with per-path write-permission indicators.
  - Disk space status with colour-coded warn/critical badges.
  - Active config summary: providers, env overrides, download client, schedule mode.
  - Copyable `docker-compose.yml` quick-start example.
  - Linux volume and permissions troubleshooting guidance.
- Added **Container** entry to the sidebar navigation.

#### GitHub Actions CI/CD

- Added `.github/workflows/ci.yml` — runs pytest and ruff lint on Ubuntu and
  Windows for Python 3.11 and 3.12 on every push and PR.
- Added `.github/workflows/docker.yml` — builds and publishes multi-arch Docker
  images (`linux/amd64`, `linux/arm64`) to GHCR on push to `main` and version tags,
  with layer caching, Docker metadata tagging, and Trivy vulnerability scanning.

#### Documentation

- Added `docs/DOCKER.md` — comprehensive Docker deployment guide covering:
  quick start, environment variable reference, volume mapping, media path setup,
  Traefik and nginx reverse proxy, Unraid, Synology, permissions, Prometheus metrics,
  upgrading, troubleshooting, and migration from v1.3.

#### Compatibility

- All existing Windows installs, `config.yaml` files, and v1.3 databases are fully
  compatible with v1.4. No manual migration steps required.
- `run.py` already detected non-Windows platforms for headless mode; Docker uses
  this path directly.

---

## [1.3.0.0] - 2026-05-13

### Search diagnostics and degraded-pipeline safety

- Added end-to-end search diagnostics for Prowlarr and direct Newznab searches:
  request URLs with secrets redacted, response status, latency, raw/parsed result counts,
  parser failures, timeouts, malformed payloads, indexer reliability, and rejection summaries.
- Added a dedicated Search Diagnostics page with live requests, indexer responses,
  filtered-vs-accepted counts, failure heatmap, last successful search, reliability metrics,
  and a manual Search Test Harness with raw payload inspection.
- Added degraded-search detection so automation no longer appears healthy while searches are
  effectively failing:
  100 consecutive zero-result searches, repeated all-provider failures, missing search
  providers, malformed payloads, and category mismatch warnings are surfaced to the UI.
- Hardened Newznab parsing so auth errors and malformed XML are no longer silently treated as
  empty result sets.
- Added regression tests for Prowlarr request construction, Newznab parsing, empty results,
  malformed payloads, auth failures, timeout diagnostics, category extraction, and degraded
  zero-result detection.
- Tightened diagnostics security and retention:
  raw payload previews are truncated, API keys/tokens/passwords/auth headers are redacted,
  diagnostics history is bounded, and search diagnostics are included in support bundles.
- Split degraded-search state into warnings and blocking failures so 100+ zero-result searches
  no longer pause automation by itself, while repeated all-provider failures still block cycles.
- Improved Newznab compatibility by parsing namespaced or unprefixed Newznab attributes and
  namespaced error payloads.
- Added persisted diagnostics history stored on disk with pagination and basic text search via
  `GET /system/search-diagnostics/history`.
- Expanded Search Diagnostics UI with persisted-history controls (filter, search, pagination)
  so incident review is no longer limited to in-memory session events.
- Included persisted diagnostics history in support bundles (`system.search.diagnostics.history.json`).
- Hardened diagnostics redaction to also mask bearer/basic credential payloads in quoted
  authorization fields.

### Media Intelligence and automation safety

- Added Quality Intelligence V2 parsing for source type, resolution, codec, HDR/Dolby Vision,
  audio codec/channels, language markers, subtitle risk markers, PROPER/REPACK, release group,
  and low-quality source detection.
- Added Media Health scoring for candidate releases and local media with ratings:
  Excellent, Good, Acceptable, Risky, and Reject.
- Added Dolby Vision safety mode defaults:
  `comparison.avoid_dolby_vision: true` and
  `comparison.allow_dolby_vision_with_hdr_fallback: false`.
- Added language/audio safety defaults:
  `comparison.require_english_audio: true`, optional dual/multi-audio rejection, and
  hardcoded subtitle rejection.
- Comparison decisions now expose media health score/rating/reasons in search results,
  Movie Detail candidate drawers, and decision audit responses.
- Quality upgrades can now accept a larger file only when the existing copy is clearly poor
  quality and the candidate is a bounded good-source 1080p upgrade.
- Added regression tests for Dolby Vision filtering, language/subtitle safeguards,
  low-quality source rejection, bounded quality upgrades, diagnostics redaction, and
  retention limits.
- Added MediaInfo-backed local stream probing during library scans to enrich missing
  resolution/video codec/audio codec/bitrate metadata from actual files.
- Improved library poster rendering performance with viewport-aware staged image loading,
  skeleton placeholders, and async image decoding for large libraries.

### Stability hardening and operator overrides

- Hardened candidate scoring and downloader health calculations against null numeric values
  so a single malformed row no longer aborts processing with `float(None)` errors.
- Added malformed search-result guardrails in the search pipeline: results with missing titles,
  invalid sizes, or per-item processing exceptions are now logged and skipped instead of
  stopping movie processing.
- Added force-download controls in Movie Detail so operators can explicitly queue a
  non-recommended release after confirmation.
- Added persistent per-movie preferred release override:
  - backend support via `movies.preferred_release_title`
  - API endpoints to set/clear preferred release from existing search results
  - orchestrator selection path that prioritizes preferred release when present,
    with fallback to normal scoring when absent
  - UI controls to set/clear preferred release and warning text when the preferred
    release is not present in the current search pass

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
- Updated system API runtime version constant to `1.2.0.0` for accurate `/system/info` and
  `/system/update-check` reporting.

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

**Final release additions and platform polish**
- Added stricter preferred-language filtering behavior in the comparison engine:
  - candidates with explicit language tags must include the configured preferred language
  - English preference now rejects explicit non-English title markers (for example ITA/French/German tags) when English is not present
- Added schedule-window enforcement with timezone support for overnight cross-check workflows:
  - new `schedule.timezone` config setting (`local` by default)
  - scheduler now runs window-aware checks and skips cycles outside configured start/end times
  - overnight windows spanning midnight (for example 23:00 -> 05:00) are supported
- Added cycle guardrails so long-running cycles stop processing new movies once the configured schedule window closes.
- Added regression test coverage for:
  - English-preferred language rejection of Italian-tagged candidates
  - overnight schedule-window evaluation logic
- Centralized application version metadata in `backend/version.py` and wired runtime/system APIs to that source for consistent version reporting.
- Aligned release metadata to `1.2.0.0` across backend runtime, frontend package metadata, installer metadata, and docs.
- Updated updater behavior messaging and safeguards:
  - clarified that `update.bat` is for git source checkouts only
  - added early guard when `.git` is not present to avoid misleading "updated" flows on installer deployments
- Improved installer build output quality:
  - removed obsolete/deprecated Inno Setup directives from installer config to eliminate packaging warnings
  - ensured installer config template generation includes schedule defaults for timezone/window settings
- Reduced startup noise in common Windows deployments by pinning bcrypt to a passlib-compatible version (`bcrypt==4.0.1`).
- Refreshed GitHub Pages docs site visuals and content hierarchy to highlight v1.2.0.0 improvements and improve release discoverability.

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
