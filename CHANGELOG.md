# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **39 new pipeline operations**; the exposed catalogue is now 57 operations
  (59 in the raw registry, which also holds `reader.file` and `writer.file`,
  hidden unless `CORE_PIPELINE_FILE_IO_ENABLED=true`), all executed in DuckDB
  or in-process with Shapely (BSD-3-Clause):
  - 15 geometry/coordinate/SRID transformers: `swapCoordinates`,
    `translateGeometry`, `scaleGeometry`, `rotateGeometry`, `createGeometry`,
    `concatCoordinates`, `roundCoordinates`, `extractElevation`,
    `extractDimension`, `countVertices`, `extractCoordinates`, `extractSrid`,
    `setSrid`, `reprojectAttribute`, `formatCoordinates`;
  - 11 schema/cardinality transformers: `bulkRemoveAttributes`,
    `bulkRenameAttributes`, `scanSchema`, `explodeList`, `explodeGeometry`,
    `exposeAttributes`, `validateAttributes`, `sort`, `detectChanges`,
    `mergeChildren`, `mapSchema`;
  - 4 readers: `reader.connector.bigquery`, `reader.connector.mssql`,
    `reader.connector.oracle`, `reader.connector.blob`;
  - 9 replacements for the removed QGIS engine (see *Removed* below):
    `centroid`, `convexHull`, `simplify`, `boundingGeometry`, `snapToLayer`,
    `resolveOverlaps`, `triangulate`, `densify`, `minimumBoundingCircle`.
- `reader.file` / `writer.file` (local files through DuckDB spatial), disabled
  by default and gated by `CORE_PIPELINE_FILE_IO_ENABLED`.
- Optional `groupBy` (list of column names) on `transform.triangulate` and
  `transform.minimumBoundingCircle`: one triangulation / one circle per group
  instead of a single global result; empty (default) keeps the previous
  behaviour. Degenerate inputs (NULL geometry, empty input, non-point geometry
  for `triangulate`) now fail with an explicit pipeline error (HTTP 400 on
  preview) instead of an internal error.

### Removed

- **Breaking: the `transform.qgis` pipeline operation and its
  `deploy/qgis-worker/` sidecar have been removed entirely** (GPL-2.0-or-later
  licensing concern — GeoStudio's engine policy requires MIT/BSD/Apache/EDL).
  Removed: the QGIS Processing execution path in `core/app/pipelines/`, the
  `qgis-worker` container and its `docker-compose.yml` wiring (`etl` profile,
  shared `etl-scratch` volume entry), the `core-qgis` CI job, and the
  `geostudio-qgis-worker` published image. The 50-algorithm allowlist
  (`core/app/pipelines/ops/qgis_algorithms.{py,json}`) is kept as a
  historical FME↔QGIS reference table — no row in the coverage matrix
  currently validates against it (the 7 raster rows below are
  `capability_removed`, not `qgis_frozen`) — and nothing in the pipeline
  runtime executes against it.
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

### Changed

- **`geostudio-minio`'s image source changed from a pulled third-party image
  to a from-source AGPL rebuild**: `quay.io/minio/minio` and `minio/minio`
  (Docker Hub) are both locked out of anonymous pull on every tag (401/pull
  access denied, verified 2026-09-25), so `deploy/minio/Dockerfile` now
  compiles the MinIO server from its official sources
  (`github.com/minio/minio`) instead. The bundled MinIO server version moves
  from `RELEASE.2025-09-07T16-13-09Z` to `RELEASE.2025-10-15T17-29-55Z` — a
  one-way upgrade, since MinIO does not support downgrading a data volume
  once it has been started against a newer release, though this specific
  version gap has no known data-format concern. Existing production
  deployments pulling `ghcr.io/tlenenao/geostudio-minio:${GEOSTUDIO_VERSION}`
  will get "manifest unknown" until a new `v*` release tag is cut that
  includes this 9th published image (the same situation already exists for
  `geostudio-titiler`, not a new problem introduced here, but worth calling
  out for MinIO specifically since it is a newly published image).

- **Pre-release audit (P01–P15) — deployment and API notes.**
  - `core` image now installs the dependencies pinned by `uv.lock`.
  - Jobs: the API process opens the procrastinate connector (every
    `.defer()` used to raise `AppNotOpen`); the worker consumes `harvest`
    and runs `CORE_WORKER_CONCURRENCY` jobs (default 4). `GET /health` gains
    `jobsBacklog` (age/size of the job queue; `status` stays the liveness).
  - S3: set `S3_PUBLIC_ENDPOINT_URL` (public URL used to sign presigned
    links); in production Traefik routes it through the new `minio-s3`
    router on the hostname `S3_PUBLIC_HOST` (must point to the instance).
    MinIO CORS comes from `MINIO_API_CORS_ALLOW_ORIGIN`. File imports are
    capped by `CORE_UPLOAD_MAX_BYTES` (512 MiB by default, 413 above).
  - Secrets: the three token HMAC secrets are now generated at install
    (`bootstrap-env.sh`/`install.sh`); an empty key counts as absent and
    share-link creation answers 503 without one. Existing instances with an
    empty secret must generate it.
  - Production Traefik reaches Docker through `docker-socket-proxy` (read-only,
    containers/events only) instead of mounting `docker.sock`. Keycloak dynamic
    client registration is limited by Trusted Hosts: `install.sh` resyncs the
    policy; **existing instances must add it by hand**.
  - Releases: the `v*` tag must equal `GEOSTUDIO_VERSION` of `.env.example`,
    point to a commit on `main` with a green `ci.yml` (`verify-tag`). The
    published `v0.1.0` has no `minio`/`titiler` image: cut a new release.
  - Database: migration 0043 adds `ON DELETE` to the foreign keys on `items`
    (deleting an item with history now succeeds); writes to a config
    (`PUT /v1/configs/{id}` and `PUT /v1/configs/by-item/{id}`) honour `If-Match` and answer 412 on a stale version
    (app builder at the time; extended to the other editors below); config write bodies are capped at 5 MB (413).
  - Self-contained export: the bundled mini-server answers under `/v1` and the
    image is pinned to the core version that produced the bundle.
  - Authorization: role assignment is capped to the caller's own privileges;
    publishing/sharing requires the item's kind privilege; sensitive fields
    (`sensitiveFields`) are excluded from app exports, pipeline
    `reader.collection`, MCP schema and the collection record.

- **Pre-release audit (P22–P35) — behaviour notes.**
  - Quotas (`CORE_QUOTAS_ENABLED`, `CORE_QUOTA_MAX_*`) are enforced at the single
    creation point of items and collections (REST, MCP, import, pipelines,
    harvest, 3D) and the variables are now wired on the worker too. A refusal
    answers 413 (storage) or 409 (count). No migration.
  - Public item thumbnails are served with a `sandbox` CSP (scripted SVG no
    longer runs in the core origin). The public catalogue lives at `/public`
    and `sitemap.xml` covers all public pages (single file, 50,000 URL cap).
  - MCP tool calls and copilot turns leave `mcp.tool_call` / `copilot.turn`
    rows in `audit_log`; copilot writes require a click confirmation.
- **Breaking (blob secrets)**: `s3_credentials` / `azure_blob_credentials` /
  `gcs_credentials` secrets now carry a `bucketUrl`, mandatory on create/update,
  and `reader.connector.blob` rejects any `path` outside that bucket/prefix
  (REV-197). An existing secret without `bucketUrl` stays readable, but
  pipelines using it fail with a message asking for it to be set: edit the
  secret (no automatic migration). There is no secret edit form in the shell
  yet: use `PUT /v1/secrets/{id}` or delete and re-create the secret. Glob
  wildcards are refused in `bucketUrl`.
- **Breaking (SMTP secrets)**: an SMTP secret with `useTls=false` is refused
  at write time and at send time unless its host is `localhost`; existing
  ones must be re-created with TLS. Port 465 now uses implicit TLS
  (`SMTP_SSL`); STARTTLS certificates are verified.
- **Blob reader limits**: `reader.connector.blob` is capped by
  `CORE_PIPELINES_BLOB_MAX_FILES` (default 100), `CORE_PIPELINES_BLOB_MAX_BYTES`
  (default 1 GiB) and `CORE_PIPELINES_BLOB_TIMEOUT_S` (default 600 s), wired on
  `core` and `worker`. The worker container gets `mem_limit:
  ${WORKER_MEM_LIMIT:-2g}`.
- **Optimistic concurrency on editors**: the map, dataset, pipeline and
  scheduled-report editors send the version they read (`If-Match`) and show a
  conflict notice on 412 instead of silently overwriting; the MCP tool
  `save_app_config` accepts `expectedVersion`. Not yet covered: the edit path
  of the visual query wizard.
- **Pipeline runs**: cancelling an already cancelled run answers 200
  (idempotent); a run cancelled while queued is no longer executed by the
  worker.

### Security

- Egress (pipelines, alerts, harvest, search, copilot, Postgres DSN, S3
  endpoint): connections are pinned to the IP address validated by the SSRF
  guard (no DNS rebinding between check and connect). MSSQL/Oracle DSNs are
  not pinned yet.
- The shell's `authFetch` only sends the token to the core's origin and throws
  on any other URL; a relative `VITE_CORE_URL` (`/api`) is resolved against the
  page origin.
- `GET /v1/share-links/{token}` is rate limited per client IP (new
  `share-link` group, 60/min).
- Deleting a referenced secret answers 409 listing only the objects the
  caller can read.

- `admin.collections.manage` now opens read access to a collection's items,
  aggregates, exports, tiles and attachments (REV-185); re-applying the DDL no
  longer reopens a sensitive column to `gis_rls_masked` (REV-186).

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
