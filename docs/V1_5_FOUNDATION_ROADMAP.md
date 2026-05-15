# Slimarr v1.5+ Foundation Roadmap

This document defines the v1.5 architectural evolution from a mature containerized app
into a production-grade self-hosted media optimization platform.

## 1) Full Implementation Plan

### Scope principle
- Keep SQLite default and lightweight behavior intact.
- Add optional advanced capabilities behind clear runtime flags/config.
- Prefer additive schema and API evolution only.

### v1.5 execution goals
- Optional PostgreSQL backend with zero-regression SQLite behavior.
- In-process worker isolation framework that can later split into separate processes/nodes.
- Advanced observability persistence and trend analytics.
- ffprobe-powered media intelligence expansion.
- Operational UX improvements for homelab deployment and supportability.

## 2) Architectural Refactor Roadmap

### Phase A: Data and runtime substrate
- Introduce database capability abstraction (`DatabaseCapabilities`) for backend-specific behavior.
- Add async database health probes, retry policies, and pool diagnostics.
- Introduce `TaskRuntime` abstraction with typed task envelopes and heartbeats.

### Phase B: In-process worker plane
- Add worker interfaces: `Worker`, `TaskEnvelope`, `TaskResult`, `RetryPolicy`.
- Introduce queue persistence table and task lifecycle events.
- Route long-running work through worker bus instead of direct orchestrator calls.

### Phase C: Operational intelligence plane
- Persist time-series metrics snapshots.
- Add diagnostics analytics APIs with trend windows and grouped aggregations.
- Add richer dashboard surfaces for worker, provider, and queue health.

### Phase D: Media intelligence plane
- Add ffprobe service layer with cached probe records.
- Extend compare engine weighting for stream/HDR/audio compatibility.
- Add profile-aware policy engine for quality-intent decisions.

## 3) Risk Assessment

### High risk
- Migration complexity between SQLite and PostgreSQL.
- Concurrency regressions from worker transition.
- Diagnostics write amplification and storage growth.

### Medium risk
- ffprobe runtime cost on large libraries.
- UI complexity growth without progressive disclosure.

### Mitigations
- Feature-flag every major subsystem change.
- Keep fallback behavior to current path when advanced subsystem fails.
- Add targeted stress tests and soak tests before default-enabling features.

## 4) Database Evolution Plan

### Current status
- SQLite remains default.
- Optional PostgreSQL backend introduced as environment-driven backend selection.

### v1.5 next steps
- Add explicit `SLIMARR_DB_URL` docs and validation diagnostics.
- Add backend capability report in diagnostics bundle.
- Add migration revision table for deterministic schema version reporting.
- Add PostgreSQL compose templates with tuned pool settings.

### Safety controls
- Startup retry/backoff.
- Pool limits and timeout defaults.
- Slow-query logging.
- DB backend telemetry (`backend`, pool checked-out, growth trend).

## 5) Worker Architecture Proposal

### Worker classes
- `ScanWorker`
- `SearchWorker`
- `CompareWorker`
- `DownloadMonitorWorker`
- `DiagnosticsWorker`
- `CleanupWorker`
- `MetadataWorker`

### Core interfaces
- `Worker.enqueue(task)`
- `Worker.cancel(task_id)`
- `Worker.heartbeat(task_id)`
- `Worker.status()`

### Execution model
- Start in-process with persisted queue table.
- Add watchdog loop for stuck-task detection.
- Add retry history and bounded exponential backoff.

### Future-ready path
- Move queue backend to Redis when needed.
- Spawn worker containers sharing the same event schema.

## 6) Observability Roadmap

### Metrics expansion
- Search latency percentiles by provider.
- Provider uptime/degradation counters.
- Download lifecycle success/failure categories.
- Compare decision distribution by quality intent.
- Daily reclaim trend (`bytes_reclaimed_per_day`).

### Diagnostics persistence
- Time-series snapshot table (hourly/day buckets).
- Trend APIs with rolling windows (24h, 7d, 30d).

### Tracing
- Correlation ID propagation into worker/task events.
- Task lineage (`parent_task_id`, `origin`, `attempt`).
- Optional OpenTelemetry exporter path (off by default).

## 7) ffprobe / Media Intelligence Plan

### Service design
- `MediaProbeService` with provider chain: ffprobe -> MediaInfo -> parser fallback.
- Async execution with timeout and process-budget limits.
- Probe cache table keyed by path+mtime+size hash.

### Extracted dimensions
- HDR type, Dolby Vision profile/layer, color primaries/transfer/matrix.
- Audio codec/channel layout/object metadata.
- Subtitle stream inventory including forced/default flags.
- True stream bitrate/frame-rate/profile levels.

### Compare impacts
- Device compatibility score.
- Transcode risk score.
- HDR safety score.
- Stream fidelity score.

## 8) Docker UX Improvements

### Near-term
- First-run deployment wizard with compose/env generator.
- Volume mapping assistant and writable-path tests.
- Reverse-proxy helper and networking diagnostics.

### Platform templates
- Unraid template.
- Synology template.
- Portainer stack example.
- CasaOS app definition.
- Experimental Kubernetes manifests.

## 9) Reliability Audit Findings

### Findings
- Single-process orchestration can still stall API responsiveness under load.
- Queue lifecycle and retry reasons need deeper persistence and visibility.
- Long-running operations need heartbeat and stuck-task heuristics.

### Actions
- Worker isolation with bounded concurrency.
- Standardized timeout/retry policy registry.
- Memory pressure and runaway task detectors.

## 10) CI/CD Expansion Plan

### Additions
- PostgreSQL integration test matrix.
- Docker startup smoke tests and compose validation.
- Worker concurrency stress tests.
- Long-run soak tests.
- Supply-chain scanning and SBOM generation.

### Release engineering
- Nightly/beta/stable channels.
- Signed artifacts and provenance metadata.
- Automated changelog/release-note generation.

## 11) Security Hardening Recommendations

### API and auth
- Introduce rate limiting middleware.
- Add CSRF protections for cookie-auth paths (future option).
- Add login audit history table.
- Add optional MFA groundwork (TOTP seed store, disabled by default).

### Secrets and diagnostics
- Extend redaction coverage for nested tokens and headers.
- Add insecure configuration warnings (public bind + weak auth).

### Runtime hardening
- Keep non-root container defaults.
- Continue dependency vulnerability scans in CI.

## 12) Future v2.0 Considerations

- Distributed task bus (Redis/NATS/Kafka adapter).
- Remote worker nodes and site-level scan agents.
- Object-storage support for artifacts and diagnostics bundles.
- ML-assisted release quality scoring with explainability constraints.

## 13) Detailed Changelog Draft (v1.5 foundation)

### Added
- Optional PostgreSQL backend selection via runtime DB URL.
- Database runtime diagnostics and pool metadata exposure.
- Slow-query timing instrumentation.
- Per-movie Quality Intent profile model with force-keep controls.
- Compare-engine profile-aware decisions and override notes.

### Changed
- Search evaluation now applies per-movie quality intent policies.
- Cycle processing skips force-kept movies for automation safety.

### Docs
- Added v1.5 roadmap and architectural migration plan.

## 14) Migration Notes

### SQLite users
- No migration action required.
- New quality-intent columns are additive and default-safe.

### PostgreSQL users (optional)
- Set `SLIMARR_DB_URL=postgresql+asyncpg://...`.
- Ensure `asyncpg` is installed in deployment image.
- Start once and verify `/api/v1/system/info` reports `db_backend=postgresql`.

## 15) Suggested Directory Structure Evolution

```
backend/
  workers/
    base.py
    bus.py
    policies.py
    scan_worker.py
    search_worker.py
    compare_worker.py
    download_worker.py
    diagnostics_worker.py
    cleanup_worker.py
    metadata_worker.py
  services/
    db_capabilities.py
    metrics_store.py
    media_probe_service.py
    tracing.py
  policies/
    quality_intent.py
    device_profiles.py
```

## 16) Technical Debt Audit

- Uploader health lookup path is SQLite-specific and should move to async SQLAlchemy service.
- Some orchestrator paths still directly invoke long-running operations.
- Diagnostics domain has mixed in-memory and persisted pathways.
- Add stricter typing for ad-hoc dict payloads in worker/diagnostic events.

## 17) Performance Bottleneck Analysis

### Bottlenecks
- Search result scoring loops under high result volume.
- Diagnostics serialization overhead under high event rates.
- SQLite write contention in high-frequency update paths.

### Mitigations
- Batch writes for diagnostics and task events.
- Worker queue backpressure and rate limiting.
- Optional PostgreSQL for write-heavy deployments.

## 18) Prioritized Implementation Phases

### P0 (now)
- Quality intent profile core with force-keep safeguards.
- DB backend abstraction and diagnostics visibility.

### P1
- Worker runtime abstraction and in-process queue persistence.
- Worker dashboard and heartbeat/stuck-task detection.

### P2
- ffprobe integration + compatibility scoring.
- Historical metrics persistence and trend APIs.

### P3
- Deployment wizard, compose/env generation UX.
- Release engineering upgrades (SBOM/signing/channels).

---

## Preferred Quality / Force-Keep System (Implemented Foundation)

### Profiles
- `space_saver` (default)
- `balanced`
- `premium`
- `reference`
- `locked` / `pinned`

### Per-movie controls
- `quality_intent`
- `force_keep`
- `allow_larger_replacements`
- `quality_profile_overrides` (JSON)

### Current policy behavior
- `locked`/`pinned` or `force_keep=true`: automatic replacements rejected.
- `balanced`/`premium`/`reference`: optional larger replacement acceptance based on profile gates.
- Override hooks: `preferred_codec`, `preferred_sources`, `resolution_floor`, `reject_release_groups`, `max_size_increase_pct`.

### API
- `POST /api/v1/library/movies/{movie_id}/quality-intent`
  - body: `{ quality_intent, force_keep, allow_larger_replacements, quality_profile_overrides }`

### Safety
- Force-kept movies are excluded from automation cycles.
- Compare notes include active quality intent for auditability.
