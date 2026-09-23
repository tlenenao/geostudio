# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- **Breaking: the `transform.qgis` pipeline operation and its
  `deploy/qgis-worker/` sidecar have been removed entirely** (GPL-2.0-or-later
  licensing concern — GeoStudio's engine policy requires MIT/BSD/Apache/EDL).
  Removed: the QGIS Processing execution path in `core/app/pipelines/`, the
  `qgis-worker` container and its `docker-compose.yml` wiring (`etl` profile,
  shared `etl-scratch` volume entry), the `core-qgis` CI job, and the
  `geostudio-qgis-worker` published image. The 50-algorithm allowlist
  (`core/app/pipelines/ops/qgis_algorithms.{py,json}`) is kept deliberately —
  it is still used by `core/scripts/fme_coverage_cli.py` to validate the 7
  raster rows below — but nothing in the pipeline runtime executes against it
  any more.
  **There is no automatic migration.** Any existing pipeline with a
  `transform.qgis` node will fail to load/run after upgrading
  (`OPERATIONS.get("transform.qgis")` returns `None`). 12 of the 19 FME
  transformers this engine used to cover now have a drop-in GeoStudio
  operation; the other 7 (all raster) have no replacement in this release.
  Manual migration table (old `algorithmId` → new op, or none):

  | FME transformer | old QGIS `algorithmId` | replacement |
  |---|---|---|
  | CenterPointReplacer | `native:centroids` | `transform.centroid` |
  | HullReplacer | `native:convexhull` | `transform.convexHull` |
  | Generalizer | `native:simplifygeometries` | `transform.simplify` |
  | BoundingBoxReplacer | `qgis:minimumboundinggeometry` | `transform.boundingGeometry` |
  | Snapper | `native:snapgeometries` | `transform.snapToLayer` |
  | AreaOnAreaOverlayer | `native:union` | `transform.resolveOverlaps` |
  | TINGenerator | `native:delaunaytriangulation` | `transform.triangulate` |
  | SurfaceModeller | `native:delaunaytriangulation` | `transform.triangulate` |
  | Densifier | `native:densifygeometriesgivenaninterval` | `transform.densify` |
  | MinimumSpanningCircleReplacer | `qgis:minimumboundinggeometry` | `transform.minimumBoundingCircle` |
  | Clipper | `native:clip` | `transform.intersection` (`outputGeometry: "intersection"`, equivalent to FME's `Inside` port) |
  | Dissolver | `native:dissolve` | `transform.aggregate` + `ST_Union_Agg` |
  | RasterResampler | `gdal:warpreproject` | *(none — raster unsupported)* |
  | RasterHillshader | `native:hillshade` | *(none)* |
  | RasterSlopeCalculator | `native:slope` | *(none)* |
  | RasterAspectCalculator | `native:aspect` | *(none)* |
  | RasterToPolygonCoercer | `gdal:polygonize` | *(none)* |
  | DEMGenerator | `qgis:tininterpolation` | *(none)* |
  | ContourGenerator | `gdal:contour` | *(none)* |

  Pipeline authors relying on one of the 7 raster QGIS algorithms have no
  migration path in this release — raster support does not exist anywhere in
  the pipeline engine (architectural gap, not a technical one; see
  `docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md`
  §8.6 and §7.5).

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

- A `procrastinate` connector (`SyncPsycopgConnector`) that prevented the
  `worker` service from starting under `docker compose up` — found during
  SP-7's branch-final review but left unresolved there, then fixed in a
  dedicated debugging session on 2026-07-13, outside any SP branch.
- A missing `tenant_id` on the `Config`/`ConfigRevision` ORM models that a
  real Alembic-migrated deployment would have hit as an `IntegrityError` —
  found as a pre-existing, unrelated defect during SP-6b's branch-final
  review, deferred, and fixed in the same 2026-07-13 dedicated debugging
  session as the item above.
- An MCP write path that bypassed the extension-widget permission-scope
  check enforced on the equivalent REST routes — found and fixed during
  SP-8c's branch-final review.

[Unreleased]: https://github.com/tlenenao/geostudio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tlenenao/geostudio/releases/tag/v0.1.0
