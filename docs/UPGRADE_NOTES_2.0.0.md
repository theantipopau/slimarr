# Upgrading to Slimarr 2.0.0

**Theme:** Backend audit and reliability fixes, a competitive gap analysis
against mature *arr platforms, and a new deterministic **Discovery &
Recommendations** feature.

This release does not remove or rename anything. Every existing config key,
API route, and behavior from 1.9.0.0 is unchanged unless explicitly noted
below. The new feature is off by default — upgrading and restarting with no
config changes at all leaves Slimarr behaving exactly as it did in 1.9.0.0.

## What's new

- **Discovery & Recommendations** — a new page that suggests titles related
  to what you already own (missing collection entries, sequels/prequels,
  related titles), each with a deterministic score and a human-readable
  reason. See `docs/RECOMMENDATION_ARCHITECTURE.md`.
- **Region-specific streaming availability** via TMDB's own
  `/watch/providers` endpoint, timestamped and treated as stale after 24
  hours. No streaming service is ever scraped or asked for credentials.
- **Explicit, capability-checked hand-off to Radarr/Sonarr** from a
  recommendation — never automatic, and always duplicate-checked against
  the live instance first. Seerr hand-off is not implemented this release;
  see `docs/RECOMMENDATION_INTEGRATIONS.md` for why.
- **Optional, provider-neutral AI reranking abstraction**, disabled by
  default with only a no-op provider shipped. It can rerank an
  already-sourced candidate list or produce short explanations — nothing
  more. See `docs/RECOMMENDATION_PRIVACY.md` for exactly what it can and
  cannot see.
- Two confirmed backend correctness fixes found during the audit (orphan
  cleanup could lose track of a download on a failed removal; two SABnzbd
  error paths could log an API key). See `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md`.

## Do I need to do anything to upgrade?

No. `config.yaml` is loaded with defaults for any key you don't set, so a
1.9.0.0 config file loads unchanged. If you're on SQLite, the five new
recommendation tables are created automatically the first time the new
backend starts (`init_db()` calls `create_all()`, as it always has) — there
is no manual migration step. If you're on PostgreSQL, the same applies; no
`ALTER TABLE` statements are required for existing tables.

`SCHEMA_VERSION` moves from `5` to `6` to reflect the new tables. This is a
metadata bump only, consistent with how prior additive schema changes have
been versioned in this project — it does not gate startup or trigger a
destructive migration.

## Trying Discovery

Recommendations are entirely opt-in:

```yaml
recommendations:
  enabled: true
  region: "US"   # required for streaming-availability lookups; leave empty to skip them
```

With `enabled: false` (the default), the Discovery page shows a clear
"disabled" state, no TMDB calls beyond what Slimarr already makes for
library enrichment happen, and `POST /recommendations/refresh` is refused.

Once enabled, trigger the first refresh from the Discovery page's **Refresh**
button, or `POST /api/v1/recommendations/refresh`. The refresh runs as a
durable background job (visible on the Operations page like any other job),
walking your owned movies once and sourcing/scoring candidates — it does
not run on every request.

## Config keys added

All new; none replace or rename an existing key. Full reference and
defaults are in the README's Configuration section and
`config.yaml.example`.

- `recommendations.enabled` (default `false`)
- `recommendations.region` (default `""` — no streaming lookups until set)
- `recommendations.subscribed_providers`
- `recommendations.enabled_categories`
- `recommendations.media_types` (movies only in this release; `tv` is
  accepted by the schema for forward compatibility but not yet sourced)
- `recommendations.minimum_score`
- `recommendations.languages`, `genres_include`, `genres_exclude`,
  `excluded_keywords`
- `recommendations.use_plex_watch_history` (default `false`)
- `recommendations.refresh_interval_hours`
- `recommendations.max_recommendations_retained`
- `recommendations.ai.*` (default `enabled: false`, `provider: "none"`) —
  see `docs/RECOMMENDATION_PRIVACY.md` before turning this on

## API routes added

All new, under `/api/v1/recommendations` — see `docs/RECOMMENDATION_INTEGRATIONS.md`
and `backend/api/recommendations.py`. None of Slimarr's existing routes
changed shape or behavior.

## Known limitations in this release

- TV recommendations are not sourced yet (movies only); see
  `docs/RECOMMENDATION_ARCHITECTURE.md`'s "Known Limitations" section.
- Seerr hand-off reports as unavailable — verifying a live instance's actual
  API surface is out of scope for this release rather than guessed at.
- Only a no-op AI provider ships; real adapters (OpenAI-compatible,
  Anthropic, Azure OpenAI, Ollama) are documented as future work in
  `docs/RECOMMENDATION_ARCHITECTURE.md` rather than implemented against
  undocumented behavior.

## Rolling back

Because the new tables and config keys are purely additive, a rollback to
1.9.0.0 is safe: the older backend simply ignores the new tables and the
`recommendations:` config block. No data written by this feature is
referenced by, or required for, any 1.9.0.0 code path.
