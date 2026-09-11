# GAP-25 — Couche sémantique minimale (métriques nommées) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un catalogue de métriques nommées par collection
(`Collection.metrics: list[NamedMetric]`), résolu par `metricName` dans
toute requête d'agrégat qui passe déjà par `run_collection_aggregate`
(REST `POST /collections/{id}/aggregate`/`.../export`, outil MCP
`run_analytics_query`), édité depuis l'écran d'admin de collection, et
proposé en autofill dans le wizard de requête visuelle.

**Architecture:** 10 tâches. Migration+modèle d'abord (Tâche 1), puis le
cœur de résolution dans `app/analytics/aggregate.py` avec son test
d'équivalence SQL (Tâche 2, la plus à risque — tout le reste en dépend),
puis les 3 call sites REST/MCP (Tâches 3-4), puis l'édition du catalogue
(Tâche 5), régénération OpenAPI/TS (Tâche 6), puis le shell — types (Tâche
7), UI d'admin (Tâche 8), autofill du wizard (Tâche 9) — et une revue
finale de branche qui vérifie explicitement l'absence de diff sur les
fichiers exclus par la spec (Tâche 10).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/DuckDB (cœur),
TypeScript/React/Vitest (shell). Aucune nouvelle dépendance.

**Document source :**
`docs/superpowers/specs/2026-09-06-gap25-couche-semantique-design.md`
(sections citées : §1 contexte, §2 décisions, §3 hors périmètre, §4
architecture détaillée, §5 critères d'acceptation).

## Global Constraints

- **Une métrique reste scopée à sa collection** (spec §3) : jamais de
  jointure/référence cross-collection.
- **Un seul chemin d'exécution SQL** : la résolution de `metricName`
  produit un `AggregateMeasure` classique **avant** tout appel à
  `_agg_expr` (`core/app/analytics/aggregate.py`), à l'intérieur de
  `_measures_for()` — jamais un second générateur de SQL (spec §2.2, §4.2).
- **Fichiers explicitement exclus de ce plan, à ne JAMAIS modifier** :
  `core/app/alerts/jobs.py`, `core/app/appexport/miniserver/main.py`,
  `core/app/appexport/snapshot.py`, `core/app/harvest/routes.py` (spec §3).
  La Tâche 10 vérifie mécaniquement qu'aucun de ces 4 fichiers n'apparaît
  dans le diff de branche.
- **Pas de validation de `field` contre les colonnes réelles au moment du
  PATCH** du catalogue (spec §2.4) — seule la forme (`agg`/`p`, exclusivité
  `metricName`) est validée à l'écriture ; l'existence du champ reste
  validée à la résolution/exécution, comme pour toute mesure ad hoc
  aujourd'hui.
- **Aucun nouveau mécanisme de version** sur `Collection` (spec §1.4/§2.5) :
  ne pas ajouter de compteur, ne pas toucher `Collection.version` (champ
  texte DCAT existant, sans rapport). L'entrée `audit_log`
  `"collection.update"` déjà émise par `patch_collection` suffit.
- **`QuerySummaryBuilder.tsx` n'envoie jamais `metricName` sur le réseau**
  (spec §1.5, §4.5) : le sélecteur de métrique nommée n'est qu'un autofill
  client des champs `MetricConfig` existants — `MetricConfig`/
  `SummaryConfig`/`compilePipeline.ts` ne gagnent aucun champ nouveau.
- **TDD systématique** : chaque tâche écrit son test avant son code, le
  fait échouer, puis implémente.
- **Suite complète rejouée avant le dernier commit de chaque tâche cœur** :
  `cd core && uv run pytest` (au minimum les fichiers touchés + un passage
  complet avant de clore la tâche, piège CLAUDE.md n°6). Idem shell :
  `cd shell && npx vitest run`.
- **Migration testée upgrade/downgrade/upgrade sur base non vide** (piège
  CLAUDE.md n°8, Tâche 1).
- **Régénération OpenAPI/TS obligatoire** (piège CLAUDE.md n°1) — Tâche 6,
  dédiée, après que toutes les routes/modèles aient changé de forme.
- **`uv run lint-imports` reste vert sans nouvelle exception nommée** —
  `app.collections -> app.analytics.aggregate` est une direction déjà
  autorisée par le contrat de couches (`app.collections` au-dessus
  d'`app.analytics`, spec §4.3) : si `lint-imports` échoue quand même à la
  Tâche 5, c'est un signal que la prémisse de la spec était fausse — le
  vérifier contre `core/pyproject.toml` avant de contourner.
- Commits **conventional**, français, un sujet par commit
  (`feat(core): ...`, `feat(shell): ...`, `test(core): ...`).
- Docs/messages en français, code/identifiants en anglais (`NamedMetric`,
  `metricName`, `metrics_catalog`).

---

## Task 1 : migration + modèle `Collection.metrics`

Risque : faible (mécanique, patron `attachment_fields` déjà en place).

**Files:**
- Create: `core/alembic/versions/0041_collection_metrics.py`
- Modify: `core/app/collections/models.py`
- Test: `core/tests/test_collections_models.py`
- Test: `core/tests/test_model_alembic_parity.py` (aucune modification de
  code, juste vérifier qu'il passe déjà — c'est un comparateur générique)

**Interfaces:**
- Produces: `Collection.metrics: list` (liste de dicts JSON bruts, forme
  `NamedMetric` sérialisée — le typage Pydantic arrive Tâche 2). Toute
  tâche suivante qui lit/écrit `col.metrics` suppose cette colonne
  présente, `default=list`, `nullable=False`.

- [ ] **Step 1 : trouver le numéro et le style exacts de la migration
  `attachment_fields` pour les reproduire à l'identique**

```bash
cd core && grep -rl "attachment_fields" alembic/versions/
```

Lire le fichier trouvé en entier (probablement `alembic/versions/003x_*.py`)
pour copier son `upgrade()`/`downgrade()` mot pour mot, seul le nom de
colonne change.

- [ ] **Step 2 : écrire le test modèle qui doit échouer**

Ajouter à `core/tests/test_collections_models.py` (si ce fichier n'a pas
déjà de fixture de création directe de `Collection` en base de test,
regarder comment `attachment_fields` y est déjà couvert et reproduire le
même style de test) :

```python
def test_collection_metrics_defaults_to_empty_list(session):
    from app.collections.models import Collection

    col = Collection(
        id="villes",
        tenant_id="t1",
        owner_id="u1",
        table_name="villes",
        title="Villes",
        pk_column="id",
    )
    session.add(col)
    session.flush()
    assert col.metrics == []
```

- [ ] **Step 3 : lancer le test, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_collections_models.py -k metrics -v
```

Attendu : FAIL — `AttributeError: 'Collection' object has no attribute
'metrics'` (ou équivalent, la colonne n'existe pas encore côté modèle).

- [ ] **Step 4 : ajouter la colonne au modèle**

Dans `core/app/collections/models.py`, juste après `attachment_fields`
(ligne ~53) :

```python
    # Catalogue de métriques nommées (GAP-25, chantier sémantique minimal) —
    # même forme qu'AggregateMeasure (app.analytics.aggregate) plus un
    # identifiant stable ; résolu par metricName dans une requête d'agrégat.
    # Patron JSON identique à attachment_fields ci-dessus (server_default="[]"
    # en chaîne nue, jamais un cast "::json" — casse le DDL SQLite des tests
    # unitaires, cf. commentaire attachment_fields plus haut).
    metrics: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False, server_default="[]"
    )
```

- [ ] **Step 5 : écrire la migration 0041**

`core/alembic/versions/0041_collection_metrics.py` — copier l'en-tête
(`revision`, `down_revision="0040"`, imports) du fichier trouvé Step 1, et :

```python
def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("collections", "metrics")
```

- [ ] **Step 6 : lancer le test modèle, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_collections_models.py -k metrics -v
```

Attendu : PASS.

- [ ] **Step 7 : tester la migration upgrade/downgrade/upgrade sur base non
  vide (piège CLAUDE.md n°8)**

Contre `postgis-test` (`CORE_TEST_DATABASE_URL` positionné, cf. CLAUDE.md) :

```bash
cd core && uv run alembic upgrade 0040
uv run python -c "
from sqlalchemy import create_engine, text
import os
eng = create_engine(os.environ['CORE_TEST_DATABASE_URL'])
with eng.begin() as c:
    c.execute(text(\"INSERT INTO tenants (id, name) VALUES ('t-mig-test', 't') ON CONFLICT DO NOTHING\"))
    c.execute(text(\"INSERT INTO users (id, tenant_id, email, oidc_sub, is_admin) VALUES ('u-mig-test', 't-mig-test', 'x@x.fr', 'sub', false) ON CONFLICT DO NOTHING\"))
    c.execute(text(\"INSERT INTO collections (id, tenant_id, owner_id, table_name, title, pk_column) VALUES ('c-mig-test', 't-mig-test', 'u-mig-test', 'c_mig_test', 'T', 'id') ON CONFLICT DO NOTHING\"))
"
uv run alembic upgrade 0041
uv run python -c "
from sqlalchemy import create_engine, text
import os
eng = create_engine(os.environ['CORE_TEST_DATABASE_URL'])
with eng.begin() as c:
    row = c.execute(text(\"SELECT metrics FROM collections WHERE id='c-mig-test'\")).fetchone()
    assert row[0] == [], row
    print('OK metrics ==', row[0])
"
uv run alembic downgrade 0040
uv run alembic upgrade 0041
```

Attendu : chaque commande réussit, `OK metrics == []` s'affiche, aucune
exception. Nettoyer la ligne de test après coup si le conteneur est
partagé (`DELETE FROM collections WHERE id='c-mig-test'; DELETE FROM users
WHERE id='u-mig-test'; DELETE FROM tenants WHERE id='t-mig-test';`).

- [ ] **Step 8 : lancer `test_model_alembic_parity.py` en entier**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
```

Attendu : PASS — le comparateur générique détecte la nouvelle colonne et la
valide automatiquement contre le patron JSON déjà toléré pour
`attachment_fields` (aucune modification de ce fichier de test n'est
attendue).

- [ ] **Step 9 : commit**

```bash
cd core && git add alembic/versions/0041_collection_metrics.py app/collections/models.py tests/test_collections_models.py
git commit -m "feat(core): ajoute Collection.metrics (catalogue de métriques nommées, GAP-25)"
```

---

## Task 2 : `NamedMetric`, `AggregateMeasure.metricName`, résolution dans `_measures_for`/`run_collection_aggregate`

Risque : le plus élevé de ce plan — c'est le seul générateur de SQL du
dépôt pour les agrégats, toute erreur ici se propage à tous les
consommateurs.

**Files:**
- Modify: `core/app/analytics/aggregate.py`
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: rien de nouveau (fichier autonome).
- Produces: `NamedMetric(AggregateMeasure)` avec un champ `name: str`
  (importable par toute tâche suivante via
  `from app.analytics.aggregate import NamedMetric`) ;
  `AggregateMeasure.metricName: str | None` ;
  `run_collection_aggregate(..., metrics_catalog: list[NamedMetric] | None
  = None)` — nouveau paramètre à mots-clé, optionnel, backward-compatible.

- [ ] **Step 1 : écrire le test d'équivalence SQL (métrique nommée vs. mesure
  ad hoc identique) — doit échouer**

Ajouter à `core/tests/test_analytics_aggregate.py`, après les imports
existants ajouter `NamedMetric` :

```python
from app.analytics.aggregate import (
    AggregateMeasure,
    AggregateRequestBody,
    NamedMetric,
    UnknownAggregateField,
    run_collection_aggregate,
)
```

Puis, à la suite des tests existants (fin de fichier) :

```python
def test_named_metric_produces_identical_rows_to_equivalent_ad_hoc_measure(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Sud", "2025", 5, lsn=1),
        ],
    )
    catalog = [NamedMetric(name="total_pop", field="pop", agg="sum")]

    named_request = AggregateRequestBody(
        groupBy="region", measures=[AggregateMeasure(metricName="total_pop")]
    )
    ad_hoc_request = AggregateRequestBody(
        groupBy="region", measures=[AggregateMeasure(field="pop", agg="sum", label="total_pop")]
    )

    named_key, named_rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=named_request,
        metrics_catalog=catalog,
    )
    ad_hoc_key, ad_hoc_rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=ad_hoc_request,
    )

    assert named_key == ad_hoc_key
    assert sorted(named_rows, key=lambda r: r["region"]) == sorted(
        ad_hoc_rows, key=lambda r: r["region"]
    )


def test_named_metric_label_defaults_to_metric_name_not_agg_field(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    catalog = [NamedMetric(name="total_pop", field="pop", agg="sum")]
    request = AggregateRequestBody(
        groupBy="region", measures=[AggregateMeasure(metricName="total_pop")]
    )

    _key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
        metrics_catalog=catalog,
    )

    assert rows == [{"region": "Nord", "total_pop": 10}]


def test_unknown_metric_name_raises_unknown_aggregate_field(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region", measures=[AggregateMeasure(metricName="nope")]
    )

    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
            metrics_catalog=[NamedMetric(name="autre_metrique", agg="count")],
        )
    assert "nope" in exc_info.value.message


def test_metric_name_cannot_combine_with_field(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region",
        measures=[AggregateMeasure(metricName="total_pop", field="pop")],
    )

    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
            metrics_catalog=[NamedMetric(name="total_pop", field="pop", agg="sum")],
        )
    assert "metricName" in exc_info.value.message


def test_run_collection_aggregate_without_metrics_catalog_still_works(tmp_path, conn):
    # Non-régression : un appelant qui ne passe pas metrics_catalog du tout
    # (appexport/miniserver, alerts/jobs.py — hors périmètre de ce plan)
    # continue de fonctionner à l'identique pour une requête ad hoc.
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )
    assert key == "region"
    assert rows == [{"region": "Nord", "value": 10}]
```

- [ ] **Step 2 : lancer les 5 tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -k "named_metric or unknown_metric_name or metric_name_cannot or without_metrics_catalog" -v
```

Attendu : les 4 premiers FAIL (`NamedMetric`/`metricName`/`metrics_catalog`
n'existent pas encore — `ImportError` ou `TypeError: unexpected keyword
argument`) ; le 5e (`test_run_collection_aggregate_without_metrics_catalog_still_works`)
PASS déjà (comportement inchangé), ce qui est attendu — il sert de garde de
non-régression pour la suite, pas un test à faire échouer.

- [ ] **Step 3 : ajouter `metricName` à `AggregateMeasure` et `NamedMetric`**

Dans `core/app/analytics/aggregate.py`, remplacer la classe existante
(lignes 26-33) :

```python
class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None
    # Centile demandé, en POURCENTAGE (0 < p < 100), pas en fraction.
    # Obligatoire pour agg="percentile", refusé pour tout autre agg
    # (_validate_p ci-dessous). La division par 100 se fait dans _agg_expr.
    p: float | None = None
    # GAP-25 : référence une NamedMetric de Collection.metrics par son name.
    # Exclusif avec field/agg/p (validé par _validate_fields, ci-dessous) —
    # une mesure porte soit une définition ad hoc, soit une référence
    # nommée, jamais les deux.
    metricName: str | None = None


class NamedMetric(AggregateMeasure):
    """Une entrée du catalogue Collection.metrics (GAP-25) — même forme
    qu'AggregateMeasure, plus un identifiant stable unique par collection.
    N'a jamais de metricName propre (une métrique nommée ne référence pas
    une autre métrique nommée — pas de chaînage en v0)."""

    name: str = Field(min_length=1, max_length=64)
```

Ajouter `Field` à l'import pydantic en tête de fichier
(`from pydantic import BaseModel, Field`).

- [ ] **Step 4 : ajouter la garde d'exclusivité dans `_validate_fields`**

Dans `_validate_fields` (ligne ~97), remplacer la boucle existante sur les
mesures (lignes 122-124) :

```python
    for i, m in enumerate(request.measures or []):
        if m.metricName is not None and (
            m.field is not None or m.agg != "count" or m.p is not None
        ):
            raise UnknownAggregateField(
                f"measures[{i}]", "metricName cannot be combined with field/agg/p"
            )
        check(m.field, f"measures[{i}].field")
        _validate_p(m.agg, m.p, f"measures[{i}].p")
```

- [ ] **Step 5 : réécrire `_measures_for` pour résoudre `metricName`**

Remplacer la fonction existante (lignes 210-213) :

```python
def _measures_for(
    request: AggregateRequestBody,
    metrics_catalog: dict[str, AggregateMeasure] | None = None,
) -> list[AggregateMeasure]:
    raw = request.measures or [
        AggregateMeasure(field=request.field, agg=request.agg, label="value", p=request.p)
    ]
    catalog = metrics_catalog or {}
    resolved: list[AggregateMeasure] = []
    for i, m in enumerate(raw):
        if m.metricName is None:
            resolved.append(m)
            continue
        stored = catalog.get(m.metricName)
        if stored is None:
            raise UnknownAggregateField(
                f"measures[{i}].metricName", f"unknown metric '{m.metricName}'"
            )
        resolved.append(
            AggregateMeasure(
                field=stored.field,
                agg=stored.agg,
                p=stored.p,
                # Le libellé de sortie d'une métrique nommée retombe sur son
                # NOM plutôt que sur la dérivation générique {agg}_{field} :
                # la clé de résultat reste stable même si la définition de
                # la métrique change plus tard dans le catalogue.
                label=m.label or stored.label or m.metricName,
            )
        )
    return resolved
```

- [ ] **Step 6 : brancher `metrics_catalog` dans `run_collection_aggregate`**

Modifier la signature (ligne ~437) en ajoutant le paramètre :

```python
def run_collection_aggregate(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    request: AggregateRequestBody,
    metrics_catalog: list[NamedMetric] | None = None,
) -> tuple[str | list[str], list[dict[str, Any]]]:
```

Juste après `fields = _groupby_fields(request)` (ligne ~446), ajouter :

```python
    catalog_by_name = {m.name: m for m in (metrics_catalog or [])}
```

Puis remplacer les deux appels existants `_measures_for(request)` (lignes
~492 et ~542) par `_measures_for(request, catalog_by_name)`.

- [ ] **Step 7 : lancer les 5 tests, vérifier qu'ils passent tous**

```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -k "named_metric or unknown_metric_name or metric_name_cannot or without_metrics_catalog" -v
```

Attendu : 5 PASS.

- [ ] **Step 8 : lancer la suite complète de ce fichier + suite complète du
  cœur**

```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -v
uv run pytest -q
```

Attendu : tous PASS (aucune régression sur les tests existants —
`_measures_for(request)` sans second argument continue de fonctionner
partout où il est encore appelé ainsi : `alerts/jobs.py`,
`mcp/tools/analytics.py` branche `arcgis`).

- [ ] **Step 9 : commit**

```bash
cd core && git add app/analytics/aggregate.py tests/test_analytics_aggregate.py
git commit -m "feat(core): résout metricName en AggregateMeasure dans _measures_for (GAP-25)"
```

---

## Task 3 : `POST /collections/{id}/aggregate` et `.../export` passent `metrics_catalog`

Risque : faible — deux lignes ajoutées à deux appels déjà existants.

**Files:**
- Modify: `core/app/features/routes.py`
- Test: `core/tests/test_features_aggregate_routes.py`

**Interfaces:**
- Consumes: `run_collection_aggregate(..., metrics_catalog=...)` (Tâche 2),
  `col.metrics` (Tâche 1, liste de dicts bruts — nécessite un parsing en
  `NamedMetric` avant passage).

- [ ] **Step 1 : écrire le test qui doit échouer**

Ce fichier utilise la fixture `env` (retourne
`app, client, admin, regular, tmp_path, tenant_id`), le helper `_register(app,
client, admin, public=False)` (POST `/v1/collections`) et
`_write_partition(base_dir, *, tenant_id, collection_id, rows)` — même
montage que `test_aggregate_returns_wide_rows_for_a_readable_collection`
(ligne ~106 du fichier). La fixture `env` ne renvoie pas de session
directement, mais `app.dependency_overrides[db.get_session]` (posé par
`env`, ligne ~76) est le générateur `override_session` fermé sur le même
`Session`/engine que le reste de la fixture — l'appeler directement donne
une session réelle sur cette base sans dupliquer le montage ni modifier la
signature de `env` (qu'un grand nombre d'autres tests de ce fichier
déballent positionnellement). Ajouter ce petit helper en tête de fichier,
à la suite de `_register` :

```python
def _set_collection_metrics(app, collection_id, metrics):
    session = next(app.dependency_overrides[db.get_session]())
    from app.collections.models import Collection

    col = session.get(Collection, collection_id)
    col.metrics = metrics
    session.commit()
```

Puis les tests :

```python
def test_aggregate_route_resolves_metric_name_from_collection_catalog(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
            {
                "id": 2,
                "region": "Sud",
                "pop": 5,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1, 1),
            },
        ],
    )
    _set_collection_metrics(
        app, col["id"], [{"name": "total_pop", "field": "pop", "agg": "sum", "label": None, "p": None}]
    )

    response = client.post(
        f"/v1/collections/{col['id']}/aggregate",
        json={"groupBy": "region", "measures": [{"metricName": "total_pop"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(body["rows"], key=lambda r: r["region"]) == [
        {"region": "Nord", "total_pop": 10},
        {"region": "Sud", "total_pop": 5},
    ]


def test_export_route_resolves_metric_name_from_collection_catalog(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
    )
    _set_collection_metrics(
        app, col["id"], [{"name": "total_pop", "field": "pop", "agg": "sum", "label": None, "p": None}]
    )

    response = client.post(
        f"/v1/collections/{col['id']}/export?format=csv",
        json={"groupBy": "region", "measures": [{"metricName": "total_pop"}]},
    )

    assert response.status_code == 200
    assert b"total_pop" in response.content


def test_aggregate_route_unknown_metric_name_returns_400(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
    )

    response = client.post(
        f"/v1/collections/{col['id']}/aggregate",
        json={"groupBy": "region", "measures": [{"metricName": "inconnu"}]},
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "unknown_field"
```

(`test_aggregate_unknown_group_by_field_returns_400`, dans ce même fichier,
prouve que ce chemin d'erreur répond bien 400 avec ce format — **pas 422** :
`_validation_error(...)` dans `features/routes.py` (ligne 118, défaut
`status: int = 400`) mappe déjà `UnknownAggregateField` sur 400, pas le 422
par défaut de FastAPI/Pydantic. Écart avec la spec §5 critère 3, qui disait
422 par généralisation à partir du comportement Pydantic générique — **le
code réel est 400** ; le nom du test ci-dessus reflète ça, contrairement au
brouillon initial de la spec.)

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_features_aggregate_routes.py -k metric_name -v
```

Attendu : FAIL — `metricName` n'est résolu par aucune route pour l'instant
(erreur 400 `unknown_field` sur `metricName` lui-même côté
`_validate_fields`, faute de catalogue jamais passé par la route).

- [ ] **Step 3 : brancher `metrics_catalog` sur les deux routes**

Dans `core/app/features/routes.py`, importer `NamedMetric` :

```python
from app.analytics.aggregate import (
    AggregateRequestBody,
    NamedMetric,
    UnknownAggregateField,
    run_collection_aggregate,
)
```

Dans `aggregate_features` (ligne ~251-280) et `export_collection_aggregate`
(ligne ~286-330), juste avant l'appel à `run_collection_aggregate`, ajouter :

```python
    metrics_catalog = [NamedMetric.model_validate(m) for m in col.metrics]
```

puis passer `metrics_catalog=metrics_catalog` dans les deux appels à
`run_collection_aggregate` (aux deux endroits).

- [ ] **Step 4 : lancer les tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_features_aggregate_routes.py -v
```

Attendu : tous PASS, y compris les nouveaux.

- [ ] **Step 5 : suite complète du cœur**

```bash
cd core && uv run pytest -q
```

Attendu : PASS, aucune régression.

- [ ] **Step 6 : commit**

```bash
cd core && git add app/features/routes.py tests/test_features_aggregate_routes.py
git commit -m "feat(core): POST /collections/{id}/aggregate|export résolvent metricName (GAP-25)"
```

---

## Task 4 : MCP `run_analytics_query` + `explain_dataset`

Risque : faible — même patron que la Tâche 3, sur un fichier qui « mirrors »
déjà la route REST par contrat documenté (docstring existante).

**Files:**
- Modify: `core/app/mcp/tools/analytics.py`
- Test: `core/tests/test_mcp_tools_run_analytics_query.py`
- Test: `core/tests/test_mcp_tools_explain_dataset.py`

**Interfaces:**
- Consumes: identique à la Tâche 3.

- [ ] **Step 1 : écrire les tests qui doivent échouer**

Ces deux fichiers utilisent la fixture `app_client`
(`tests/test_mcp_tools_query_features.py`, marquée
`pytestmark = pytest.mark.postgis` — nécessite `CORE_TEST_DATABASE_URL`),
le helper `_register_incidents_collection(app_client)`, `call_tool(app_client,
name, args)`/`call_tool_expecting_error`, et
`app_client.session_factory()` pour toute manipulation DB directe (déjà
utilisé par `_register_incidents_collection` elle-même). Dans
`tests/test_mcp_tools_run_analytics_query.py`, ajouter, à la suite de
`_create_collection_dataset` :

```python
def _set_collection_metrics(app_client, collection_id, metrics):  # noqa: F811
    with app_client.session_factory() as session:
        from app.collections import repository as collections_repo

        col = collections_repo.get_collection(
            session, tenant_id=app_client.tenant.id, collection_id=collection_id
        )
        col.metrics = metrics
        session.commit()


def test_run_analytics_query_resolves_metric_name(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        _write_partition(
            _local_duckdb,
            tenant_id=app_client.tenant.id,
            collection_id=collection_id,
            rows=[
                {
                    "id": 1,
                    "tenant_id": app_client.tenant.id,
                    "titre": "Nid de poule",
                    "_op": "insert",
                    "_lsn": 1,
                    "_ts": 1.0,
                    "geom": Point(2.3, 48.8),
                },
            ],
        )
        _set_collection_metrics(
            app_client,
            collection_id,
            [{"name": "total_incidents", "field": None, "agg": "count", "label": None, "p": None}],
        )
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        result = call_tool(
            app_client,
            "run_analytics_query",
            {
                "datasetId": dataset_item_id,
                "query": {"groupBy": "titre", "measures": [{"metricName": "total_incidents"}]},
            },
        )

    assert result["rows"] == [{"titre": "Nid de poule", "total_incidents": 1}]
```

Dans `tests/test_mcp_tools_explain_dataset.py`, ajouter :

```python
def test_explain_dataset_exposes_collection_metrics(app_client):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        with app_client.session_factory() as session:
            from app.collections import repository as collections_repo

            col = collections_repo.get_collection(
                session, tenant_id=app_client.tenant.id, collection_id=collection_id
            )
            col.metrics = [
                {"name": "total_incidents", "field": None, "agg": "count", "label": None, "p": None}
            ]
            session.commit()
        create_result = call_tool(
            app_client,
            "create_dataset",
            {
                "title": "Incidents (dataset)",
                "source": "collection",
                "collectionId": collection_id,
                "columns": {},
                "timeField": None,
                "reactsToExtent": True,
            },
        )
        result = call_tool(app_client, "explain_dataset", {"datasetId": create_result["pk"]})

    assert result["metrics"] == [
        {"name": "total_incidents", "field": None, "agg": "count", "label": None, "p": None}
    ]
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_mcp_tools_run_analytics_query.py -k resolves_metric_name -v
cd core && uv run pytest tests/test_mcp_tools_explain_dataset.py -k exposes_collection_metrics -v
```

Attendu : FAIL sur les deux (le premier avec une erreur MCP portant
`UnknownAggregateField`/`metricName` faute de résolution, le second avec un
`KeyError`/`AssertionError` sur `result["metrics"]` absent).

- [ ] **Step 3 : brancher `metrics_catalog` dans `run_analytics_query`**

Dans `core/app/mcp/tools/analytics.py`, importer `NamedMetric` (ligne
11-17, ajouter à l'import existant) et, dans la branche `collection` de
`run_analytics_query` (lignes 94-120), juste avant l'appel à
`run_collection_aggregate` (ligne 108) :

```python
                metrics_catalog = [NamedMetric.model_validate(m) for m in col.metrics]
```

puis passer `metrics_catalog=metrics_catalog` à l'appel.

- [ ] **Step 4 : ajouter `metrics` à la réponse d'`explain_dataset`**

Dans la branche `collection` d'`explain_dataset` (lignes 181-194), après la
construction de `schema`/`fields` :

```python
                return {**base, "fields": fields, "metrics": col.metrics}
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_explain_dataset.py -v
```

Attendu : PASS.

- [ ] **Step 6 : suite complète du cœur**

```bash
cd core && uv run pytest -q
```

- [ ] **Step 7 : commit**

```bash
cd core && git add app/mcp/tools/analytics.py tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_explain_dataset.py
git commit -m "feat(core): run_analytics_query résout metricName, explain_dataset expose le catalogue (GAP-25)"
```

---

## Task 5 : édition du catalogue via `PATCH /collections/{id}`

Risque : moyen — touche la validation Pydantic et l'audit log d'une route
déjà chargée.

**Files:**
- Modify: `core/app/collections/schemas.py`
- Modify: `core/app/collections/routes.py`
- Test: `core/tests/test_collections_routes.py`
- Test: `core/tests/test_collections_json_contract.py` (vérifier qu'il
  passe déjà, aucune modification attendue — c'est un contrat qui liste
  déjà les clés de `_collection_json`, y ajouter `metrics` si ce fichier
  énumère les clés attendues de façon exhaustive)

**Interfaces:**
- Consumes: `NamedMetric` (Tâche 2).
- Produces: `CollectionPatch.metrics: list[NamedMetric] | None`,
  `_collection_json()["metrics"]`.

- [ ] **Step 1 : vérifier la direction du contrat de couches AVANT d'écrire
  le code (spec §4.3)**

```bash
cd core && uv run lint-imports
```

(Doit déjà être vert sur l'état actuel — sert de point de référence avant
modification. Puis relire `pyproject.toml` autour de la ligne 244/265 pour
confirmer `app.collections` est bien listé au-dessus d'`app.analytics`.)

- [ ] **Step 2 : écrire les tests qui doivent échouer**

Ce fichier utilise la fixture `env` (retourne
`app, client, Session, admin, _regular, _ddl`, cf.
`test_patch_collection_declares_attachment_fields`, ligne ~687) — routes
préfixées `/v1/`. La lecture d'audit se fait en ouvrant une session
directement sur `Session` et en listant `AuditLog` (cf.
`test_mutations_are_audited`, ligne ~549). Ajouter, à la suite de
`test_patch_collection_rejects_duplicate_attachment_field_keys` :

```python
def test_patch_collection_persists_metrics_catalog(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/v1/collections/incidents",
        json={"metrics": [{"name": "total_incidents", "agg": "count"}]},
    )
    assert res.status_code == 200
    assert res.json()["metrics"] == [
        {"name": "total_incidents", "field": None, "agg": "count", "label": None, "p": None}
    ]

    get_res = client.get("/v1/collections/incidents")
    assert get_res.json()["metrics"] == res.json()["metrics"]


def test_patch_collection_rejects_duplicate_metric_names(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/v1/collections/incidents",
        json={
            "metrics": [
                {"name": "dup", "agg": "count"},
                {"name": "dup", "agg": "sum", "field": "pop"},
            ]
        },
    )
    assert res.status_code == 422
    assert "dup" in res.text


def test_patch_collection_metrics_appears_in_audit_log(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})
    client.patch(
        "/v1/collections/incidents",
        json={"metrics": [{"name": "total_incidents", "agg": "count"}]},
    )

    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        entry = s.scalars(
            select(AuditLog)
            .where(AuditLog.action == "collection.update")
            .order_by(AuditLog.id.desc())
        ).first()
    assert entry.payload["metrics"] == [
        {"name": "total_incidents", "field": None, "agg": "count", "label": None, "p": None}
    ]
```

- [ ] **Step 3 : lancer les tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_collections_routes.py -k metrics -v
```

Attendu : FAIL — `metrics` n'existe pas encore sur `CollectionPatch` (422
« extra field not permitted » ou champ ignoré selon la config Pydantic, à
vérifier) ni sur `_collection_json`.

- [ ] **Step 4 : ajouter `metrics` à `CollectionPatch` + validateur de
  dédoublonnage**

Dans `core/app/collections/schemas.py`, importer :

```python
from app.analytics.aggregate import NamedMetric
```

Ajouter à `CollectionPatch` (après `attachmentFields`, ligne ~72) :

```python
    metrics: list[NamedMetric] | None = None
```

Ajouter le validateur (à la suite de
`_reject_duplicate_attachment_field_keys`, ligne ~98-113) :

```python
    @model_validator(mode="after")
    def _reject_duplicate_metric_names(self) -> "CollectionPatch":
        if self.metrics is None:
            return self
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate metric name(s): {', '.join(duplicates)}")
        return self
```

- [ ] **Step 5 : vérifier `lint-imports` après l'import ajouté**

```bash
cd core && uv run lint-imports
```

Attendu : vert, sans modification de `pyproject.toml`. **Si rouge** :
arrêter, relire `pyproject.toml` en entier autour du bloc `layers` pour
comprendre pourquoi la spec s'est trompée, documenter l'écart réel trouvé
(ne jamais ajouter une exemption sans avoir d'abord compris la cause), puis
corriger — soit en redéclarant `NamedMetric` localement dans
`app.collections.schemas` (dupliquant sa forme), soit avec une exemption
nommée `"app.collections.schemas -> app.analytics.aggregate"` si c'est la
seule issue propre.

- [ ] **Step 6 : brancher l'assignation + `_collection_json` dans
  `routes.py`**

Dans `patch_collection` (ligne ~537-570), après le bloc
`if body.attachmentFields is not None: ...` (ligne 569) :

```python
    if body.metrics is not None:
        col.metrics = [m.model_dump() for m in body.metrics]
```

Dans `_collection_json()` (ligne 153-178), ajouter après `"attachmentFields":
col.attachment_fields,` (ligne 167) :

```python
        "metrics": col.metrics,
```

- [ ] **Step 7 : lancer les tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_collections_routes.py -v
cd core && uv run pytest tests/test_collections_json_contract.py -v
```

Attendu : PASS partout. Si `test_collections_json_contract.py` échoue parce
qu'il énumère une liste fermée de clés attendues sans `metrics`, l'étendre
pour y ajouter `"metrics"` (ne pas le contourner).

- [ ] **Step 8 : suite complète du cœur**

```bash
cd core && uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
```

- [ ] **Step 9 : commit**

```bash
cd core && git add app/collections/schemas.py app/collections/routes.py tests/test_collections_routes.py tests/test_collections_json_contract.py
git commit -m "feat(core): PATCH /collections/{id} édite le catalogue de métriques nommées (GAP-25)"
```

---

## Task 6 : régénération OpenAPI + types TS

Risque : nul (mécanique), mais oubliable (piège CLAUDE.md n°1) — tâche
dédiée pour ne pas la sauter.

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: toutes les routes/modèles modifiés par les Tâches 1-5.

- [ ] **Step 1 : régénérer l'OpenAPI**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
```

- [ ] **Step 2 : régénérer les types TS**

```bash
cd shell && npm run gen:api-types
```

- [ ] **Step 3 : vérifier le diff**

```bash
cd core && git diff --stat openapi.json
cd ../shell && git diff --stat src/api/generated/core-schema.d.ts
```

Attendu : diff **non vide** sur les deux fichiers — nouvelle propriété
`metricName` sur le schéma `AggregateMeasure`, nouvelle propriété `metrics`
sur les schémas `CollectionAdmin`-équivalent et `CollectionPatch`-équivalent
générés. Si un diff est vide, une des Tâches 1-5 n'a pas réellement changé
la forme d'une route REST — revenir vérifier avant de continuer (piège
CLAUDE.md n°1, forme inversée : un diff vide inattendu, pas seulement un
oubli de régénération).

- [ ] **Step 4 : `npm run build` (shell) pour confirmer que les types
  générés compilent**

```bash
cd shell && npm run build
```

Attendu : succès (les Tâches 7-9 n'ont pas encore consommé les nouveaux
types, donc rien ne doit encore les référencer à ce stade — ce build ne
fait que confirmer que le fichier généré est syntaxiquement valide et ne
casse rien d'existant).

- [ ] **Step 5 : commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore: régénère openapi.json + core-schema.d.ts (GAP-25)"
```

---

## Task 7 : types TS `NamedMetric` + champs `metrics` sur `CollectionAdmin`/`CollectionPatchInput`

Risque : faible.

**Files:**
- Modify: `shell/src/api/types.ts`
- Test: aucun test dédié (types purs) — validé par `tsc` à la Tâche 8/9.

**Interfaces:**
- Produces: `NamedMetric` (type TS, consommé par les Tâches 8-9),
  `CollectionAdmin.metrics: NamedMetric[]`,
  `CollectionPatchInput.metrics?: NamedMetric[]`.

- [ ] **Step 1 : ajouter le type et les deux champs**

Dans `shell/src/api/types.ts`, juste avant `export type CollectionAdmin`
(ligne ~827) :

```ts
export type NamedMetric = {
  name: string;
  field: string | null;
  agg: string;
  label: string | null;
  p: number | null;
};
```

Dans `CollectionAdmin` (ligne 827-851), ajouter après `attachmentFields:
{ key: string; label: string }[];` (ligne 840) :

```ts
  metrics: NamedMetric[];
```

Dans `CollectionPatchInput` (ligne 870-886), ajouter après
`attachmentFields?: { key: string; label: string }[];` (ligne 875) :

```ts
  metrics?: NamedMetric[];
```

- [ ] **Step 2 : vérifier que `tsc` ne casse rien**

```bash
cd shell && npx tsc --noEmit
```

Attendu : succès. Si un site de construction de `CollectionAdmin` sans
`metrics` échoue (objet littéral non `Partial`), c'est un site de test/mock
existant à mettre à jour dans cette même tâche — chercher :

```bash
grep -rln "attachmentFields: \[\]" shell/src --include=*.ts --include=*.tsx
```

et ajouter `metrics: []` à côté de chaque `attachmentFields: []` littéral
trouvé (fixtures de test/mocks).

- [ ] **Step 3 : lancer la suite shell complète**

```bash
cd shell && npx vitest run
```

Attendu : PASS (aucun test de comportement ne dépend encore de ce champ —
seule la compilation est en jeu ici).

- [ ] **Step 4 : commit**

```bash
cd shell && git add src/api/types.ts $(git diff --name-only | grep -E '\.(ts|tsx)$')
git commit -m "feat(shell): type NamedMetric, CollectionAdmin/CollectionPatchInput.metrics (GAP-25)"
```

---

## Task 8 : UI d'admin — panneau « Métriques » dans `EditCollectionPanel.tsx`

Risque : moyen — UI React avec état local, patron à reproduire fidèlement.

**Files:**
- Modify: `shell/src/shell/EditCollectionPanel.tsx`
- Test: `shell/src/shell/EditCollectionPanel.test.tsx` (créer si absent —
  vérifier d'abord s'il existe déjà un fichier de test pour ce composant)
- Modify: `shell/src/i18n/catalog.fr.ts` (nouvelles clés `t()`)

**Interfaces:**
- Consumes: `NamedMetric` (Tâche 7), `collection.metrics` (prop déjà portée
  par `CollectionAdmin`).

**Découverte de forme réelle du composant** (à lire avant d'écrire quoi que
ce soit — le brouillon initial de cette tâche supposait à tort des props
`onSave`/`onCancel` directes) : `EditCollectionPanel({ collection, onClose
}: { collection: CollectionAdmin; onClose: () => void })` sauvegarde via
`const updateCollection = useUpdateCollection(collection.id)` (mock
`useUpdateCollection` dans le fichier de test, via `vi.mock("../api/hooks",
...)`) — le bouton `t("common.save")` (« Enregistrer ») appelle
`submit()`, qui construit lui-même l'objet patch et appelle
`updateCollection.mutateAsync({...})` puis `onClose()`. L'UI est un
`<Tabs>` (`ui/kit/Tabs`, `defaultValue="general"`) à 3 onglets existants —
`"general"`, `"metadata"`, `"attachments"` (ligne 246, `t("editCollection.
attachmentsTab")`) — ce plan ajoute un 4e onglet `"metrics"` après
`"attachments"` (ligne ~295, juste avant la fermeture du tableau `tabs={[`).

- [ ] **Step 1 : lire le fichier de test existant en entier**

```bash
cat shell/src/shell/EditCollectionPanel.test.tsx
```

Noter en particulier : `baseCollection: CollectionAdmin` (fixture de base,
ligne ~34, ne porte pas encore `metrics` — Tâche 7 l'a déjà rendu
obligatoire sur le type, donc `metrics: []` doit y être ajouté dans cette
même tâche, Step 2) ; le mock `vi.mock("../api/hooks", () => ({
useUpdateCollection: mockUseUpdateCollection, ... }))` ; le patron de test
d'attachmentFields (`describe("EditCollectionPanel — champs attachment
(SP-40)", ...)`, cliquer l'onglet via `screen.getByRole("tab", { name:
"Pièces jointes" })` avant d'interagir avec son contenu) — **le nouvel
onglet « Métriques » doit être cliqué de la même façon avant que son
contenu soit dans le DOM** (les autres onglets ne sont pas montés tant que
non actifs, cf. comportement de `ui/kit/Tabs` déjà exercé par les tests
attachmentFields).

- [ ] **Step 2 : ajouter `metrics: []` à `baseCollection` (fixture)**

```tsx
const baseCollection: CollectionAdmin = {
  // ... champs existants inchangés ...
  attachmentFields: [],
  metrics: [],
  // ... reste inchangé ...
};
```

- [ ] **Step 3 : écrire les tests qui doivent échouer**

À la suite du `describe("EditCollectionPanel — champs attachment (SP-40)",
...)` existant :

```tsx
describe("EditCollectionPanel — métriques nommées (GAP-25)", () => {
  it("affiche les métriques déjà déclarées", async () => {
    render(
      <EditCollectionPanel
        collection={{
          ...baseCollection,
          metrics: [{ name: "total_incidents", field: null, agg: "count", label: null, p: null }],
        }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métriques" }));
    expect(screen.getByDisplayValue("total_incidents")).toBeInTheDocument();
  });

  it("ajoute puis soumet une nouvelle métrique", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel collection={{ ...baseCollection, metrics: [] }} onClose={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métriques" }));

    await userEvent.type(screen.getByLabelText("Nom de la métrique"), "total_pop");
    // ui/kit/Select est un composant Radix (pas un <select> natif) — même
    // patron d'interaction que le test existant "soumet une licence
    // choisie" plus haut dans ce fichier : ouvrir le combobox puis choisir
    // l'option, jamais userEvent.selectOptions (qui ne s'applique qu'à un
    // <select> HTML natif).
    await userEvent.click(screen.getByRole("combobox", { name: "Fonction de la métrique" }));
    await userEvent.click(await screen.findByRole("option", { name: "Somme" }));
    await userEvent.type(screen.getByLabelText("Champ de la métrique"), "pop");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une métrique" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        metrics: [{ name: "total_pop", field: "pop", agg: "sum", label: null, p: null }],
      }),
    );
  });

  it("supprime une métrique existante", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{
          ...baseCollection,
          metrics: [{ name: "total_pop", field: "pop", agg: "sum", label: null, p: null }],
        }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métriques" }));
    await userEvent.click(screen.getByRole("button", { name: "Supprimer la métrique total_pop" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ metrics: [] }));
  });
});
```

- [ ] **Step 4 : lancer les tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx -t "métriques nommées"
```

Attendu : FAIL — `metrics` n'existe pas sur `CollectionAdmin` avant la
Tâche 7 (déjà faite à ce stade du plan — donc l'échec ici porte sur
l'absence de l'onglet « Métriques »/des champs, pas sur le typage).

- [ ] **Step 5 : implémenter l'onglet « Métriques »**

Dans `shell/src/shell/EditCollectionPanel.tsx`, ajouter l'état (à la suite
de `attachmentFields`, ligne 29) :

```tsx
  const [metrics, setMetrics] = useState(collection.metrics);
  const [draftMetricName, setDraftMetricName] = useState("");
  const [draftMetricAgg, setDraftMetricAgg] = useState<string>("count");
  const [draftMetricField, setDraftMetricField] = useState("");
```

Fonctions (à la suite d'`addAttachmentField`/`removeAttachmentField`,
lignes 80-91) :

```tsx
  function addMetric() {
    const name = draftMetricName.trim();
    if (!name || metrics.some((m) => m.name === name)) return;
    setMetrics((ms) => [
      ...ms,
      {
        name,
        agg: draftMetricAgg,
        field: draftMetricAgg === "count" ? null : draftMetricField.trim() || null,
        label: null,
        p: null,
      },
    ]);
    setDraftMetricName("");
    setDraftMetricField("");
  }

  function removeMetric(name: string) {
    setMetrics((ms) => ms.filter((m) => m.name !== name));
  }
```

Ajouter `metrics` au payload de `submit()` (ligne 57-73, à la suite de
`attachmentFields,`) :

```tsx
      await updateCollection.mutateAsync({
        title,
        description,
        isPublic,
        editable,
        attachmentFields,
        metrics,
        // ... reste inchangé ...
```

Ajouter un 4e onglet, juste après la fermeture de l'onglet `"attachments"`
(après la ligne 295 `},`, avant `]}` ligne 296) :

```tsx
            {
              value: "metrics",
              label: t("editCollection.metricsTab"),
              content: (
                <div className="flex flex-col gap-1 pt-3">
                  <p className="text-sm font-medium text-ink">
                    {t("editCollection.metricsTitle")}
                  </p>
                  <ul className="flex flex-col gap-1">
                    {metrics.map((m) => (
                      <li key={m.name} className="flex items-center gap-2">
                        <Input
                          aria-label={t("editCollection.existingMetricNameAria", { name: m.name })}
                          value={m.name}
                          readOnly
                          className="text-xs"
                        />
                        <span className="text-xs text-ink-2">
                          {m.agg}
                          {m.field ? `(${m.field})` : ""}
                        </span>
                        <button
                          type="button"
                          className="text-danger underline text-xs"
                          onClick={() => removeMetric(m.name)}
                        >
                          {t("editCollection.removeMetricAria", { name: m.name })}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2">
                    <Input
                      aria-label={t("editCollection.metricNameAria")}
                      value={draftMetricName}
                      onChange={(e) => setDraftMetricName(e.target.value)}
                    />
                    <Select
                      aria-label={t("editCollection.metricAggAria")}
                      value={draftMetricAgg}
                      onValueChange={setDraftMetricAgg}
                      options={[
                        { value: "count", label: t("editCollection.metricAggCount") },
                        { value: "sum", label: t("editCollection.metricAggSum") },
                        { value: "avg", label: t("editCollection.metricAggAvg") },
                        { value: "min", label: t("editCollection.metricAggMin") },
                        { value: "max", label: t("editCollection.metricAggMax") },
                        {
                          value: "countDistinct",
                          label: t("editCollection.metricAggCountDistinct"),
                        },
                        { value: "median", label: t("editCollection.metricAggMedian") },
                        { value: "stddev", label: t("editCollection.metricAggStddev") },
                      ]}
                    />
                    {draftMetricAgg !== "count" && (
                      <Input
                        aria-label={t("editCollection.metricFieldAria")}
                        value={draftMetricField}
                        onChange={(e) => setDraftMetricField(e.target.value)}
                      />
                    )}
                    <Button type="button" variant="outline" size="sm" onClick={addMetric}>
                      {t("editCollection.addMetricButton")}
                    </Button>
                  </div>
                </div>
              ),
            },
```

(Utilise `Select` du kit, déjà importé dans ce fichier pour l'onglet
« Métadonnées ouvertes » — pas un `<select>` natif : ce fichier a déjà
migré ses menus déroulants vers `ui/kit/Select`, cf. le contrôle
« Licence » quelques lignes plus haut ; l'onglet attachmentFields voisin
utilise encore un `<button>` natif pour « Supprimer », pas `Button` — reproduit
à l'identique ici pour la cohérence de CE panneau plutôt que de suivre la
convention `Button`-partout d'autres écrans, cf. décision « `<button>`
natif vs `Button` du kit » de `CLAUDE.md`, qui réserve `<button>` natif à
« une action répétée par ligne dans une liste dense » — exactement ce cas.
**Percentile délibérément omis de ce v0 d'onglet d'authoring** — `p`
persiste toujours à `null` pour toute métrique créée depuis ce panneau ;
une métrique `percentile` ne peut être déclarée que via un futur ajustement
de cet onglet ou via l'API directement. Documenter cette limitation dans le
message de commit — pas un défaut à corriger silencieusement, une
simplification de v0 assumée dans ce plan (absente du texte de la spec,
donc à signaler explicitement plutôt que noyée dans le diff).)

Note importante sur le nom du bouton de suppression pour les tests Step 3 :
le libellé visible ET l'aria n'en font qu'un ici (`{t("editCollection.
removeMetricAria", { name: m.name })}` sert à la fois de contenu de bouton
et de nom accessible, cf. `screen.getByRole("button", { name: "Supprimer la
métrique total_pop" })` dans le test Step 3) — même patron que
`removeAttachmentField` voisin (`{t("editCollection.removeField")}`, texte
seul, sans variante `aria-label` séparée).

- [ ] **Step 6 : ajouter les clés i18n**

Dans `shell/src/i18n/catalog.fr.ts`, ajouter (bloc `editCollection.*`
existant, à la suite de `attachmentFieldsTitle`, ligne ~593) — interpolation
à simple accolade `{name}`, format déjà utilisé par
`editCollection.existingKeyAria` (ligne 594), pas `{{name}}` :

```ts
  "editCollection.metricsTab": "Métriques",
  "editCollection.metricsTitle": "Métriques",
  "editCollection.existingMetricNameAria": "Métrique existante : {name}",
  "editCollection.metricNameAria": "Nom de la métrique",
  "editCollection.metricAggAria": "Fonction de la métrique",
  "editCollection.metricFieldAria": "Champ de la métrique",
  "editCollection.metricAggCount": "Nombre",
  "editCollection.metricAggSum": "Somme",
  "editCollection.metricAggAvg": "Moyenne",
  "editCollection.metricAggMin": "Minimum",
  "editCollection.metricAggMax": "Maximum",
  "editCollection.metricAggCountDistinct": "Nombre distinct",
  "editCollection.metricAggMedian": "Médiane",
  "editCollection.metricAggStddev": "Écart-type",
  "editCollection.addMetricButton": "Ajouter une métrique",
  "editCollection.removeMetricAria": "Supprimer la métrique {name}",
```

- [ ] **Step 7 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx
```

- [ ] **Step 8 : garde i18n + suite complète**

```bash
cd shell && npm run lint
npx vitest run
```

Attendu : `npm run lint` (inclut le détecteur i18n) vert — aucune chaîne
française codée en dur introduite hors `t()`.

- [ ] **Step 9 : commit**

```bash
cd shell && git add src/shell/EditCollectionPanel.tsx src/shell/EditCollectionPanel.test.tsx src/i18n/catalog.fr.ts
git commit -m "feat(shell): panneau d'édition du catalogue de métriques nommées (GAP-25)"
```

---

## Task 9 : autofill de métrique nommée dans `QuerySummaryBuilder.tsx`

Risque : moyen — doit prouver l'invariant central de la spec (§1.5, §4.5) :
le payload de pipeline compilé reste identique, aucun `metricName` envoyé.

**Files:**
- Modify: `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`
- Test: `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx` (lire
  l'existant s'il y en a un, sinon en créer un minimal)
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `NamedMetric` (Tâche 7), `MetricConfig`/`SummaryConfig`
  (`inferSchema.ts`, inchangés), `compileVisualQueryToPipeline`
  (`compilePipeline.ts`, inchangé — utilisé uniquement par le test
  d'équivalence, pas par le composant).
- Produces: prop supplémentaire `namedMetrics?: NamedMetric[]` sur
  `QuerySummaryBuilder`.

- [ ] **Step 1 : écrire le test d'autofill (payload identique) — doit
  échouer**

Dans `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx` :

```tsx
import { compileVisualQueryToPipeline } from "./compilePipeline";

// Forme réelle de CollectionSchema (cf. src/builder/visualQuery/
// QuerySummaryBuilder.test.tsx existant) : collection/pk obligatoires,
// pas seulement fields/geometry comme un brouillon plus rapide le
// supposerait.
const SCHEMA: CollectionSchema = {
  collection: "villes",
  pk: "id",
  geometry: null,
  fields: [
    { name: "region", type: "string", required: true },
    { name: "pop", type: "integer", required: false },
  ],
};

const NAMED_METRICS: NamedMetric[] = [
  { name: "total_pop", field: "pop", agg: "sum", label: null, p: null },
];

test("sélectionner une métrique nommée renseigne function/sourceColumn", async () => {
  const onChange = vi.fn();
  render(
    <QuerySummaryBuilder
      schema={SCHEMA}
      value={{ groupBy: [], metrics: [{ alias: "m1", function: "count", sourceColumn: null, p: null }] }}
      onChange={onChange}
      namedMetrics={NAMED_METRICS}
    />,
  );

  await userEvent.selectOptions(
    screen.getByLabelText(/métrique nommée/i),
    "total_pop",
  );

  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      metrics: [
        expect.objectContaining({ function: "sum", sourceColumn: "pop", p: null }),
      ],
    }),
  );
});

test("le payload de pipeline compilé est identique entre autofill et construction manuelle", () => {
  const viaAutofill: MetricConfig = {
    alias: "total_pop",
    function: "sum",
    sourceColumn: "pop",
    p: null,
  };
  const manual: MetricConfig = {
    alias: "total_pop",
    function: "sum",
    sourceColumn: "pop",
    p: null,
  };

  const stateAutofill = {
    title: "t",
    baseCollectionId: "villes",
    filters: [],
    join: null,
    summary: { groupBy: ["region"], metrics: [viaAutofill] },
    refreshPolicy: null,
  };
  const stateManual = { ...stateAutofill, summary: { groupBy: ["region"], metrics: [manual] } };

  const compiledAutofill = compileVisualQueryToPipeline(stateAutofill, SCHEMA, null, "out", "item-1");
  const compiledManual = compileVisualQueryToPipeline(stateManual, SCHEMA, null, "out", "item-1");

  expect(compiledAutofill).toEqual(compiledManual);
});
```

(Ce 2e test est délibérément trivial dans sa forme — `viaAutofill`/`manual`
sont construits identiques — car il vérifie une PROPRIÉTÉ ARCHITECTURALE
[`QuerySummaryBuilder` ne doit produire aucune structure de données
différente selon l'origine du choix], pas un comportement du compilateur
lui-même. La vraie preuve que l'UI ne fuit rien de plus est le 1er test :
`onChange` ne reçoit QUE `function`/`sourceColumn`/`p`, jamais de champ
`metricName`/`sourceMetricName` — vérifier explicitement son absence :)

```tsx
test("onChange ne reçoit jamais de référence à la métrique nommée elle-même", async () => {
  const onChange = vi.fn();
  render(
    <QuerySummaryBuilder
      schema={SCHEMA}
      value={{ groupBy: [], metrics: [{ alias: "m1", function: "count", sourceColumn: null, p: null }] }}
      onChange={onChange}
      namedMetrics={NAMED_METRICS}
    />,
  );

  await userEvent.selectOptions(screen.getByLabelText(/métrique nommée/i), "total_pop");

  const [[nextValue]] = onChange.mock.calls;
  expect(Object.keys(nextValue.metrics[0]).sort()).toEqual(
    ["alias", "function", "p", "sourceColumn"].sort(),
  );
});
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/builder/visualQuery/QuerySummaryBuilder.test.tsx -t "métrique nommée"
```

Attendu : FAIL — la prop `namedMetrics` et le sélecteur n'existent pas
encore ; le test d'équivalence de payload (2e test) passe probablement déjà
trivialement (il ne teste pas encore le composant) — le garder comme filet
de non-régression permanent, pas comme test à faire échouer.

- [ ] **Step 3 : implémenter le sélecteur**

Dans `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`, ajouter à la
signature du composant (ligne ~31-39) :

```tsx
export function QuerySummaryBuilder({
  schema,
  value,
  onChange,
  namedMetrics = [],
}: {
  schema: CollectionSchema;
  value: SummaryConfig;
  onChange: (next: SummaryConfig) => void;
  namedMetrics?: NamedMetric[];
}) {
```

Ajouter la fonction d'autofill (à la suite d'`updateMetric`, ligne ~46-60) :

```tsx
  function applyNamedMetric(index: number, metricName: string) {
    const stored = namedMetrics.find((m) => m.name === metricName);
    if (!stored) return;
    updateMetric(index, {
      function: stored.agg as MetricFunction,
      sourceColumn: stored.field,
      p: stored.agg === "percentile" ? stored.p : null,
    });
  }
```

Ajouter le `<select>` dans le JSX de chaque ligne de métrique (à la suite
du `<select>` de fonction existant, avant le `<select>` de colonne, ligne
~92-104), conditionné à `namedMetrics.length > 0` :

```tsx
          {namedMetrics.length > 0 && (
            <select
              aria-label={t("querySummaryBuilder.namedMetricAria", { n: i + 1 })}
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
              value=""
              onChange={(e) => {
                if (e.target.value) applyNamedMetric(i, e.target.value);
              }}
            >
              <option value="">{t("querySummaryBuilder.namedMetricPlaceholder")}</option>
              {namedMetrics.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          )}
```

Importer `NamedMetric` en tête de fichier :

```tsx
import type { NamedMetric } from "../../api/types";
```

- [ ] **Step 4 : ajouter les clés i18n**

Dans `shell/src/i18n/catalog.fr.ts`, à la suite du bloc
`querySummaryBuilder.*` existant :

```ts
  "querySummaryBuilder.namedMetricAria": "Métrique nommée pour la ligne {{n}}",
  "querySummaryBuilder.namedMetricPlaceholder": "Métrique nommée…",
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/builder/visualQuery/QuerySummaryBuilder.test.tsx
```

Attendu : PASS, y compris le test « onChange ne reçoit jamais de référence
à la métrique nommée elle-même » — c'est la preuve concrète que
`MetricConfig`/`compilePipeline.ts` restent inchangés.

- [ ] **Step 6 : câbler l'appelant réel, `shell/src/pages/VisualQueryWizardPage.tsx`**

Ce fichier porte déjà `collectionsQuery = useCollectionsAdmin({ enabled:
true })` (ligne 51, `CollectionAdmin[]`) et `baseCollectionId` (ligne 57,
état du sélecteur de collection de base) — la collection de base résolue
n'a pas encore de variable dédiée, ajouter juste avant l'appel à
`QuerySummaryBuilder` (ligne ~440) :

```tsx
              const baseCollection = collectionsQuery.data?.find((c) => c.id === baseCollectionId);
```

(ou, si une variable équivalente existe déjà à un autre endroit du
composant au moment d'implémenter — relire les lignes 51-230 en entier
avant d'en ajouter une seconde). Puis, sur le `<QuerySummaryBuilder
schema={baseSchema} ...>` existant (ligne 440-443), ajouter :

```tsx
                        <QuerySummaryBuilder
                          schema={baseSchema}
                          value={summary ?? { groupBy: [], metrics: [] }}
                          onChange={setSummary}
                          namedMetrics={baseCollection?.metrics ?? []}
                        />
```

(Les 3 premières props sont déjà celles du fichier réel — ne pas les
redéviner autrement au moment d'implémenter, seule `namedMetrics` est
ajoutée ; vérifier les noms exacts de `value`/`onChange` déjà en place
avant d'écrire, ce squelette peut différer d'un détail du fichier réel.)

- [ ] **Step 7 : garde i18n + suite complète shell**

```bash
cd shell && npm run lint
npx vitest run
npm run build
```

- [ ] **Step 8 : commit**

```bash
cd shell && git add src/builder/visualQuery/QuerySummaryBuilder.tsx src/builder/visualQuery/QuerySummaryBuilder.test.tsx src/i18n/catalog.fr.ts $(git diff --name-only | grep -v test)
git commit -m "feat(shell): autofill de métrique nommée dans QuerySummaryBuilder, sans changement de payload compilé (GAP-25)"
```

---

## Task 10 : revue finale de branche

Risque : nul en soi (aucun code de production modifié), mais c'est la seule
tâche qui peut encore détecter un défaut de croisement entre tâches (piège
CLAUDE.md n°4) et une violation du périmètre exclu (spec §3).

**Files:**
- Aucun fichier de production modifié.
- Peut modifier : `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`
  ou l'équivalent le plus récent (entrée `### Livré`), et
  `docs/revue/2026-09-04-analyse-gaps.md` (GAP-25 : ouvert → fermé),
  conformément à la discipline CLAUDE.md « à la clôture d'un SP ». Si ce
  plan est exécuté comme un SP à part entière, régénérer aussi le bilan de
  fonctionnalités après avoir ajouté les nouvelles surfaces à
  `docs/revue/inventaire-fonctionnalites.jsonl`
  (`cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py
  --repo .. --write`) — nouvelles surfaces : aucune nouvelle route REST/
  outil MCP (extension de routes/tools existants, pas de nouvelle entrée
  d'inventaire a priori ; vérifier contre `test_feature_inventory.py` s'il
  exige quand même une entrée pour un champ ajouté — sinon, rien à faire
  ici).

- [ ] **Step 1 : vérifier mécaniquement l'absence de diff sur les 4
  fichiers explicitement exclus**

```bash
git diff main...HEAD --stat -- core/app/alerts/jobs.py core/app/appexport/miniserver/main.py core/app/appexport/snapshot.py core/app/harvest/routes.py
```

Attendu : sortie **vide**. Si un de ces fichiers apparaît, c'est une
violation de la spec §3 — revenir sur la tâche qui l'a introduite et la
corriger avant de continuer.

- [ ] **Step 2 : grep de contrôle — aucun de ces fichiers ne référence
  `metrics_catalog`/`NamedMetric`**

```bash
grep -n "metrics_catalog\|NamedMetric" core/app/alerts/jobs.py core/app/appexport/miniserver/main.py core/app/appexport/snapshot.py core/app/harvest/routes.py
```

Attendu : aucune correspondance (grep sort avec un code de retour non nul,
c'est le résultat attendu ici).

- [ ] **Step 3 : suite complète cœur, avec portes de qualité**

```bash
cd core
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

Attendu : tout vert, couverture non régressive.

- [ ] **Step 4 : suite complète shell, avec portes de qualité**

```bash
cd shell
npx vitest run
npm run lint && npm run format:check
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
```

Attendu : tout vert, couverture non régressive, chunk d'entrée sous le
seuil `.bundle-size-threshold`.

- [ ] **Step 5 : E2E ciblée (si un scénario existant touche l'écran
  d'admin de collection ou le wizard de requête visuelle)**

```bash
cd shell && grep -rln "EditCollectionPanel\|attachmentFields\|QuerySummaryBuilder\|requête visuelle" e2e --include=*.spec.ts
```

Lancer les specs trouvées en ciblé :

```bash
npx playwright test <specs trouvées> --project=chromium
```

Attendu : PASS. Puis suite E2E complète pour détecter une régression
croisée (piège CLAUDE.md n°6) :

```bash
npm run e2e
```

Comparer le compte de résultats à la dernière mesure connue documentée dans
`CLAUDE.md` (`### Commandes`) — aucune régression de compte, l'unique échec
préexistant documenté reste le seul rouge.

- [ ] **Step 6 : checklist de revue croisée (piège CLAUDE.md n°4) — à
  vérifier une par une, par lecture directe du code, pas par mémoire du
  plan**

  - `_measures_for` est bien appelé avec un `catalog_by_name` construit
    UNE SEULE fois dans `run_collection_aggregate` (pas reconstruit à
    chaque appel) : `grep -n "catalog_by_name" core/app/analytics/aggregate.py`.
  - Les 2 endroits de `features/routes.py` (`aggregate_features` ET
    `export_collection_aggregate`) construisent `metrics_catalog` de la
    même façon (`NamedMetric.model_validate(m) for m in col.metrics`) —
    pas une variante différente sur l'un des deux :
    `grep -n "metrics_catalog" core/app/features/routes.py` doit montrer 2
    occurrences de construction identiques.
  - `explain_dataset` et `run_analytics_query` (MCP) restent tous deux à
    jour l'un par rapport à l'autre (le docstring de `run_analytics_query`
    s'engage à « mirror » la route REST — vérifier que ce mirroring est
    resté vrai après les Tâches 3-4, pas seulement au moment où chaque
    tâche a été écrite isolément).
  - `_collection_json()` (REST, `collections/routes.py`) expose `metrics`
    — confirmer qu'aucun AUTRE endroit ne sérialise une `Collection` en
    JSON pour une réponse HTTP sans passer par cette fonction (un second
    sérialiseur oublié serait invisible à `test_collections_json_contract.py`
    s'il ne couvre que celui-ci) : `grep -rn "def _collection_json\|collectionJson =" core/app` en dehors de `snapshot.py` (déjà exclu, Step 1-2).
  - Le composant `EditCollectionPanel.tsx` envoie bien `metrics` dans
    TOUTES les branches de sauvegarde du formulaire (pas seulement le
    chemin heureux testé) — relire la fonction de soumission en entier.
  - `QuerySummaryBuilder.tsx` : le sélecteur de métrique nommée
    n'apparaît que si `namedMetrics.length > 0` — confirmer que l'appelant
    (Tâche 9, Step 6) passe bien un tableau, jamais `undefined` sans
    valeur par défaut côté composant (déjà gardé par `= []` sur le
    paramètre, mais vérifier que l'appelant ne passe pas `null`
    explicitement, ce que le défaut de paramètre ne rattraperait pas).

- [ ] **Step 7 : mettre à jour la documentation de clôture**

Ajouter une ligne dans `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`
(ou son successeur le plus récent si ce fichier a été remplacé entre-temps
— vérifier `docs/superpowers/` avant d'écrire) décrivant ce chantier,
passer `GAP-25` d'ouvert à fermé dans
`docs/revue/2026-09-04-analyse-gaps.md` avec référence à ce plan, et
ajouter une ligne dans `### Livré` de `CLAUDE.md`.

- [ ] **Step 8 : commit final de documentation**

```bash
git add docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md \
        docs/revue/2026-09-04-analyse-gaps.md \
        CLAUDE.md
git commit -m "docs: clôture GAP-25 (couche sémantique minimale, métriques nommées)"
```
