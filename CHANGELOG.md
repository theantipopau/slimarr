# Changelog

All notable changes to Slimarr are documented here.

---

## [1.0.0.3] — 2026-04-27

### Release focus

Failed download recovery and diagnostics. This release adds comprehensive tooling to detect, diagnose, and recover from failed downloads—including automatic folder cleanup, downloader history purge, and a dedicated failed-download management page.

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
  * "Retry Search" button (stubbed for Phase 2)
  * Real-time updates via `download:cleanup` socket events
- Pagination ready (initial: 50 failed downloads per page)

**API additions**
- `GET /queue/failed?limit=50` — fetch failed downloads with cleanup metadata
- `POST /queue/{id}/cleanup` — manually trigger cleanup for a download
- Updated `/queue/active` and `/queue/recent` responses to include `storage_path` and `cleanup_status`

**Diagnostics**
- Download model now tracks:
  * `storage_path` — downloader's folder location (captured from job metadata)
  * `cleanup_status` — cleanup attempt outcome
- Logs now include full storage paths for failed jobs, making it easy to diagnose orphaned folders
- Failed downloads are queryable by status, making audit and recovery workflows simpler

**Download client improvements**
- Download client protocol now defines `purge_job()` contract — all downloader adapters must implement it
- SABnzbd client now uses `queue?action=delete` API for clean history removal
- NZBGet client now uses `editqueue` RPC with `GroupDelete` operation for job removal
- Client purge failures are non-fatal and logged as warnings (cleanup continues with folder deletion)

**Next steps (Phase 2)**
- Implement retry ladder: on failure, automatically try next accepted candidate instead of marking movie as failed
- Add blacklist memory: prevent same exact release from retrying repeatedly
- Add orphan scanner: find downloader folders that Slimarr no longer tracks, offer bulk cleanup
- Implement retry endpoint: `/POST /queue/{id}/retry`

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
