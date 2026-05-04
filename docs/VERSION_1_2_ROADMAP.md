# Slimarr v1.2.0.0 Roadmap

Date: 2026-05-04
Status: Proposed

## Goals

1. Keep replacements under Slimarr control after a successful optimize action.
2. Improve trust and safety of automation decisions.
3. Harden local-network security defaults without breaking home-lab workflows.
4. Upgrade UI clarity and visual quality to a premium, high-signal operations console.
5. Raise release quality with tests, telemetry, and stronger installer/runtime checks.

## Deep Audit Summary

This roadmap is based on a code-level audit across backend, frontend, installer, and docs.

High-impact observations:
- Radarr is triggered post-replace for rescan only today, but there is no policy bridge to prevent Radarr re-upgrades after Slimarr optimization.
- TLS verification is globally disabled for multiple HTTP clients, which is convenient but unsafe as a default.
- Auth/session model uses localStorage bearer tokens and permissive CORS, which is acceptable for localhost-only but weak for LAN exposure.
- API response shapes are inconsistent across routes (mixed success envelopes and plain payloads).
- Settings and System pages are feature-rich but visually dense; key actions and risk states can be clearer.
- No dedicated automated test suite gate is enforced for core decision logic and integration boundaries.

## Proposed Scope By Category

### 1) Functionality and Reliability

1. Add Radarr post-replace policy controls (High, M)
- Add settings to choose one of: rescan only, rescan + unmonitor movie, or no Radarr action.
- Add optional cooldown lock (for example 7 days) to prevent immediate re-upgrade loops.
- Files: backend/core/replacer.py, backend/integrations/radarr.py, backend/config.py, frontend/src/pages/Settings.tsx.

2. Add per-movie replacement lock (High, M)
- Mark optimized movies as Slimarr-locked to avoid repeated replacement churn.
- Add lock badge and override action in Movie Detail.
- Files: backend/database.py, backend/core/orchestrator.py, backend/api/library.py, frontend/src/pages/MovieDetail.tsx.

3. Add source-of-truth outcome states for replacement lifecycle (Med, M)
- Standardize statuses: queued, downloading, processing, replaced, skipped, blocked, failed.
- Prevent ambiguous transitions in retry scenarios.
- Files: backend/core/download_workflow.py, backend/core/downloader.py, backend/api/queue.py.

4. Add smarter exclusion presets (Med, S)
- Presets for kids library, family videos, and archival remux retention.
- Files: backend/config.py, frontend/src/pages/Settings.tsx.

5. Add pre-replace risk simulation panel (Med, M)
- Show disk, path mapping, and rollback likelihood before replacement starts.
- Files: backend/api/system.py, frontend/src/pages/System.tsx.

6. Add bulk approve/reject for review-required mode (Med, M)
- Improve operation speed for large libraries.
- Files: backend/api/library.py, frontend/src/pages/Library.tsx, frontend/src/pages/MovieDetail.tsx.

### 2) Security Hardening

7. Default to TLS verify true with per-integration opt-out (High, M)
- Replace unconditional verify=False with configurable trust policy.
- Allow local self-signed mode explicitly per service.
- Files: backend/main.py, backend/integrations/radarr.py, backend/integrations/sonarr.py, plus other integration clients.

8. Restrict CORS by config instead of wildcard (High, S)
- Default allow localhost origins only.
- Add optional LAN origins list in config.
- Files: backend/main.py, backend/config.py.

9. Improve password policy and lockout model (High, S)
- Increase minimum complexity, add progressive backoff on login attempts.
- Files: backend/auth/router.py.

10. Replace localStorage auth token with httpOnly cookie mode option (High, L)
- Keep bearer token mode for backward compatibility.
- Add secure cookie mode for local server usage.
- Files: backend/auth/router.py, backend/auth/dependencies.py, frontend/src/lib/auth.ts, frontend/src/lib/api.ts.

11. Add audit events for auth and settings changes (Med, S)
- Capture login failures, successful auth, settings writes, and key integration toggles.
- Files: backend/auth/router.py, backend/api/settings.py, backend/database.py.

### 3) Installer and Runtime Robustness

12. Add first-run readiness checks after install (High, S)
- Validate config, write permissions, db init, and frontend assets before opening browser.
- Files: start.bat, build-installer.ps1, tray.py.

13. Add startup diagnostics bundle command (Med, S)
- One-click collect logs, config redactions, health output for support.
- Files: backend/api/system.py, scripts/.

14. Add venv integrity hash and dependency lock verification for source installs (Med, M)
- Detect drift and suggest repair action.
- Files: install.ps1, update.bat.

### 4) Backend Architecture and Maintainability

15. Create service-layer modules for settings, health, and queue orchestration (Med, M)
- Reduce router complexity and tighten separation of concerns.
- Files: backend/api/*.py, backend/core/*.py.

16. Centralize error envelope and exception mapping (High, M)
- Standard response schema: code, message, details, correlation_id.
- Files: backend/main.py, backend/api/*.py.

17. Add idempotency guards for background tasks (Med, M)
- Prevent duplicate task starts and race windows.
- Files: backend/scheduler/scheduler.py, backend/core/orchestrator.py, backend/api/system.py.

### 5) API Consistency and Developer Experience

18. Add OpenAPI response models for all endpoints (Med, M)
- Ensure predictable frontend typing and clearer docs.
- Files: backend/api/*.py.

19. Add API versioned contract tests (Med, M)
- Validate key payload shapes consumed by frontend.
- Files: tests/api/ (new).

20. Add request correlation IDs and structured logs (Med, S)
- Improve tracing across async jobs and integrations.
- Files: backend/utils/logger.py, backend/main.py.

### 6) UI/UX Flow and GUI Clarity

21. Introduce guided setup wizard for first run (High, M)
- Stepper: Plex -> Downloader -> Search source -> TMDB -> Dry-run check -> Go live.
- Files: frontend/src/pages/Login.tsx, frontend/src/pages/Settings.tsx, frontend/src/App.tsx.

22. Add global command bar and quick actions (Med, M)
- Keyboard command palette for scan, run cycle, pause, retry failed, open logs.
- Files: frontend/src/components/, frontend/src/pages/Dashboard.tsx.

23. Improve action confirmation UX with risk tiers (Med, S)
- Replace generic confirm() dialogs with modal cards explaining impact and rollback.
- Files: frontend/src/pages/System.tsx, frontend/src/pages/Settings.tsx.

24. Add persistent operation timeline panel (Med, M)
- Unified feed for scan, search, download, replace, radarr action, cleanup.
- Files: frontend/src/pages/Dashboard.tsx, frontend/src/pages/Activity.tsx.

25. Improve settings information architecture (Med, M)
- Split into tabs and sticky section summary with validation counters.
- Files: frontend/src/pages/Settings.tsx.

### 7) Visual Design and Premium Finish

26. Add design token system and refined typographic scale (Med, M)
- Define color, spacing, radius, elevation, and motion tokens.
- Files: frontend/src/index.css, tailwind config.

27. Upgrade dashboard visual hierarchy (Med, M)
- More contrast between primary action zone, health, and timeline.
- Files: frontend/src/pages/Dashboard.tsx, frontend/src/components/StatCard.tsx.

28. Add subtle motion language (Low, S)
- Page transitions, skeleton loading, status pulse states.
- Files: frontend/src/index.css, frontend/src/components/.

29. Accessibility pass for contrast and keyboard flow (High, M)
- Focus rings, aria labels, table navigation, reduced motion support.
- Files: frontend/src/**/*.tsx.

### 8) Performance

30. Add server-side pagination and query tuning for large libraries (High, M)
- Improve heavy table endpoints and dashboard aggregations.
- Files: backend/api/library.py, backend/api/dashboard.py, backend/database.py.

31. Add cached health and stats invalidation strategy (Med, S)
- Avoid duplicate polling load from multiple pages.
- Files: backend/api/system.py, frontend polling hooks.

32. Optimize initial dashboard payload (Low, S)
- Defer secondary widgets and lazy fetch low-priority data.
- Files: frontend/src/pages/Dashboard.tsx.

### 9) Testing and Release Quality

33. Add backend unit tests for compare/replacer/radarr policy bridge (High, M)
- Include regression test for post-replace Radarr re-upgrade prevention mode.
- Files: tests/backend/ (new).

34. Add integration tests for settings save/test and auth flows (High, M)
- Cover unsaved test behavior and secure-mode auth.
- Files: tests/api/ (new).

35. Add frontend smoke tests for core pages and critical actions (Med, M)
- Dashboard, Library, Settings, System paths.
- Files: frontend tests (new).

36. Add release checklist automation (Med, S)
- Verify installer boot, health endpoint, and browser launch sequence.
- Files: scripts/, build-installer.ps1.

### 10) Observability and Troubleshooting

37. Add user-facing incident panel (Med, S)
- Surface recent errors with quick remediation hints.
- Files: frontend/src/pages/System.tsx, backend/api/system.py.

38. Add structured event taxonomy for lifecycle actions (Med, S)
- Standard event names for scan/search/download/replace/rescan/cleanup.
- Files: backend/realtime/events.py, backend/core/*.py.

39. Add health history snapshots (Med, M)
- Trend view for service uptime, queue depth, and failure rates.
- Files: backend/database.py, backend/api/system.py, frontend/src/pages/System.tsx.

## Roadmap Milestones

### Milestone A: Control and Safety (v1.2.0.0-alpha)

Scope:
- Items 1, 2, 7, 8, 9, 16, 33.

Acceptance criteria:
- User can enable "rescan + unmonitor" for Radarr in settings.
- After successful replacement with that mode, Radarr does not auto-upgrade monitored status for the movie.
- TLS defaults to verified connections unless user explicitly opts out.
- CORS defaults to localhost-only policy.
- Core replacement/radarr behavior covered by tests.

### Milestone B: UX and Premium Console (v1.2.0.0-beta)

Scope:
- Items 21, 22, 23, 24, 25, 26, 27, 29, 32.

Acceptance criteria:
- First-run setup wizard successfully configures a clean install.
- Settings page validation and navigation reduce setup time and misconfiguration.
- Dashboard provides clearer action hierarchy and live operational timeline.
- Accessibility checks pass for keyboard navigation and contrast targets.

### Milestone C: Reliability, Performance, and Release Quality (v1.2.0.0-rc)

Scope:
- Items 12, 13, 14, 15, 18, 19, 20, 30, 31, 34, 35, 36, 37, 38, 39.

Acceptance criteria:
- Installer startup checks confirm healthy backend before browser open.
- API contracts are consistent and tested.
- Large-library queries meet target response times.
- Release pipeline includes installer smoke verification and test gates.

## Explicit v1.2.0.0 Feature Proposal: Radarr Post-Replace Control

Proposed settings block:
- radarr.post_replace_action: rescan | rescan_unmonitor | none
- radarr.reupgrade_cooldown_days: integer (optional)
- radarr.only_apply_to_slimarr_replacements: true by default

Expected user outcome:
- Slimarr savings do not get immediately undone by Radarr quality upgrades unless user chooses that behavior.

## Non-Goals For v1.2.0.0

- Full multi-user RBAC.
- Cloud-hosted orchestration.
- TV episode replacement parity with movies.

## Risks and Dependencies

- Cookie-mode auth requires careful migration to avoid breaking current bearer-token installs.
- TLS hardening may require clearer self-signed onboarding to avoid support churn.
- UI redesign must preserve current power-user speed for bulk operations.

## Definition of Done for v1.2.0.0

- Milestones A, B, and C acceptance criteria pass.
- Changelog and migration notes updated.
- Installer and source install paths validated on a clean Windows host.
- No regression in replacement safety guarantees (never replace with larger file).
