# Slimarr v1.3 Plan

## Release Focus

Slimarr v1.3 is the Media Intelligence + Premium Automation release. The goal is to make every search, comparison, and automation decision explainable, especially when the search pipeline is degraded or a candidate release is risky.

Primary principles:

- Stability first
- Transparency second
- Automation third
- Never silently fail
- Never silently make dangerous decisions

## Search Diagnostics

v1.3 adds a bounded in-memory search diagnostics subsystem and UI page at `/system/search-diagnostics`.

Captured diagnostics include:

- Redacted request URLs for Prowlarr and Newznab
- Provider/indexer name
- HTTP status code
- Response latency
- Raw and parsed result counts
- Timeout, auth, HTTP, and parser failures
- Category mismatch warnings
- Filtering summaries and rejection reasons
- Failure heatmap
- Indexer reliability metrics
- Last successful search

Live diagnostics are retained in memory with caps to prevent unbounded growth, and persisted diagnostics history is stored on disk for incident review and support bundles. Raw payload previews are truncated and redacted before exposure.

## Search Test Harness

The Search Test Harness runs manual searches without downloads and without mutating library state.

It exposes:

- Provider raw payload previews
- Parsed results
- Accepted candidates
- Rejected candidates
- Filtering stages
- Media health and comparison reasoning

Known limitation: raw previews are diagnostic samples, not archival payload storage.

## Degraded Pipeline Detection

Slimarr now detects suspicious search behavior instead of reporting healthy cycles with misleading zero-result logs.

Warning states:

- 100+ consecutive zero-result searches
- Missing search provider configuration
- Category mismatch warnings

Blocking states:

- Repeated all-provider search failures

Zero-result streaks are warning-only so niche libraries are not blocked forever. Provider failures block automation when Slimarr can show that searches are failing rather than merely empty.

## Quality Intelligence V2

The comparison engine now parses and scores richer release metadata:

- Resolution
- Source type
- Video codec
- HDR and Dolby Vision markers
- Audio codec and channel count
- Language markers
- Subtitle risk markers
- Release group/uploader
- PROPER/REPACK
- Suspicious file-size signals

Poor local copies such as CAM, TS, HDCAM, weak 720p, poor WEBRip, and low-bitrate files can be targeted for higher quality replacements. A larger candidate is allowed only when the local copy is clearly poor and the candidate is a bounded good-source 1080p upgrade.

## Dolby Vision Safety Mode

Defaults:

```yaml
comparison:
  avoid_dolby_vision: true
  allow_dolby_vision_with_hdr_fallback: false
```

DV-only releases are rejected by default to avoid Plex/client compatibility issues. HDR10, HDR10+, HLG, and SDR releases are allowed normally. Hybrid DV/HDR10 releases can be allowed explicitly.

## Language and Audio Safety

Defaults:

```yaml
comparison:
  preferred_language: "english"
  require_english_audio: true
  reject_dual_audio: false
  reject_multi_audio: false
  reject_hardcoded_subs: true
```

Explicit non-English-only audio is rejected when English audio is required. Hardcoded subtitle markers such as KORSUB, VOSTFR, HC, HCSUB, HARDCODED, and SUBBED are rejected by default. Unknown language is not rejected unless a stricter future mode requires it.

## Media Health

Media Health ratings:

- Excellent
- Good
- Acceptable
- Risky
- Reject

Health considers source, resolution, codec, suspicious file size, DV risk, subtitle risk, language markers, uploader reliability, and local file quality signals. MediaInfo-backed probing is now used to enrich missing local stream metadata during scans.

## Large Library and Observability Work

Implemented in this pass:

- Search diagnostics retention caps
- Additive database migrations for media health fields
- Search-result and decision-audit metadata for richer UI explanations
- Additional indexes for search results, decision audit, and activity log history
- Persisted diagnostics history with pagination and text search API
- Search diagnostics history surfaced in the UI and included in support bundles
- Poster lazy-loading and staged image rendering for large libraries
- MediaInfo-backed bitrate/stream detection fallback during scans

Remaining candidates:

- WebSocket throttling for very active installs
- Diagnostics bundle expansion with decision timelines
- ffprobe-backed deep stream inspection parity (optional, for environments where ffprobe is preferred)

## Known Limitations

- Live diagnostics counters and in-memory reliability windows reset on restart, but persisted diagnostics history remains available on disk.
- MediaInfo probing is best-effort and currently runs only when Plex metadata is missing key stream fields.
- Prowlarr reliability is measured at the aggregate Prowlarr response level; per-indexer reliability inside Prowlarr depends on what Prowlarr includes in search payloads.
- Search Test Harness uses a fixed comparison baseline so it is diagnostic, not a perfect substitute for a real movie-specific comparison.
