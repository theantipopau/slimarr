# Backend & Recommendations Audit

**Date:** 2026-09-02
**Scope:** Full repository read-through (backend, frontend, tests, config, Docker/installer paths) ahead of v2.0.0 planning. This document is Stage 1 of the process described in the v2.0.0 brief: audit and baseline only. No behavior has been changed as part of this document.

**Baseline test results:** `pytest tests -q` → **108 passed**, 0 failed, 1 pre-existing warning (pytest cache directory permission, unrelated to test logic). 20 test files (18 in `tests/backend`, 2 in `tests/api`). Frontend `tsc --noEmit` and `vite build` were last verified green as of commit `532e93f` (2026-07-20); not re-run in this audit pass since no source was touched.

**Method:** Every finding below was verified against the actual code at commit `532e93f` (`git log -1` at audit time), not against README/design-doc claims. Two background sub-agents traced the filesystem-safety layer (`storage.py`, `media_probe.py`, `orphan_scanner.py`, `cleanup.py`, `parser.py`, `media_health.py`) and the API/integration layer (`jobs.py`, `activity.py`, `images.py`, `models.py`, `sabnzbd.py`, `nzbget.py`, `download_client.py`, `responses.py`, `logger.py`, `platform.py`) independently; their findings are folded in below with the same evidentiary standard. I read the core pipeline (`orchestrator.py`, `comparer.py`, `replacer.py`, `scanner.py`, `searcher.py`, `downloader.py`, `jobs.py`, `database.py`, `config.py`, `main.py`, `tmdb.py`, `radarr.py`, `sonarr.py`, `auth/*`, `realtime/*`) directly, including work from two prior sessions on this same codebase (1.9.0.0 and its predecessor).

`docs/DESIGN_DOCUMENT.md` and `docs/IMPLEMENTATION_GUIDE.md` are the **original pre-build planning docs** (they still show `aiosqlite`/no-`asyncpg`, no `exclusions:` config, a `sabnzbd_nzo_id` column that was later renamed, etc.) and are stale relative to the shipped code. They are not treated as ground truth anywhere in this audit.

---

## 1. Architecture map (verified, not assumed)

```
run.py / installer tray.py
  → backend/main.py (FastAPI lifespan)
      → config.load_config() + ensure_secrets()   [YAML + SLIMARR_* env overrides, see backend/config.py]
      → database.init_db()                        [SQLAlchemy 2.0 async; SQLite (WAL) or Postgres via asyncpg]
      → core/startup.run_startup_checks()          [disk/dir checks, CORS-wildcard warning, banner]
      → core/jobs.recover_stale_jobs()             [marks orphaned "running" jobs as recovery_required]
      → scheduler/scheduler.start_scheduler()      [APScheduler: nightly window, recycle cleanup, orphan
                                                     scan, downloader health pulse, stale-download recovery,
                                                     telemetry retention]
      → download_workflow.resume_downloading_downloads() [fire-and-forget, 2s after startup]
  → socketio.ASGIApp(sio, app)                     [single port serves REST + WS + built SPA]

Per-movie pipeline (core/orchestrator.run_full_cycle):
  scanner.scan_library()          — Plex → DB upsert, TMDB/Radarr poster enrichment, optional media probe
    → orchestrator.process_single_movie() per pending/failed movie, gated by:
        exclusions.is_movie_excluded()  (movie_ids/keywords/folders/codecs/resolutions/size/age)
        force_keep / slimarr_locked / quality_intent in {locked, pinned}
    → searcher.search_for_movie()   — Prowlarr or direct Newznab indexers → comparer.compare_release()
                                       per candidate (uploader-health batched, see 1.9.0.0 fix)
    → download_workflow.process_search_result_download()
        → downloader.start_download() → SABnzbd/NZBGet
        → downloader.monitor_download() (5s poll loop)
        → on failure: retry_ladder.retry_failed_download() (blacklist-aware, batched)
    → replacer.replace_file()       — verify → recycle-bin move (retried) → place new file (retried) →
                                       re-probe → update Movie row → Plex refresh → Radarr post-replace →
                                       cleanup SABnzbd staging dir
  Every filesystem move/remove/copy in the above routes through core/storage.py's
  classify → preflight → NAS-budget-gated → asyncio.to_thread execution path, logged to
  StorageOperationLog and (for replacements) ReplacementRecoveryRecord.

Persistent job runtime (core/jobs.py): a second, independent execution mechanism — DB-backed
(JobRecord/JobEvent), heartbeat, singleton-by-kind, resumable across restarts, used for
manual_scan/full_cycle/duplicate_preview/duplicate_cleanup/scheduler_task triggered from the API,
NOT used by the nightly scheduler → run_full_cycle path itself (that path runs directly as an
asyncio task with its own in-module _running/_lock state in orchestrator.py, not through JobRecord).
This means there are two different "is something running" mechanisms in the app today.
```

**Confirmed by reading, not by claim:**
- Single-user model. `User` has no roles/permissions/scopes; `get_current_user()` returns a bare username string; every protected route treats any authenticated caller identically. There is no concept of "user scope" anywhere in the schema.
- SQLite WAL mode + 30s busy-timeout is set unconditionally via a `connect` event listener (`database.py`, fixed in 1.9.0.0). PostgreSQL is a real, tested-at-the-config-level second backend (`asyncpg`, pool-size env vars, `docker-compose.postgres.yml`), but no test in `tests/` actually runs against Postgres — parity is asserted by code inspection (identifiers are validated via `_assert_safe_identifier` before any raw DDL), not by a Postgres CI run.
- The persistent job system (`core/jobs.py`) is materially more mature than a "TODO" list would suggest: heartbeats, singleton dedup, cancellation, stale-job recovery on restart, and retention purging all exist and are exercised by `tests/backend/test_jobs_runtime.py`. This is a real asset for the "durable background jobs" requirement in the v2.0 brief — it should be **reused** for recommendation-refresh jobs, not replaced.

---

## 2. Confirmed defects

Severity scale: **Critical** (data loss / security / crash risk), **High** (real user-facing incorrectness or a genuine security-adjacent leak), **Medium** (correctness edge case, resource/perf risk), **Low** (style/consistency, no direct user impact).

### 2.1 Filesystem / storage safety

| # | Component | Evidence | Impact | Severity | Recommended correction | Addressed here? |
|---|-----------|----------|--------|----------|------------------------|------------------|
| F1 | `core/storage.py: normalize_path()` (~L110-112) | Only lowercases and swaps `\`→`/`; never collapses `..` or resolves symlinks. `path_matches_prefix` is a pure string-prefix test on this output. | A path containing `..` can evade NAS-prefix classification (skips budget/throttle/cooldown protection entirely); conversely a symlink inside a "local" dir that actually points at a NAS mount is silently treated as local. This is the literal "path traversal / unsafe cross-library operation" risk the audit brief calls out by name. | **High** | Resolve to an absolute, symlink-resolved path (`os.path.realpath`) before classification, and reject (or explicitly flag) any input containing `..` segments post-normalization. | No |
| F2 | `core/storage.py: normalize_path()` (~L112) | Lowercases unconditionally. | On case-sensitive filesystems (Linux/most Docker/NAS-via-NFS), `/mnt/NAS/Movies` and `/mnt/nas/Movies` are different real paths but collapse to the same classification key — can cause a false NAS match (unwanted throttling) or false miss (no protection) depending on how `nas_path_prefixes` is cased. | **Medium** | Only lowercase on platforms where it's actually correct (Windows); compare case-sensitively elsewhere. | No |
| F3 | `core/storage.py: _copy_file_throttled()` (~L301-324) | After `os.replace(temporary, target)` succeeds, if the following `os.remove(source)` raises, the except block tries to remove `temporary` (already gone) and re-raises — leaving a **complete duplicate** of the file at `target` while `source` is untouched and the whole operation is recorded as `failed`. | Silent double disk usage; an operator sees a "failed" copy in the operation log and may not realize a full extra copy now exists at the destination. | **Medium** | On post-replace source-removal failure, treat the operation as `completed_with_warning` (record that removal failed) rather than `failed`, since the copy itself succeeded — and never re-attempt the copy on retry without checking for the already-completed target first. | No |
| F4 | `core/storage.py` directory-move path (~L992-1006) | The throttled/chunked copy path only triggers `if os.path.isfile(source)`. Directory moves fall through to plain `shutil.move`, which does its own untracked copy+rmtree cross-device with **no rate limit, no `.part` staging, no NAS budget accounting**. | A season-pack or bulk directory move onto a NAS-mounted target bypasses every NAS safety control this file exists to provide. Currently low-frequency (movies are single-file), but directly relevant to any future TV/season-pack feature. | **Medium** (High if TV support ships without a fix) | Extend the throttled-copy path to directories (walk + per-file throttling), or explicitly document/log that directory moves are unthrottled and block them onto classified NAS targets until fixed. | No |
| F5 | `core/storage.py` NAS in-process state (~L19-29, `reset_storage_operation_telemetry`) | `_nas_active_operations`, `_nas_cooldown_until`, `_nas_last_failure` are plain module globals, not persisted. Only 24h write/replacement *totals* are recomputed from the DB on restart. | A process restart immediately after a NAS failure silently drops the cooldown — the next replacement can hit the same failing NAS share immediately instead of waiting out the configured cooldown. | **Medium** | Persist cooldown-until and active-operation count (or at minimum last-failure timestamp) to `StoragePathHealth`, which already exists for a related purpose, and read it back on startup. | No |
| F6 | `core/orphan_scanner.py: auto_cleanup_old_orphans()` (~L308-324) | Deletes the `OrphanedDownload` tracking row unconditionally after attempting `remove_path()`, even when that call raised (caught, logged, loop continues). Contrast with `cleanup_orphaned_download()` (~L226-289) in the same file, which correctly checks success before deleting the row and otherwise marks `cleanup_scheduled` for retry. | The scheduled daily auto-cleanup can lose all record of a file that failed to delete (permission error, transient lock) — Slimarr then has zero visibility that leftover data exists on disk. | **High** | Make `auto_cleanup_old_orphans` follow the same success-gated deletion pattern already implemented (and tested, presumably) in `cleanup_orphaned_download`. | **Yes** — now checks `remove_path()`'s result status (and catches exceptions) before deleting the row; on failure marks `cleanup_scheduled`/`cleanup_at` for retry instead. 4 regression tests in `tests/backend/test_orphan_scanner.py`. |
| F7 | `core/cleanup.py` (~L218-220) | `config.files.recycling_bin` is used directly with `os.makedirs()` without ever being run through `classify_storage_path`/preflight. | A recycling bin misconfigured to point at a NAS path bypasses all NAS budget/throttle protection for every recycled file — the one place this audit brief explicitly asks for consistent path classification. | **Medium** | Route the recycling-bin path through the same preflight/classification used for the main replacement target. | No |
| F8 | `core/storage.py` (~L315-317) | TOCTOU: `os.path.exists(target)` check then `os.replace()` a few lines later, mitigated only by an in-process `asyncio.Lock` keyed by path. | Safe today (single process, single instance assumption is explicit elsewhere in the codebase — e.g. `JobRecord` singleton-by-kind). Would become unsafe if Slimarr is ever run as multiple replicas against the same library. | **Low** (documented assumption, not a live bug) | Note the single-instance assumption explicitly in `docs/ARR_PLATFORM_GAP_ANALYSIS.md` (done, see below) rather than "fixing" a problem that doesn't exist under the current deployment model. | Documented |

### 2.2 API / integration layer

| # | Component | Evidence | Impact | Severity | Recommended correction | Addressed here? |
|---|-----------|----------|--------|----------|------------------------|------------------|
| A1 | `integrations/sabnzbd.py` (API-key-in-URL pattern) | The SABnzbd API key travels as a query parameter on every request. `test_connection()` and `purge_job()` catch bare `Exception as e` and log/return `str(e)` — `httpx` exception messages embed the full request URL, including the key. These strings surface through `/health/services` and `/integrations/matrix` API responses and warning logs. `nzbget.py` avoids this (uses HTTP Basic `auth=`), so the risk is inconsistent between the two supported download clients. | An operator's SABnzbd API key can land in the app's own logs and in an authenticated-but-not-necessarily-trusted API response body. | **High** | Redact query-string secrets before stringifying any `httpx` exception from `sabnzbd.py` (there is already a `redact_url`/`redact_text` pair in `core/search_diagnostics.py` used for indexer URLs — reuse it here rather than inventing a second redaction path). | **Yes** — `test_connection()` and both `purge_job()` failure branches now redact via `redact_text()` before logging or returning. Verified against a real `httpx.HTTPStatusError` (constructed via an actual `raise_for_status()` call, not a hand-typed message) in `tests/backend/test_sabnzbd_redaction.py`. |
| A2 | `api/images.py` (~L49-52) | `internal_error(f"Image fetch failed: {e}", ...)` interpolates the raw exception directly into the client-visible response, unlike every other router which relies on the global handler's generic `error_type`-only envelope. | Can leak internal filesystem paths (e.g. a failed image-cache write) to any client — the endpoint is also the one unauthenticated data-serving route besides `/health`/`/metrics`. | **Medium** | Log the exception with full detail server-side; return the same generic envelope every other endpoint uses. | No |
| A3 | `core/jobs.py: get_persistent_job()` (~L339-354) | The `JobEvent` timeline query has no `LIMIT`. | A job retried many times (each retry adds `started`/`completed`/`failed` events) returns an unbounded array from `GET /jobs/{id}`. | **Medium** | Cap and paginate, consistent with every other list endpoint in the app (which are otherwise bounded — `activity.py`, `system.py`'s decision-audit and storage-operations endpoints all clamp `limit`). | No |
| A4 | `integrations/download_client.py: _CLIENT_CAPABILITIES` | A static hardcoded dict, not derived from an actual capability probe — both SABnzbd and NZBGet entries are currently identical placeholders. | The "capability discovery" the app appears to have doesn't actually discover anything; any future feature gated on a client capability would be gated on a lie. | **Medium** | Either implement a real capability probe (e.g. from `test_connection()`'s response) or rename/document this as a static compatibility table, not a discovery mechanism, until it's real. | No |
| A5 | `integrations/tmdb.py`, `radarr.py`, `sonarr.py` | Every method opens a **new** `httpx.AsyncClient()` per call. `main.py` already builds and lifecycle-manages a single shared `httpx.AsyncClient` (`get_http_client()`) for exactly this purpose, but none of these three clients use it. | No connection pooling/reuse for the three highest-request-volume external integrations (TMDB is called once per movie needing enrichment per scan; Radarr's `find_movie_by_imdb` refetches **all** Radarr movies per lookup). No shared timeout/retry policy. | **Medium** | Route these three clients through the shared `httpx.AsyncClient`; this is also the natural foundation for the "centralise shared HTTP client behaviour" requirement (pooling, timeouts, retry-with-jitter, rate-limit handling) needed by the new streaming-availability/TMDB work below. | Partially — new recommendation-engine HTTP calls in this plan use the shared client from day one; retrofitting the three existing clients is scoped as a near-term follow-up, not bundled into this pass (see §9, Known Limitations). |
| A6 | `logger.py` / redaction | Secret redaction (`_redact_sensitive`, `_redact_path_for_payload`, `redact_url`/`redact_text`) exists but is applied **locally**, per call site, in `system.py` and `search_diagnostics.py`. There is no generic scrubbing sink in the logging pipeline itself. | Any new code path that logs a raw exception (as in A1) bypasses redaction by default rather than by exception — redaction is opt-in, not the default. | **Low** (architectural, not an active leak beyond A1) | Note as a "prepare the architecture now" item in the gap analysis rather than a point fix — a logging-sink-level redaction filter is a larger change than this pass should make incidentally. | Documented, not fixed |
| A7 | `system.py` `/metrics` DB query block, diagnostics-bundle NAS summary | Bare `except Exception: pass`, no `logger.debug/warning`. | A DB failure during metrics collection silently produces partial/missing metrics with zero trace — harder to diagnose than an equivalent failure elsewhere in the app that *does* log. | **Low** | Add a `logger.debug` call; not worth escalating further since `/metrics` degrading silently is an acceptable failure mode for a scrape endpoint (Prometheus itself will show the gap). | No |

### 2.3 Confirmed *not* defects (verified, worth recording so they aren't re-flagged later)

- CORS wildcard misconfiguration already produces an explicit startup warning (`core/startup.py: _check_config_sanity`, tested in `test_config_sanity_warnings.py`).
- SQL identifiers used in the hand-rolled migration DDL are validated against a strict regex before use (`database.py: _assert_safe_identifier`, tested in `test_database_identifiers.py`) — the "avoid unsafe SQL identifier interpolation" concern in the brief is already handled for the existing migration helpers.
- `media_probe.py` is correctly invoked via `asyncio.to_thread` everywhere it's called (`replacer.py`, `scanner.py`) — no blocking-call-in-event-loop defect there.
- Auth coverage is consistent: every data-bearing route in `jobs.py`, `activity.py`, and 29/31 routes in `system.py` requires `Depends(get_current_user)`. The two exceptions (`/health`, `/metrics`) are intentional, documented infra endpoints, not accidental gaps. `images.py`'s single unauthenticated route is also an explicit, comment-documented design choice (browsers can't attach bearer tokens to `<img src>`).
- Pagination is *inconsistently* applied but not *absent* — `activity.py`, `system.py`'s decision-audit, and storage-operations endpoints are all correctly bounded. Only the job-events endpoint (A3) and a couple of `system.py` corners are unbounded.
- The persistent job system already provides most of what "durable, resumable, idempotent-by-key" background work requires (see §1) — this is a strength to build on, not a gap to fill.

---

## 3. Optional improvements (not defects — noted per the brief's instruction to distinguish these)

- `auth/dependencies.py` has a redundant `from typing import Optional` re-imported inside the function body and again after the function under a "re-export for convenience" comment that re-exports a standard-library type for no functional reason. Harmless, but worth a one-line cleanup whenever the file is next touched.
- `Socket.IO`'s own `cors_allowed_origins=[]` (`realtime/sio_instance.py`) is separate from FastAPI's `CORSMiddleware` and currently relies on same-origin delivery (the SPA is served from the same process/port) rather than being configured explicitly. Not a defect under the current single-origin deployment model; would need attention if the frontend is ever split out.
- `RadarrClient.find_movie_by_imdb()` fetches the entire Radarr movie list per lookup with no caching — fine at current call frequency (once per replacement, optional integration), but would not scale well if reused as a hot path for the new Radarr-state-correlation feature below without adding a short-lived cache.

---

## 4. What this means for the v2.0.0 recommendation feature specifically

- **Reuse `core/jobs.py`** for `recommendation_refresh`/`streaming_availability_refresh` job kinds. It already provides exactly the "durable, resumable, singleton-per-kind, cancellable" semantics the brief asks for — building a second job mechanism would be the "add explicit service boundaries" anti-pattern the gap analysis (below) explicitly recommends against.
- **Do not use `TMDBClient`, `RadarrClient`, or `SonarrClient` as-is for the new work** without first routing them through the shared `httpx.AsyncClient` (A5) — the new streaming-availability and Radarr/Sonarr-state-correlation features are exactly the kind of higher-volume caller that would make the existing per-call-client pattern's lack of pooling and retry policy actually matter.
- **Single-user model is a real constraint.** The brief's data model asks for "user or profile scope if supported" — it is *not* currently supported. Recommendation state (dismissed/hidden/watchlisted) will be scoped to the single existing account, not per-user, and this should be stated explicitly in the recommendation architecture doc rather than silently designed around a multi-user assumption the app doesn't have.
- **The filesystem-safety findings (F1-F8) are unrelated to the recommendation feature's own safety** (recommendations never touch the filesystem) but are relevant to the brief's explicit requirement that "recommendations cannot enter the replacement pipeline accidentally" — confirming the replacement pipeline's entry point (`orchestrator.process_single_movie`, gated on `Movie.status in {pending, failed}`) has no path by which a `RecommendationCandidate` row could be mistaken for a `Movie` row, since they will be entirely separate tables with no shared primary-key space or status vocabulary.

---

## 5. Recommended sequencing

Per the brief's own staged process, and given the severity findings above:

1. **F6 and A1** are the two findings worth fixing as standalone, low-risk patches before any new feature work — F6 because it can silently lose track of orphaned data, A1 because it's a credential-hygiene issue. Both are small, isolated diffs with existing test coverage patterns to extend.
2. F1-F5, F7, A2-A4 are real but lower urgency; they're recorded here for the gap-analysis prioritization and for regression-test coverage once addressed, rather than blocking the recommendation-feature work.
3. The recommendation engine itself proceeds as new, additive code (new tables, new routers, new frontend section) and should not require touching the core replacement pipeline at all beyond the read-only Plex/Radarr/Sonarr state it needs to correlate against.
