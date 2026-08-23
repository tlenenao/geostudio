# Symbologie dans l'éditeur de cartes (SP-25) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An author can style a map layer's color (classed choropleth or
continuous) and size from a chosen field, method (quantile / equal interval
/ natural breaks / continuous), class count and palette — in both the
standalone map editor (`LayersPanel`) and the app/dashboard map widget
(`mapWidget.tsx`) — with the computed classes frozen into the config so a
published map renders identically on reload, with zero extra network calls.

**Architecture:** One declarative type, `LayerSymbology`, replaces the
widget's ephemeral `MapEncodings`/props.encodings mechanism and becomes the
one thing both surfaces read/write, edited by one shared component
(`MapSymbologyEditor`, same precedent as `PopupEditor`/SP-24). Domain/class
computation goes through the existing `/collections/{id}/aggregate` route
(already generic over any `collectionId`, already has `min`/`max`/
`percentile` since SP-23) plus one new capability, `sample`, needed only for
the natural-breaks (Jenks) algorithm, which then runs as a small
dynamic-programming routine in the browser. `MapView` reads `symbology`
directly at render time (a pure, free function call — the domain is already
frozen, no network call), falling back to the existing raw `paint` field
when `symbology` is absent.

**Tech Stack:** TypeScript/React/Vitest (shell), Python/FastAPI/DuckDB/pytest
(core). No new dependencies (Jenks is a maison DP implementation; no
charting/color library added).

## Global Constraints

- Every task that touches `core/`: `uv run pytest` must show **no drop**
  from the reference measured at the end of SP-24 (**1868 passed, 5
  skipped**), `ruff check`, `ruff format --check`, `mypy --strict` (the 4
  gated modules), `lint-imports` all green, coverage **≥ 85**.
- Every task that touches `shell/`: `npm run lint`, `npm run format:check`,
  `npm run test` must show **no drop** from the reference (**159 files /
  1387 tests**), `npm run build` green, coverage **≥ 88** (measured after
  removing `dist/`/`dist-export/` — documented trap, SP-22/23/24).
- Any task that changes a FastAPI route/schema: regenerate OpenAPI + TS
  types (`core/scripts/export_openapi.py` needs `PYTHONPATH=.` and
  `CORE_SECRETS_MASTER_KEY` set — the bare command in the script's own
  docstring fails, per SP-23/SP-24 precedent) and commit the diff.
- Commits are conventional (`feat(core): …`, `feat(shell): …`,
  `test(shell): …`), one subject each, in French prose for messages, code
  identifiers in English — per `CLAUDE.md`.
- **Deviations from the committed spec, locked in during this plan** (found
  while reading the real code the spec described from memory — same class
  of correction this repo's history makes routinely):
  1. `ColorDomain`'s existing numeric tag is `"numeric"` (not
     `"numeric-continuous"` as the spec's §3.1 sketch wrote it) — the real
     `mapSymbology.ts` and its 15 existing tests already use `"numeric"`.
     Renaming it would be a gratuitous breaking change to a type with zero
     product value gained. The new classed variant is `"numeric-classed"`.
  2. `buildMapPaint`/`buildLegend` keep their existing 4-argument signature
     as the default path (100% backward compatible with all 15 existing
     tests, verified in Task 6) and gain a 5th **optional** parameter
     (`palette?: ResolvedPalette`) rather than being rewritten to consume
     `LayerSymbology` directly. `LayerSymbology` is a storage/editing
     envelope; a small pure adapter (`symbologyToPaintInputs`, Task 6)
     bridges the two — this is what keeps `mapSymbology.ts`'s existing test
     suite untouched instead of rewritten.
  3. `MapView.tsx` **does** need a small change (the spec's §3.5 assumed it
     wouldn't): when `layer.symbology` is present, the effective paint is
     computed from it at render time via the pure `buildMapPaint`/
     `symbologyToPaintInputs` (free — the domain is already frozen, no
     network call), instead of writing a compiled cache back into
     `layer.paint` at save time. One source of truth, no risk of a stale
     `paint` cache drifting from `symbology` after a bug in the "recompile
     at save" path. `layer.paint` stays exactly as-is (manual fallback) for
     any layer without a `symbology`.
  4. `MapSymbologyEditor`'s injected dependency is not a single
     `onComputeColorDomain` callback per the spec's §3.6 sketch, but two
     low-level primitives (`runStatistics`, `sampleField`) plus a shared,
     host-agnostic orchestration function `computeColorDomain`/
     `computeSizeDomain` living in `mapSymbology.ts` itself (Task 6). This
     removes duplicated quantile/equal-interval assembly logic that would
     otherwise be written twice (once per host), which is exactly the kind
     of duplication this codebase's own conventions avoid.

---

## File Structure

| File | Responsibility |
|---|---|
| `core/app/analytics/aggregate.py` | **Modify.** New `sample` capability on `AggregateRequestBody` + `run_collection_aggregate`. |
| `core/tests/test_analytics_aggregate.py` | **Modify.** Unit tests for `sample` (in-memory DuckDB + local parquet, no postgis marker — same pattern as `bins`). |
| `core/tests/test_features_aggregate_routes.py` | **Modify.** One HTTP-level test proving `sample` is reachable through the route. |
| `core/app/configs/schemas.py` | **Modify.** `MapLayer.symbology: dict \| None = None`. |
| `core/tests/test_configs_map_symbology.py` | **Create.** Round-trip test for the new field. |
| `shell/src/builder/widgets/palette.ts` | **Create.** Curated palettes + theme-derived ramp + RGB interpolation. |
| `shell/src/builder/widgets/palette.test.ts` | **Create.** |
| `shell/src/builder/widgets/mapSymbology.ts` | **Modify.** `ColorClassification`, `PaletteId`, `LayerSymbology`, classed `ColorDomain` variant, `equalIntervalBreaks`, `quantileMeasures`/`quantileBreaksFromRow`, `jenksBreaks`, `computeColorDomain`/`computeSizeDomain`, `symbologyToPaintInputs`, extended `buildMapPaint`/`buildLegend`. |
| `shell/src/builder/widgets/mapSymbology.test.ts` | **Modify.** All 15 existing tests untouched; new tests appended. |
| `shell/src/api/types.ts` | **Modify.** `MapLayer` (`vector`/`feature`) gains `symbology?: LayerSymbology`; `LegendSpec.color` gains a `"classed"` variant; `ItemClient` gains `sampleCollectionField`. |
| `shell/src/api/itemClient.ts` | **Modify.** `sample` in `STAT_KEYS`/`buildAggregateBody`; real `sampleCollectionField` implementation. |
| `shell/src/staticExport/StaticItemClient.ts` | **Modify.** `sampleCollectionField` → `unsupported()`. |
| `shell/src/map/MapSymbologyEditor.tsx` | **Create.** Shared editor, same precedent as `PopupEditor.tsx`. |
| `shell/src/map/MapSymbologyEditor.test.tsx` | **Create.** |
| `shell/src/map/LayersPanel.tsx` | **Modify.** Mounts `MapSymbologyEditor` per `vector`/`feature` layer. |
| `shell/src/map/LayersPanel.test.tsx` | **Modify.** |
| `shell/src/map/MapView.tsx` | **Modify.** Effective paint derives from `layer.symbology` when present. |
| `shell/src/map/MapView.test.tsx` | **Modify.** |
| `shell/src/builder/registry.ts` | **Modify.** `WidgetDefinition["PropsPanel"]` gains optional `theme?: Theme`. |
| `shell/src/builder/PropsPanel.tsx` | **Modify.** Threads optional `theme` prop through. |
| `shell/src/builder/PropsPanel.test.tsx` | **Modify.** |
| `shell/src/pages/AppBuilderPage.tsx` | **Modify.** Passes `draft.theme` to `<PropsPanel>`. |
| `shell/src/builder/widgets/mapWidget.tsx` | **Modify.** `props.symbology` replaces `props.encodings`; `PropsPanel` mounts `MapSymbologyEditor`; `Component` reads frozen `props.symbology` instead of live `useQuery` domains; legend gains classed rendering. |
| `shell/src/builder/widgets/mapWidget.test.tsx` | **Modify.** |
| `shell/e2e/map-symbology.spec.ts` | **Create.** The plan's acceptance proof. |

---

## Task 1: Core — `sample` capability on the aggregate route

**Files:**
- Modify: `core/app/analytics/aggregate.py`
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `AggregateRequestBody.sample: int | None`; `run_collection_aggregate(...)` returns `("value", [{"value": <float>}, ...])` when `request.sample` is set — a shape distinct from the groupBy path's `(categoryKey, rows)`, but the exact same return type (`tuple[str | list[str], list[dict[str, Any]]]`), so no caller-side type change is needed.

- [ ] **Step 1: Write the failing unit tests**

Append to `core/tests/test_analytics_aggregate.py` (same file, same fixtures
`conn`/`TABLE_INFO`/`_write_partition`/`_row` already defined at the top):

```python
def test_sample_returns_bounded_values_for_the_field(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i, lsn=1) for i in range(1, 21)],
    )
    request = AggregateRequestBody(field="pop", sample=5)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert len(rows) == 5
    values = {r["value"] for r in rows}
    assert values.issubset(set(range(1, 21)))


def test_sample_excludes_non_castable_values(tmp_path, conn):
    rows = [_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)]
    # pop is declared "integer" in TABLE_INFO but DuckDB will TRY_CAST a
    # non-numeric string to NULL rather than raise — simulate that with a
    # tombstoned row instead, since _row's pop is always an int: exercise
    # the WHERE value IS NOT NULL clause via a collection with fewer than
    # `sample` rows instead (the boundary that actually matters here).
    _write_partition(tmp_path, rows=rows)
    request = AggregateRequestBody(field="pop", sample=100)

    _category_key, result_rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # Sampling more rows than exist returns everything, not an error.
    assert {r["value"] for r in result_rows} == {10, 20}


def test_sample_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_bins_raises(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10, bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 2001):
        request = AggregateRequestBody(field="pop", sample=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="villes",
                table_info=TABLE_INFO,
                request=request,
            )
        assert exc.value.field == "sample"


def test_sample_on_empty_collection_returns_no_rows(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert rows == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k sample -v`
Expected: FAIL — `AggregateRequestBody` has no field `sample` (Pydantic
`ValidationError: Extra inputs are not permitted` or similar).

- [ ] **Step 3: Add the `sample` field and its validation**

In `core/app/analytics/aggregate.py`, add to `AggregateRequestBody` (next to
`bins: int | None = None`):

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    p: float | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    geomIntersects: dict[str, Any] | None = None
    bucket: Literal["hour", "day", "week", "month", "quarter", "year"] | None = None
    bins: int | None = None
    sample: int | None = None
```

In `_validate_fields`, right after the existing `if request.bins is not None:`
block:

```python
    if request.sample is not None:
        if request.field is None:
            raise UnknownAggregateField("sample", "sample requires a field")
        if fields:
            raise UnknownAggregateField("sample", "sample cannot combine with groupBy")
        if request.bins is not None:
            raise UnknownAggregateField("sample", "sample cannot combine with bins")
        if not (1 <= request.sample <= 2000):
            raise UnknownAggregateField("sample", "sample must be between 1 and 2000")
```

- [ ] **Step 4: Add the DuckDB sampling routine**

In `core/app/analytics/aggregate.py`, add a new function right after
`_run_binned_histogram` (same file, same section):

```python
def _run_sample(
    conn: duckdb.DuckDBPyConnection,
    *,
    dedup_cte: str,
    where_sql: str,
    where_params: list[Any],
    field: str,
    sample: int,
) -> list[dict[str, Any]]:
    field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    not_null_clause = f"{field_expr} IS NOT NULL"
    full_where = f"{where_sql} AND {not_null_clause}" if where_sql else f"WHERE {not_null_clause}"
    sql = (
        f"{dedup_cte} SELECT {field_expr} AS value FROM live {full_where} "
        f"USING SAMPLE {int(sample)} ROWS"
    )
    return _fetch_rows(conn, sql, where_params)
```

Wire it into `run_collection_aggregate`, right after the existing
`if request.bins is not None:` block returns:

```python
    if request.sample is not None:
        assert request.field is not None
        rows = _run_sample(
            conn,
            dedup_cte=dedup_cte,
            where_sql=where_sql,
            where_params=where_params,
            field=request.field,
            sample=request.sample,
        )
        return "value", rows
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k sample -v`
Expected: PASS (7 tests). **If `USING SAMPLE ... ROWS` raises a DuckDB
syntax error**, this is exactly the kind of thing this repo's own history
(SP-11b's bbox spike) says to verify empirically rather than trust from
memory — try `USING SAMPLE reservoir({n} ROWS)` as the fallback spelling
and re-run; keep whichever the real DuckDB version installed here accepts.

- [ ] **Step 6: Add one route-level test**

In `core/tests/test_features_aggregate_routes.py`, following the existing
pattern (`_register_collection` helper, `client` fixture already in that
file) — add:

```python
def test_aggregate_sample_returns_bare_values(env):
    client, session = env
    col = _register_collection(client, public=True)
    client.post(
        f"/collections/{col['id']}/items",
        json={
            "type": "Feature",
            "properties": {"region": "Nord", "annee": "2025", "pop": 42},
            "geometry": None,
        },
    )

    response = client.post(f"/collections/{col['id']}/aggregate", json={"field": "pop", "sample": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["categoryKey"] == "value"
    assert body["rows"] == [{"value": 42.0}]
```

Read the actual feature-creation payload shape used by neighboring tests in
that file first (grep `client.post(f"/collections/{col\['id'\]}/items"` in
the same file) and match it exactly — do not guess the property/geometry
shape.

- [ ] **Step 7: Run the full core suite**

Run: `cd core && uv run pytest -v`
Expected: PASS, count ≥ 1868 + 8 new tests, 0 failed.

- [ ] **Step 8: Lint gates**

Run: `cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py core/tests/test_features_aggregate_routes.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute la capacité sample à l'agrégat de collection

Nécessaire au calcul des seuils naturels (Jenks) côté shell (SP-25) :
un échantillon borné de valeurs, sans groupBy ni géométrie.
EOF
)"
```

---

## Task 2: Core — `symbology` field on `MapLayer`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_configs_map_symbology.py` (create)

**Interfaces:**
- Produces: `MapLayer.symbology: dict | None = None` (untyped, mirrors
  `paint: dict | None` and `props: dict | None` on the same model — this
  model validates coarse shape only, exactly like its two neighbors).

- [ ] **Step 1: Find the existing round-trip test pattern for `MapLayer`**

Run: `grep -rn "popup" core/tests/test_configs*.py`

Read whichever file that finds (it exercises `MapLayer.popup` round-trip
through `POST /configs` or `PUT /configs/{id}` — SP-24 added it) to copy its
exact request/assertion shape for the new test below.

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_configs_map_symbology.py`, mirroring the file found
in Step 1 (same fixtures, same route, same auth setup — copy them, don't
invent new ones):

```python
# SPDX-License-Identifier: Apache-2.0
"""symbology (SP-25) round-trips through MapConfig exactly like paint/popup
(SP-24) — an untyped dict on MapLayer, same precedent."""

# (imports and fixtures: copy verbatim from the file found in Task 2 Step 1)


def test_map_layer_symbology_round_trips(client):
    payload = {
        "kind": "map",
        "title": "Carte test",
        "owner": "u1",
    }
    item = client.post("/configs", json=payload).json()

    map_config = {
        "basemap": {"style": "https://example.test/style.json"},
        "view": {"center": [0, 0], "zoom": 5},
        "layers": [
            {
                "id": "l1",
                "title": "Communes",
                "visible": True,
                "kind": "vector",
                "tilesUrl": "https://example.test/tiles/{z}/{x}/{y}.mvt",
                "sourceLayer": "communes",
                "collectionId": "communes",
                "symbology": {
                    "color": {
                        "field": "population",
                        "mode": "numeric",
                        "classification": {"method": "quantile", "classes": 5},
                        "palette": "sequential-blue",
                        "domain": {"kind": "numeric-classed", "breaks": [0, 10, 20, 30, 40, 50]},
                        "computedAt": "2026-08-23T00:00:00Z",
                    }
                },
            }
        ],
    }
    response = client.put(f"/configs/{item['id']}", json={"config": map_config})
    assert response.status_code == 200

    got = client.get(f"/configs/{item['id']}").json()
    assert got["config"]["layers"][0]["symbology"] == map_config["layers"][0]["symbology"]
```

Adjust the exact route paths/payload envelope (`POST /configs` vs a
different creation route, `PUT` vs `PATCH`, whether `config` is nested or
top-level) to match precisely what the file found in Step 1 actually uses —
this sketch shows the shape of the assertion, not a guaranteed-correct route
contract.

- [ ] **Step 3: Run it to verify it fails**

Run: `cd core && uv run pytest tests/test_configs_map_symbology.py -v`
Expected: FAIL — `symbology` stripped from the round-tripped config (Pydantic
drops unknown fields silently by default) or a 422 if `MapLayer` is
constructed with `extra="forbid"` (check `class Config` / `model_config` on
`MapLayer` first — if it forbids extra fields, this test fails loudly
instead of silently, which is the RED state either way).

- [ ] **Step 4: Add the field**

In `core/app/configs/schemas.py`, in `MapLayer` (right after `popup:
PopupConfig | None = None`):

```python
    popup: PopupConfig | None = None
    symbology: dict | None = None
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd core && uv run pytest tests/test_configs_map_symbology.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full core suite + gates**

Run: `cd core && uv run pytest -v && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green, count ≥ previous + 1.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_configs_map_symbology.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute symbology à MapLayer

Champ non typé, même précédent que paint/props — le shell (SP-25) y
écrit la symbologie déclarative d'une couche.
EOF
)"
```

---

## Task 3: OpenAPI + TS regeneration

**Files:**
- Modify: `core/openapi.json` (or wherever it's exported — check
  `scripts/export_openapi.py`'s output path)
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:** none new — mechanical regeneration task.

- [ ] **Step 1: Regenerate**

Run (per CLAUDE.md/SP-23 precedent, the bare script command fails):

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=$(openssl rand -base64 32) uv run python scripts/export_openapi.py
```

Then regenerate the TS side per whatever `npm` script does it (check
`shell/package.json` for a `generate:api`/`openapi` script) and run it.

- [ ] **Step 2: Verify the diff is non-empty and sane**

Run: `git diff --stat`
Expected: `AggregateRequestBody`'s schema gains `sample`; `MapLayer`'s schema
gains `symbology`. No unrelated fields move — if anything else changed,
investigate before committing (a stray unrelated diff here has burned this
project before, per the SP-23/SP-24 "classe d'oubli la plus récurrente"
notes — regenerating late is the usual failure, not regenerating wrong, but
verify anyway).

- [ ] **Step 3: Run both suites to confirm nothing broke**

Run: `cd core && uv run pytest -q` and `cd shell && npm run build`
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
chore(api): régénère OpenAPI et les types TS (sample, symbology)
EOF
)"
```

---

## Task 4: Shell — `palette.ts`

**Files:**
- Create: `shell/src/builder/widgets/palette.ts`
- Test: `shell/src/builder/widgets/palette.test.ts`

**Interfaces:**
- Consumes: `ThemeColors` from `shell/src/api/types.ts` (already has
  `primary?: string` etc.).
- Produces: `PaletteId`, `ResolvedPalette`, `CURATED_PALETTES`,
  `resolvePalette(id, themeColors)`, `colorsForClasses(palette, n)` — all
  consumed by `mapSymbology.ts` in Task 6.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/palette.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { CURATED_PALETTES, colorsForClasses, resolvePalette } from "./palette";

test("resolvePalette returns a curated palette by id, ignoring theme", () => {
  const resolved = resolvePalette("categorical-a", undefined);
  expect(resolved).toEqual(CURATED_PALETTES["categorical-a"]);
});

test("resolvePalette returns null for theme-primary without a theme", () => {
  expect(resolvePalette("theme-primary", undefined)).toBeNull();
  expect(resolvePalette("theme-primary", {})).toBeNull();
});

test("resolvePalette derives a sequential ramp from theme.primary", () => {
  const resolved = resolvePalette("theme-primary", { primary: "#2563eb" });
  expect(resolved).toEqual({ kind: "sequential", low: expect.any(String), high: "#2563eb" });
});

test("colorsForClasses on a categorical palette slices then repeats", () => {
  const palette = CURATED_PALETTES["categorical-a"];
  const three = colorsForClasses(palette, 3);
  expect(three).toEqual(palette.kind === "categorical" ? palette.colors.slice(0, 3) : []);
  const many = colorsForClasses(palette, (palette as { colors: string[] }).colors.length + 2);
  expect(many[many.length - 1]).toBe((palette as { colors: string[] }).colors[1]); // wraps
});

test("colorsForClasses on a sequential palette interpolates n evenly-spaced RGB stops", () => {
  const palette = { kind: "sequential" as const, low: "#000000", high: "#ffffff" };
  const stops = colorsForClasses(palette, 3);
  expect(stops).toEqual(["#000000", "#7f7f7f", "#ffffff"]);
});

test("colorsForClasses on a sequential palette with n=1 returns the low color", () => {
  const palette = { kind: "sequential" as const, low: "#112233", high: "#445566" };
  expect(colorsForClasses(palette, 1)).toEqual(["#112233"]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/palette.test.ts`
Expected: FAIL — module `./palette` does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/builder/widgets/palette.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { ThemeColors } from "../../api/types";

export type PaletteId =
  | "categorical-a"
  | "categorical-b"
  | "sequential-blue"
  | "sequential-warm"
  | "theme-primary";

export type ResolvedPalette =
  | { kind: "categorical"; colors: string[] }
  | { kind: "sequential"; low: string; high: string };

// "categorical-a" is mapSymbology.ts's existing CATEGORICAL_PALETTE,
// unchanged — the default when an author picks no palette at all keeps
// rendering identically to pre-SP-25 maps.
export const CURATED_PALETTES: Record<Exclude<PaletteId, "theme-primary">, ResolvedPalette> = {
  "categorical-a": {
    kind: "categorical",
    colors: [
      "#2563eb",
      "#dc2626",
      "#16a34a",
      "#d97706",
      "#7c3aed",
      "#0891b2",
      "#db2777",
      "#65a30d",
    ],
  },
  "categorical-b": {
    kind: "categorical",
    colors: [
      "#0f766e",
      "#b45309",
      "#4338ca",
      "#be123c",
      "#3f6212",
      "#a21caf",
      "#0369a1",
      "#854d0e",
    ],
  },
  "sequential-blue": { kind: "sequential", low: "#dbeafe", high: "#1e3a8a" },
  "sequential-warm": { kind: "sequential", low: "#fef3c7", high: "#7c2d12" },
};

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  const c = (v: number) => Math.round(v).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}

function lerpColor(low: string, high: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(low);
  const [r2, g2, b2] = hexToRgb(high);
  return rgbToHex([r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t]);
}

// Rampe séquentielle dérivée de theme.colors.primary : du blanc jusqu'à la
// couleur primaire elle-même — pas de bibliothèque de teinte/luminosité,
// une interpolation RGB simple suffit pour un "clair → primary".
export function resolvePalette(id: PaletteId, themeColors: ThemeColors | undefined): ResolvedPalette | null {
  if (id === "theme-primary") {
    const primary = themeColors?.primary;
    if (!primary) return null;
    return { kind: "sequential", low: "#ffffff", high: primary };
  }
  return CURATED_PALETTES[id];
}

export function colorsForClasses(palette: ResolvedPalette, n: number): string[] {
  if (n <= 0) return [];
  if (palette.kind === "categorical") {
    return Array.from({ length: n }, (_, i) => palette.colors[i % palette.colors.length]);
  }
  if (n === 1) return [palette.low];
  return Array.from({ length: n }, (_, i) => lerpColor(palette.low, palette.high, i / (n - 1)));
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/palette.test.ts`
Expected: PASS (6 tests). If the `theme-primary` test's exact `low` color
assertion needs adjusting to match `"#ffffff"` literally, fix the test, not
the implementation, once you've confirmed the implementation's choice is
deliberate (white low-anchor is the simplest correct choice, per this step).

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: all green, test count ≥ 1387 + 6.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/palette.ts shell/src/builder/widgets/palette.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le module de palettes de symbologie

Palettes curatées + rampe dérivée du thème, aucune bibliothèque de
couleur ajoutée (lerp RGB maison).
EOF
)"
```

---

## Task 5: Shell — types partagés (`LayerSymbology`, `MapLayer.symbology`, `ItemClient.sampleCollectionField`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`
- Test: `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient` gains `sampleCollectionField(collectionId: string,
  field: string, limit: number): Promise<number[]>`.

(`MapLayer.symbology: LayerSymbology` is added later, in Task 6 Step 11 —
`LayerSymbology` is defined in that same task, in `mapSymbology.ts`, so
adding the field to `MapLayer` right there avoids a forward reference to a
type that doesn't exist yet. This task only handles
`sampleCollectionField`, which has no dependency on Task 6.)

- [ ] **Step 1: Write the failing test for `sampleCollectionField`**

Add to `shell/src/api/itemClient.test.ts` (find the existing `describe`/test
block that exercises `queryDataSource`'s statistics path, to reuse its
`fetchMock`/`coreUrl` setup):

```ts
test("sampleCollectionField posts sample+field and returns bare numeric values", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ categoryKey: "value", rows: [{ value: 1 }, { value: 2.5 }] }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  const values = await client.sampleCollectionField("communes", "population", 500);

  expect(values).toEqual([1, 2.5]);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://core.test/collections/communes/aggregate");
  expect(JSON.parse(init.body as string)).toEqual({ field: "population", sample: 500 });
});
```

Adjust `createItemClient`'s exact constructor signature and the `fetchMock`
setup style to match whatever the file's existing tests actually do (read
the nearest existing `queryDataSource`/statistics test in that file first —
this sketch shows the shape of the assertions, not a verbatim copy of test
scaffolding you have not read).

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t sampleCollectionField`
Expected: FAIL — `client.sampleCollectionField is not a function`.

- [ ] **Step 3: Add the interface method**

In `shell/src/api/types.ts`, in the `ItemClient` interface, right after
`listLayerSources`:

```ts
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
  sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]>;
```

- [ ] **Step 4: Implement it in `itemClient.ts`**

In `shell/src/api/itemClient.ts`, add `sample` to the existing `STAT_KEYS`
set:

```ts
const STAT_KEYS = new Set([
  "groupBy",
  "split",
  "agg",
  "field",
  "measures",
  "bbox",
  "bucket",
  "bins",
  "sample",
  "p",
]);
```

And in `buildAggregateBody`, right after the `bins` line:

```ts
  if (query.bins) body.bins = Number(query.bins);
  if (query.sample) body.sample = Number(query.sample);
```

Then add the method itself, right after `queryDataSource` in the returned
client object (same file, same `request<T>` helper already used
everywhere):

```ts
    async sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]> {
      const data = await request<{ categoryKey: string | string[]; rows: { value: number }[] }>(
        "POST",
        `/collections/${collectionId}/aggregate`,
        { field, sample: limit },
      );
      return data.rows.map((r) => Number(r.value));
    },
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t sampleCollectionField`
Expected: PASS.

- [ ] **Step 6: Implement `StaticItemClient`'s explicit rejection**

In `shell/src/staticExport/StaticItemClient.ts`, add (near
`exportDataSource`'s `unsupported()` entry, same style):

```ts
    async sampleCollectionField(_collectionId: string, _field: string, _limit: number) {
      return unsupported();
    },
```

Add a matching test in `shell/src/staticExport/StaticItemClient.test.ts`
(mirror whichever existing `unsupported()` test is there, e.g. for
`exportDataSource`):

```ts
test("sampleCollectionField rejects — no backend in a static export", async () => {
  const client = createStaticItemClient(EMPTY_CONFIG); // use whatever fixture name the file already defines
  await expect(client.sampleCollectionField("c", "f", 10)).rejects.toThrow(
    "Non disponible dans un export statique",
  );
});
```

- [ ] **Step 7: Run the full shell suite**

Run: `cd shell && npx vitest run && npm run build`
Expected: PASS, no `ItemClient` implementer left incomplete (TypeScript
would already fail `npm run build` if `StaticItemClient.ts` were missing the
method — this is the mechanism SP-18a relies on, verify it actually catches
it by checking the diff includes `StaticItemClient.ts`).

- [ ] **Step 8: Gates + commit**

Run: `cd shell && npm run lint && npm run format:check`

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute ItemClient.sampleCollectionField

Premier appelant : le calcul des seuils naturels (Jenks) côté
MapSymbologyEditor (SP-25). Rejeté explicitement en export statique,
même précédent que les autres méthodes réseau de StaticItemClient.
EOF
)"
```

---

## Task 6: Shell — classification, palette-aware paint/legend, and orchestration in `mapSymbology.ts`

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`
- Modify: `shell/src/api/types.ts` (`MapLayer.symbology`, `LegendSpec.color` classed variant)

**Interfaces:**
- Consumes: `PaletteId`, `ResolvedPalette`, `resolvePalette`,
  `colorsForClasses` from `./palette` (Task 4); `DataRecord`, `ThemeColors`
  from `../../api/types`.
- Produces: `ColorClassification`, `LayerSymbology`, extended `ColorDomain`
  (adds `"numeric-classed"`), `equalIntervalBreaks(min, max, classes)`,
  `quantileMeasures(field, classes)`, `quantileBreaksFromRow(row, classes)`,
  `jenksBreaks(sample, classes)`, `computeColorDomain(params, deps)`,
  `computeSizeDomain(field, deps)`, `symbologyToPaintInputs(symbology,
  themeColors)`, extended `buildMapPaint`/`buildLegend` (5th optional
  `palette` parameter, classed branch) — all consumed by
  `MapSymbologyEditor` (Task 7), `LayersPanel` (Task 8), `mapWidget.tsx`
  (Task 10), `MapView.tsx` (Task 9).

This is the largest task. It's still one task (not split further) because
every piece here is exercised by the same test file and reviewed as one
coherent unit — splitting it would leave intermediate commits with
half-finished, untestable types.

- [ ] **Step 1: Write the failing tests for classification math**

Append to `shell/src/builder/widgets/mapSymbology.test.ts` (existing 15
tests stay untouched above this point):

```ts
test("equalIntervalBreaks divides [min, max] into `classes` equal-width breaks", () => {
  expect(equalIntervalBreaks(0, 100, 4)).toEqual([0, 25, 50, 75, 100]);
  expect(equalIntervalBreaks(10, 10, 3)).toEqual([10, 10, 10, 10]);
});

test("quantileMeasures builds one min/max plus classes-1 percentile measures", () => {
  expect(quantileMeasures("pop", 4)).toEqual([
    { field: "pop", agg: "min", label: "min" },
    { field: "pop", agg: "percentile", label: "q1", p: 25 },
    { field: "pop", agg: "percentile", label: "q2", p: 50 },
    { field: "pop", agg: "percentile", label: "q3", p: 75 },
    { field: "pop", agg: "max", label: "max" },
  ]);
});

test("quantileBreaksFromRow reads min/q1..qk-1/max in order", () => {
  const row = { min: 0, q1: 10, q2: 20, q3: 30, max: 40 };
  expect(quantileBreaksFromRow(row, 4)).toEqual([0, 10, 20, 30, 40]);
});

test("jenksBreaks finds the boundaries of three well-separated clusters", () => {
  const sample = [1, 1, 2, 2, 50, 51, 52, 100, 101, 102];
  expect(jenksBreaks(sample, 3)).toEqual([1, 2, 52, 102]);
});

test("jenksBreaks is invariant to input order", () => {
  const sample = [102, 1, 51, 2, 100, 1, 52, 2, 50, 101];
  expect(jenksBreaks(sample, 3)).toEqual([1, 2, 52, 102]);
});
```

```ts
test("computeColorDomain: categorical mode runs a groupBy statistics query", async () => {
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "Nord", properties: {} },
    { id: "Sud", properties: {} },
  ]);
  const domain = await computeColorDomain(
    { field: "region", mode: "categorical" },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "categorical", values: ["Nord", "Sud"] });
  expect(runStatistics).toHaveBeenCalledWith({ groupBy: "region" });
});

test("computeColorDomain: numeric without classification runs min/max and returns a continuous domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric" },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric", min: 0, max: 100 });
});

test("computeColorDomain: equalInterval derives breaks from min/max client-side", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "equalInterval", classes: 4 } },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [0, 25, 50, 75, 100] });
});

test("computeColorDomain: quantile issues one measures call and reads it back", async () => {
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "", properties: { min: 0, q1: 10, q2: 20, q3: 30, max: 40 } },
  ]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "quantile", classes: 4 } },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [0, 10, 20, 30, 40] });
  expect(runStatistics).toHaveBeenCalledTimes(1);
});

test("computeColorDomain: jenks samples then classifies client-side", async () => {
  const sampleField = vi.fn().mockResolvedValue([1, 1, 2, 2, 50, 51, 52, 100, 101, 102]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "jenks", classes: 3 } },
    { runStatistics: vi.fn(), sampleField },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [1, 2, 52, 102] });
  expect(sampleField).toHaveBeenCalledWith("pop", 2000);
});

test("computeSizeDomain runs min/max and returns it", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 50 } }]);
  const domain = await computeSizeDomain("montant", { runStatistics });
  expect(domain).toEqual({ min: 0, max: 50 });
});
```

```ts
test("buildMapPaint with a numeric-classed domain and a palette emits a step expression", () => {
  const { paint } = buildMapPaint(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: [0, 10, 20, 30] },
    null,
    "polygon",
    { kind: "sequential", low: "#000000", high: "#ffffff" },
  );
  expect(paint["fill-color"]).toEqual([
    "step",
    ["get", "pop"],
    "#000000",
    10,
    "#7f7f7f",
    20,
    "#ffffff",
  ]);
});

test("buildMapPaint categorical with an explicit palette uses its colors instead of the constants", () => {
  const { paint } = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "polygon",
    { kind: "categorical", colors: ["#111111", "#222222"] },
  );
  expect(paint["fill-color"]).toEqual(["match", ["get", "region"], "Nord", "#111111", "Sud", "#222222", "#111111"]);
});

test("buildLegend with a numeric-classed domain returns one range per class", () => {
  const legend = buildLegend(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: [0, 10, 20] },
    null,
    "polygon",
    { kind: "sequential", low: "#000000", high: "#ffffff" },
  );
  expect(legend).toEqual({
    color: {
      kind: "classed",
      field: "pop",
      classes: [
        { color: "#000000", from: 0, to: 10 },
        { color: "#ffffff", from: 10, to: 20 },
      ],
    },
  });
});
```

```ts
test("symbologyToPaintInputs maps a frozen LayerSymbology to buildMapPaint's inputs", () => {
  const symbology: LayerSymbology = {
    color: {
      field: "pop",
      mode: "numeric",
      classification: { method: "quantile", classes: 2 },
      palette: "sequential-blue",
      domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
      computedAt: "2026-08-23T00:00:00Z",
    },
  };
  const inputs = symbologyToPaintInputs(symbology, undefined);
  expect(inputs.encodings).toEqual({
    color: { field: "pop", mode: "numeric", classification: { method: "quantile", classes: 2 } },
  });
  expect(inputs.colorDomain).toEqual({ kind: "numeric-classed", breaks: [0, 50, 100] });
  expect(inputs.sizeDomain).toBeNull();
  expect(inputs.palette).toEqual({ kind: "sequential", low: "#dbeafe", high: "#1e3a8a" });
});

test("symbologyToPaintInputs on undefined symbology returns empty/null inputs", () => {
  const inputs = symbologyToPaintInputs(undefined, undefined);
  expect(inputs).toEqual({ encodings: {}, colorDomain: null, sizeDomain: null, palette: undefined });
});
```

Add the necessary imports at the top of the test file:

```ts
import {
  buildLegend,
  buildMapPaint,
  computeColorDomain,
  computeSizeDomain,
  detectGeometryKind,
  equalIntervalBreaks,
  jenksBreaks,
  quantileBreaksFromRow,
  quantileMeasures,
  symbologyToPaintInputs,
} from "./mapSymbology";
import type { LayerSymbology } from "./mapSymbology";
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: FAIL — none of the new exports exist yet; the 15 pre-existing
tests above still pass (confirm this explicitly in the output — that's the
backward-compatibility guarantee this task is built around).

- [ ] **Step 3: Implement classification helpers**

In `shell/src/builder/widgets/mapSymbology.ts`, add near the top (after the
existing type exports, before `paletteColor`):

```ts
export type PaletteId = import("./palette").PaletteId;
export type ResolvedPalette = import("./palette").ResolvedPalette;

export type ColorClassification =
  | { method: "quantile"; classes: number }
  | { method: "equalInterval"; classes: number }
  | { method: "jenks"; classes: number };
```

Update `MapEncodings` and `ColorDomain` (existing types) additively:

```ts
export type ColorDomain =
  | { kind: "categorical"; values: string[] }
  | { kind: "numeric"; min: number; max: number }
  | { kind: "numeric-classed"; breaks: number[] };

export type MapEncodings = {
  color?: { field: string; mode: "categorical" | "numeric"; classification?: ColorClassification };
  size?: { field: string };
};

export type LayerSymbology = {
  color?: NonNullable<MapEncodings["color"]> & {
    palette: PaletteId;
    domain: ColorDomain;
    computedAt: string;
  };
  size?: NonNullable<MapEncodings["size"]> & { domain: SizeDomain; computedAt: string };
};
```

Add the classification math functions (anywhere below the type
declarations, above `buildMapPaint`):

```ts
export function equalIntervalBreaks(min: number, max: number, classes: number): number[] {
  return Array.from({ length: classes + 1 }, (_, i) => min + (i * (max - min)) / classes);
}

export function quantileMeasures(
  field: string,
  classes: number,
): { field: string; agg: string; label: string; p?: number }[] {
  const measures: { field: string; agg: string; label: string; p?: number }[] = [
    { field, agg: "min", label: "min" },
  ];
  for (let i = 1; i < classes; i++) {
    measures.push({ field, agg: "percentile", label: `q${i}`, p: (100 * i) / classes });
  }
  measures.push({ field, agg: "max", label: "max" });
  return measures;
}

export function quantileBreaksFromRow(row: Record<string, unknown>, classes: number): number[] {
  const breaks = [Number(row.min)];
  for (let i = 1; i < classes; i++) breaks.push(Number(row[`q${i}`]));
  breaks.push(Number(row.max));
  return breaks;
}

// Fisher-Jenks natural breaks, classic dynamic-programming form. O(n^2 * k) —
// deliberately not the SMAWK-accelerated variant: bounded to a 2000-point
// sample and ≤ 9 classes (spec §4 decision 2), well within budget (~36M ops).
export function jenksBreaks(data: number[], classes: number): number[] {
  const sorted = [...data].sort((a, b) => a - b);
  const n = sorted.length;
  const mat1: number[][] = Array.from({ length: n + 1 }, () => new Array(classes + 1).fill(0));
  const mat2: number[][] = Array.from({ length: n + 1 }, () => new Array(classes + 1).fill(0));
  for (let i = 1; i <= classes; i++) {
    mat1[1][i] = 1;
    mat2[1][i] = 0;
    for (let j = 2; j <= n; j++) mat2[j][i] = Infinity;
  }
  let v = 0;
  for (let l = 2; l <= n; l++) {
    let s1 = 0;
    let s2 = 0;
    let w = 0;
    for (let m = 1; m <= l; m++) {
      const i3 = l - m + 1;
      const val = sorted[i3 - 1];
      s2 += val * val;
      s1 += val;
      w++;
      v = s2 - (s1 * s1) / w;
      const i4 = i3 - 1;
      if (i4 !== 0) {
        for (let j = 2; j <= classes; j++) {
          if (mat2[l][j] >= v + mat2[i4][j - 1]) {
            mat1[l][j] = i3;
            mat2[l][j] = v + mat2[i4][j - 1];
          }
        }
      }
    }
    mat1[l][1] = 1;
    mat2[l][1] = v;
  }
  const kClass = new Array(classes + 1).fill(0);
  kClass[classes] = sorted[n - 1];
  kClass[0] = sorted[0];
  let k = n;
  for (let j = classes; j >= 2; j--) {
    const id = mat1[k][j] - 2;
    kClass[j - 1] = sorted[id];
    k = mat1[k][j] - 1;
  }
  return kClass;
}
```

- [ ] **Step 4: Run to verify the classification-math tests pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "equalIntervalBreaks|quantileMeasures|quantileBreaksFromRow|jenksBreaks"`
Expected: PASS (5 tests). If `jenksBreaks` doesn't match the exact expected
arrays, print `mat1`/`mat2` for the small fixture and compare against the
well-known Fisher-Jenks reference behavior before changing the test
expectations — this is a textbook algorithm, a mismatch is far more likely
an off-by-one in the transcription above than in the test's expectation.

- [ ] **Step 5: Implement `computeColorDomain`/`computeSizeDomain`**

Add (needs `DataRecord` imported from `../../api/types`):

```ts
export type StatQueryFn = (query: Record<string, unknown>) => Promise<DataRecord[]>;
export type SampleFieldFn = (field: string, limit: number) => Promise<number[]>;

export async function computeColorDomain(
  params: { field: string; mode: "categorical" | "numeric"; classification?: ColorClassification },
  deps: { runStatistics: StatQueryFn; sampleField: SampleFieldFn },
): Promise<ColorDomain> {
  if (params.mode === "categorical") {
    const rows = await deps.runStatistics({ groupBy: params.field });
    return { kind: "categorical", values: rows.map((r) => String(r.id)) };
  }
  const classification = params.classification;
  if (!classification || classification.method === "equalInterval") {
    const rows = await deps.runStatistics({
      measures: [
        { field: params.field, agg: "min", label: "min" },
        { field: params.field, agg: "max", label: "max" },
      ],
    });
    const p = rows[0]?.properties ?? {};
    const min = Number(p.min ?? 0);
    const max = Number(p.max ?? 0);
    if (!classification) return { kind: "numeric", min, max };
    return { kind: "numeric-classed", breaks: equalIntervalBreaks(min, max, classification.classes) };
  }
  if (classification.method === "quantile") {
    const rows = await deps.runStatistics({ measures: quantileMeasures(params.field, classification.classes) });
    const p = rows[0]?.properties ?? {};
    return { kind: "numeric-classed", breaks: quantileBreaksFromRow(p, classification.classes) };
  }
  const sample = await deps.sampleField(params.field, 2000);
  return { kind: "numeric-classed", breaks: jenksBreaks(sample, classification.classes) };
}

export async function computeSizeDomain(
  field: string,
  deps: { runStatistics: StatQueryFn },
): Promise<SizeDomain> {
  const rows = await deps.runStatistics({
    measures: [
      { field, agg: "min", label: "min" },
      { field, agg: "max", label: "max" },
    ],
  });
  const p = rows[0]?.properties ?? {};
  return { min: Number(p.min ?? 0), max: Number(p.max ?? 0) };
}
```

Add the import at the top of `mapSymbology.ts`: `import type { DataRecord }
from "../../api/types";`

- [ ] **Step 6: Run to verify the orchestration tests pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t computeColorDomain`
Expected: PASS (5 tests), plus `computeSizeDomain` (1 test).

- [ ] **Step 7: Extend `buildMapPaint`/`buildLegend` with the optional palette parameter and the classed branch**

Replace the existing `buildMapPaint` function body's color section:

```ts
export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPaletteRuntime,
): MapPaintResult {
  const renderAs: "fill" | "circle" | "line" =
    geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
  const paint: Record<string, unknown> = {};

  if (encodings?.color && colorDomain) {
    const prop = colorPaintProperty(renderAs);
    if (colorDomain.kind === "categorical") {
      const colors = palette
        ? colorsForClasses(palette, colorDomain.values.length)
        : colorDomain.values.map((_, i) => paletteColor(i));
      const match: unknown[] = ["match", ["get", encodings.color.field]];
      colorDomain.values.forEach((value, i) => match.push(value, colors[i]));
      match.push(colors[0]);
      paint[prop] = match;
    } else if (colorDomain.kind === "numeric-classed") {
      const nClasses = colorDomain.breaks.length - 1;
      const colors = palette
        ? colorsForClasses(palette, nClasses)
        : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
      const step: unknown[] = ["step", ["get", encodings.color.field], colors[0]];
      for (let i = 1; i < nClasses; i++) step.push(colorDomain.breaks[i], colors[i]);
      paint[prop] = step;
    } else if (colorDomain.min === colorDomain.max) {
      paint[prop] = palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW;
    } else {
      const low = palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW;
      const high = palette?.kind === "sequential" ? palette.high : NUMERIC_COLOR_HIGH;
      paint[prop] = [
        "interpolate",
        ["linear"],
        ["get", encodings.color.field],
        colorDomain.min,
        low,
        colorDomain.max,
        high,
      ];
    }
  }

  if (encodings?.size && sizeDomain && renderAs === "circle") {
    paint["circle-radius"] =
      sizeDomain.min === sizeDomain.max
        ? SIZE_RADIUS_MIN
        : [
            "interpolate",
            ["linear"],
            ["get", encodings.size.field],
            sizeDomain.min,
            SIZE_RADIUS_MIN,
            sizeDomain.max,
            SIZE_RADIUS_MAX,
          ];
  }

  return { renderAs, paint };
}
```

(`ResolvedPaletteRuntime` here is just `import("./palette").ResolvedPalette`
— add `import type { ResolvedPalette as ResolvedPaletteRuntime,
colorsForClasses } from "./palette";` — actually `colorsForClasses` is a
value import, not a type: `import { colorsForClasses } from "./palette";
import type { ResolvedPalette } from "./palette";` and use `ResolvedPalette`
directly as the parameter type instead of introducing an alias — simplify
the sketch above accordingly when writing the real file.)

Update `buildLegend` similarly — add the classed branch and the `palette`
parameter:

```ts
export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
): LegendSpec | null {
  const legend: LegendSpec = {};

  if (encodings?.color && colorDomain) {
    if (colorDomain.kind === "categorical") {
      const colors = palette
        ? colorsForClasses(palette, colorDomain.values.length)
        : colorDomain.values.map((_, i) => paletteColor(i));
      legend.color = {
        kind: "categorical",
        field: encodings.color.field,
        entries: colorDomain.values.map((value, i) => ({ value, color: colors[i] })),
      };
    } else if (colorDomain.kind === "numeric-classed") {
      const nClasses = colorDomain.breaks.length - 1;
      const colors = palette
        ? colorsForClasses(palette, nClasses)
        : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
      legend.color = {
        kind: "classed",
        field: encodings.color.field,
        classes: Array.from({ length: nClasses }, (_, i) => ({
          color: colors[i],
          from: colorDomain.breaks[i],
          to: colorDomain.breaks[i + 1],
        })),
      };
    } else {
      legend.color = {
        kind: "numeric",
        field: encodings.color.field,
        min: colorDomain.min,
        max: colorDomain.max,
        colorLow: palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW,
        colorHigh: palette?.kind === "sequential" ? palette.high : NUMERIC_COLOR_HIGH,
      };
    }
  }

  if (encodings?.size && sizeDomain && geometryKind === "point") {
    legend.size = {
      field: encodings.size.field,
      min: sizeDomain.min,
      max: sizeDomain.max,
      radiusMin: SIZE_RADIUS_MIN,
      radiusMax: SIZE_RADIUS_MAX,
    };
  }

  return legend.color || legend.size ? legend : null;
}
```

Update `LegendSpec` (existing type) to add the classed variant:

```ts
export type LegendSpec = {
  color?:
    | { kind: "categorical"; field: string; entries: { value: string; color: string }[] }
    | { kind: "classed"; field: string; classes: { color: string; from: number; to: number }[] }
    | { kind: "numeric"; field: string; min: number; max: number; colorLow: string; colorHigh: string };
  size?: { field: string; min: number; max: number; radiusMin: number; radiusMax: number };
};
```

- [ ] **Step 8: Run to verify the paint/legend tests pass, and the original 15 still pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, all tests (15 original + ~15 new).

- [ ] **Step 9: Implement `symbologyToPaintInputs`**

```ts
export function symbologyToPaintInputs(
  symbology: LayerSymbology | undefined,
  themeColors: ThemeColors | undefined,
): {
  encodings: MapEncodings;
  colorDomain: ColorDomain | null;
  sizeDomain: SizeDomain | null;
  palette: ResolvedPalette | undefined;
} {
  if (!symbology) return { encodings: {}, colorDomain: null, sizeDomain: null, palette: undefined };
  const encodings: MapEncodings = {};
  let colorDomain: ColorDomain | null = null;
  let palette: ResolvedPalette | undefined;
  if (symbology.color) {
    encodings.color = {
      field: symbology.color.field,
      mode: symbology.color.mode,
      classification: symbology.color.classification,
    };
    colorDomain = symbology.color.domain;
    palette = resolvePalette(symbology.color.palette, themeColors) ?? undefined;
  }
  if (symbology.size) encodings.size = { field: symbology.size.field };
  const sizeDomain = symbology.size?.domain ?? null;
  return { encodings, colorDomain, sizeDomain, palette };
}
```

Add `import { resolvePalette } from "./palette"; import type { ThemeColors }
from "../../api/types";` at the top.

- [ ] **Step 10: Run the full test file**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, all tests including the `symbologyToPaintInputs` pair.

- [ ] **Step 11: Add `MapLayer.symbology` in `shell/src/api/types.ts`**

```ts
export type MapLayer =
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "vector";
      tilesUrl: string;
      sourceLayer: string;
      paint?: Record<string, unknown>;
      collectionId?: string;
      geometryKind?: "point" | "line" | "polygon";
      pkColumn?: string;
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "feature";
      url: string;
      paint?: Record<string, unknown>;
      renderAs?: "fill" | "circle" | "line";
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | ... // raster/deck/tiles3d unchanged
```

(Using the inline `import(...)` type syntax avoids a circular value import —
`types.ts` has no runtime dependency on `mapSymbology.ts`, only a type one.)

- [ ] **Step 12: Full shell suite + build**

Run: `cd shell && npx vitest run && npm run build && npm run lint && npm run format:check`
Expected: all green.

- [ ] **Step 13: Commit**

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts shell/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(shell): classification et symbologie déclarative dans mapSymbology.ts

Quantile/intervalle égal/Jenks, palettes optionnelles sur
buildMapPaint/buildLegend (rétrocompatible, 15 tests existants
inchangés), LayerSymbology et son adaptateur vers le compilateur.
EOF
)"
```

---

## Task 7: Shell — `MapSymbologyEditor`

**Files:**
- Create: `shell/src/map/MapSymbologyEditor.tsx`
- Create: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `LayerSymbology`, `ColorClassification`, `PaletteId`,
  `computeColorDomain`, `computeSizeDomain`, `StatQueryFn`, `SampleFieldFn`
  from `../builder/widgets/mapSymbology`; `CURATED_PALETTES` from
  `../builder/widgets/palette`; `ThemeColors` from `../api/types`.
- Produces: `MapSymbologyEditor` component, mounted by `LayersPanel` (Task
  8) and `mapWidget.tsx`'s `PropsPanel` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/MapSymbologyEditor.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapSymbologyEditor } from "./MapSymbologyEditor";
import type { LayerSymbology } from "../builder/widgets/mapSymbology";

test("no color field selected: shows the field picker only", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={["population", "region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();
});

test("theme-primary palette option is absent without a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(false);
});

test("theme-primary palette option is present with a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={{ primary: "#2563eb" }}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("classification method selector is hidden in categorical mode and shown in numeric mode", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <MapSymbologyEditor
      value={{ color: { field: "region", mode: "categorical", palette: "categorical-a", domain: { kind: "categorical", values: [] }, computedAt: "" } }}
      availableFields={["region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();

  rerender(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.getByLabelText("Méthode de classification")).toBeInTheDocument();
});

test("class count selector is hidden when the method is continuous", () => {
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByLabelText("Nombre de classes")).not.toBeInTheDocument();
});

test("recompute button calls runStatistics and writes domain + computedAt via onChange", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(runStatistics).toHaveBeenCalled();
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      color: expect.objectContaining({
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: expect.any(String),
      }),
    }),
  );
});

test("recompute button for the size field calls runStatistics and writes size domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 1, max: 9 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer la taille" }));

  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      size: expect.objectContaining({ domain: { min: 1, max: 9 }, computedAt: expect.any(String) }),
    }),
  );
});

test("computed breaks are shown as text", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          classification: { method: "quantile", classes: 2 },
          palette: "sequential-blue",
          domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
          computedAt: "2026-08-23T10:00:00Z",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/0.*50.*100/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/map/MapSymbologyEditor.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  computeColorDomain,
  computeSizeDomain,
  type ColorClassification,
  type LayerSymbology,
  type SampleFieldFn,
  type StatQueryFn,
} from "../builder/widgets/mapSymbology";
import type { PaletteId } from "../builder/widgets/palette";
import type { ThemeColors } from "../api/types";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";

const PALETTE_OPTIONS: { id: Exclude<PaletteId, "theme-primary">; label: string }[] = [
  { id: "categorical-a", label: "Catégorielle A" },
  { id: "categorical-b", label: "Catégorielle B" },
  { id: "sequential-blue", label: "Séquentielle bleue" },
  { id: "sequential-warm", label: "Séquentielle chaude" },
];

function formatDomain(domain: LayerSymbology["color"] extends infer C
  ? C extends { domain: infer D }
    ? D
    : never
  : never): string {
  if (domain.kind === "categorical") return domain.values.join(", ");
  if (domain.kind === "numeric-classed") return domain.breaks.map((b) => b.toFixed(1)).join(" – ");
  return `${domain.min} – ${domain.max}`;
}

// Éditeur partagé par les DEUX surfaces (éditeur de cartes et PropsPanel du
// widget carte) — même précédent que PopupEditor.tsx (SP-24). Les deux
// hôtes ne diffèrent que par comment `runStatistics`/`sampleField`
// résolvent (collectionId direct vs datasetId), jamais par l'UI elle-même.
export function MapSymbologyEditor({
  value,
  availableFields,
  themeColors,
  runStatistics,
  sampleField,
  onChange,
}: {
  value: LayerSymbology | undefined;
  availableFields: string[];
  themeColors: ThemeColors | undefined;
  runStatistics: StatQueryFn;
  sampleField: SampleFieldFn;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
  const [busy, setBusy] = useState<"color" | "size" | null>(null);
  const color = value?.color;
  const size = value?.size;

  function setColorField(patch: Partial<NonNullable<LayerSymbology["color"]>>) {
    onChange({
      ...value,
      color: {
        field: color?.field ?? "",
        mode: color?.mode ?? "categorical",
        classification: color?.classification,
        palette: color?.palette ?? "categorical-a",
        domain: color?.domain ?? { kind: "categorical", values: [] },
        computedAt: color?.computedAt ?? "",
        ...patch,
      },
    });
  }

  async function recomputeColor() {
    if (!color?.field) return;
    setBusy("color");
    try {
      const domain = await computeColorDomain(
        { field: color.field, mode: color.mode, classification: color.classification },
        { runStatistics, sampleField },
      );
      onChange({ ...value, color: { ...color, domain, computedAt: new Date().toISOString() } });
    } finally {
      setBusy(null);
    }
  }

  async function recomputeSize() {
    if (!size?.field) return;
    setBusy("size");
    try {
      const domain = await computeSizeDomain(size.field, { runStatistics });
      onChange({ ...value, size: { ...size, domain, computedAt: new Date().toISOString() } });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className={labelCls}>
        Champ couleur
        <input
          aria-label="Champ couleur"
          list="map-symbology-fields"
          className={inputCls}
          value={color?.field ?? ""}
          onChange={(e) => setColorField({ field: e.target.value })}
        />
      </label>
      <datalist id="map-symbology-fields">
        {availableFields.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      {color?.field && (
        <>
          <label className={labelCls}>
            Type de couleur
            <select
              aria-label="Type de couleur"
              className={inputCls}
              value={color.mode}
              onChange={(e) =>
                setColorField({
                  mode: e.target.value as "categorical" | "numeric",
                  classification: e.target.value === "categorical" ? undefined : color.classification,
                })
              }
            >
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          {color.mode === "numeric" && (
            <>
              <label className={labelCls}>
                Méthode de classification
                <select
                  aria-label="Méthode de classification"
                  className={inputCls}
                  value={color.classification?.method ?? "continuous"}
                  onChange={(e) => {
                    const v = e.target.value;
                    setColorField({
                      classification:
                        v === "continuous"
                          ? undefined
                          : ({ method: v, classes: color.classification?.classes ?? 5 } as ColorClassification),
                    });
                  }}
                >
                  <option value="continuous">Continu (dégradé)</option>
                  <option value="quantile">Quantiles</option>
                  <option value="equalInterval">Intervalles égaux</option>
                  <option value="jenks">Seuils naturels (Jenks)</option>
                </select>
              </label>
              {color.classification && (
                <label className={labelCls}>
                  Nombre de classes
                  <input
                    aria-label="Nombre de classes"
                    type="number"
                    min={2}
                    max={9}
                    className={inputCls}
                    value={color.classification.classes}
                    onChange={(e) =>
                      setColorField({
                        classification: {
                          ...color.classification!,
                          classes: Math.min(9, Math.max(2, Number(e.target.value) || 2)),
                        },
                      })
                    }
                  />
                </label>
              )}
            </>
          )}
          <label className={labelCls}>
            Palette
            <select
              aria-label="Palette"
              className={inputCls}
              value={color.palette}
              onChange={(e) => setColorField({ palette: e.target.value as PaletteId })}
            >
              {PALETTE_OPTIONS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
              {themeColors?.primary && <option value="theme-primary">Thème du site</option>}
            </select>
          </label>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "color"}
            onClick={() => void recomputeColor()}
          >
            {busy === "color" ? "Calcul…" : "Recalculer les classes"}
          </button>
          {color.computedAt && (
            <p className="text-xs text-slate-500">
              Classes calculées le {new Date(color.computedAt).toLocaleString()} : {formatDomain(color.domain)}
            </p>
          )}
        </>
      )}
      <label className={labelCls}>
        Champ taille
        <input
          aria-label="Champ taille"
          list="map-symbology-fields"
          className={inputCls}
          value={size?.field ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              size: { field: e.target.value, domain: size?.domain ?? { min: 0, max: 0 }, computedAt: size?.computedAt ?? "" },
            })
          }
        />
      </label>
      {size?.field && (
        <>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "size"}
            onClick={() => void recomputeSize()}
          >
            {busy === "size" ? "Calcul…" : "Recalculer la taille"}
          </button>
          {size.computedAt && (
            <p className="text-xs text-slate-500">
              Taille calculée le {new Date(size.computedAt).toLocaleString()} : {size.domain.min} – {size.domain.max}
            </p>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS. If the `formatDomain` conditional type is rejected by
`tsc`, replace it with a concrete union type
(`ColorDomain` imported from `mapSymbology.ts`) instead of the derived
`infer` gymnastics shown above — that inline type was written for
readability of intent in this plan, not guaranteed to compile verbatim;
prefer `import type { ColorDomain } from "../builder/widgets/mapSymbology";
function formatDomain(domain: ColorDomain): string { ... }`.

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green, count ≥ previous + 9.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): éditeur de symbologie partagé (MapSymbologyEditor)

Monté ensuite sur LayersPanel et le widget carte — même précédent que
PopupEditor.tsx (SP-24).
EOF
)"
```

---

## Task 8: Shell — wire `LayersPanel.tsx`

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `MapSymbologyEditor` (Task 7); `client.queryDataSource`,
  `client.sampleCollectionField` (Task 5).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/map/LayersPanel.test.tsx`:

```tsx
test("a vector layer with a collectionId exposes the symbology editor and can recompute a numeric domain", async () => {
  const onChange = vi.fn();
  const client = {
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [{ name: "pop" }] }),
    queryDataSource: vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]),
    sampleCollectionField: vi.fn(),
  } as unknown as ItemClient;
  const vectorLayer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "u",
    sourceLayer: "communes",
    collectionId: "communes",
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={[vectorLayer]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await userEvent.type(screen.getByLabelText("Champ couleur"), "pop");
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(client.queryDataSource).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "statistics",
      service: "core",
      layer: "communes",
      query: expect.objectContaining({ measures: expect.any(Array) }),
    }),
  );
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      symbology: expect.objectContaining({
        color: expect.objectContaining({ domain: { kind: "numeric", min: 0, max: 100 } }),
      }),
    }),
  ]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx -t "symbology editor"`
Expected: FAIL — no symbology editor rendered yet.

- [ ] **Step 3: Wire it**

In `shell/src/map/LayersPanel.tsx`, add a `LayerSymbologyEditor` wrapper
component mirroring the existing `LayerPopupEditor` (same file):

```tsx
function LayerSymbologyEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  if (!collectionId) return null; // external tiles / plain GeoJSON feature layer: no collection to query
  return (
    <MapSymbologyEditor
      value={layer.symbology}
      availableFields={schema.data?.fields.map((f) => f.name) ?? []}
      themeColors={undefined} // no Theme on a standalone MapConfig (spec §1)
      runStatistics={(query) =>
        client.queryDataSource({
          id: `map-symbology-${collectionId}`,
          type: "statistics",
          service: "core",
          layer: collectionId,
          query,
        })
      }
      sampleField={(field, limit) => client.sampleCollectionField(collectionId, field, limit)}
      onChange={(symbology) => onChangeLayer({ ...layer, symbology })}
    />
  );
}
```

Mount it right after the existing `LayerPopupEditor` in the layer `<li>`:

```tsx
            {(layer.kind === "vector" || layer.kind === "feature") && (
              <div className="basis-full pl-2">
                <LayerPopupEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
                <LayerSymbologyEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
              </div>
            )}
```

Import `MapSymbologyEditor` at the top of the file.

Note: for a `"feature"` kind layer (no `collectionId` ever, per its type),
`LayerSymbologyEditor` returns `null` — a `feature` layer's data comes from
an arbitrary GeoJSON URL, not a queryable collection, so there is no
`runStatistics` source for it in `LayersPanel` (the same layer kind used
inside `mapWidget.tsx` DOES get symbology, Task 10, because there
`runStatistics` resolves through the widget's own `datasetId`, not through
`LayersPanel`'s collection-only path). Document this explicitly as a scoped
limitation, not a bug: standalone `feature` layers keep the pre-existing
`paint`-only manual path.

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS, all tests (5 existing + 1 new).

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): branche MapSymbologyEditor sur les couches vector de l'éditeur de cartes
EOF
)"
```

---

## Task 9: Shell — `MapView` reads `layer.symbology` at render

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `symbologyToPaintInputs`, `buildMapPaint` from
  `../builder/widgets/mapSymbology`.

- [ ] **Step 1: Read the current `applyLayers` vector/feature branches**

Run: `grep -n "kind === \"vector\"\|kind === \"feature\"" shell/src/map/MapView.tsx`

Read the exact surrounding code (paint assembly per sub-layer, lines ~222-296
per earlier exploration) before editing — the plan shows the transformation
to apply, not a verbatim replacement of code you have not just re-read.

- [ ] **Step 2: Write the failing test**

Add to `shell/src/map/MapView.test.tsx` (find the existing test that
asserts on a rendered `fill-color`/paint for a vector or feature layer, to
reuse its MapLibre-mocking setup):

```tsx
test("a layer with symbology renders paint compiled from its frozen domain, ignoring any stale raw paint", () => {
  const layer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "feature",
    url: "u",
    paint: { "fill-color": "#000000" }, // stale/irrelevant once symbology is present
    symbology: {
      color: {
        field: "pop",
        mode: "numeric",
        palette: "sequential-blue",
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: "2026-08-23T00:00:00Z",
      },
    },
  };
  // (render MapView with this single layer, following whichever existing
  // test in this file already asserts on setPaintProperty/addLayer calls —
  // copy its exact mock/assertion mechanics)
});
```

Fill in the actual render/assertion mechanics by copying the nearest
existing paint-assertion test in this file verbatim, then swap in the
`symbology`-bearing layer above and assert the resulting paint uses the
`interpolate` shape from `#dbeafe`→`#1e3a8a` (the `sequential-blue`
palette), not `"#000000"`.

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t symbology`
Expected: FAIL — `paint` still comes from the raw `layer.paint`.

- [ ] **Step 4: Implement**

In `shell/src/map/MapView.tsx`'s `applyLayers`, wherever `layer.paint ??
{}` (or equivalent) is read for `kind === "vector"` and `kind ===
"feature"`, replace with a small helper computed once per layer:

```ts
function effectivePaint(layer: Extract<MapLayer, { kind: "vector" | "feature" }>): Record<string, unknown> {
  if (!layer.symbology) return layer.paint ?? {};
  const geometryKind =
    layer.kind === "vector" ? (layer.geometryKind ?? "polygon") : "polygon"; // feature layers: renderAs already carries geometry choice, see below
  const { encodings, colorDomain, sizeDomain, palette } = symbologyToPaintInputs(layer.symbology, undefined);
  return buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette).paint;
}
```

For `kind === "feature"`, the existing code already derives `renderAs` from
`layer.renderAs` (author-set), not from a detected `geometryKind` — pass the
render-as-implied geometry kind consistently with whatever `applyLayers`
already does today for that layer kind (read the exact existing branch
before writing this, per Step 1 — do not invent a new geometryKind
inference here).

For the `vector` kind's existing per-sub-layer split (point/line/polygon
sub-layers by `geometryKind`, from SP-24's I1 fix), call `effectivePaint`
once for the whole layer and keep applying the existing `paintFor(...,
paintPrefix)` filter on its result exactly as today — `buildMapPaint`'s
output already only contains the single `renderAs`-appropriate paint key
(e.g. `"fill-color"`), so this composes without change to the sub-layer
splitting logic itself.

- [ ] **Step 5: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, all tests (no regression on layers without `symbology`,
which must still read `layer.paint` exactly as before).

- [ ] **Step 6: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): MapView compile le paint depuis symbology quand elle est présente

Aucun appel réseau : le domaine est déjà figé dans la config.
layer.paint reste le chemin manuel pour toute couche sans symbology.
EOF
)"
```

---

## Task 10: Shell — thread `theme` through both the editor and the render path

**Files:**
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/PropsPanel.tsx`
- Modify: `shell/src/builder/PropsPanel.test.tsx`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/WidgetHost.test.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`

**Interfaces:**
- Produces: `WidgetDefinition["PropsPanel"]` receives an additional
  `theme?: Theme` field (editor-time); `WidgetContext` (consumed by
  `WidgetDefinition["Component"]`) also gains `theme?: Theme` (render-time —
  needed so a `"theme-primary"` palette resolves to the *same* color both in
  the editor's preview and in the actually-published widget; without this,
  `Component` would have no way to resolve `"theme-primary"` and would
  silently fall back to default colors at render, while the editor showed
  the right ones — caught during this plan's self-review, not part of the
  original spec).

**Two separate threading paths, both needed:**
1. Editor time: `AppBuilderPage.tsx` → `PropsPanel` (wrapper) → `def.PropsPanel`.
2. Render time: `AppRenderer.tsx` (the one call site that matters — it is
   "the one runtime" per `CLAUDE.md` rule 3, used for edit/preview/runtime
   modes alike) → `WidgetHost` → `WidgetContext.theme` → `def.Component`.

**Deliberate scope limit, both paths**: the four other `<WidgetHost>`/
`<PropsPanel>` call sites inside `tabs.tsx`/`drawer.tsx`/`modal.tsx` (via
`LayoutEditor.tsx`, for their own nested children) do **not** get `theme`
threaded in this task — a map widget nested inside a container widget
simply doesn't see a theme, on both the editing and the rendering side,
consistently. This is the same already-handled `themeColors: undefined`
state as a standalone map (Task 4/6/7), not a crash or a silent wrong
color — `resolvePalette("theme-primary", undefined)` returns `null`,
`MapSymbologyEditor` doesn't even offer the option, and `buildMapPaint`
falls back to its hardcoded default when no palette is provided at all.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/PropsPanel.test.tsx`:

```tsx
test("passes theme through to the widget's PropsPanel", () => {
  const receivedThemes: (unknown | undefined)[] = [];
  registerWidget({
    type: "theme-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: ({ theme }) => {
      receivedThemes.push(theme);
      return null;
    },
    Component: () => null,
  });
  render(
    <PropsPanel
      item={{ id: "1", widget: "theme-probe", x: 0, y: 0, w: 1, h: 1, props: {} }}
      dataSources={[]}
      theme={{ colors: { primary: "#2563eb" } }}
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
  );
  expect(receivedThemes).toEqual([{ colors: { primary: "#2563eb" } }]);
});
```

(`registerWidget`/`getWidget` come from `../builder/registry`, already
imported by neighboring tests in this file — check the existing imports at
the top and reuse them, don't re-add a duplicate import.)

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx -t "theme through"`
Expected: FAIL — `PropsPanel` accepts no `theme` prop (TS error) or the
widget's `PropsPanel` never receives it.

- [ ] **Step 3: Update the registry type — both `PropsPanel` and `WidgetContext`**

In `shell/src/builder/registry.ts`:

```ts
import type { DataSource, DataSourceState, Page, RenderMode, Theme } from "../api/types";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, unknown>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
  breakpoint?: Breakpoint;
  theme?: Theme;
};
```

```ts
  PropsPanel: (p: {
    props: P;
    onChange: (props: P) => void;
    dataSources: DataSource[];
    theme?: Theme;
  }) => ReactNode;
```

- [ ] **Step 4: Thread it through the `PropsPanel` wrapper**

In `shell/src/builder/PropsPanel.tsx`:

```ts
import type { DataSource, Theme, WidgetItem } from "../api/types";

export function PropsPanel({
  item,
  dataSources,
  theme,
  onChange,
  onVisibleWhenChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  theme?: Theme;
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
}) {
  ...
      <Panel props={item.props} dataSources={dataSources} theme={theme} onChange={(p) => onChange(p)} />
  ...
```

- [ ] **Step 5: Pass it from `AppBuilderPage.tsx`**

```tsx
              <PropsPanel
                item={selected}
                dataSources={draft.dataSources}
                theme={draft.theme}
                onChange={updateSelectedProps}
                onVisibleWhenChange={updateSelectedVisibleWhen}
              />
```

`LayoutEditor.tsx`'s own `<PropsPanel>` call (used by `tabs`/`drawer`/
`modal` for their nested children) is **not** changed in this task — it
keeps omitting `theme`, which is valid since the prop is optional (see
Interfaces note above).

- [ ] **Step 6: Run to verify the editor-time test passes**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx`
Expected: PASS.

- [ ] **Step 7: Thread `theme` through the render path — write the failing test first**

Add to `shell/src/builder/WidgetHost.test.tsx` (find its existing render
helper/imports and reuse them):

```tsx
test("passes theme through to the widget's Component via ctx", () => {
  const receivedThemes: (unknown | undefined)[] = [];
  registerWidget({
    type: "theme-ctx-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: ({ ctx }) => {
      receivedThemes.push(ctx.theme);
      return null;
    },
  });
  render(
    <WidgetHost
      item={{ id: "1", widget: "theme-ctx-probe", x: 0, y: 0, w: 1, h: 1, props: {} }}
      mode="runtime"
      theme={{ colors: { primary: "#2563eb" } }}
    />,
  );
  expect(receivedThemes).toEqual([{ colors: { primary: "#2563eb" } }]);
});
```

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx -t "theme through to the widget's Component"`
Expected: FAIL — `WidgetHost` accepts no `theme` prop.

- [ ] **Step 8: Implement**

In `shell/src/builder/WidgetHost.tsx`:

```tsx
import type { Page, RenderMode, Theme, WidgetItem } from "../api/types";

export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
  breakpoint,
  theme,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
  breakpoint?: Breakpoint;
  theme?: Theme;
}) {
  // ... unchanged body ...
  return (
    <WidgetErrorBoundary>
      <Widget
        props={resolvedProps}
        ctx={{
          mode,
          data,
          bus: bus ?? undefined,
          widgetId: item.id,
          pages,
          navigate,
          variables,
          user,
          breakpoint,
          theme,
        }}
      />
    </WidgetErrorBoundary>
  );
}
```

In `shell/src/builder/AppRenderer.tsx`, at its one `<WidgetHost>` call site
(around line 210 — re-read the surrounding JSX before editing, since this
plan does not reproduce it verbatim), add `theme={config.theme}` alongside
the existing props passed there. The three other call sites
(`tabs.tsx`/`drawer.tsx`/`modal.tsx`, via `LayoutEditor.tsx`'s own
`<WidgetHost item={item} mode="edit" />`) are **not** changed — same
documented scope limit as Step 5.

- [ ] **Step 9: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: PASS.

- [ ] **Step 10: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green — this also proves the ~22 other widgets' `Component`/
`PropsPanel` implementations still compile unchanged (structural typing:
none of them destructure `theme`/`ctx.theme`, only `mapWidget.tsx` will,
starting Task 11).

- [ ] **Step 11: Commit**

```bash
git add shell/src/builder/registry.ts shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx shell/src/builder/WidgetHost.tsx shell/src/builder/WidgetHost.test.tsx shell/src/builder/AppRenderer.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): theme accessible aux widgets, à l'édition et au rendu

WidgetDefinition.PropsPanel ET WidgetContext (Component) reçoivent le
theme de l'AppConfig englobant — nécessaire pour que la palette
"Thème du site" du widget carte (SP-25) résolve à la même couleur dans
l'éditeur et dans le rendu publié. Un widget imbriqué dans
tabs/drawer/modal ne le reçoit pas encore (LayoutEditor ne le propage
pas, aux deux endroits) — limite assumée, mêmes garanties qu'une carte
standalone sans theme.
EOF
)"
```

---

## Task 11: Shell — wire `mapWidget.tsx` onto `LayerSymbology`

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `MapSymbologyEditor` (Task 7), `symbologyToPaintInputs`,
  `LayerSymbology` (Task 6), `theme` prop on `PropsPanel` and `ctx.theme`
  on `WidgetContext` (both from Task 10).
- Removes: `props.encodings`, `MapEncodings` import for that purpose,
  `useNumericDomain`, the two domain `useQuery`s in `Component`.

This is the breaking change documented in the spec (§2, §7): any
already-saved app config with `props.encodings` loses its symbology on next
load — it is not migrated.

- [ ] **Step 1: Read the current file in full again**

It was already read in full during planning (reproduced above in this
plan's research) — re-read it live before editing, since this task rewrites
most of `PropsPanel` and `Component`.

- [ ] **Step 2: Update the failing/changed tests first**

In `shell/src/builder/widgets/mapWidget.test.tsx`, find every test that sets
`props.encodings` or asserts on the domain `useQuery` calls (`groupBy`/
`min`/`max` statistics queries triggered by `Component` itself) — these
tests describe the **old** behavior being removed. Rewrite them to use
`props.symbology` instead, and to assert `Component` does **not** call
`client.queryDataSource` at all (no live domain fetch at render):

```tsx
test("Component renders paint from frozen props.symbology, without querying any domain", () => {
  const client = {
    queryDataSource: vi.fn(), // must NOT be called by Component
    getAuthToken: () => undefined,
    getCoreUrl: () => "https://core.test",
  } as unknown as ItemClient;
  // ... render the widget's Component with props.symbology set and a
  // ctx.data.url present, following this file's existing render helper ...
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("PropsPanel mounts MapSymbologyEditor with theme from props", () => {
  // ... render PropsPanel with theme={{ colors: { primary: "#2563eb" } }},
  // assert the "Thème du site" option is present in the rendered select ...
});

test("Component resolves the theme-primary palette from ctx.theme at render time", () => {
  // render the widget's Component with props.symbology.color.palette ===
  // "theme-primary" and ctx.theme = { colors: { primary: "#2563eb" } };
  // assert the resulting paint's interpolate/step expression ends on
  // "#2563eb" (the high stop of resolvePalette("theme-primary", ...)),
  // not the "categorical-a"/"sequential-blue" hardcoded defaults — this is
  // the exact bug this plan's self-review caught (Task 10): without
  // ctx.theme threaded through, this would silently render wrong colors.
});
```

Fill in the exact render helper by copying this file's existing
`PropsPanel`/`Component` render setup (it already exists for the
`encodings`-based tests being replaced) rather than inventing new
scaffolding.

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL — old tests reference removed behavior; new tests fail
against the not-yet-updated implementation.

- [ ] **Step 4: Rewrite `PropsPanel`**

Replace the widget's `PropsPanel` entirely:

```tsx
    PropsPanel: ({ props, onChange, dataSources, theme }) => {
      const client = useItemClient();
      const dataSourceId = String(props.dataSourceId ?? "");
      const dataSource = dataSources.find((d) => d.id === dataSourceId);
      const datasetId = dataSource?.datasetId;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect
            value={dataSourceId}
            dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })}
          />
          <MapSymbologyEditor
            value={props.symbology as LayerSymbology | undefined}
            availableFields={[]} // PropsPanel has no schema (registry.ts) — same PopupEditor precedent
            themeColors={theme?.colors}
            runStatistics={(query) =>
              client.queryDataSource({
                id: `map-domain-${datasetId}`,
                type: "statistics",
                service: "core",
                layer: "",
                datasetId,
                query,
              })
            }
            sampleField={async () => {
              throw new Error("Jenks sur le widget carte nécessite un collectionId résolu — non câblé");
            }}
            onChange={(symbology) => onChange({ ...props, symbology })}
          />
          <PopupEditor
            value={props.popup as PopupConfig | undefined}
            availableFields={[]}
            onChange={(popup) => onChange({ ...props, popup })}
          />
        </div>
      );
    },
```

Note the `sampleField` stub: `mapWidget.tsx`'s `runStatistics` resolves
through `datasetId` (not a direct `collectionId`), and `sampleCollectionField`
on `ItemClient` takes a `collectionId`. Resolving a `datasetId` to its
underlying `collectionId` for this one call requires the same
`resolveDataset`-style lookup `itemClient.ts` already does internally for
`queryDataSource` — **but that resolution is private to `itemClient.ts`,
not exposed on the `ItemClient` interface**. Rather than exposing an
internal implementation detail through the public interface for one call
site, **Jenks is out of scope for the widget's color field in this task**:
the "Seuils naturels (Jenks)" option in `MapSymbologyEditor`'s method
selector will throw if chosen from the widget's `PropsPanel`. Write one
more test proving this explicitly:

```tsx
test("choosing Jenks from the widget's PropsPanel surfaces an error instead of hanging", async () => {
  // select "jenks" as the classification method, click "Recalculer les
  // classes", assert an error is shown (not a silent hang or a crash) —
  // MapSymbologyEditor's recomputeColor already wraps the call and resets
  // `busy` in its `finally`, so the button re-enables; add an error string
  // state to MapSymbologyEditor if none exists yet (check Task 7's
  // implementation — if recomputeColor has no catch, add one there instead
  // of duplicating it here, since both hosts share the component).
});
```

Go back to `MapSymbologyEditor.tsx` (Task 7) and add a caught-error display,
since this is exactly the kind of thing "no placeholders" rules out leaving
implicit:

```tsx
  const [error, setError] = useState<string | null>(null);
  async function recomputeColor() {
    if (!color?.field) return;
    setBusy("color");
    setError(null);
    try {
      const domain = await computeColorDomain(/* ... */);
      onChange(/* ... */);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }
```

And render `{error && <p role="alert" className="text-xs text-red-600">{error}</p>}`
near the recompute button. Add one test for this in Task 7's test file too
(retroactively — this is a real gap the two-task split surfaced, fix it
where the component actually lives):

```tsx
test("a failing recompute surfaces an error instead of hanging silently", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("boom"));
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});
```

- [ ] **Step 5: Rewrite `Component`**

Replace the domain-fetching section and paint/legend construction:

```tsx
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

      const symbology = props.symbology as LayerSymbology | undefined;
      const { encodings, colorDomain, sizeDomain, palette } = symbologyToPaintInputs(
        symbology,
        ctx.theme?.colors,
      );
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      const { renderAs, paint } = buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette);
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind, palette);

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [
              {
                id: `ds-${String(props.dataSourceId)}`,
                title: "Données",
                visible: true,
                kind: "feature",
                url,
                renderAs,
                paint,
                popup: props.popup as PopupConfig | undefined,
              },
            ]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu
            datasetId={ctx.data?.datasetId}
            dataSourceId={String(props.dataSourceId ?? "")}
            resolvedSource={ctx.data?.resolvedSource}
            hasGeometry={ctx.data?.hasGeometry}
          />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn)
                  setCrossFilter(
                    datasetId,
                    pkColumn,
                    String(record.id),
                    String(props.dataSourceId ?? ""),
                    record.geometry,
                  );
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
```

Remove `useNumericDomain`, the `useQuery` import if now unused elsewhere in
the file (check — `Component` no longer uses it, but confirm nothing else
in the file does before deleting the import), `MapEncodings`/`ColorDomain`/
`SizeDomain` imports (replaced by `LayerSymbology`/`symbologyToPaintInputs`),
and update the top-of-file import block:

```tsx
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { buildLegend, buildMapPaint, detectGeometryKind, symbologyToPaintInputs } from "./mapSymbology";
import type { LayerSymbology, LegendSpec } from "./mapSymbology";
import type { ItemClient, MapConfig, PopupConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";
import { PopupEditor } from "../../map/PopupEditor";
import { MapSymbologyEditor } from "../../map/MapSymbologyEditor";
```

(`lazy`/`Suspense`/`useRef` from `"react"` stay; `ItemClient` type import
stays only if still referenced — check before keeping it.)

Update `MapSymbologyLegend` to render the new `"classed"` legend kind
(alongside the existing `"categorical"`/`"numeric"` branches):

```tsx
      {legend.color?.kind === "classed" && (
        <ul>
          {legend.color.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: c.color }} />
              {c.from.toFixed(1)} – {c.to.toFixed(1)}
            </li>
          ))}
        </ul>
      )}
```

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS, all tests.

- [ ] **Step 7: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green, count reflecting removed old tests + added new ones.

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte utilise LayerSymbology au lieu d'encodings

Changement cassant assumé (spec §2/§7) : une app déjà publiée avec une
symbologie de widget carte perd sa configuration au prochain
chargement. Jenks non câblé sur cette surface (pas de collectionId
direct) — méthode refusée avec une erreur visible plutôt qu'un hang.
Component ne fait plus aucun appel réseau de domaine à chaque rendu.
EOF
)"
```

---

## Task 12: Shell E2E — the plan's acceptance proof

**Files:**
- Create: `shell/e2e/map-symbology.spec.ts`

**Interfaces:** none new — end-to-end proof only.

- [ ] **Step 1: Read the nearest precedent**

Run: `grep -n "tiles.*mvt\|world-tile" shell/e2e/map-popup.spec.ts shell/e2e/mocks.ts`

`map-popup.spec.ts` (SP-24) already mounts a real MapLibre canvas against a
mocked MVT tile fixture and a mocked `/collections` catalog — reuse its
exact scaffolding (fixture file, route mocks, canvas click mechanics)
instead of inventing new ones.

- [ ] **Step 2: Write the E2E spec**

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("author 5 quantile classes on a tiled layer, save, reload, and the rendered colors survive with no new aggregate call", async ({ page }) => {
  await mockCore(page);
  // (reuse map-popup.spec.ts's MVT tile fixture route mock verbatim)

  let aggregateCallsAfterSave = 0;
  await page.route("**/collections/*/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: "value",
        rows: [{ value: 0, min: 0, q1: 20, q2: 40, q3: 60, q4: 80, max: 100 }],
      },
    });
  });

  // navigate to the map editor, add the tiled collection layer (mirrors
  // map-popup.spec.ts's layer-add flow), open its symbology editor
  await page.goto("/");
  // ... (follow map-popup.spec.ts's exact navigation to a map item's editor) ...

  await page.getByLabel("Champ couleur").fill("population");
  await page.getByLabel("Type de couleur").selectOption("numeric");
  await page.getByLabel("Méthode de classification").selectOption("quantile");
  await page.getByLabel("Nombre de classes").fill("5");
  await page.getByLabel("Palette").selectOption("sequential-blue");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText(/0\.0.*100\.0/)).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // stop counting real aggregate calls from here — any further one is a bug
  page.on("request", (req) => {
    if (req.url().includes("/aggregate")) aggregateCallsAfterSave++;
  });

  await page.reload();
  await expect(page.locator("canvas")).toBeVisible();
  expect(aggregateCallsAfterSave).toBe(0);
});
```

Fill in the elided navigation/layer-add steps by copying `map-popup.spec.ts`
line for line for that portion — do not write new selectors from a guess.

- [ ] **Step 3: Run it**

Run: `cd shell && npm run e2e -- map-symbology`
Expected: PASS.

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: PASS, no regression on `map-popup.spec.ts`/`map-editor.spec.ts`
(both touch the same `LayersPanel`/`MapView` code paths this plan modified).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/map-symbology.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): prouve le round-trip de la symbologie sur une couche tuilée

5 classes en quantiles, palette nommée, enregistrement, rechargement,
rendu identique sans nouvel appel d'agrégat — critère de sortie du
plan d'action (SP-25).
EOF
)"
```

---

## Task 13: Final validation gate

**Files:** none (verification only).

- [ ] **Step 1: Core suite**

Run: `cd core && uv run pytest -v`
Expected: PASS, no drop from 1868 passed / 5 skipped + this plan's ~16 new
tests (Tasks 1-2).

- [ ] **Step 2: Core lint/type/import gates**

Run: `cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green.

- [ ] **Step 3: Core coverage**

Run: `cd core && uv run pytest --cov=app --cov-report=term-missing -q | tail -5`
Expected: ≥ 85 (per `core/.coverage-threshold`).

- [ ] **Step 4: Shell suite**

Run: `cd shell && npx vitest run`
Expected: PASS, no drop from 159 files / 1387 tests + this plan's new tests
(Tasks 4, 6, 7, 8, 9, 10, 11).

- [ ] **Step 5: Shell lint/format/build**

Run: `cd shell && npm run lint && npm run format:check && npm run build`
Expected: all green.

- [ ] **Step 6: Shell coverage**

Run: `rm -rf shell/dist shell/dist-export && cd shell && npx vitest run --coverage | tail -20`
Expected: ≥ 88 (per `shell/.coverage-threshold`) — measured after removing
build artifacts, per the documented SP-22/23/24 trap.

- [ ] **Step 7: Shell E2E**

Run: `cd shell && npm run e2e`
Expected: PASS, no regression (baseline 107 passed / 4 skipped at end of
SP-24, plus this plan's new spec).

- [ ] **Step 8: Deployability guard**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: all green — this plan adds no new env var, no new service, no new
bucket, so this should be a no-op confirmation, not a fix.

- [ ] **Step 9: pre-commit**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 hooks green.

- [ ] **Step 10: Confirm OpenAPI/TS sync**

Run: `git status --porcelain -- core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: empty (already committed in Task 3, nothing drifted since).

- [ ] **Step 11: Update CLAUDE.md**

Add an SP-25 entry to `### Fait` (and remove/adjust the SP-25 forward
references currently in `### À venir`), following this repo's own
established format (one bullet per SP, cross-references to the spec file,
notable deviations from plan/spec called out explicitly — see the SP-24
entry as the immediate template). This is a documentation task, not a code
task — no test/build steps apply, just accuracy against what was actually
built (re-read the final diffs of Tasks 1-12 before writing it, don't
describe intentions from this plan as if they were unconditionally true —
Task 11 in particular narrowed the widget's Jenks support versus the
spec's original assumption, and that narrowing must show up here).

- [ ] **Step 12: Final commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(sp25): consigne la symbologie de l'éditeur de cartes
EOF
)"
```
