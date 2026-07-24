# Task 3 report — Connecteur CKAN (`CkanConnector`), registre, schémas, openapi.json (SP-12g)

## What was implemented

- `core/app/harvest/connectors/ckan.py` (new): `CkanConnector`, `type = "ckan"`,
  `supports_copy = True`. Calls CKAN's `package_search` JSON REST API only
  (never `package_show`, avoiding N+1), paginated via `start`/`rows` (page
  size 100), merges admin-supplied query params from the source URL with
  pagination params — overwriting any admin-supplied `start`/`rows` rather
  than duplicating them. Bounded by `_MAX_CKAN_DATASETS = 500` and
  `_MAX_CKAN_PAGES = 50`. Extracts bbox from a `spatial` extra (GeoJSON
  envelope walk), defaulting to world bbox on absence/malformed
  JSON/non-Polygon shapes. Picks the best copyable resource
  (GeoJSON > GPKG/GEOPACKAGE > SHP/SHAPEFILE, CSV excluded) and sets
  `items_url` + `copy_filename` accordingly (`harvest.geojson` /
  `harvest.gpkg` / `harvest.zip`). Never raises: HTTP/JSON/malformed-package
  errors are logged and degrade gracefully (empty page / skip package /
  keep partial results across page failures), same philosophy as
  `StacConnector`.
- `core/tests/test_harvest_ckan_connector.py` (new): 26 tests, transcribed
  verbatim from the brief, using `httpx.MockTransport` for real HTTP-level
  behavior (no over-mocking) — single page extraction, title/external_url
  fallbacks, skip on missing id, pagination param merge + start advance,
  admin start/rows override (not duplicated), pagination stop on count
  exhausted / empty page, dataset/page caps, bbox extraction (valid/absent/
  malformed), copy-resource format preference + CSV exclusion + missing url,
  tolerance to malformed tags/extras/resources, non-dict package skip,
  missing result / invalid JSON / HTTP error → empty, partial results kept
  on next-page failure, `fetch_copy_geojson` behavior, and registry lookup.
- `core/app/harvest/connectors/__init__.py`: added `CkanConnector` import and
  `"ckan": CkanConnector()` to `_REGISTRY` (8th connector).
- `core/app/harvest/schemas.py`: `HarvestSourceCreate.type` Literal extended
  with `"ckan"`.
- `core/tests/test_harvest_routes.py`: added
  `test_create_ckan_source_is_accepted` and `test_copy_mode_accepted_for_ckan`.
- `core/openapi.json`: regenerated.

## TDD evidence

**Step 2 — RED** (`cd core && uv run pytest tests/test_harvest_ckan_connector.py -v`):
```
ModuleNotFoundError: No module named 'app.harvest.connectors.ckan'
Interrupted: 1 error during collection
```
Exactly as predicted by the brief.

**Step 4 — intermediate state after creating `ckan.py`, before registry edit**
(`cd core && uv run pytest tests/test_harvest_ckan_connector.py -v`):
```
25 passed, 1 failed in 0.17s
FAILED tests/test_harvest_ckan_connector.py::test_get_connector_returns_ckan
  ValueError: unknown harvest connector type: 'ckan'
```
Exactly the predicted intermediate signal — confirms the connector class
itself is correct in isolation, and the only gap is registration.

**Step 8 — GREEN** (`cd core && uv run pytest tests/test_harvest_ckan_connector.py tests/test_harvest_routes.py -v`):
```
51 passed in 4.11s
```
All 26 connector tests + all 25 route tests (23 pre-existing + 2 new) pass.

## Non-regression

**Full harvest suite** (`cd core && uv run pytest tests/ -k harvest -v`):
```
169 passed, 13 skipped, 693 deselected in 7.58s
```
(13 skips are pre-existing postgis-marked tests requiring docker, unrelated
to this change.)

**Full core suite** (`cd core && uv run pytest tests/`):
```
775 passed, 100 skipped in 41.72s
```
No regressions anywhere in the core test suite.

## openapi.json regeneration

Command: `cd core && PYTHONPATH=. uv run python scripts/export_openapi.py openapi.json`
(note: needed `PYTHONPATH=.` explicitly since pytest picks up `pythonpath = ["."]`
from `pyproject.toml` automatically but running the script directly does not;
this is an environment quirk, not a brief error — the brief's command as
written failed with `ModuleNotFoundError: No module named 'app'`).

Diff (`git diff --stat core/openapi.json`): 1 file changed, 2 insertions(+), 1 deletion(-).

```diff
               "wfs",
               "wmts",
               "csw",
-              "ogc-records"
+              "ogc-records",
+              "ckan"
             ],
```

Only `"ckan"` added to the `HarvestSourceCreate.type` enum — nothing else changed.

## Files changed

- `core/app/harvest/connectors/ckan.py` (new)
- `core/tests/test_harvest_ckan_connector.py` (new)
- `core/app/harvest/connectors/__init__.py` (modified)
- `core/app/harvest/schemas.py` (modified)
- `core/tests/test_harvest_routes.py` (modified)
- `core/openapi.json` (regenerated)

Commit: created on branch `dev`, message
`feat(core): connecteur de moissonnage CKAN/data.gouv.fr, copie opt-in (SP-12g)`
(6 files, +545/-2).

## Self-review

- **Completeness**: connector file, test file, registry, schema, route
  tests, openapi regen — all present, matching the brief's exact content.
- **Quality**: style matches neighboring connectors (`stac.py` in
  particular — lazy `build_guarded_client` import, `owns_client` pattern,
  `fetch_copy_geojson` signature, tolerant `_package_to_record`-style
  helper catching `(AttributeError, TypeError, KeyError, ValueError)`,
  logging on every degradation path).
- **Discipline**: confirmed via `grep -n "package_show"` that no
  `package_show` call exists anywhere in `ckan.py` (search-only, no N+1).
  No new admin-facing filter fields were added — the admin's query params
  simply pass through from the source URL, as specified. Nothing built
  beyond the brief's scope. No other connector files touched (confirmed
  via `git status --short` before commit — only the 6 intended files
  staged).
- **Testing**: verified tests use `httpx.MockTransport` for real
  request/response behavior (URL/query-param assertions on the actual
  outgoing request), not mocks of internal methods. TDD evidence captured
  at each meaningful step (RED at step 2, intermediate 25/26 at step 4,
  full green at step 8). Test output is pristine (no warnings, no
  unexpected skips).

## Issues or concerns

- Minor doc/comment wording nit (not a functional issue, not fixed per
  instructions to transcribe faithfully and flag rather than silently
  change): the module docstring in `ckan.py` says "Seul connecteur
  non-STAC/ArcGIS avec supports_copy=True", but `WfsConnector` also has
  `supports_copy = True` (verified via
  `grep -n "supports_copy" app/harvest/connectors/*.py`). This is exactly
  the brief's transcribed text, so it was kept as-is; flagging for
  awareness only, not blocking.
- The brief's Step 10 command (`uv run python scripts/export_openapi.py
  openapi.json`) needed `PYTHONPATH=.` prepended to resolve
  `ModuleNotFoundError: No module named 'app'` — an environment detail
  (pytest's `pythonpath` config doesn't apply to a bare script invocation),
  not a code issue. Noted for future task briefs.
- Note: this file previously contained a stale report from a different
  task (SP-12f "Task 3"); it has been overwritten in full with this task's
  content.

No other concerns. All 6 target files match the brief's exact specified
content; no extra files created; no other connectors touched.
