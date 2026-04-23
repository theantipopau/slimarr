# Changelog

All notable changes to Slimarr are documented here.

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
