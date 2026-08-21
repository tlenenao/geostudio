# SP-23 — Les quatre bouchons à coût faible : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer les quatre chantiers 4.18, 4.6, 4.15 et 4.16 du plan d'action
2026-08-20 : un panneau d'historique/rollback atteignable depuis les cinq
éditeurs, un catalogue qui filtre sur les 12 types de ressource, quatre
agrégats analytiques de plus et six grains temporels au lieu de trois.

**Architecture:** Aucune nouvelle table, aucune migration, aucune nouvelle
route serveur. Trois des quatre chantiers étendent une surface existante
(`AggregateRequestBody`, `_STAT_TYPES`, le sélecteur de `CatalogPage`) ; le
quatrième câble deux routes qui existent depuis SP-0 et que rien n'appelait
(`GET /configs/{id}/revisions`, `POST /configs/{id}/rollback`), en corrigeant
au passage le fait que le rollback court-circuite les validateurs de payload.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic / DuckDB / SQLAlchemy côté
cœur ; React 18 / TypeScript / Vitest / Playwright côté shell.

**Spec de référence :** `docs/superpowers/specs/2026-08-21-sp23-quatre-bouchons-design.md`

## Global Constraints

- Docs et messages utilisateur en **français** ; code et identifiants en **anglais**.
- Commits **conventional** (`feat(core): …`, `fix(shell): …`), petits, un sujet.
- **TDD systématique** : le test échoue d'abord, pour la bonne raison.
- Branche de travail : `dev`.
- Le hook `commit-msg` (commitlint) refuse un sujet capitalisé — écrire
  `feat(core): ajoute …`, jamais `feat(core): Ajoute …`.
- Les hooks `pre-commit` lancent `ruff --fix`, `eslint --fix .` et
  `prettier --write .` sur tout `shell/` : un `git add` de plus peut être
  nécessaire après un premier `git commit` refusé.
- Compteurs de référence à ne pas faire baisser (mesurés le 2026-08-21) :
  core **1653 passed / 153 skipped / 0 failed** ; shell **152 fichiers /
  1235 tests**.
- Seuils de couverture versionnés : `core/.coverage-threshold` = **85**,
  `shell/.coverage-threshold` = **88**.
- Commandes : `cd core && uv run pytest` ; `cd shell && npm run test` /
  `npm run e2e` / `npm run build` / `npm run lint` / `npm run format:check`.
- **`p` est toujours exprimé en pourcentage** (`0 < p < 100`), jamais en
  fraction — côté serveur comme côté shell. La division par 100 se fait
  dans `_agg_expr` et dans `metricExpr`, nulle part ailleurs.
- Les quatre nouveaux noms d'agrégat sont, littéralement et partout :
  `countDistinct`, `median`, `percentile`, `stddev`.
- Les six grains temporels sont, littéralement et partout :
  `hour`, `day`, `week`, `month`, `quarter`, `year`.

## Structure des fichiers

**Créés :**

| Fichier | Responsabilité |
|---|---|
| `shell/src/api/resourceTypes.ts` | Le `Record<ResourceType, string>` exhaustif des libellés — source unique pour `CatalogPage` et `ItemCard` |
| `shell/src/builder/aggregates.ts` | La liste des agrégats analytiques et leurs libellés français — source unique pour les deux `<select>` de `DataSourcePanel` |
| `shell/src/builder/ConfigHistoryPanel.tsx` | Le panneau « Historique » générique (liste + Restaurer) |
| `shell/src/builder/ConfigHistoryPanel.test.tsx` | Ses tests |
| `shell/src/api/resourceTypes.test.ts` | Test d'exhaustivité des libellés de type |
| `shell/e2e/config-history.spec.ts` | E2E : restaurer une version depuis le builder |

**Modifiés (cœur) :** `core/app/analytics/aggregate.py`,
`core/app/harvest/live_query.py`, `core/app/configs/routes.py`, `core/openapi.json`.

**Modifiés (shell) :** `shell/src/api/types.ts`, `shell/src/api/itemClient.ts`,
`shell/src/api/generated/core-schema.d.ts`,
`shell/src/staticExport/StaticItemClient.ts`,
`shell/src/builder/DataSourcePanel.tsx`,
`shell/src/builder/useUndoableDraft.ts`,
`shell/src/builder/widgets/chartOption.ts`,
`shell/src/builder/widgets/indicator.tsx`,
`shell/src/lib/comparisonWindow.ts`,
`shell/src/builder/visualQuery/inferSchema.ts`,
`shell/src/builder/visualQuery/compilePipeline.ts`,
`shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`,
`shell/src/pages/CatalogPage.tsx`, `shell/src/ui/ItemCard.tsx`,
`shell/src/shell/routes.tsx`, et les cinq éditeurs
(`AppBuilderPage`, `MapEditorPage`, `DatasetEditPage`, `PipelineBuilderPage`,
`ReportEditPage`), `shell/e2e/catalog.spec.ts`, `CLAUDE.md`.

---

## Lot A — Cœur : agrégats et grains

### Task 1: Quatre agrégats et le paramètre `p`

**Files:**
- Modify: `core/app/analytics/aggregate.py`
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: rien.
- Produces: `AggregateMeasure(field, agg, label, p)` et
  `AggregateRequestBody(..., p: float | None)` ; `_agg_expr(agg, field, p=None)`.
  Quatre valeurs d'`agg` de plus : `countDistinct`, `median`, `percentile`,
  `stddev`. Contrat de valeur vide : `countDistinct` → `0`,
  `median`/`percentile`/`stddev` → `None`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_analytics_aggregate.py` :

```python
def test_count_distinct_counts_distinct_text_values(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
            _row(3, "Nord", "2026", 30, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="countDistinct", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 2}]


def test_median_returns_the_middle_value(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
            _row(3, "Nord", "2025", 60, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="median", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 20}]


def test_percentile_uses_p_as_a_percentage(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i * 10, lsn=1) for i in range(1, 11)],
    )
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop", p=90)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows[0]["region"] == "Nord"
    assert rows[0]["value"] == pytest.approx(91.0, abs=10.0)


def test_stddev_is_the_sample_standard_deviation(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 2, lsn=1),
            _row(2, "Nord", "2025", 4, lsn=1),
            _row(3, "Nord", "2025", 4, lsn=1),
            _row(4, "Nord", "2025", 6, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="stddev", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # STDDEV_SAMP (n-1) de [2,4,4,6] = 1.632…, là où STDDEV_POP donnerait 1.414.
    assert rows[0]["value"] == pytest.approx(1.632993, abs=1e-5)


def test_stddev_of_a_single_row_group_is_null_not_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="stddev", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": None}]


def test_median_of_a_group_without_castable_values_is_null_not_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "pas-un-nombre", None, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="median", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": None}]


def test_count_distinct_of_a_group_without_values_is_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", None, 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="countDistinct", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 0}]


def test_percentile_without_p_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop")

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_percentile_out_of_range_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop", p=100)

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_p_on_a_non_percentile_agg_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", p=50)

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_measure_level_p_is_validated_independently(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region",
        measures=[AggregateMeasure(agg="percentile", field="pop", label="p90")],
    )

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "measures[0].p"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "distinct or median or percentile or stddev or _p_on_" -v`

Expected: FAIL. `test_percentile_uses_p_as_a_percentage` échoue au
`AggregateRequestBody(... p=90)` (champ inconnu ignoré par Pydantic, puis
`unknown agg 'percentile'` levé par `_agg_expr`) ; les autres échouent sur
`UnknownAggregateField: unknown agg '…'`.

- [ ] **Step 3: Add `p` to the two Pydantic models**

Dans `core/app/analytics/aggregate.py`, remplacer les deux classes :

```python
class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None
    # Centile demandé, en POURCENTAGE (0 < p < 100), pas en fraction.
    # Obligatoire pour agg="percentile", refusé pour tout autre agg
    # (_validate_p ci-dessous). La division par 100 se fait dans _agg_expr.
    p: float | None = None


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
    bucket: Literal["day", "week", "month"] | None = None
    bins: int | None = None
```

- [ ] **Step 4: Extend `_agg_expr`**

Remplacer entièrement la fonction `_agg_expr` :

```python
def _agg_expr(agg: str, field: str | None, p: float | None = None) -> str:
    if agg == "count":
        return "COUNT(*)"
    if field is None:
        raise UnknownAggregateField("field", f"agg '{agg}' requires a field")
    if agg == "countDistinct":
        # Pas de TRY_CAST ici, contrairement aux agrégats numériques :
        # compter des valeurs textuelles distinctes est légitime, et un cast
        # en DOUBLE les fusionnerait toutes sur NULL (donc 0 distinct).
        return f"COALESCE(COUNT(DISTINCT {_qi(field)}), 0)"
    col = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    if agg == "sum":
        return f"COALESCE(SUM({col}), 0)"
    if agg == "avg":
        return f"COALESCE(AVG({col}), 0)"
    if agg == "min":
        return f"COALESCE(MIN({col}), 0)"
    if agg == "max":
        return f"COALESCE(MAX({col}), 0)"
    # Indéfini n'est PAS zéro : pas de COALESCE sur les trois suivants
    # (design §3.1). La médiane d'un ensemble vide et l'écart-type d'une
    # ligne unique n'existent pas ; renvoyer 0 produirait un graphique faux
    # plutôt qu'un trou.
    if agg == "median":
        return f"QUANTILE_CONT({col}, 0.5)"
    if agg == "percentile":
        # _validate_p a déjà garanti la présence et les bornes de p
        # (appelé par _validate_fields, avant tout appel à _agg_expr).
        assert p is not None
        return f"QUANTILE_CONT({col}, {p / 100.0!r})"
    if agg == "stddev":
        # SAMP (n-1) et non POP : parité visée avec le statisticType
        # "stddev" d'ArcGIS (cf. spec §3.1, parité affirmée non mesurée).
        return f"STDDEV_SAMP({col})"
    raise UnknownAggregateField("agg", f"unknown agg '{agg}'")
```

- [ ] **Step 5: Validate `p`**

Ajouter, juste au-dessus de `_validate_fields` :

```python
def _validate_p(agg: str, p: float | None, label: str) -> None:
    if agg == "percentile":
        if p is None:
            raise UnknownAggregateField(label, "agg 'percentile' requires p")
        if not (0 < p < 100):
            raise UnknownAggregateField(label, "p must be strictly between 0 and 100")
    elif p is not None:
        raise UnknownAggregateField(label, f"agg '{agg}' does not accept p")
```

Puis, dans `_validate_fields`, remplacer la boucle sur les mesures :

```python
    check(request.split, "split")
    check(request.field, "field")
    # request.agg/request.field/request.p restent utilisés même quand
    # `measures` est renseigné : le chemin `split` de
    # run_collection_aggregate les lit directement. Les deux niveaux se
    # valident donc toujours, pas l'un ou l'autre.
    _validate_p(request.agg, request.p, "p")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
        _validate_p(m.agg, m.p, f"measures[{i}].p")
```

- [ ] **Step 6: Thread `p` through the four call sites**

Dans `_measures_for` :

```python
def _measures_for(request: AggregateRequestBody) -> list[AggregateMeasure]:
    if request.measures:
        return request.measures
    return [
        AggregateMeasure(field=request.field, agg=request.agg, label="value", p=request.p)
    ]
```

Dans `run_collection_aggregate`, les trois appels à `_agg_expr` deviennent :

```python
        measure_cols = ", ".join(
            f"{_agg_expr(m.agg, m.field, m.p)} AS m{i}" for i, m in enumerate(measures)
        )
```

(branche `len(fields) > 1`),

```python
        agg_sql = _agg_expr(request.agg, request.field, request.p)
```

(branche `request.split`), et

```python
    measure_cols = ", ".join(
        f"{_agg_expr(m.agg, m.field, m.p)} AS m{i}" for i, m in enumerate(measures)
    )
```

(branche finale).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`

Expected: PASS, tous les tests du fichier (anciens compris).

- [ ] **Step 8: Run the full core suite**

Run: `cd core && uv run pytest -q`

Expected: au moins 1653 passed, 0 failed.

- [ ] **Step 9: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): ajoute countDistinct, median, percentile et stddev aux agrégats"
```

---

### Task 2: Six grains temporels

**Files:**
- Modify: `core/app/analytics/aggregate.py:40` (le `Literal` de `bucket`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: Task 1 (même fichier).
- Produces: `AggregateRequestBody.bucket` accepte
  `"hour" | "day" | "week" | "month" | "quarter" | "year"`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `core/tests/test_analytics_aggregate.py` :

```python
def test_bucket_groups_rows_by_year(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025-03-05", 10, lsn=1),
            _row(2, "Nord", "2025-11-20", 3, lsn=1),
            _row(3, "Nord", "2026-01-06", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="year", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2025-01-01 00:00:00", "value": 2},
        {"annee": "2026-01-01 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_quarter(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05", 10, lsn=1),
            _row(2, "Nord", "2026-02-20", 3, lsn=1),
            _row(3, "Nord", "2026-05-06", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="quarter", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-01 00:00:00", "value": 2},
        {"annee": "2026-04-01 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_hour(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05 08:10:00", 10, lsn=1),
            _row(2, "Nord", "2026-01-05 08:55:00", 3, lsn=1),
            _row(3, "Nord", "2026-01-05 09:01:00", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="hour", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 08:00:00", "value": 2},
        {"annee": "2026-01-05 09:00:00", "value": 1},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "by_year or by_quarter or by_hour" -v`

Expected: FAIL — `pydantic_core.ValidationError` sur `bucket`, « Input should
be 'day', 'week' or 'month' ».

- [ ] **Step 3: Widen the literal**

Dans `core/app/analytics/aggregate.py`, remplacer la ligne du champ `bucket`
de `AggregateRequestBody` :

```python
    bucket: Literal["hour", "day", "week", "month", "quarter", "year"] | None = None
```

Aucun autre changement : `DATE_TRUNC` accepte les six unités telles quelles.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): ajoute les grains temporels hour, quarter et year"
```

---

### Task 3: `stddev` sur le chemin ArcGIS

**Files:**
- Modify: `core/app/harvest/live_query.py:17`
- Test: `core/tests/test_harvest_live_query.py`

**Interfaces:**
- Consumes: rien (chemin indépendant de Task 1).
- Produces: `_STAT_TYPES` = `{"count", "sum", "avg", "min", "max", "stddev"}`.
  `countDistinct`, `median` et `percentile` continuent de lever
  `ArcgisQueryError("agg", …)`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `core/tests/test_harvest_live_query.py` :

```python
def test_stddev_is_translated_to_the_native_arcgis_statistic_type():
    params = translate_aggregate_query(
        group_by=["region"],
        measures=[("stddev", "pop", "ecart")],
        filters={},
        bbox=None,
    )

    assert json.loads(params["outStatistics"]) == [
        {"statisticType": "stddev", "onStatisticField": "pop", "outStatisticFieldName": "m0"}
    ]


@pytest.mark.parametrize("agg", ["countDistinct", "median", "percentile"])
def test_aggregates_without_an_arcgis_equivalent_are_refused(agg):
    with pytest.raises(ArcgisQueryError) as exc:
        translate_aggregate_query(
            group_by=["region"],
            measures=[(agg, "pop", "x")],
            filters={},
            bbox=None,
        )

    assert exc.value.field == "agg"
```

Vérifier que `json`, `pytest`, `translate_aggregate_query` et
`ArcgisQueryError` sont bien importés en tête du fichier ; ajouter les
imports manquants.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -k "stddev or without_an_arcgis" -v`

Expected: le test `stddev` FAIL (`ArcgisQueryError: unknown agg 'stddev'`) ;
les trois paramétrés PASSENT déjà (comportement existant qu'on verrouille).

- [ ] **Step 3: Add `stddev` to the allowed statistic types**

Dans `core/app/harvest/live_query.py`, remplacer la ligne 17 :

```python
# "stddev" est un statisticType natif du Feature Service ArcGIS. Les autres
# agrégats de SP-23 (countDistinct, median, percentile) n'ont pas
# d'équivalent : ils restent refusés ici plutôt que mal-traduits — précédent
# SP-16b, échouer explicitement plutôt que mal-évaluer en silence.
_STAT_TYPES = {"count", "sum", "avg", "min", "max", "stddev"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/live_query.py core/tests/test_harvest_live_query.py
git commit -m "feat(core): accepte stddev sur le chemin arcgis, refuse les trois autres"
```

---

### Task 4: Régénération OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: Tasks 1 et 2 (le schéma de `AggregateRequestBody` a changé :
  champ `p` ajouté, `bucket` élargi).
- Produces: la CI `api-types-drift` reste verte.

> **Pourquoi une tâche à part** : l'oubli de régénération est la classe de
> défaut la plus récurrente de ce dépôt (5 occurrences recensées). Ici le
> diff n'est **pas** vide, contrairement au cas `CORE_ETL_ENABLED` :
> `AggregateRequestBody` est le corps de quatre routes montées
> inconditionnellement.

- [ ] **Step 1: Regenerate the OpenAPI spec**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`

- [ ] **Step 2: Verify the diff is non-empty and expected**

Run: `git diff --stat core/openapi.json`

Expected: `core/openapi.json` modifié. Vérifier dans `git diff core/openapi.json`
que le schéma `AggregateRequestBody` porte bien un champ `p` et un `bucket`
à six valeurs, et que **rien d'autre** n'a bougé.

- [ ] **Step 3: Regenerate the TypeScript types**

Run: `cd shell && npm run gen:api-types`

- [ ] **Step 4: Verify the shell still builds**

Run: `cd shell && npm run build`

Expected: succès (`tsc --noEmit` puis `vite build`).

- [ ] **Step 5: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore: régénère la spec openapi et les types ts après les agrégats sp23"
```

---

## Lot B — Shell : chemin analytique

### Task 5: Module partagé des agrégats + `DataSourcePanel`

**Files:**
- Create: `shell/src/builder/aggregates.ts`
- Modify: `shell/src/builder/DataSourcePanel.tsx`
- Test: `shell/src/builder/DataSourcePanel.test.tsx`

**Interfaces:**
- Consumes: Task 1 (les 4 noms d'agrégat, le champ `p`).
- Produces: `ANALYTICS_AGGREGATES: { value: string; label: string }[]` et
  `aggregateNeedsP(agg: string): boolean`, exportés depuis
  `shell/src/builder/aggregates.ts`.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/DataSourcePanel.test.tsx` (si le fichier
n'existe pas, le créer en copiant les imports et le rendu d'un test existant
du même dossier) :

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { DataSourcePanel } from "./DataSourcePanel";
import type { DataSource } from "../api/types";

const STATS_SOURCE: DataSource = {
  id: "s1",
  type: "statistics",
  service: "core",
  layer: "villes",
  query: { groupBy: "region", agg: "count" },
};

test("propose les neuf agrégats analytiques", () => {
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={() => {}} />);

  const select = screen.getByLabelText("Agrégation (source s1)");
  const values = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(values).toEqual([
    "count",
    "countDistinct",
    "sum",
    "avg",
    "median",
    "percentile",
    "stddev",
    "min",
    "max",
  ]);
});

test("le champ centile n'apparaît que pour percentile et se patche en pourcentage", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={onChange} />);

  expect(screen.queryByLabelText("Centile (source s1)")).toBeNull();

  await userEvent.selectOptions(screen.getByLabelText("Agrégation (source s1)"), "percentile");
  expect(onChange).toHaveBeenCalledWith([
    { ...STATS_SOURCE, query: { groupBy: "region", agg: "percentile" } },
  ]);
});

test("affiche le champ centile quand la source est déjà en percentile", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "percentile", p: 90 },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);

  const p = screen.getByLabelText("Centile (source s1)");
  expect((p as HTMLInputElement).value).toBe("90");

  await userEvent.clear(p);
  await userEvent.type(p, "95");
  expect(onChange).toHaveBeenLastCalledWith([
    { ...source, query: { groupBy: "region", agg: "percentile", p: 95 } },
  ]);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`

Expected: FAIL — la liste d'options ne contient que les cinq agrégats
existants et `Centile (source s1)` n'existe pas.

- [ ] **Step 3: Create the shared module**

Créer `shell/src/builder/aggregates.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// Source unique des agrégats du chemin analytique (AggregateRequestBody,
// core/app/analytics/aggregate.py). Les deux <select> de DataSourcePanel
// (requête simple et mesures) lisent cette liste au lieu de la dupliquer.
// L'ordre est celui affiché à l'auteur : du plus courant au plus rare.
export const ANALYTICS_AGGREGATES: { value: string; label: string }[] = [
  { value: "count", label: "Nombre" },
  { value: "countDistinct", label: "Nombre de valeurs distinctes" },
  { value: "sum", label: "Somme" },
  { value: "avg", label: "Moyenne" },
  { value: "median", label: "Médiane" },
  { value: "percentile", label: "Centile" },
  { value: "stddev", label: "Écart-type" },
  { value: "min", label: "Min" },
  { value: "max", label: "Max" },
];

// Seul "percentile" porte un paramètre. Il est exprimé en POURCENTAGE
// (0 < p < 100), jamais en fraction — le serveur divise par 100 lui-même.
export function aggregateNeedsP(agg: string): boolean {
  return agg === "percentile";
}
```

- [ ] **Step 4: Wire the two selects and the `p` field**

Dans `shell/src/builder/DataSourcePanel.tsx` :

1. Ajouter l'import en tête :

```ts
import { ANALYTICS_AGGREGATES, aggregateNeedsP } from "./aggregates";
```

2. Remplacer les cinq `<option>` du `<select>` `Agrégation (source …)` par :

```tsx
                    {ANALYTICS_AGGREGATES.map((a) => (
                      <option key={a.value} value={a.value}>
                        {a.label}
                      </option>
                    ))}
```

3. Juste après le champ `Champ agrégé (source ${s.id})`, ajouter le champ
   centile conditionnel :

```tsx
                  {aggregateNeedsP(String(s.query.agg ?? "count")) && (
                    <input
                      aria-label={`Centile (source ${s.id})`}
                      type="number"
                      min={1}
                      max={99}
                      placeholder="centile (1–99)"
                      className={inputCls}
                      value={String(s.query.p ?? "")}
                      onChange={(e) =>
                        patchQuery(s.id, {
                          p: e.target.value ? Number(e.target.value) : undefined,
                        })
                      }
                    />
                  )}
```

4. Remplacer les cinq `<option>` du `<select>` `Agrégation mesure … (source …)`
   par la même boucle qu'en (2), et ajouter après le champ
   `Champ mesure ${mi + 1} (source ${s.id})` :

```tsx
                        {aggregateNeedsP(m.agg) && (
                          <input
                            aria-label={`Centile mesure ${mi + 1} (source ${s.id})`}
                            type="number"
                            min={1}
                            max={99}
                            placeholder="centile"
                            className={inputCls}
                            value={String(m.p ?? "")}
                            onChange={(e) =>
                              setMeasures(
                                s,
                                measuresOf(s).map((x, i) =>
                                  i === mi
                                    ? {
                                        ...x,
                                        p: e.target.value ? Number(e.target.value) : undefined,
                                      }
                                    : x,
                                ),
                              )
                            }
                          />
                        )}
```

5. Élargir le type local `Measure` en tête du fichier :

```ts
type Measure = { field?: string; agg: string; label?: string; p?: number };
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/aggregates.ts shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx
git commit -m "feat(shell): expose les neuf agrégats et le centile dans le panneau de source"
```

---

### Task 6: Sélecteur de grain temporel

**Files:**
- Modify: `shell/src/lib/comparisonWindow.ts:7`,
  `shell/src/builder/widgets/chartOption.ts:330-333`,
  `shell/src/builder/DataSourcePanel.tsx`
- Test: `shell/src/builder/DataSourcePanel.test.tsx`,
  `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Consumes: Task 2 (les six grains côté serveur), Task 5 (le fichier
  `DataSourcePanel.tsx` déjà modifié).
- Produces: `BucketGranularity` = les six valeurs ; le contrôle
  `Grain temporel (source ${id})` dans `DataSourcePanel`.

> `bucketFor()` **n'est pas modifié** : c'est l'heuristique de la fenêtre de
> comparaison, pas un choix d'auteur (décision 8 de la spec). Seul son type
> de retour s'élargit, pour que `BucketGranularity` reste le seul nom du
> concept côté shell.

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/builder/DataSourcePanel.test.tsx` :

```tsx
test("propose les six grains temporels, plus l'absence de grain", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={onChange} />);

  const select = screen.getByLabelText("Grain temporel (source s1)");
  const values = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(values).toEqual(["", "hour", "day", "week", "month", "quarter", "year"]);

  await userEvent.selectOptions(select, "year");
  expect(onChange).toHaveBeenCalledWith([
    { ...STATS_SOURCE, query: { groupBy: "region", agg: "count", bucket: "year" } },
  ]);
});

test("le grain temporel est désactivé sans groupBy à un seul champ", () => {
  const multi: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: ["region", "annee"], agg: "count" },
  };
  render(<DataSourcePanel sources={[multi]} onChange={() => {}} />);

  expect(screen.getByLabelText("Grain temporel (source s1)")).toBeDisabled();
});
```

Ajouter à `shell/src/builder/widgets/chartOption.test.ts` :

```ts
test("étiquette les périodes de comparaison pour les six grains", () => {
  const props = { chartType: "line" } as Parameters<typeof buildCompareOption>[0];
  const points = [{ bucket: "a", value: 1 }];
  const labelFor = (bucket: Parameters<typeof buildCompareOption>[3]) =>
    (buildCompareOption(props, points, points, bucket).xAxis as { data: string[] }).data[0];

  expect(labelFor("hour")).toBe("Heure 1");
  expect(labelFor("day")).toBe("Jour 1");
  expect(labelFor("week")).toBe("Semaine 1");
  expect(labelFor("month")).toBe("Mois 1");
  expect(labelFor("quarter")).toBe("Trimestre 1");
  expect(labelFor("year")).toBe("Année 1");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx src/builder/widgets/chartOption.test.ts`

Expected: FAIL — `Grain temporel (source s1)` introuvable ; `labelFor("quarter")`
renvoie `"Mois 1"` (repli actuel) et `"hour"`/`"year"` ne compilent pas
(`BucketGranularity` ne les contient pas).

- [ ] **Step 3: Widen `BucketGranularity`**

Dans `shell/src/lib/comparisonWindow.ts`, remplacer la ligne 7 :

```ts
// Les six grains acceptés par AggregateRequestBody.bucket côté cœur
// (core/app/analytics/aggregate.py). bucketFor() ci-dessous n'en produit
// toujours que trois : c'est une heuristique de fenêtre de comparaison, pas
// un choix d'auteur, et l'élargir changerait le rendu de widgets déjà
// livrés (spec SP-23 §3.2, décision 8).
export type BucketGranularity = "hour" | "day" | "week" | "month" | "quarter" | "year";
```

- [ ] **Step 4: Complete `offsetLabel`**

Dans `shell/src/builder/widgets/chartOption.ts`, remplacer `offsetLabel` :

```ts
const BUCKET_UNIT_LABELS: Record<BucketGranularity, string> = {
  hour: "Heure",
  day: "Jour",
  week: "Semaine",
  month: "Mois",
  quarter: "Trimestre",
  year: "Année",
};

function offsetLabel(bucket: BucketGranularity, index: number): string {
  return `${BUCKET_UNIT_LABELS[bucket]} ${index + 1}`;
}
```

- [ ] **Step 5: Add the bucket control**

Dans `shell/src/builder/DataSourcePanel.tsx`, ajouter en tête du fichier :

```ts
import type { BucketGranularity } from "../lib/comparisonWindow";

const BUCKET_OPTIONS: { value: BucketGranularity; label: string }[] = [
  { value: "hour", label: "Heure" },
  { value: "day", label: "Jour" },
  { value: "week", label: "Semaine" },
  { value: "month", label: "Mois" },
  { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Année" },
];

// Le cœur refuse un bucket sans groupBy à un seul champ
// (_validate_fields: "bucket requires a single-field groupBy"). L'UI
// reflète cet invariant au lieu de laisser construire une requête que le
// serveur rejettera.
function bucketAllowed(groupBy: unknown): boolean {
  if (Array.isArray(groupBy)) return groupBy.length === 1;
  return typeof groupBy === "string" && groupBy.trim() !== "";
}
```

Puis, juste après le champ `Séparer par (source ${s.id})` :

```tsx
                <select
                  aria-label={`Grain temporel (source ${s.id})`}
                  className={selectCls}
                  disabled={!bucketAllowed(s.query.groupBy)}
                  value={String(s.query.bucket ?? "")}
                  onChange={(e) => patchQuery(s.id, { bucket: e.target.value || undefined })}
                >
                  <option value="">Aucun grain temporel</option>
                  {BUCKET_OPTIONS.map((b) => (
                    <option key={b.value} value={b.value}>
                      {b.label}
                    </option>
                  ))}
                </select>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx src/builder/widgets/chartOption.test.ts`

Expected: PASS.

- [ ] **Step 7: Run the full shell suite**

Run: `cd shell && npm run test`

Expected: 0 failed.

- [ ] **Step 8: Commit**

```bash
git add shell/src/lib/comparisonWindow.ts shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx
git commit -m "feat(shell): ajoute le sélecteur de grain temporel et les six unités de comparaison"
```

---

### Task 7: Rendu d'une valeur indéfinie dans l'indicateur

**Files:**
- Modify: `shell/src/builder/widgets/indicator.tsx`
- Test: `shell/src/builder/widgets/indicator.test.tsx`

**Interfaces:**
- Consumes: Task 1 (le serveur peut désormais renvoyer `value: null`).
- Produces: l'indicateur affiche `—` au lieu de `0` pour une valeur nulle.

> **Limite explicitement acceptée** : `num()` de `chartOption.ts` continue de
> convertir `null` en `0` pour les séries ECharts. Changer cela toucherait
> les onze types de graphique (dont boxplot/radar/sankey, qui n'acceptent pas
> `null`) pour un gain cosmétique sur un cas étroit — un groupe d'une seule
> ligne en `stddev`. À reconsidérer si le cas devient courant. Cette limite
> est reportée dans `### Suivis non bloquants ouverts` en Task 18.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/widgets/indicator.test.tsx` un test qui rend le
widget avec une source `statistics` dont l'unique enregistrement porte
`properties: { value: null }`, en réutilisant le harnais de rendu déjà
présent dans ce fichier (mêmes providers, même façon de fournir les données
que les tests existants du même fichier — **lire les tests voisins et copier
leur mise en place, ne pas en inventer une**) :

```tsx
test("affiche — plutôt que 0 quand l'agrégat est indéfini", async () => {
  // … même mise en place que le test voisin qui rend une valeur numérique,
  // avec records = [{ properties: { value: null } }]
  expect(await screen.findByText("—")).toBeInTheDocument();
  expect(screen.queryByText("0")).toBeNull();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx -t "indéfini"`

Expected: FAIL — le widget affiche `0`.

- [ ] **Step 3: Format the displayed value**

Dans `shell/src/builder/widgets/indicator.tsx`, ajouter au-dessus du
composant :

```ts
// Un agrégat indéfini (médiane d'un ensemble vide, écart-type d'une ligne
// unique) vaut null côté serveur depuis SP-23, pas 0 : l'afficher « 0 »
// mentirait sur la donnée.
function displayValue(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : String(value);
}
```

Puis remplacer `{value}` par `{displayValue(value)}` dans le `<span>` de la
valeur, et rendre le calcul de `flatValue` tolérant :

```ts
      const rawValue = data.records[0]?.properties.value;
      const flatValue =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      const value =
        comparison.active && referencePeriod && comparison.value !== null
          ? comparison.value
          : rawValue === null
            ? null
            : flatValue;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx`

Expected: PASS, y compris les tests existants du fichier.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx
git commit -m "fix(shell): affiche un tiret plutôt que zéro pour un agrégat indéfini"
```

---

## Lot C — Assistant de requête visuelle

### Task 8: `MetricFunction` et inférence de type

**Files:**
- Modify: `shell/src/builder/visualQuery/inferSchema.ts:5-6,45-53`
- Test: `shell/src/builder/visualQuery/inferSchema.test.ts`

**Interfaces:**
- Consumes: rien.
- Produces: `MetricFunction = "count" | "countDistinct" | "sum" | "avg" | "median" | "percentile" | "stddev" | "min" | "max"` ;
  `MetricConfig = { alias: string; function: MetricFunction; sourceColumn: string | null; p: number | null }`.

> `MetricConfig.p` est **non optionnel et nullable** (`p: number | null`),
> comme `sourceColumn` juste à côté : TypeScript force alors chaque site de
> construction à décider explicitement, plutôt que de laisser un `undefined`
> se propager en silence dans le SQL compilé.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/visualQuery/inferSchema.test.ts` :

```ts
test("infère le type de sortie des quatre nouvelles fonctions", () => {
  const schema: CollectionSchema = {
    fields: [
      { name: "region", type: "string", required: true },
      { name: "pop", type: "integer", required: true },
    ],
  } as CollectionSchema;

  const result = inferOutputColumns(schema, null, null, {
    groupBy: ["region"],
    metrics: [
      { alias: "nb_distinct", function: "countDistinct", sourceColumn: "region", p: null },
      { alias: "med", function: "median", sourceColumn: "pop", p: null },
      { alias: "p90", function: "percentile", sourceColumn: "pop", p: 90 },
      { alias: "ecart", function: "stddev", sourceColumn: "pop", p: null },
    ],
  });

  expect(result.columns).toEqual([
    { name: "region", sqlType: "text" },
    { name: "nb_distinct", sqlType: "integer" },
    { name: "med", sqlType: "double precision" },
    { name: "p90", sqlType: "double precision" },
    { name: "ecart", sqlType: "double precision" },
  ]);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/visualQuery/inferSchema.test.ts -t "quatre nouvelles"`

Expected: FAIL — erreur de type sur `"countDistinct"` (absent de
`MetricFunction`) et sur `p` (absent de `MetricConfig`).

- [ ] **Step 3: Widen the types and the inference**

Dans `shell/src/builder/visualQuery/inferSchema.ts`, remplacer les lignes 5-6 :

```ts
export type MetricFunction =
  | "count"
  | "countDistinct"
  | "sum"
  | "avg"
  | "median"
  | "percentile"
  | "stddev"
  | "min"
  | "max";
// `p` est le centile demandé, en POURCENTAGE (0 < p < 100), et n'a de sens
// que pour function === "percentile". Nullable et non optionnel, comme
// sourceColumn : chaque site de construction doit trancher explicitement.
export type MetricConfig = {
  alias: string;
  function: MetricFunction;
  sourceColumn: string | null;
  p: number | null;
};
```

Puis remplacer le calcul de `sqlType` de la boucle sur les métriques :

```ts
    for (const metric of summary.metrics) {
      const sqlType =
        metric.function === "count" || metric.function === "countDistinct"
          ? "integer"
          : metric.function === "sum" ||
              metric.function === "avg" ||
              metric.function === "median" ||
              metric.function === "percentile" ||
              metric.function === "stddev"
            ? "double precision"
            : sqlTypeOf(base, metric.sourceColumn ?? "");
      columns.push({ name: metric.alias, sqlType });
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/visualQuery/inferSchema.test.ts`

Expected: PASS. Les autres fichiers du dossier ne compilent plus (les
`MetricConfig` littéraux n'ont pas de `p`) — c'est attendu, Task 9 et
Task 10 les réparent.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/inferSchema.ts shell/src/builder/visualQuery/inferSchema.test.ts
git commit -m "feat(shell): élargit MetricFunction aux quatre nouveaux agrégats"
```

---

### Task 9: Compilation et décompilation SQL des métriques

**Files:**
- Modify: `shell/src/builder/visualQuery/compilePipeline.ts:27-30,132-148`
- Test: `shell/src/builder/visualQuery/compilePipeline.test.ts`

**Interfaces:**
- Consumes: Task 8 (`MetricFunction`, `MetricConfig.p`).
- Produces: `metricExpr` et `decompileMetrics` réciproques sur les neuf
  fonctions. Formes SQL exactes, à respecter **au caractère près** des deux
  côtés :

| function | SQL produit |
|---|---|
| `count` | `count(*)` |
| `countDistinct` | `count(distinct "col")` |
| `sum` / `avg` / `min` / `max` | `sum("col")`, … |
| `median` | `median("col")` |
| `percentile` | `quantile_cont("col", 0.9)` |
| `stddev` | `stddev_samp("col")` |

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/visualQuery/compilePipeline.test.ts` :

```ts
test("compile puis décompile les neuf fonctions sans perte", () => {
  const metrics: MetricConfig[] = [
    { alias: "nb", function: "count", sourceColumn: null, p: null },
    { alias: "nbd", function: "countDistinct", sourceColumn: "region", p: null },
    { alias: "tot", function: "sum", sourceColumn: "pop", p: null },
    { alias: "moy", function: "avg", sourceColumn: "pop", p: null },
    { alias: "med", function: "median", sourceColumn: "pop", p: null },
    { alias: "p90", function: "percentile", sourceColumn: "pop", p: 90 },
    { alias: "sd", function: "stddev", sourceColumn: "pop", p: null },
    { alias: "mn", function: "min", sourceColumn: "pop", p: null },
    { alias: "mx", function: "max", sourceColumn: "pop", p: null },
  ];

  const compiled = Object.fromEntries(metrics.map((m) => [m.alias, metricExpr(m)]));

  expect(compiled).toEqual({
    nb: "count(*)",
    nbd: 'count(distinct "region")',
    tot: 'sum("pop")',
    moy: 'avg("pop")',
    med: 'median("pop")',
    p90: 'quantile_cont("pop", 0.9)',
    sd: 'stddev_samp("pop")',
    mn: 'min("pop")',
    mx: 'max("pop")',
  });

  expect(decompileMetrics(compiled)).toEqual(metrics);
});

test("décompile un centile non entier", () => {
  expect(decompileMetrics({ p995: 'quantile_cont("pop", 0.995)' })).toEqual([
    { alias: "p995", function: "percentile", sourceColumn: "pop", p: 99.5 },
  ]);
});

test("refuse une forme SQL non produite par metricExpr", () => {
  expect(decompileMetrics({ x: 'variance("pop")' })).toBeNull();
});
```

`metricExpr` et `decompileMetrics` doivent être exportés pour ce test —
ajouter `export` devant les deux dans `compilePipeline.ts` s'il n'y est pas,
et importer `MetricConfig` depuis `./inferSchema` dans le fichier de test.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/visualQuery/compilePipeline.test.ts -t "neuf fonctions"`

Expected: FAIL — `metricExpr` produit `countDistinct("region")` (concaténation
naïve du nom de fonction) et `decompileMetrics` renvoie `null`.

- [ ] **Step 3: Extend `metricExpr`**

Dans `shell/src/builder/visualQuery/compilePipeline.ts`, remplacer
`metricExpr` :

```ts
// Les formes produites ici sont le contrat que decompileMetrics doit savoir
// relire au caractère près : c'est ce round-trip qui permet de rouvrir une
// requête visuelle (« Modifier la requête »). Toute divergence fait
// silencieusement retomber l'auteur sur PipelineBuilderPage.
export function metricExpr(metric: MetricConfig): string {
  if (metric.function === "count") return "count(*)";
  const col = quoteIdent(metric.sourceColumn!);
  if (metric.function === "countDistinct") return `count(distinct ${col})`;
  if (metric.function === "stddev") return `stddev_samp(${col})`;
  if (metric.function === "percentile") return `quantile_cont(${col}, ${metric.p! / 100})`;
  return `${metric.function}(${col})`;
}
```

- [ ] **Step 4: Extend `decompileMetrics`**

Remplacer `decompileMetrics` :

```ts
const SIMPLE_FN_RE = /^(sum|avg|min|max|median|stddev_samp)\("((?:[^"]|"")+)"\)$/;
const COUNT_DISTINCT_RE = /^count\(distinct "((?:[^"]|"")+)"\)$/;
const QUANTILE_RE = /^quantile_cont\("((?:[^"]|"")+)", (\d+(?:\.\d+)?)\)$/;

const SIMPLE_FN_TO_METRIC: Record<string, MetricFunction> = {
  sum: "sum",
  avg: "avg",
  min: "min",
  max: "max",
  median: "median",
  stddev_samp: "stddev",
};

export function decompileMetrics(metrics: Record<string, string>): MetricConfig[] | null {
  const result: MetricConfig[] = [];
  for (const [alias, expr] of Object.entries(metrics)) {
    if (expr === "count(*)") {
      result.push({ alias, function: "count", sourceColumn: null, p: null });
      continue;
    }
    const distinct = COUNT_DISTINCT_RE.exec(expr);
    if (distinct) {
      result.push({
        alias,
        function: "countDistinct",
        sourceColumn: distinct[1].replace(/""/g, '"'),
        p: null,
      });
      continue;
    }
    const quantile = QUANTILE_RE.exec(expr);
    if (quantile) {
      result.push({
        alias,
        function: "percentile",
        sourceColumn: quantile[1].replace(/""/g, '"'),
        // Le SQL porte une fraction, l'état de l'assistant un pourcentage.
        // Arrondi à 4 décimales : 0.995 * 100 vaut 99.50000000000001 en
        // flottant IEEE-754, ce qui casserait l'égalité du round-trip.
        p: Math.round(Number(quantile[2]) * 100 * 1e4) / 1e4,
      });
      continue;
    }
    const simple = SIMPLE_FN_RE.exec(expr);
    if (!simple) return null;
    result.push({
      alias,
      function: SIMPLE_FN_TO_METRIC[simple[1]],
      sourceColumn: simple[2].replace(/""/g, '"'),
      p: null,
    });
  }
  return result;
}
```

Importer `MetricFunction` depuis `./inferSchema` en tête du fichier si ce
n'est pas déjà le cas.

- [ ] **Step 5: Fix the existing literals**

Les `MetricConfig` littéraux des tests existants de
`compilePipeline.test.ts` n'ont pas de `p` et ne compilent plus. Ajouter
`p: null` à chacun (`git grep -n "function: \"" shell/src/builder/visualQuery/`
les liste tous).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/visualQuery/`

Expected: PASS sur tout le dossier.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/visualQuery/compilePipeline.ts shell/src/builder/visualQuery/compilePipeline.test.ts
git commit -m "feat(shell): compile et décompile les quatre nouveaux agrégats de requête visuelle"
```

---

### Task 10: UI de l'assistant — fonctions et centile

**Files:**
- Modify: `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`
- Test: `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx`

**Interfaces:**
- Consumes: Tasks 8 et 9.
- Produces: le `<select>` de fonction propose les neuf ; un champ
  `Centile de la métrique ${i + 1}` apparaît pour `percentile`.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx` (en
copiant la mise en place — `schema`, `value`, `onChange` — d'un test voisin
du même fichier) :

```tsx
test("propose les neuf fonctions et un champ centile pour percentile", async () => {
  const onChange = vi.fn();
  render(
    <QuerySummaryBuilder
      schema={SCHEMA}
      value={{
        groupBy: [],
        metrics: [{ alias: "m1", function: "count", sourceColumn: null, p: null }],
      }}
      onChange={onChange}
    />,
  );

  const select = screen.getByLabelText("Fonction de la métrique 1");
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toEqual([
    "count",
    "countDistinct",
    "sum",
    "avg",
    "median",
    "percentile",
    "stddev",
    "min",
    "max",
  ]);
  expect(screen.queryByLabelText("Centile de la métrique 1")).toBeNull();

  await userEvent.selectOptions(select, "percentile");
  expect(onChange).toHaveBeenCalledWith({
    groupBy: [],
    metrics: [
      { alias: "m1", function: "percentile", sourceColumn: expect.any(String), p: 50 },
    ],
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/visualQuery/QuerySummaryBuilder.test.tsx -t "neuf fonctions"`

Expected: FAIL — cinq options seulement, et `p` absent du patch.

- [ ] **Step 3: Extend the component**

Dans `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx` :

1. Remplacer `FUNCTION_LABELS` (l'ordre des clés est celui du `<select>`) :

```ts
const FUNCTION_LABELS: Record<MetricFunction, string> = {
  count: "Compter",
  countDistinct: "Compter les valeurs distinctes",
  sum: "Somme",
  avg: "Moyenne",
  median: "Médiane",
  percentile: "Centile",
  stddev: "Écart-type",
  min: "Minimum",
  max: "Maximum",
};

// Centile par défaut quand l'auteur bascule sur "percentile" : la médiane,
// le seul choix qui ne surprend personne. Exprimé en pourcentage.
const DEFAULT_PERCENTILE = 50;
```

2. Dans `updateMetric`, gérer `p` en miroir de `sourceColumn` :

```ts
  function updateMetric(index: number, patch: Partial<MetricConfig>) {
    const metrics = value.metrics.map((m, i) => {
      if (i !== index) return m;
      const next = { ...m, ...patch };
      if (next.function === "count") next.sourceColumn = null;
      else if (next.sourceColumn === null) next.sourceColumn = firstNumericField(schema);
      if (next.function === "percentile") {
        if (next.p === null) next.p = DEFAULT_PERCENTILE;
      } else {
        next.p = null;
      }
      return next;
    });
    onChange({ ...value, metrics });
  }
```

3. Dans `addMetric`, ajouter `p: null` au littéral :

```ts
        { alias: `metrique_${value.metrics.length + 1}`, function: "count", sourceColumn: null, p: null },
```

4. Après le `<select>` de colonne, ajouter le champ centile :

```tsx
          {metric.function === "percentile" && (
            <input
              aria-label={`Centile de la métrique ${i + 1}`}
              type="number"
              min={1}
              max={99}
              className="h-8 w-20 rounded border border-slate-300 px-2 text-xs"
              value={metric.p ?? DEFAULT_PERCENTILE}
              onChange={(e) => updateMetric(i, { p: Number(e.target.value) })}
            />
          )}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/visualQuery/ src/pages/VisualQueryWizardPage.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/QuerySummaryBuilder.tsx shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx
git commit -m "feat(shell): expose les neuf fonctions et le centile dans l'assistant de requête"
```

---

## Lot D — Catalogue (4.6)

### Task 11: Libellés de type exhaustifs

**Files:**
- Create: `shell/src/api/resourceTypes.ts`, `shell/src/api/resourceTypes.test.ts`
- Modify: `shell/src/pages/CatalogPage.tsx:56-72`, `shell/src/ui/ItemCard.tsx:6-8`
- Test: `shell/src/pages/CatalogPage.test.tsx`

**Interfaces:**
- Consumes: rien.
- Produces: `RESOURCE_TYPE_LABELS: Record<ResourceType, string>` et
  `RESOURCE_TYPE_ORDER: ResourceType[]`, exportés depuis
  `shell/src/api/resourceTypes.ts`.

- [ ] **Step 1: Write the failing tests**

Créer `shell/src/api/resourceTypes.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "./resourceTypes";

// Le vrai garde-fou d'exhaustivité est le type `Record<ResourceType, string>`
// lui-même : ajouter une valeur à ResourceType sans son libellé casse la
// compilation. Ce test verrouille en plus que l'ordre d'affichage couvre
// exactement les mêmes clés — un oubli qui, lui, compilerait.
test("l'ordre d'affichage couvre exactement les types étiquetés", () => {
  expect([...RESOURCE_TYPE_ORDER].sort()).toEqual(Object.keys(RESOURCE_TYPE_LABELS).sort());
});

test("les douze types de ressource sont étiquetés", () => {
  expect(RESOURCE_TYPE_ORDER).toHaveLength(12);
});
```

Ajouter à `shell/src/pages/CatalogPage.test.tsx` :

```tsx
test("le filtre Type propose les douze types plus « Tous »", () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });

  const select = screen.getByLabelText("Type");
  expect(select.querySelectorAll("option")).toHaveLength(13);
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toContain("dataset");
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toContain("tileset3d");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/resourceTypes.test.ts src/pages/CatalogPage.test.tsx`

Expected: FAIL — module `./resourceTypes` introuvable ; le `<select>` n'a
que 4 options.

- [ ] **Step 3: Create the shared module**

Créer `shell/src/api/resourceTypes.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import type { ResourceType } from "./types";

// Source unique des libellés de type de ressource, lue par le filtre du
// catalogue (CatalogPage) ET par la pastille des cartes d'item (ItemCard).
//
// Le type est `Record<ResourceType, string>` et NON `Partial<Record<…>>` :
// c'est ce qui donne le critère de sortie du chantier 4.6 (« aucun type de
// ResourceType n'est absent du sélecteur »). Ajouter un 13e type à
// ResourceType casse la compilation tant qu'il n'a pas son libellé ici —
// même argument d'exhaustivité prouvée par le typage que StaticItemClient
// (SP-18a).
export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  app: "App",
  dashboard: "Dashboard",
  map: "Carte",
  site: "Site",
  dataset: "Dataset",
  bookmark: "Vue enregistrée",
  pipeline: "Pipeline",
  alert: "Alerte",
  report: "Rapport",
  tileset3d: "Tuiles 3D",
  terrain3d: "Terrain 3D",
  external: "Externe",
};

// Ordre d'affichage dans le filtre : les objets que l'on crée le plus
// souvent d'abord, les objets techniques et moissonnés ensuite.
export const RESOURCE_TYPE_ORDER: ResourceType[] = [
  "app",
  "dashboard",
  "map",
  "site",
  "dataset",
  "bookmark",
  "pipeline",
  "alert",
  "report",
  "tileset3d",
  "terrain3d",
  "external",
];
```

- [ ] **Step 4: Wire `CatalogPage`**

Dans `shell/src/pages/CatalogPage.tsx`, ajouter l'import :

```ts
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "../api/resourceTypes";
```

et remplacer les trois `<option>` en dur par :

```tsx
              <option value="">Tous</option>
              {RESOURCE_TYPE_ORDER.map((t) => (
                <option key={t} value={t}>
                  {RESOURCE_TYPE_LABELS[t]}
                </option>
              ))}
```

- [ ] **Step 5: Wire `ItemCard`**

Dans `shell/src/ui/ItemCard.tsx`, supprimer le `RESOURCE_TYPE_LABELS` local
(lignes 6-8) et importer le partagé :

```ts
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
```

Le rendu de la pastille devient (plus de repli `??`, le record est total) :

```tsx
          {RESOURCE_TYPE_LABELS[item.resourceType]}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/api/resourceTypes.test.ts src/pages/CatalogPage.test.tsx src/ui/`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/resourceTypes.ts shell/src/api/resourceTypes.test.ts shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx shell/src/ui/ItemCard.tsx
git commit -m "feat(shell): filtre le catalogue sur les douze types de ressource"
```

---

### Task 12: Destination des types `alert` et `external`

**Files:**
- Modify: `shell/src/shell/routes.tsx:42-83`
- Test: `shell/src/shell/routes.test.tsx` (créer le fichier s'il n'existe
  pas, sur le modèle d'un test de page voisin)

**Interfaces:**
- Consumes: Task 11 (les deux types sont désormais sélectionnables).
- Produces: `openItemAsync` route `external` vers `/items/{pk}` et `alert`
  vers `/datasets/{datasetItemId}/edit`.
- Requiert de `ItemClient` : `getAlertRuleConfig(pk)`, qui existe déjà
  (`shell/src/api/types.ts`) et renvoie un payload portant `datasetItemId`.

- [ ] **Step 1: Write the failing test**

Écrire un test qui rend le catalogue avec un item `alert` et un item
`external` et vérifie l'URL après clic sur « Ouvrir », en réutilisant le
harnais de rendu de `shell/src/pages/CatalogPage.test.tsx` (mêmes providers,
même `MemoryRouter`) :

```tsx
test("ouvrir une alerte mène à la page de son dataset", async () => {
  // item resourceType "alert", pk "al-1", getAlertRuleConfig renvoyant
  // { datasetItemId: "ds-7", … }
  await userEvent.click(screen.getByRole("button", { name: /ouvrir/i }));
  await waitFor(() => expect(location.pathname).toBe("/datasets/ds-7/edit"));
});

test("ouvrir un item externe mène à sa fiche", async () => {
  // item resourceType "external", pk "ex-1"
  await userEvent.click(screen.getByRole("button", { name: /ouvrir/i }));
  await waitFor(() => expect(location.pathname).toBe("/items/ex-1"));
});

test("une alerte dont la config est illisible affiche l'erreur d'ouverture", async () => {
  // getAlertRuleConfig rejette
  await userEvent.click(screen.getByRole("button", { name: /ouvrir/i }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`

Expected: FAIL — les deux premiers atterrissent sur `/apps/{pk}/edit`.

- [ ] **Step 3: Add the two branches**

Dans `shell/src/shell/routes.tsx`, à l'intérieur de `openItemAsync`, juste
après la branche `bookmark` :

```tsx
    if (type === "alert") {
      // Une règle d'alerte n'a pas d'écran propre : elle s'édite dans la
      // section « Alertes » de la page de son dataset. Même patron async
      // que `bookmark` ci-dessus, y compris le catch — l'appelant est un
      // `(pk, type) => void` fire-and-forget, une promesse rejetée y serait
      // une unhandled rejection sans retour utilisateur.
      try {
        const rule = await client.getAlertRuleConfig(pk);
        setOpenError(false);
        navigate(`/datasets/${encodeURIComponent(rule.datasetItemId)}/edit`);
      } catch {
        setOpenError(true);
      }
      return;
    }
    if (type === "external") {
      // Item moissonné : aucune config éditable, le repli générique
      // /apps/{pk}/edit ouvrirait le builder sur une config vide. Même
      // raison que tileset3d/terrain3d ci-dessous.
      navigate(`/items/${pk}`);
      return;
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/shell/`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx
git commit -m "feat(shell): route les items alerte et externe vers leur destination réelle"
```

---

## Lot E — Historique de versions (4.18)

### Task 13: Valider la config restaurée avant de l'écrire

**Files:**
- Modify: `core/app/configs/routes.py:214-241`
- Test: `core/tests/test_configs_rollback_validation.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: `POST /configs/{id}/rollback` répond **422** si la config
  restaurée ne passe pas les validateurs de payload, et n'écrit aucune
  version dans ce cas.

> **Pourquoi maintenant** : jusqu'ici rien dans le shell n'appelait cette
> route ; Task 16 la câble sur cinq éditeurs. Restaurer une vieille version
> d'un pipeline ou d'une alerte peut ressusciter une référence vers une
> collection supprimée depuis, ou réactiver une capacité éteinte.

- [ ] **Step 1: Write the failing test**

Créer `core/tests/test_configs_rollback_validation.py`. Réutiliser la
fixture de client de test et le patron d'authentification de
`core/tests/test_configs_models.py` (les lire et copier, ne pas en inventer
un). Le test :

1. crée une config `kind="alert"` valide, référençant un dataset existant ;
2. la met à jour vers une seconde version (également valide) ;
3. supprime l'item dataset référencé par la version 1 ;
4. `POST /configs/{id}/rollback` vers la version 1 → attend **422** ;
5. `GET /configs/{id}` → attend que `version` n'ait **pas** changé.

Plus un test de non-régression : un rollback vers une version restée valide
répond 200 et incrémente la version.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd core && uv run pytest tests/test_configs_rollback_validation.py -v`

Expected: FAIL — le rollback répond 200 et écrit une version invalide.

- [ ] **Step 3: Validate before rolling back**

Dans `core/app/configs/routes.py`, remplacer le corps de `rollback_config`
entre le `_require_access` et l'appel au repository :

```python
    _require_access(session, user=user, item_id=existing.itemId, action="write")

    # Le rollback écrit une nouvelle version comme le ferait un PUT, mais
    # sans repasser par aucun validateur de payload — un trou théorique tant
    # que rien n'appelait cette route, réel depuis que le panneau
    # « Historique » (SP-23) la câble sur les cinq éditeurs. Une vieille
    # version peut référencer une collection supprimée depuis, ou une
    # capacité éteinte depuis. On valide donc la config restaurée AVANT de
    # l'écrire, avec exactement la même séquence que update_config.
    candidate = repo.get_revision_config(session, config_id, request.version)
    if candidate is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    try:
        _require_etl_enabled_for_pipeline(candidate)
        _require_export_enabled_for_report(candidate)
        _validate_extension_scope(session, candidate, tenant_id=user.tenant_id)
        _validate_dataset_payload(session, candidate, user=user)
        _validate_bookmark_payload(session, candidate, user=user)
        _validate_pipeline_payload(session, candidate, user=user)
        _validate_alert_payload(session, candidate, user=user)
        _validate_report_payload(session, candidate, user=user)
        _validate_tileset3d_payload(session, candidate, user=user)
        _validate_terrain3d_payload(session, candidate, user=user)
    except HTTPException as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"la version {request.version} n'est plus valide et ne peut pas "
                f"être restaurée : {exc.detail}"
            ),
        ) from exc

    result = repo.rollback_config(session, config_id, request.version, tenant_id=user.tenant_id)
```

**Attention** : les huit `_validate_*` lèvent `HTTPException` avec des codes
variés (400/403/404). Vérifier leur signature réelle avant d'écrire le
`except` ; si l'une lève autre chose qu'`HTTPException`, élargir en
`except (HTTPException, ValueError)` et adapter le message. **Lire les huit
fonctions, ne pas supposer.**

- [ ] **Step 4: Add the repository helper**

Dans `core/app/configs/repository.py`, à côté de `rollback_config` :

```python
def get_revision_config(session: Session, config_id: str, version: int) -> BuilderConfig | None:
    """Lit les données d'une révision sans rien écrire — utilisé par la
    route de rollback pour valider la config restaurée AVANT de créer la
    version N+1 (SP-23, chantier 4.18)."""
    source = session.scalar(
        select(ConfigRevision).where(
            ConfigRevision.config_id == config_id, ConfigRevision.version == version
        )
    )
    if source is None:
        return None
    return BuilderConfig.model_validate(source.data)
```

Vérifier que `BuilderConfig` est importé dans ce module ; l'ajouter sinon.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_configs_rollback_validation.py tests/test_configs_models.py -v`

Expected: PASS.

- [ ] **Step 6: Run the full core suite**

Run: `cd core && uv run pytest -q`

Expected: 0 failed.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/routes.py core/app/configs/repository.py core/tests/test_configs_rollback_validation.py
git commit -m "fix(core): valide la config restaurée avant d'écrire un rollback"
```

---

### Task 14: `ItemClient` — révisions et rollback

**Files:**
- Modify: `shell/src/api/types.ts` (interface `ItemClient`),
  `shell/src/api/itemClient.ts`,
  `shell/src/staticExport/StaticItemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`,
  `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Consumes: Task 13.
- Produces, sur `ItemClient` :

```ts
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
```

  avec `export type ConfigRevisionInfo = { version: number; createdAt: string };`
  dans `shell/src/api/types.ts`.

> **Clé par `pk` d'item, pas par `configId`** : aucun des cinq éditeurs ne
> connaît son `configId` (vérifié). `CoreItemClient` résout par
> `GET /configs/by-item/{pk}`, déjà la monnaie courante du client (dix
> appels existants), plutôt que d'ajouter deux routes `by-item` au serveur.

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/api/itemClient.test.ts` (en suivant le patron `msw` du
fichier — lire un test voisin qui intercepte `/configs/by-item/…`) :

```ts
test("listConfigRevisions résout la config par item puis lit ses révisions", async () => {
  // GET /configs/by-item/app-1 -> { id: "cfg-1", … }
  // GET /configs/cfg-1/revisions -> [{ version: 1, created_at: "2026-08-01T10:00:00" },
  //                                  { version: 2, created_at: "2026-08-02T11:00:00" }]
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  expect(await client.listConfigRevisions("app-1")).toEqual([
    { version: 1, createdAt: "2026-08-01T10:00:00" },
    { version: 2, createdAt: "2026-08-02T11:00:00" },
  ]);
});

test("rollbackConfig poste la version demandée sur la config résolue", async () => {
  let posted: { version: number } | null = null;
  // GET /configs/by-item/app-1 -> { id: "cfg-1" }
  // POST /configs/cfg-1/rollback -> capture le corps, renvoie 200 {}
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  await client.rollbackConfig("app-1", 3);

  expect(posted).toEqual({ version: 3 });
});

test("rollbackConfig propage l'erreur quand le serveur refuse la version", async () => {
  // POST /configs/cfg-1/rollback -> 422
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow();
});
```

Ajouter à `shell/src/staticExport/StaticItemClient.test.ts` :

```ts
test("les révisions ne sont pas disponibles hors ligne", async () => {
  const client = createStaticItemClient(CONFIG);
  await expect(client.listConfigRevisions("app-1")).rejects.toThrow(/export statique/);
  await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow(/export statique/);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/StaticItemClient.test.ts`

Expected: FAIL — `listConfigRevisions` n'existe pas sur `ItemClient`.

- [ ] **Step 3: Extend the interface**

Dans `shell/src/api/types.ts`, ajouter le type et les deux signatures dans
l'interface `ItemClient` (à côté des autres méthodes de config) :

```ts
export type ConfigRevisionInfo = { version: number; createdAt: string };
```

```ts
  // Historique de versions (SP-23, chantier 4.18). Clés par `pk` d'item et
  // non par `configId` : aucun éditeur du shell ne connaît son configId.
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
```

- [ ] **Step 4: Implement in `CoreItemClient`**

Dans `shell/src/api/itemClient.ts`, à l'intérieur de `createItemClient`,
ajouter à l'objet retourné :

```ts
    async listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      const rows = await request<{ version: number; created_at: string }[]>(
        "GET",
        `/configs/${id}/revisions`,
      );
      return rows.map((r) => ({ version: r.version, createdAt: r.created_at }));
    },
    async rollbackConfig(pk: string, version: number): Promise<void> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      await request<unknown>("POST", `/configs/${id}/rollback`, { version });
    },
```

Importer `ConfigRevisionInfo` depuis `./types`.

- [ ] **Step 5: Implement in `StaticItemClient`**

Dans `shell/src/staticExport/StaticItemClient.ts`, ajouter aux méthodes non
supportées :

```ts
    async listConfigRevisions(..._args: unknown[]) {
      return unsupported();
    },
    async rollbackConfig(..._args: unknown[]) {
      return unsupported();
    },
```

- [ ] **Step 6: Run the tests and the type check**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/ && npm run build`

Expected: PASS et build vert. Si `npm run build` échoue sur une autre
implémentation d'`ItemClient` (mocks de test), l'y ajouter aussi.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "feat(shell): expose les révisions de config et le rollback sur ItemClient"
```

---

### Task 15: `useUndoableDraft.resetDraft`

**Files:**
- Modify: `shell/src/builder/useUndoableDraft.ts`
- Test: `shell/src/builder/useUndoableDraft.test.tsx`

**Interfaces:**
- Consumes: rien.
- Produces: `UndoableDraft` gagne `resetDraft(value: AppConfig): void`, qui
  remplace le brouillon **et** vide la pile (past et future), annule le
  timer de coalescing en attente, et remet `canUndo`/`canRedo` à `false`.

> **Piège SP-19** : tout le bookkeeping de refs se fait dans le corps de la
> fonction, **jamais** dans une fonction passée à `setDraftState` — sous
> `<StrictMode>` React invoque un updater deux fois. Le test doit tourner
> sous `<StrictMode>` (les tests existants du fichier le font déjà : lire
> leur mise en place et la réutiliser).

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/useUndoableDraft.test.tsx` :

```tsx
test("resetDraft remplace le brouillon et vide la pile", () => {
  const { result } = renderUndoableDraft(); // helper existant du fichier

  act(() => result.current.seedDraft(CONFIG_A));
  act(() => result.current.setDraft(CONFIG_B));
  act(() => vi.advanceTimersByTime(500));
  expect(result.current.canUndo).toBe(true);

  act(() => result.current.resetDraft(CONFIG_C));

  expect(result.current.draft).toBe(CONFIG_C);
  expect(result.current.canUndo).toBe(false);
  expect(result.current.canRedo).toBe(false);

  // Un undo après reset ne doit rien faire, pas revenir à CONFIG_B.
  act(() => result.current.undo());
  expect(result.current.draft).toBe(CONFIG_C);
});

test("resetDraft annule un burst d'édition encore en attente", () => {
  const { result } = renderUndoableDraft();

  act(() => result.current.seedDraft(CONFIG_A));
  act(() => result.current.setDraft(CONFIG_B)); // burst armé, pas encore flushé
  act(() => result.current.resetDraft(CONFIG_C));
  act(() => vi.advanceTimersByTime(500)); // le timer ne doit rien flusher

  expect(result.current.canUndo).toBe(false);
});
```

Adapter les noms (`renderUndoableDraft`, `CONFIG_A/B/C`) à ce que le fichier
de test définit déjà.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/useUndoableDraft.test.tsx -t "resetDraft"`

Expected: FAIL — `result.current.resetDraft` n'est pas une fonction.

- [ ] **Step 3: Implement `resetDraft`**

Dans `shell/src/builder/useUndoableDraft.ts`, ajouter au type :

```ts
  resetDraft: (value: AppConfig) => void;
```

et, après `seedDraft` :

```ts
  // Remplace le brouillon par une valeur qui vient du SERVEUR (restauration
  // d'une version antérieure, SP-23) et vide l'historique. La pile ne peut
  // pas défaire une écriture serveur : la laisser pleine ferait croire à
  // l'auteur qu'un Ctrl+Z annule la restauration, alors qu'il ne toucherait
  // que son brouillon local pendant que le serveur porte déjà la version
  // N+1. Tout le bookkeeping se fait ici, jamais dans un updater passé à
  // setDraftState (<StrictMode> l'invoquerait deux fois — SP-19, C1).
  const resetDraft = useCallback((value: AppConfig) => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingBaselineRef.current = null;
    stackRef.current = createUndoStack();
    draftRef.current = value;
    setCanUndo(false);
    setCanRedo(false);
    setDraftState(value);
  }, []);
```

et l'ajouter au retour :

```ts
  return { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/useUndoableDraft.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/useUndoableDraft.ts shell/src/builder/useUndoableDraft.test.tsx
git commit -m "feat(shell): ajoute resetDraft au hook d'undo du builder"
```

---

### Task 16: Le panneau `ConfigHistoryPanel`

**Files:**
- Create: `shell/src/builder/ConfigHistoryPanel.tsx`,
  `shell/src/builder/ConfigHistoryPanel.test.tsx`

**Interfaces:**
- Consumes: Task 14 (`listConfigRevisions`, `rollbackConfig`).
- Produces:

```tsx
export function ConfigHistoryPanel({
  pk,
  currentVersion,
  onRestored,
}: {
  pk: string;
  currentVersion: number | null;
  onRestored: () => void | Promise<void>;
}): JSX.Element
```

> `currentVersion` peut être `null` quand l'éditeur ne le connaît pas ; dans
> ce cas le panneau considère la version la plus haute comme courante.

- [ ] **Step 1: Write the failing test**

Créer `shell/src/builder/ConfigHistoryPanel.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ConfigHistoryPanel } from "./ConfigHistoryPanel";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";

function renderPanel(client: Partial<ItemClient>, onRestored = vi.fn()) {
  render(
    <ItemClientProvider client={client as ItemClient}>
      <ConfigHistoryPanel pk="app-1" currentVersion={2} onRestored={onRestored} />
    </ItemClientProvider>,
  );
  return onRestored;
}

beforeEach(() => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

test("liste les versions, la plus récente en tête, et marque la courante", async () => {
  renderPanel({
    listConfigRevisions: vi.fn().mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]),
  });

  const items = await screen.findAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Version 2");
  expect(items[0]).toHaveTextContent("courante");
  expect(items[1]).toHaveTextContent("Version 1");
  // Pas de bouton Restaurer sur la version courante.
  expect(screen.getAllByRole("button", { name: /restaurer/i })).toHaveLength(1);
});

test("un échec de chargement est visible et distinct d'un historique vide", async () => {
  renderPanel({ listConfigRevisions: vi.fn().mockRejectedValue(new Error("boom")) });

  expect(await screen.findByRole("alert")).toHaveTextContent(/impossible de charger/i);
  expect(screen.queryByText(/aucune version/i)).toBeNull();
});

test("un historique vide le dit explicitement", async () => {
  renderPanel({ listConfigRevisions: vi.fn().mockResolvedValue([]) });

  expect(await screen.findByText(/aucune version/i)).toBeInTheDocument();
});

test("restaurer demande confirmation, appelle le client puis prévient le parent", async () => {
  const rollbackConfig = vi.fn().mockResolvedValue(undefined);
  const listConfigRevisions = vi
    .fn()
    .mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]);
  const onRestored = renderPanel({ listConfigRevisions, rollbackConfig });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(window.confirm).toHaveBeenCalled();
  expect(rollbackConfig).toHaveBeenCalledWith("app-1", 1);
  await waitFor(() => expect(onRestored).toHaveBeenCalled());
  // La liste est rechargée après restauration.
  await waitFor(() => expect(listConfigRevisions).toHaveBeenCalledTimes(2));
});

test("annuler la confirmation ne restaure rien", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const rollbackConfig = vi.fn();
  renderPanel({
    listConfigRevisions: vi
      .fn()
      .mockResolvedValue([
        { version: 1, createdAt: "2026-08-01T10:00:00" },
        { version: 2, createdAt: "2026-08-02T11:00:00" },
      ]),
    rollbackConfig,
  });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(rollbackConfig).not.toHaveBeenCalled();
});

test("un échec de restauration est affiché", async () => {
  renderPanel({
    listConfigRevisions: vi
      .fn()
      .mockResolvedValue([
        { version: 1, createdAt: "2026-08-01T10:00:00" },
        { version: 2, createdAt: "2026-08-02T11:00:00" },
      ]),
    rollbackConfig: vi.fn().mockRejectedValue(new Error("422")),
  });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/impossible de restaurer/i);
});
```

Vérifier la signature réelle d'`ItemClientProvider` avant d'écrire le
harnais (lire `shell/src/api/ItemClientProvider.tsx`) et l'adapter.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/ConfigHistoryPanel.test.tsx`

Expected: FAIL — module `./ConfigHistoryPanel` introuvable.

- [ ] **Step 3: Write the component**

Créer `shell/src/builder/ConfigHistoryPanel.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
// Panneau « Historique » générique (SP-23, chantier 4.18). Les configs
// versionnées et POST /configs/{id}/rollback existent depuis SP-0 et
// n'avaient aucun appelant côté shell. Un seul composant sert les cinq
// éditeurs adossés à une config (app/dashboard/site, carte, dataset,
// pipeline, rapport) : la route serveur est générique, le coût marginal par
// éditeur est le point de montage seul.
//
// Pas de sondage, contrairement à PipelineRunPanel/ReportRunPanel : un
// historique de versions ne bouge que quand CET utilisateur enregistre ou
// restaure. On charge au montage et après chaque restauration.
import { useCallback, useEffect, useState } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { ConfigRevisionInfo } from "../api/types";
import { Button } from "../ui/button";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}

export function ConfigHistoryPanel({
  pk,
  currentVersion,
  onRestored,
}: {
  pk: string;
  currentVersion: number | null;
  onRestored: () => void | Promise<void>;
}) {
  const client = useItemClient();
  const [revisions, setRevisions] = useState<ConfigRevisionInfo[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [restoreError, setRestoreError] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await client.listConfigRevisions(pk);
      // Plus récente en tête. Le serveur trie par version croissante.
      setRevisions([...rows].sort((a, b) => b.version - a.version));
      setLoadError(false);
    } catch {
      // Sans cet état, un historique vide pour cause de panne réseau serait
      // indiscernable d'un « aucune version » légitime (même défaut corrigé
      // en revue sur SP-16b puis SP-17b).
      setLoadError(true);
    }
  }, [client, pk]);

  useEffect(() => {
    void load();
  }, [load]);

  const latest = revisions?.[0]?.version ?? null;
  const current = currentVersion ?? latest;

  async function restore(version: number) {
    // Confirmation systématique, sans chercher à savoir si le brouillon est
    // modifié : aucun des cinq éditeurs ne porte de drapeau « sale », et une
    // confirmation n'est jamais fausse devant une écriture serveur
    // (spec SP-23 §3.4).
    if (
      !window.confirm(
        `Restaurer la version ${version} ? Les modifications non enregistrées seront perdues.`,
      )
    )
      return;
    setBusy(true);
    setRestoreError(false);
    try {
      await client.rollbackConfig(pk, version);
      await load();
      await onRestored();
    } catch {
      setRestoreError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Historique</h3>
      {loadError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de charger l'historique des versions.
        </p>
      )}
      {restoreError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de restaurer cette version.
        </p>
      )}
      {!loadError && revisions !== null && revisions.length === 0 && (
        <p className="text-sm text-slate-500">Aucune version enregistrée.</p>
      )}
      <ul className="flex flex-col gap-1">
        {(revisions ?? []).map((r) => (
          <li key={r.version} className="flex items-center gap-2 text-sm">
            <span>
              Version {r.version} — {formatDate(r.createdAt)}
            </span>
            {r.version === current ? (
              <span className="text-xs text-slate-500">(courante)</span>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void restore(r.version)}
              >
                Restaurer
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/ConfigHistoryPanel.test.tsx`

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/ConfigHistoryPanel.tsx shell/src/builder/ConfigHistoryPanel.test.tsx
git commit -m "feat(shell): ajoute le panneau d'historique des versions de config"
```

---

### Task 17: Monter le panneau sur les cinq éditeurs

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`,
  `shell/src/pages/MapEditorPage.tsx`,
  `shell/src/pages/DatasetEditPage.tsx`,
  `shell/src/pages/PipelineBuilderPage.tsx`,
  `shell/src/pages/ReportEditPage.tsx`
- Test: les fichiers `.test.tsx` correspondants (créer
  `ReportEditPage.test.tsx` s'il n'existe pas)

**Interfaces:**
- Consumes: Tasks 15 et 16.
- Produces: rien pour les tâches suivantes.

- [ ] **Step 1: Write the failing tests**

Dans chacun des cinq fichiers de test de page, ajouter un test qui vérifie
que le titre « Historique » est rendu :

```tsx
test("affiche le panneau d'historique", async () => {
  // … même mise en place que les tests voisins du fichier
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});
```

Et, pour `AppBuilderPage` seulement, un test qui vérifie que la restauration
recharge le brouillon **et** vide la pile d'undo :

```tsx
test("restaurer une version recharge le brouillon et vide l'undo", async () => {
  // rollbackConfig résout ; getAppConfig renvoie ensuite une config
  // différente ; on avait fait un edit avant, donc canUndo était vrai
  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled());
});
```

Adapter le nom du bouton d'undo à ce que rend réellement `AppBuilderPage`
(le lire).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/`

Expected: FAIL — « Historique » introuvable dans les cinq pages.

- [ ] **Step 3: Mount in `AppBuilderPage`**

Dans `shell/src/pages/AppBuilderPage.tsx` :

1. importer le panneau et récupérer `resetDraft` du hook :

```ts
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
```

```ts
  const { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo } =
    useUndoableDraft();
```

2. monter le panneau dans la colonne latérale du builder, à côté des autres
   panneaux (chercher l'`<aside>` qui contient `PropsPanel`/`ThemePanel`) :

```tsx
        <ConfigHistoryPanel
          pk={pk}
          currentVersion={null}
          onRestored={async () => {
            const restored = await client.getAppConfig(pk);
            // resetDraft, pas setDraft : la pile undo ne peut pas défaire une
            // écriture serveur (cf. useUndoableDraft.resetDraft).
            resetDraft(restored);
            await query.refetch();
          }}
        />
```

Adapter `client`/`query` aux noms réellement en portée dans le fichier.

- [ ] **Step 4: Mount in the four other editors**

Même montage, sans `resetDraft` (les quatre autres éditeurs utilisent un
`useState` simple) : `onRestored` recharge la config par le getter de la
page et la réinjecte dans `setDraft`.

- `MapEditorPage` : dans l'`<aside>`, sous `PrintLayoutPanel` ;
  `onRestored` = `setDraft(await client.getMapConfig(pk))`.
- `DatasetEditPage` : à la fin du formulaire, sous la section « Alertes » ;
  `onRestored` = recharge de la config dataset.
- `PipelineBuilderPage` : dans la colonne latérale, sous
  `PipelineSchedulePanel`/`PipelineRunPanel` ; **ne pas monter le panneau
  quand `pk` est `null`** (route `/pipelines/new`, rien n'est encore
  persisté).
- `ReportEditPage` : sous `ReportRunPanel` ; même garde `pk === null`.

Lire chaque page avant d'insérer : le nom du getter et la façon de recharger
diffèrent, ne pas les deviner.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/`

Expected: PASS.

- [ ] **Step 6: Run the full shell suite and build**

Run: `cd shell && npm run test && npm run build`

Expected: 0 failed, build vert.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/
git commit -m "feat(shell): monte le panneau d'historique sur les cinq éditeurs de config"
```

---

## Lot F — Preuves de sortie et clôture

### Task 18: E2E — catalogue et restauration

**Files:**
- Modify: `shell/e2e/catalog.spec.ts`
- Create: `shell/e2e/config-history.spec.ts`
- Modify: `shell/e2e/mocks.ts` (si `mockCore` ne sert pas encore
  `/configs/{id}/revisions` ni `/configs/{id}/rollback`)

**Interfaces:**
- Consumes: Tasks 11, 12, 17.
- Produces: les deux preuves de sortie visibles du plan d'action.

- [ ] **Step 1: Write the failing E2E specs**

Ajouter à `shell/e2e/catalog.spec.ts` :

```ts
test("filtrer sur Dataset ne ramène que les datasets", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByLabel("Type").selectOption("dataset");

  await expect(page.getByRole("heading", { name: "Alpha" })).toBeHidden();
  await expect(page.getByText("Dataset", { exact: true }).first()).toBeVisible();
});
```

Vérifier d'abord que le jeu d'items de `mocks.ts` contient bien au moins un
item `resourceType: "dataset"` et respecte le paramètre `type` de
`GET /items` ; l'y ajouter sinon.

Créer `shell/e2e/config-history.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("restaurer une version antérieure depuis le builder d'app", async ({ page }) => {
  await mockCore(page);
  await page.goto("/apps/1/edit");

  await expect(page.getByText("Historique")).toBeVisible();
  await expect(page.getByText(/Version 2/)).toBeVisible();

  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Restaurer" }).click();

  // La config rechargée après rollback est celle de la version 1 : son
  // widget porte un titre différent de celui de la version courante.
  await expect(page.getByText("Titre version 1")).toBeVisible();
  // L'undo est vidé : la restauration n'est pas annulable localement.
  await expect(page.getByRole("button", { name: "Annuler" })).toBeDisabled();
});
```

- [ ] **Step 2: Extend the mock core**

Dans `shell/e2e/mocks.ts`, ajouter les deux routes :
`GET **/configs/*/revisions` renvoyant deux versions, et
`POST **/configs/*/rollback` qui bascule la config servie ensuite par
`GET /configs/by-item/1` vers la variante « Titre version 1 ». Suivre
exactement le style de routage déjà utilisé dans le fichier.

- [ ] **Step 3: Run the specs to verify they fail then pass**

Run: `cd shell && npx playwright test e2e/config-history.spec.ts e2e/catalog.spec.ts`

Expected: d'abord FAIL (avant l'ajout des mocks), puis PASS.

- [ ] **Step 4: Run the whole E2E suite**

Run: `cd shell && npm run e2e`

Expected: 0 failed.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/
git commit -m "test(shell): prouve le filtre par type et la restauration de version en e2e"
```

---

### Task 19: Clôture — suites complètes, portes et CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: toutes les tâches précédentes.

- [ ] **Step 1: Run every gate**

```bash
cd core && uv run pytest -q
cd core && uv run ruff check . && uv run ruff format --check .
cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot
cd core && uv run lint-imports
cd shell && npm run lint && npm run format:check && npm run test && npm run build && npm run e2e
uvx pre-commit run --all-files
```

Expected: tout vert. core ≥ 1653 passed / 0 failed ; shell ≥ 152 fichiers /
1235 tests.

- [ ] **Step 2: Verify the OpenAPI spec is still in sync**

Run:
```bash
cd core && uv run python scripts/export_openapi.py openapi.json && git diff --exit-code core/openapi.json
cd shell && npm run gen:api-types && git diff --exit-code src/api/generated/core-schema.d.ts
```

Expected: exit code 0 sur les deux (Task 4 les a déjà régénérés ; aucune
tâche ultérieure ne change de schéma).

- [ ] **Step 3: Verify the coverage thresholds**

Run: `cd core && uv run pytest --cov=app --cov-report=term && uv run python scripts/check_coverage.py`
puis `cd shell && npm run test -- --coverage && node scripts/check-coverage.mjs`

Expected: les deux seuils tenus (85 / 88). Vérifier les noms exacts des
scripts dans `package.json` et `core/pyproject.toml` avant de lancer.

- [ ] **Step 4: Update `CLAUDE.md`**

Ajouter une entrée **SP-23** dans `### Fait`, décrivant les quatre chantiers,
les deux trouvailles qui ont élargi le périmètre supposé par le plan
(aucune UI de `bucket`, rollback sans validateurs) et les décisions §4 de la
spec. Retirer la mention de l'étape 4 du séquencement de `### À venir` si
elle y figure.

Ajouter dans `### Suivis non bloquants ouverts` :

- `chartOption.num()` convertit toujours `null` en `0` pour les séries
  ECharts : un agrégat indéfini (écart-type d'un groupe d'une seule ligne)
  s'affiche « 0 » dans un graphique, alors que l'indicateur affiche « — ».
  Limite acceptée en SP-23 (changer `num()` toucherait les onze types de
  graphique, dont boxplot/radar/sankey qui n'acceptent pas `null`).
- La parité `STDDEV_SAMP` / `statisticType: "stddev"` d'ArcGIS est affirmée
  d'après la documentation, jamais mesurée contre un service réel.
- `GET /configs/{id}/revisions` n'est pas paginée : une config éditée des
  centaines de fois renvoie toutes ses révisions d'un coup.
- L'auteur d'une révision reste absent (`config_revisions` n'a pas
  d'`actor_id`) — relève du chantier 4.20.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: consigne sp23 et ses suivis non bloquants dans claude.md"
```

---

## Auto-revue du plan

**Couverture de la spec** — les sept sections de mécanisme sont couvertes :
§3.1 chemin analytique → Task 1 ; §3.1 chemin ArcGIS → Task 3 ; §3.1
assistant visuel → Tasks 8-10 ; §3.1 surfaces shell → Task 5 ; §3.2 → Tasks
2 et 6 ; §3.3 → Tasks 11-12 ; §3.4 cœur → Task 13 ; §3.4 `ItemClient` →
Task 14 ; §3.4 panneau → Tasks 15-17. §6 (validation) → Tasks 18-19. La
régénération OpenAPI, absente du découpage naturel, a sa propre Task 4.

**Cohérence de types** — `p` est un pourcentage partout
(`AggregateMeasure.p`, `AggregateRequestBody.p`, `MetricConfig.p`,
`DataSource.query.p`), converti en fraction uniquement dans `_agg_expr`
(Task 1) et `metricExpr` (Task 9), et reconverti en pourcentage dans
`decompileMetrics` (Task 9). `MetricConfig.p` est `number | null` et non
optionnel — Tasks 8, 9 et 10 l'écrivent tous les trois sous cette forme.
`ConfigRevisionInfo.createdAt` est en camelCase côté shell (Task 14),
mappé depuis `created_at` du serveur. `resetDraft` porte le même nom en
Tasks 15 et 17.

**Points où l'implémenteur doit lire avant d'écrire, explicitement signalés** :
la mise en place des tests de `indicator.test.tsx` (Task 7), de
`QuerySummaryBuilder.test.tsx` (Task 10), de `routes.test.tsx` (Task 12),
de `test_configs_rollback_validation.py` (Task 13), la signature réelle des
huit `_validate_*` (Task 13), celle d'`ItemClientProvider` (Task 16), et le
mode de rechargement propre à chacun des cinq éditeurs (Task 17).
