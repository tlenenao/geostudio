# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-16

Retroactive entry covering everything shipped since the fork from
`gis-project` (2026-07-05, "option C" strangler rewrite) through SP-9's
governance/legal sub-part. See `CLAUDE.md` for the full session-by-session
history this summarizes.

### Added

- **Shell (builder & catalog)**: catalog, sharing/publication, map editor,
  full no-code builder (pages, variables, themes, templates, breakpoints,
  embryonic SDK).
- **Core platform**: JWT/OIDC auth (with a mock mode), `tenants`/`users`/
  `audit_log`, module-boundary linting, `items` module with sharing/
  publication (`can()`, groups, anonymous public items), collection registry
  with live schema introspection and per-collection RLS, OGC API Features
  (Part 1+4) for reading/writing collection data, feature-count tracking.
- **MCP server**: OAuth 2.1 + PKCE authenticated `/mcp` endpoint, 7 business
  tools (`list_items`, `get_item`, `get_app_config`, `save_app_config`,
  `create_item`, `get_sharing`, `set_sharing`), then a v1 with
  `search_catalog`, `query_features`, `create_form_app`. Same repository
  functions and `can()` gate as the REST API.
- **No-code builder features**: Formulaire widget (schema-driven forms with
  overrides, create/update/delete, geometry field), edit-from-selection on
  map/table click, CEL expressions (`visibleWhen`, calculated columns,
  generalized `{ $expr: ... }` bindings on any widget prop), composed
  actions with optional CEL conditions, typed variables.
- **Ingestion pipeline**: background jobs on Postgres (`procrastinate`, no
  broker), file upload via presigned S3 URLs, parsers for GeoJSON/CSV/
  GeoPackage/zipped Shapefile (pure Python + `pyogrio`/`pyproj`, automatic
  CRS reprojection to WGS84), automatic collection + map item creation.
- **Semantic search**: pgvector-backed hybrid search (trigram + vector,
  Reciprocal Rank Fusion) across items and collections, permission-filtered
  before scoring.
- **Web Component SDK**: widget contract for standard Web Components (no
  React required), `WcHost` bridge (props/data/user/navigate as DOM
  properties, event/action wiring, native theme inheritance), a dynamic
  extension registry (`app.extensions`) letting an admin register and
  activate/deactivate externally-hosted widget modules without a shell
  redeploy, server-side permission scoping for extension widget data
  sources, a zero-dependency reference external widget and authoring guide.
- **Collections administration**: admin UI to list, register (from
  introspected PostGIS candidates), edit, share (groups × roles), and
  unregister collections, entirely as a façade over already-audited routes.
- **Governance & legal**: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant v2.1), SPDX Apache-2.0 headers across
  `core/app/`, `core/tests/`, `shell/src/`.
- **CI**: `shell` job (`npm run test`/`npm run e2e`/`npm run build`) added
  alongside the existing `migrations`/`core`/`api-types-drift` jobs; a
  `release.yml` workflow builds and publishes versioned `core`/`shell`/
  `postgis` images to `ghcr.io/tlenenao/geostudio-*` on `vX.Y.Z` tags.

### Changed

- GeoNode, Superset, and Redis fully removed from the compose stack and the
  codebase (milestone M1, 2026-07-09) — all content operations now go
  through the core.
- `pg_featureserv` removed from the compose stack once the shell reads its
  feature layers directly from the core's OGC API Features endpoints.

### Fixed

- Several latent bugs found and fixed during branch-final reviews across
  SP-5 through SP-8 (see `CLAUDE.md` for the detailed list per sub-part):
  notably a `procrastinate` connector that prevented the worker service
  from starting under `docker compose up`, a missing `tenant_id` on the
  `Config`/`ConfigRevision` ORM models that a real Alembic-migrated
  deployment would have hit as an `IntegrityError`, and an MCP write path
  that bypassed the extension-widget permission-scope check enforced on
  the equivalent REST routes.

[Unreleased]: https://github.com/tlenenao/geostudio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tlenenao/geostudio/releases/tag/v0.1.0
