# SP-24 — Carte interrogeable : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un lecteur peut cliquer une entité sur une carte publiée et voir ses attributs, y compris quand le jeu de données est assez gros pour être tuilé.

**Architecture:** les tuiles vectorielles passent désormais par le cœur (`ST_AsMVT` sous `rls_scope` + `can()`) au lieu de Martin, ce qui donne à une couche tuilée un `collectionId` — donc un schéma de champs pour le popup, une porte d'autorisation, et le socle de SP-25. Côté shell, un composant `MapPopup` unique branché dans `MapView`, seul point de passage des trois consommateurs de carte du dépôt. Le popup se décrit dans la config (`PopupConfig`), jamais en code.

**Tech Stack:** FastAPI + SQLAlchemy Core (`text()` paramétré) + PostGIS 3 (`ST_AsMVT`/`ST_AsMVTGeom`/`ST_TileEnvelope`) ; React 19 + MapLibre GL + `cel-js` + `marked`/DOMPurify ; pytest (`@pytest.mark.postgis`) et Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-08-22-sp24-carte-interrogeable-design.md`

## Global Constraints

- **Docs et messages utilisateur en français ; code et identifiants en anglais.** (CLAUDE.md)
- **Commits conventional, petits, un sujet** (`feat(core):`, `fix(shell):`, `test(shell):`…). Le `commitlint` du dépôt refuse un sujet en majuscule initiale — vérifié en pratique par SP-22.
- **En-tête `// SPDX-License-Identifier: Apache-2.0`** sur tout nouveau fichier TS/TSX, **`# SPDX-License-Identifier: Apache-2.0`** sur tout nouveau fichier Python.
- **TDD systématique** : le test échoue d'abord, et on le voit échouer.
- **`ItemClient` est le sas** : le shell ne parle jamais au cœur autrement qu'à travers lui (CLAUDE.md règle 1).
- **Tout objet de plateforme est un document déclaratif schématisé** (CLAUDE.md règle 2) : le popup se décrit dans `MapConfig`/`AppConfig`, jamais en code.
- **Aucune migration hors la 0028** nommée par la tâche 5. La dernière migration existante est `0027_app_export_jobs.py`.
- **Identifiants SQL toujours quotés** par le `quote_ident` existant (`core/app/collections/ddl.py:13`) ; les valeurs toujours paramétrées, jamais interpolées.
- **Aucune entrée `audit_log` par tuile** (décision de spec §3.1) : une vue de carte produit des centaines de tuiles.
- Commandes de référence : `cd core && uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict app/auth app/secrets app/analytics app/copilot`, `uv run lint-imports` ; `cd shell && npm run test`, `npm run lint`, `npm run format:check`, `npm run build`, `npm run e2e`.
- Compteurs de référence à ne pas faire baisser (mesurés 2026-08-22, fin de SP-23) : core **1675 passed / 154 skipped**, couverture **85,16 %** (seuil 85) ; shell **155 fichiers / 1302 tests**, couverture **89,24 %** (seuil 88).

---

## Structure de fichiers

**Cœur — créés**

| Fichier | Responsabilité |
|---|---|
| `core/app/features/tiles.py` | Helpers purs (validation z/x/y, construction du SQL MVT) **et** la route. Fichier séparé de `routes.py`, qui fait déjà 641 lignes. |
| `core/alembic/versions/0028_collection_spatial_index.py` | Rattrapage de l'index GiST sur les collections déjà enregistrées. |
| `core/tests/test_features_tiles.py` | Tests non-postgis : validation des coordonnées, forme du SQL, 400/404. |
| `core/tests/test_features_tiles_postgis.py` | Tests `@pytest.mark.postgis` : contenu de la tuile, isolation RLS, anonyme. |
| `core/tests/test_collections_spatial_index.py` | Tests `@pytest.mark.postgis` de l'index GiST et de la migration 0028. |

**Cœur — modifiés**

| Fichier | Changement |
|---|---|
| `core/app/collections/ddl.py` | Index GiST idempotent dans `apply_collection_ddl`. |
| `core/app/configs/schemas.py:76-89` | Quatre champs optionnels sur `MapLayer` + le modèle `PopupConfig`. |
| `core/app/main.py:181` | Montage de `tiles_routes.router`. |
| `core/openapi.json` + `shell/src/api/generated/` | Régénérés (tâche 7). |

**Shell — créés**

| Fichier | Responsabilité |
|---|---|
| `shell/src/map/popupTemplate.ts` | Module **pur** : interpolation `${…}` d'un gabarit markdown. |
| `shell/src/map/popupContent.ts` | Module **pur** : résolution d'un `PopupConfig` + propriétés → titre + lignes. |
| `shell/src/map/MapPopup.tsx` | Composant **présentationnel** : reçoit titre/lignes/html + position, rend le popup. |
| `shell/src/map/PopupEditor.tsx` | Éditeur d'auteur partagé par les deux surfaces. |
| `shell/e2e/map-popup.spec.ts` | La preuve de sortie du plan d'action. |

**Shell — modifiés**

| Fichier | Changement |
|---|---|
| `shell/src/api/types.ts:99-146,169-181` | `PopupConfig`, `PopupField`, champs sur `MapLayer`, retrait de `"martin"` de `LayerSource.service`. |
| `shell/src/map/MapView.tsx` | Type de couche dérivé de `geometryKind`, handler de clic sur `vector`, état du popup, `transformRequest` sur `/collections/`. |
| `shell/src/map/LayersPanel.tsx` | Montage de `PopupEditor` par couche. |
| `shell/src/map/LayerPicker.tsx:6-32` | `toMapLayer` propage `collectionId`/`geometryKind`/`pkColumn`. |
| `shell/src/builder/widgets/mapWidget.tsx` | `PopupEditor` dans le `PropsPanel`, `popup` sur la couche `feature` produite. |
| `shell/src/api/itemClient.ts:393-431,619-633` | Retrait de `fetchMartinSources`, collections rendues en `vector`. |
| `shell/src/config.ts:55`, `shell/playwright.config.ts:15`, `docker-compose.prod.yml:36-43,147` | Retrait du câblage Martin. |
| `shell/eslint.config.js:88-91` | `MapPopup.tsx` rejoint le bloc d'exception. |
| `shell/src/test/MockMaplibreMap.ts` | Ajout de `project()`. |

---

## Task 1 : helpers purs des tuiles (validation + SQL)

**Files:**
- Create: `core/app/features/tiles.py`
- Test: `core/tests/test_features_tiles.py`

**Interfaces:**
- Consumes: `TableInfo`, `ColumnInfo` de `app.collections.introspection`.
- Produces:
  - `class InvalidTileCoords(Exception)`
  - `validate_tile_coords(z: int, x: int, y: int) -> None`
  - `mvt_property_columns(info: TableInfo) -> list[str]`
  - `mvt_feature_id_column(info: TableInfo) -> str | None`
  - `build_mvt_sql(quote: Callable[[str], str], info: TableInfo) -> str`
  - `MVT_EXTENT = 4096`, `MVT_BUFFER = 64`, `MAX_TILE_ZOOM = 24`

- [ ] **Step 1: Write the failing tests**

`core/tests/test_features_tiles.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Helpers purs du service de tuiles MVT (spec SP-24 §3.1). Aucun accès base :
on teste la validation des coordonnées, la liste des colonnes de propriétés et
la forme du SQL produit — le SQL réel est exercé par
test_features_tiles_postgis.py."""

import pytest

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.tiles import (
    InvalidTileCoords,
    build_mvt_sql,
    mvt_feature_id_column,
    mvt_property_columns,
    validate_tile_coords,
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _info(pk_type: str = "integer", **kwargs) -> TableInfo:
    defaults = dict(
        table_name="demo_incidents",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type=pk_type, required=False),
            ColumnInfo(name="titre", type="string", required=True),
            ColumnInfo(name="tenant_id", type="string", required=True),
        ],
    )
    defaults.update(kwargs)
    return TableInfo(**defaults)


@pytest.mark.parametrize("coords", [(0, 0, 0), (1, 1, 1), (24, 0, 0), (2, 3, 3)])
def test_valid_coords_are_accepted(coords):
    assert validate_tile_coords(*coords) is None


@pytest.mark.parametrize(
    "coords",
    [(-1, 0, 0), (25, 0, 0), (0, 1, 0), (0, 0, 1), (1, 2, 0), (1, 0, 2), (2, -1, 0)],
)
def test_out_of_range_coords_are_rejected(coords):
    with pytest.raises(InvalidTileCoords):
        validate_tile_coords(*coords)


def test_tenant_id_never_becomes_a_tile_property():
    assert mvt_property_columns(_info()) == ["id", "titre"]


def test_integer_primary_key_becomes_the_mvt_feature_id():
    assert mvt_feature_id_column(_info(pk_type="integer")) == "id"


def test_non_integer_primary_key_yields_no_feature_id():
    # PostGIS ignore un feature_id non entier ; on préfère ne rien passer
    # plutôt que dépendre de sa clémence. Le shell retombe alors sur la
    # propriété de PK (cf. Task 10).
    assert mvt_feature_id_column(_info(pk_type="string")) is None


def test_sql_filters_on_the_untransformed_geometry_column():
    sql = build_mvt_sql(_quote, _info())
    # Le && porte sur t."geom" brut, jamais sur ST_Transform(t."geom", …) :
    # sinon l'index GiST de la Task 4 ne sert à rien (spec §3.2).
    assert 't."geom" && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)' in sql
    assert 'ST_Transform(t."geom", 3857) &&' not in sql


def test_sql_quotes_every_identifier_and_carries_the_columns():
    sql = build_mvt_sql(_quote, _info())
    assert 'public."demo_incidents"' in sql
    assert 't."titre" AS "titre"' in sql
    assert '"tenant_id"' not in sql
    assert "ST_AsMVT(" in sql
    assert "ST_AsMVTGeom(" in sql


def test_sql_drops_rows_whose_tile_geometry_is_null():
    assert "IS NOT NULL" in build_mvt_sql(_quote, _info())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_tiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.features.tiles'`

- [ ] **Step 3: Write the implementation**

`core/app/features/tiles.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Tuiles vectorielles MVT servies par le cœur (spec SP-24 §3.1).

Pourquoi ici et pas Martin : Martin se connecte en propriétaire des tables,
donc hors RLS, et n'a aucune notion de collection ni de `can()`. Servir le MVT
depuis le cœur donne les trois d'un coup — autorisation, isolation tenant, et
un `collectionId` sur la couche.

Ce module est volontairement coupé en deux : des helpers purs (testés sans
base) et une route mince qui les assemble."""

from collections.abc import Callable

from app.collections.introspection import TableInfo

MVT_EXTENT = 4096
MVT_BUFFER = 64
MAX_TILE_ZOOM = 24

# tenant_id est une colonne réelle de toute table de collection (ddl.py) et
# TableInfo.columns la contient : elle ne doit jamais partir dans une tuile.
_EXCLUDED_PROPERTIES = frozenset({"tenant_id"})


class InvalidTileCoords(Exception):
    pass


def validate_tile_coords(z: int, x: int, y: int) -> None:
    if z < 0 or z > MAX_TILE_ZOOM:
        raise InvalidTileCoords(f"z must be within [0, {MAX_TILE_ZOOM}]")
    limit = 1 << z
    if not (0 <= x < limit) or not (0 <= y < limit):
        raise InvalidTileCoords(f"x and y must be within [0, {limit - 1}] at z={z}")


def mvt_property_columns(info: TableInfo) -> list[str]:
    """TableInfo.columns exclut déjà la colonne de géométrie (introspection_pg)
    mais inclut tenant_id et la PK."""
    return [c.name for c in info.columns if c.name not in _EXCLUDED_PROPERTIES]


def mvt_feature_id_column(info: TableInfo) -> str | None:
    """ST_AsMVT n'accepte un feature_id que sur une colonne entière. On ne le
    passe donc que dans ce cas — le shell retombe sinon sur la propriété de PK."""
    for c in info.columns:
        if c.name == info.pk_column:
            return info.pk_column if c.type == "integer" else None
    return None


def build_mvt_sql(quote: Callable[[str], str], info: TableInfo) -> str:
    assert info.geometry_column is not None, "build_mvt_sql exige une géométrie"
    table = f"public.{quote(info.table_name)}"
    geom = f"t.{quote(info.geometry_column)}"
    props = ", ".join(
        f"t.{quote(name)} AS {quote(name)}" for name in mvt_property_columns(info)
    )
    props_clause = f", {props}" if props else ""
    return (
        "SELECT ST_AsMVT(tile, :layer, :extent, 'geom', :fid) FROM ("
        f"SELECT ST_AsMVTGeom(ST_Transform({geom}, 3857), "
        "ST_TileEnvelope(:z, :x, :y), :extent, :buffer, true) AS geom"
        f"{props_clause} "
        f"FROM {table} t "
        # Le filtre porte sur la géométrie brute pour rester indexable par le
        # GiST posé par apply_collection_ddl : ST_Transform à gauche du && le
        # rendrait inutilisable.
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)"
        ") AS tile WHERE tile.geom IS NOT NULL"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_tiles.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Lint**

Run: `cd core && uv run ruff check app/features/tiles.py tests/test_features_tiles.py && uv run ruff format --check app/features/tiles.py tests/test_features_tiles.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add core/app/features/tiles.py core/tests/test_features_tiles.py
git commit -m "feat(core): pose les helpers purs des tuiles mvt du cœur"
```

---

## Task 2 : la route MVT

**Files:**
- Modify: `core/app/features/tiles.py`
- Modify: `core/app/main.py:181`
- Test: `core/tests/test_features_tiles.py`

**Interfaces:**
- Consumes: Task 1 (`validate_tile_coords`, `build_mvt_sql`, `mvt_property_columns`, `mvt_feature_id_column`, `MVT_EXTENT`, `MVT_BUFFER`) ; `get_readable_collection` (`app.collections.routes:154`) ; `get_introspector` (`app.collections.routes:51`) ; `get_rls_scope` (`app.features.routes:101`) ; `get_current_user_optional` ; `get_session`.
- Produces: `router` (APIRouter) dans `app.features.tiles`, route `GET /collections/{collection_id}/tiles/{z}/{x}/{y}.mvt`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `core/tests/test_features_tiles.py` :

```python
from fastapi.testclient import TestClient

from app.collections.introspection import TableNotFound
from app.collections.routes import get_introspector


def _client(monkeypatch, info: TableInfo | None = None, collection=None):
    """App réelle, session et collection substituées : ces cas-là échouent
    AVANT tout SQL, donc aucune base n'est nécessaire."""
    from types import SimpleNamespace

    from app import db
    from app.auth.dependency import get_current_user_optional
    from app.features import tiles as tiles_module
    from app.main import create_app

    app = create_app()
    col = collection or SimpleNamespace(
        id="demo_incidents", table_name="demo_incidents", tenant_id="default", is_public=True
    )
    monkeypatch.setattr(tiles_module, "get_readable_collection", lambda s, u, c: col)
    app.dependency_overrides[db.get_session] = lambda: None
    app.dependency_overrides[get_current_user_optional] = lambda: None
    app.dependency_overrides[get_introspector] = lambda: (
        lambda s, t: info if info is not None else (_ for _ in ()).throw(TableNotFound(t))
    )
    return TestClient(app)


def test_zoom_out_of_range_is_a_400(monkeypatch):
    r = _client(monkeypatch, _info()).get("/collections/demo_incidents/tiles/99/0/0.mvt")
    assert r.status_code == 400
    assert "z must be within" in r.json()["detail"]


def test_x_out_of_range_for_the_zoom_is_a_400(monkeypatch):
    r = _client(monkeypatch, _info()).get("/collections/demo_incidents/tiles/1/9/0.mvt")
    assert r.status_code == 400


def test_collection_without_geometry_is_a_400(monkeypatch):
    info = _info(geometry_column=None, geometry_type=None, srid=None)
    r = _client(monkeypatch, info).get("/collections/demo_incidents/tiles/0/0/0.mvt")
    assert r.status_code == 400
    assert "geometry" in r.json()["detail"]


def test_unknown_table_is_a_404(monkeypatch):
    r = _client(monkeypatch, None).get("/collections/demo_incidents/tiles/0/0/0.mvt")
    assert r.status_code == 404
```

Et dans `core/tests/test_main_routes.py` — ou, s'il n'existe pas, en tête de `test_features_tiles.py` :

```python
def test_the_tile_route_is_mounted_unconditionally():
    from app.main import create_app

    paths = {r.path for r in create_app().routes}
    assert "/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt" in paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_tiles.py -v -k "400 or 404 or mounted"`
Expected: FAIL — la route n'existe pas (404 sur tout, et l'assertion de montage échoue)

- [ ] **Step 3: Write the implementation**

Ajouter à `core/app/features/tiles.py` :

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import TableNotFound
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.routes import get_rls_scope

router = APIRouter()

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"


@router.get("/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
def get_collection_tile(
    collection_id: str,
    z: int,
    x: int,
    y: int,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
) -> Response:
    # Même porte que GET /items : 404 avant 403, anonyme accepté sur une
    # collection publique. Aucune variante — la garde est réutilisée verbatim.
    col = get_readable_collection(session, user, collection_id)
    try:
        validate_tile_coords(z, x, y)
    except InvalidTileCoords as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        info = introspect(session, col.table_name)
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="collection not found") from exc
    if info.geometry_column is None:
        raise HTTPException(status_code=400, detail="collection has no geometry column")

    quote = session.get_bind().dialect.identifier_preparer.quote
    sql = build_mvt_sql(quote, info)
    # L'isolation tenant vient de la RLS (rôle gis_rls + GUC app.tenant_id),
    # jamais d'un WHERE applicatif.
    with rls(session, col.tenant_id):
        tile = session.execute(
            text(sql),
            {
                "z": z,
                "x": x,
                "y": y,
                "layer": col.id,
                "extent": MVT_EXTENT,
                "buffer": MVT_BUFFER,
                "srid": info.srid or 4326,
                "fid": mvt_feature_id_column(info),
            },
        ).scalar()
    if not tile:
        return Response(status_code=204)
    visibility = "public" if col.is_public else "private"
    return Response(
        content=bytes(tile),
        media_type=MVT_MEDIA_TYPE,
        headers={"Cache-Control": f"{visibility}, max-age=300"},
    )
```

Note d'implémentation : `get_readable_collection` est importé **au niveau module** (et non appelé via un attribut) pour que le `monkeypatch.setattr(tiles_module, "get_readable_collection", …)` des tests fonctionne.

Dans `core/app/main.py`, à côté de la ligne 32 :

```python
from app.features import tiles as tiles_routes
```

et juste après `app.include_router(features_routes.router)` (l.181) :

```python
    app.include_router(tiles_routes.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_tiles.py -v`
Expected: PASS

- [ ] **Step 5: Vérifier qu'on n'a rien cassé**

Run: `cd core && uv run pytest -q && uv run ruff check && uv run lint-imports`
Expected: pas de baisse par rapport à 1675 passed / 154 skipped ; `Contracts: 1 kept, 0 broken.`

- [ ] **Step 6: Commit**

```bash
git add core/app/features/tiles.py core/app/main.py core/tests/test_features_tiles.py
git commit -m "feat(core): sert les tuiles mvt d'une collection sous can() et rls"
```

---

## Task 3 : les preuves d'autorisation et d'isolation (PostGIS réel)

**Files:**
- Create: `core/tests/test_features_tiles_postgis.py`

**Interfaces:**
- Consumes: la route de la Task 2 ; la fixture `pg_engine` de `core/tests/conftest.py` ; le patron de fixture de `core/tests/test_features_integration.py:22-60`.
- Produces: rien de consommé par une tâche suivante.

Cette tâche ne produit **que** des tests. C'est délibéré : ce sont les seules
preuves que l'isolation vient de la RLS et non d'un `WHERE`, et elles méritent
leur propre porte de revue.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_features_tiles_postgis.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Tuiles MVT sur PostGIS réel (spec SP-24 §6, preuves 2 et 3). Le point de
ces tests : prouver que l'isolation tenant vient de la RLS (rôle gis_rls +
GUC app.tenant_id), pas d'un filtre applicatif — donc aucune substitution du
scope RLS ni du repository ici, contrairement aux tests SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

TILE_PATH = "/collections/demo_incidents/tiles/0/0/0.mvt"


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text(
                "CREATE TABLE demo_incidents (id serial PRIMARY KEY, "
                "titre text NOT NULL, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    client.post("/collections", json={"tableName": "demo_incidents"})
    yield client, app, Session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _insert(client, titre: str, lon: float = 2.35, lat: float = 48.85):
    r = client.post(
        "/collections/demo_incidents/items",
        json={
            "type": "Feature",
            "properties": {"titre": titre},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        },
    )
    assert r.status_code == 201, r.text


def test_an_empty_tile_is_a_204(pg_app):
    client, _, _ = pg_app
    r = client.get(TILE_PATH)
    assert r.status_code == 204
    assert r.content == b""


def test_a_tile_carries_the_properties_but_never_tenant_id(pg_app):
    client, _, _ = pg_app
    _insert(client, "Fuite avenue de la Gare")
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    # Les noms de colonnes apparaissent en clair dans les clés du MVT (protobuf
    # non compressé) : une assertion sur les octets suffit et évite d'ajouter
    # un décodeur MVT aux dépendances de test.
    assert b"titre" in r.content
    assert b"Fuite avenue de la Gare" in r.content
    assert b"tenant_id" not in r.content


def test_a_public_collection_is_readable_anonymously(pg_app):
    client, app, _ = pg_app
    _insert(client, "Publique")
    client.patch("/collections/demo_incidents", json={"isPublic": True})
    app.dependency_overrides[get_current_user_optional] = lambda: None
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=300"


def test_a_private_collection_tile_is_never_cached_publicly(pg_app):
    client, _, _ = pg_app
    _insert(client, "Privée")
    assert client.get(TILE_PATH).headers["cache-control"] == "private, max-age=300"


def test_a_private_collection_is_a_404_anonymously(pg_app):
    client, app, _ = pg_app
    _insert(client, "Privée")
    app.dependency_overrides[get_current_user_optional] = lambda: None
    r = client.get(TILE_PATH)
    assert r.status_code == 404
    assert b"Privée" not in r.content


def test_rows_of_another_tenant_never_reach_the_tile(pg_app):
    """Preuve de RLS, pas preuve de WHERE : la ligne du tenant "autre" est
    insérée directement en base (donc invisible d'aucun filtre applicatif de
    la route), et ne doit pas sortir dans la tuile du tenant "default"."""
    client, _, Session = pg_app
    _insert(client, "Chez nous")
    with Session() as s:
        s.execute(
            text(
                "INSERT INTO demo_incidents (titre, geom, tenant_id) VALUES "
                "('Chez le voisin', ST_SetSRID(ST_MakePoint(2.35, 48.85), 4326), 'autre')"
            )
        )
        s.commit()
    content = client.get(TILE_PATH).content
    assert b"Chez nous" in content
    assert b"Chez le voisin" not in content


def test_serving_a_tile_writes_no_audit_row(pg_app):
    """Décision de spec §3.1 : une vue de carte produit des centaines de
    tuiles, les auditer noierait la table."""
    client, _, Session = pg_app
    _insert(client, "Auditée à l'écriture seulement")
    with Session() as s:
        before = s.execute(text("SELECT count(*) FROM audit_log")).scalar()
    client.get(TILE_PATH)
    with Session() as s:
        assert s.execute(text("SELECT count(*) FROM audit_log")).scalar() == before
```

- [ ] **Step 2: Run tests to verify they run (and fail if PostGIS is absent, skip)**

Run: `cd core && uv run pytest tests/test_features_tiles_postgis.py -v`
Expected: 6 PASSED avec `CORE_TEST_DATABASE_URL` réglé ; 6 SKIPPED sinon.
**Si les tests sautent, le dire explicitement dans le rapport de tâche** — un `SKIPPED` n'est pas une preuve. Précédent SP-15d, dont les 5 tests `qgis` n'ont jamais tourné.

- [ ] **Step 3: Corriger ce que ces tests révèlent**

Aucune implémentation n'est prévue ici : la Task 2 est censée les faire passer. Si l'un échoue, c'est un défaut réel de la Task 2 — le corriger dans `tiles.py` et le noter dans le rapport de tâche.

- [ ] **Step 4: Commit**

```bash
git add core/tests/test_features_tiles_postgis.py
git commit -m "test(core): prouve l'isolation rls et la porte can() du service de tuiles"
```

---

## Task 4 : l'index GiST manquant

**Files:**
- Modify: `core/app/collections/ddl.py:20-52`
- Test: `core/tests/test_collections_spatial_index.py`
- Test: `core/tests/test_collections_ddl.py` (assertion d'idempotence existante)

**Interfaces:**
- Consumes: `apply_collection_ddl(session, table_name)`, `quote_ident(session, identifier)`.
- Produces: `spatial_index_name(table_name: str) -> str` exporté par `app.collections.ddl`, consommé par la migration de la Task 5.

- [ ] **Step 1: Write the failing test**

`core/tests/test_collections_spatial_index.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Index GiST par collection (spec SP-24 §3.2). Aucun index spatial n'existait
dans le dépôt avant SP-24 : tout filtre bbox (OGC Features, geom_intersects du
cross-filter, et désormais les tuiles) était un scan complet de table."""

import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl, spatial_index_name

pytestmark = pytest.mark.postgis


def _indexes(conn, table: str) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t"),
        {"t": table},
    ).scalars()
    return set(rows)


@pytest.fixture()
def table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))
        conn.execute(
            text(
                "CREATE TABLE idx_probe (id serial PRIMARY KEY, "
                "geom geometry(Point, 4326))"
            )
        )
    yield "idx_probe"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))


def test_apply_collection_ddl_creates_a_gist_index(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name(table) in _indexes(conn, table)
        method = conn.execute(
            text(
                "SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam "
                "WHERE c.relname = :n"
            ),
            {"n": spatial_index_name(table)},
        ).scalar()
        assert method == "gist"


def test_apply_collection_ddl_is_still_idempotent(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        apply_collection_ddl(s, table)
        s.commit()


def test_a_table_without_geometry_is_left_alone(pg_engine):
    from sqlalchemy.orm import Session

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))
        conn.execute(text("CREATE TABLE idx_flat (id serial PRIMARY KEY, nom text)"))
    with Session(pg_engine) as s:
        apply_collection_ddl(s, "idx_flat")
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name("idx_flat") not in _indexes(conn, "idx_flat")
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))


def test_the_index_name_stays_within_the_postgres_identifier_limit():
    # tableName est plafonné à 50 par CollectionCreate (configs/schemas.py) ;
    # le préfixe doit laisser la marge.
    assert len(spatial_index_name("x" * 50)) <= 63
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_spatial_index.py -v`
Expected: FAIL — `ImportError: cannot import name 'spatial_index_name'`

- [ ] **Step 3: Write the implementation**

Dans `core/app/collections/ddl.py`, après `_qi = quote_ident` :

```python
def spatial_index_name(table_name: str) -> str:
    """Nom de l'index GiST d'une collection. Partagé avec la migration 0028 —
    une seule définition, jamais deux conventions de nommage."""
    return f"ix_{table_name}_geom_gist"
```

Puis, dans `apply_collection_ddl`, après la boucle `for stmt in stmts` et avant
le bloc de la séquence :

```python
    # Index spatial : sans lui, tout filtre bbox (OGC Features, geom_intersects
    # du cross-filter SP-14n, tuiles MVT SP-24) est un scan complet de table.
    # Le nom de la colonne de géométrie vient de geometry_columns, jamais de
    # l'appelant.
    geom_col = session.execute(
        text(
            "SELECT f_geometry_column FROM geometry_columns "
            "WHERE f_table_schema = 'public' AND f_table_name = :t"
        ),
        {"t": table_name},
    ).scalar()
    if geom_col:
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_qi(session, spatial_index_name(table_name))} "
                f"ON public.{t} USING GIST ({_qi(session, geom_col)})"
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_spatial_index.py tests/test_collections_ddl.py -v`
Expected: PASS (les tests postgis SKIPPED si `CORE_TEST_DATABASE_URL` est absent — le dire dans le rapport)

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/ddl.py core/tests/test_collections_spatial_index.py
git commit -m "feat(core): indexe la géométrie de chaque collection en gist"
```

---

## Task 5 : migration 0028, rattrapage des collections existantes

**Files:**
- Create: `core/alembic/versions/0028_collection_spatial_index.py`
- Test: `core/tests/test_collections_spatial_index.py` (ajout)

**Interfaces:**
- Consumes: `spatial_index_name` (Task 4).
- Produces: rien.

- [ ] **Step 1: Vérifier la révision précédente**

Run: `cd core && ls alembic/versions | sort | tail -3 && grep -n "revision\b\|down_revision" alembic/versions/0027_app_export_jobs.py`
Expected: `0027_app_export_jobs.py` est la dernière ; noter son identifiant `revision` exact — c'est le `down_revision` de la 0028.

- [ ] **Step 2: Write the failing test**

Ajouter à `core/tests/test_collections_spatial_index.py` :

```python
def test_the_migration_backfills_an_already_registered_collection(pg_engine):
    """Une collection enregistrée avant SP-24 n'a pas d'index : la 0028 doit
    le créer, et son downgrade le retirer."""
    from sqlalchemy.orm import Session

    from alembic.versions import _import_0028  # cf. Step 4 : helper de test

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS legacy_probe"))
        conn.execute(
            text(
                "CREATE TABLE legacy_probe (id serial PRIMARY KEY, "
                "geom geometry(Point, 4326))"
            )
        )
    with Session(pg_engine) as s:
        # Enregistrement "à l'ancienne" : la ligne de registre, sans l'index.
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, table_name, title, pk_column, "
                "is_public, editable) VALUES "
                "('legacy_probe', 'default', 'legacy_probe', 'Legacy', 'id', false, true)"
            )
        )
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name("legacy_probe") not in _indexes(conn, "legacy_probe")

    mod = _import_0028()
    with pg_engine.begin() as conn:
        mod.backfill(conn)
        assert spatial_index_name("legacy_probe") in _indexes(conn, "legacy_probe")
        mod.drop_backfilled(conn)
        assert spatial_index_name("legacy_probe") not in _indexes(conn, "legacy_probe")
        conn.execute(text("DELETE FROM collections WHERE id = 'legacy_probe'"))
        conn.execute(text("DROP TABLE IF EXISTS legacy_probe"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_spatial_index.py -k migration -v`
Expected: FAIL — `ImportError` sur `_import_0028`

- [ ] **Step 4: Write the implementation**

`core/alembic/versions/0028_collection_spatial_index.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Index GiST de rattrapage sur les collections déjà enregistrées (SP-24 §3.2).

Aucun index spatial n'existait dans le dépôt : apply_collection_ddl le crée
désormais à l'enregistrement, cette migration comble le passé. Les deux sens
sont testés sur base non vide — le downgrade de la 0024 (SP-17b) échouait sur
des lignes existantes faute de ce test.

Revision ID: 0028_collection_spatial_index
Revises: <mettre ici l'identifiant lu au Step 1>
"""

from alembic import op
from sqlalchemy import text

from app.collections.ddl import spatial_index_name

revision = "0028_collection_spatial_index"
down_revision = "<identifiant lu au Step 1>"
branch_labels = None
depends_on = None


def _registered_geometry_tables(conn) -> list[tuple[str, str]]:
    """(table, colonne de géométrie) pour chaque collection du registre qui a
    réellement une géométrie. Cross-tenant par construction : une migration
    n'a pas d'utilisateur courant."""
    return [
        (row[0], row[1])
        for row in conn.execute(
            text(
                "SELECT c.table_name, g.f_geometry_column FROM collections c "
                "JOIN geometry_columns g ON g.f_table_name = c.table_name "
                "WHERE g.f_table_schema = 'public' "
                "GROUP BY c.table_name, g.f_geometry_column"
            )
        ).all()
    ]


def backfill(conn) -> None:
    preparer = conn.dialect.identifier_preparer
    for table, geom in _registered_geometry_tables(conn):
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {preparer.quote(spatial_index_name(table))} "
                f"ON public.{preparer.quote(table)} USING GIST ({preparer.quote(geom)})"
            )
        )


def drop_backfilled(conn) -> None:
    preparer = conn.dialect.identifier_preparer
    for table, _ in _registered_geometry_tables(conn):
        conn.execute(
            text(f"DROP INDEX IF EXISTS public.{preparer.quote(spatial_index_name(table))}")
        )


def upgrade() -> None:
    backfill(op.get_bind())


def downgrade() -> None:
    drop_backfilled(op.get_bind())
```

Et le helper d'import du test, à placer en tête de
`core/tests/test_collections_spatial_index.py` (les fichiers de `alembic/versions`
ne sont pas un paquet importable par leur nom) :

```python
def _import_0028():
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "0028_collection_spatial_index.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0028", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Remplacer l'import `from alembic.versions import _import_0028` du Step 2 par cet
appel local.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_spatial_index.py -v`
Expected: PASS (ou SKIPPED sans PostGIS — le dire)

- [ ] **Step 6: Vérifier la chaîne de migrations**

Run: `cd core && uv run alembic heads`
Expected: une seule tête, `0028_collection_spatial_index`

- [ ] **Step 7: Commit**

```bash
git add core/alembic/versions/0028_collection_spatial_index.py core/tests/test_collections_spatial_index.py
git commit -m "feat(core): rattrape l'index spatial des collections déjà enregistrées"
```

---

## Task 6 : le type `PopupConfig`, des deux côtés du fil

**Files:**
- Modify: `core/app/configs/schemas.py:76-89`
- Modify: `shell/src/api/types.ts:99-146`
- Test: `core/tests/test_configs_map_popup.py` (créer)
- Test: `shell/src/api/types.test.ts` — s'il n'existe pas, la preuve TS est le `npm run build`

**Interfaces:**
- Produces:
  - Python : `class PopupField(BaseModel)`, `class PopupConfig(BaseModel)`, et sur `MapLayer` les champs `popup: PopupConfig | None`, `collectionId: str | None`, `geometryKind: Literal["point","line","polygon"] | None`, `pkColumn: str | None`.
  - TypeScript : `PopupField`, `PopupConfig`, et les quatre mêmes champs sur la variante `kind: "vector"` de `MapLayer` (`popup?` seul sur la variante `kind: "feature"`).

- [ ] **Step 1: Write the failing test**

`core/tests/test_configs_map_popup.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Round-trip du popup dans une config de carte (spec SP-24 §3.3). Pydantic
ignore les champs inconnus par défaut : sans ces champs sur MapLayer, un popup
sauvegardé serait perdu en silence — c'est le défaut que SP-17a avait trouvé
sur printLayout."""

from app.configs.schemas import BuilderConfig

BASE = {
    "kind": "map",
    "map": {
        "basemap": {"style": "s"},
        "view": {"center": [2.0, 46.0], "zoom": 5},
        "layers": [],
    },
}


def _layer(**extra):
    payload = {
        **BASE,
        "map": {
            **BASE["map"],
            "layers": [
                {
                    "id": "l1",
                    "title": "Communes",
                    "visible": True,
                    "kind": "vector",
                    "tilesUrl": "http://core/collections/communes/tiles/{z}/{x}/{y}.mvt",
                    "sourceLayer": "communes",
                    **extra,
                }
            ],
        },
    }
    return BuilderConfig.model_validate(payload).map.layers[0]


def test_a_field_list_popup_round_trips():
    layer = _layer(
        popup={
            "titleField": "nom",
            "fields": [{"name": "code_insee", "label": "Code INSEE"}, {"name": "population"}],
        }
    )
    assert layer.popup.titleField == "nom"
    assert [f.name for f in layer.popup.fields] == ["code_insee", "population"]
    assert layer.popup.fields[0].label == "Code INSEE"
    assert layer.popup.fields[1].label is None


def test_a_template_popup_round_trips():
    layer = _layer(popup={"template": "## ${nom}\n\n${population} habitants"})
    assert layer.popup.template == "## ${nom}\n\n${population} habitants"


def test_the_collection_binding_round_trips():
    layer = _layer(collectionId="communes", geometryKind="polygon", pkColumn="id")
    assert (layer.collectionId, layer.geometryKind, layer.pkColumn) == (
        "communes",
        "polygon",
        "id",
    )


def test_an_unknown_geometry_kind_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _layer(geometryKind="raster")


def test_a_layer_without_popup_stays_valid():
    assert _layer().popup is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_configs_map_popup.py -v`
Expected: FAIL — `AttributeError: 'MapLayer' object has no attribute 'popup'`

- [ ] **Step 3: Write the Python implementation**

Dans `core/app/configs/schemas.py`, juste avant `class MapLayer` :

```python
class PopupField(BaseModel):
    name: str
    label: str | None = None


class PopupConfig(BaseModel):
    """Contenu du popup d'une couche (SP-24). `template` non vide l'emporte sur
    titleField/fields — un seul mode s'applique à la fois."""

    titleField: str | None = None
    fields: list[PopupField] | None = None
    template: str | None = None
```

et sur `MapLayer`, après `props` :

```python
    popup: PopupConfig | None = None
    # Lien vers la collection servie en tuiles par le cœur : c'est lui qui
    # donne au shell le schéma des champs (popup) et, plus tard, le domaine
    # des valeurs (symbologie SP-25).
    collectionId: str | None = None
    geometryKind: Literal["point", "line", "polygon"] | None = None
    pkColumn: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_configs_map_popup.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the TypeScript side**

Dans `shell/src/api/types.ts`, avant `export type MapLayer` :

```ts
export type PopupField = { name: string; label?: string };
// Le popup d'une couche, déclaratif (règle 2 de CLAUDE.md). `template` non
// vide l'emporte sur titleField/fields. L'absence de `popup` sur la couche EST
// l'état désactivé : il n'y a pas de drapeau `enabled`.
export type PopupConfig = {
  titleField?: string;
  fields?: PopupField[];
  template?: string;
};
```

et sur les deux variantes concernées de `MapLayer` :

```ts
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
    }
```

```ts
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "feature";
      url: string;
      paint?: Record<string, unknown>;
      renderAs?: "fill" | "circle" | "line";
      popup?: PopupConfig;
    }
```

- [ ] **Step 6: Verify both sides**

Run: `cd shell && npm run build` puis `cd ../core && uv run pytest tests/test_configs_map_popup.py tests/test_configs_routes.py -q`
Expected: build vert, tests verts

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_configs_map_popup.py shell/src/api/types.ts
git commit -m "feat(core): fait round-tripper le popup et le lien collection d'une couche"
```

---

## Task 7 : régénérer OpenAPI et les types TS

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:** aucune. Tâche de synchronisation d'artefacts générés.

C'est la classe d'oubli la plus récurrente du dépôt (au moins cinq occurrences).
Ici le diff sera **non vide** : la route de la Task 2 est montée
inconditionnellement et les champs de la Task 6 changent le schéma.

- [ ] **Step 1: Trouver l'incantation réelle**

Run: `grep -n "export_openapi\|openapi" .github/workflows/ci.yml`
Expected: la commande exacte du job `api-types-drift`.
**Attention** : `uv run python scripts/export_openapi.py` seul échoue en
`ModuleNotFoundError: app` (le script n'insère pas le cwd sur `sys.path`) — il
faut `PYTHONPATH=.` et un `CORE_SECRETS_MASTER_KEY` de test, comme le fait
`ci.yml`. Écart documenté par SP-23 tâche 19.

- [ ] **Step 2: Régénérer**

Run: la commande lue au Step 1, puis celle qui régénère les types TS.

- [ ] **Step 3: Vérifier que le diff est cohérent**

Run: `git diff --stat core/openapi.json shell/src/api/generated/`
Expected: diff **non vide**, portant la nouvelle route `/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt` et les champs `popup`/`collectionId`/`geometryKind`/`pkColumn`. Aucun autre changement — s'il y en a, c'est une dérive antérieure : la signaler dans le rapport plutôt que la committer en silence.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/
git commit -m "chore(core): régénère la spec openapi et les types ts"
```

---

## Task 8 : interpolation du gabarit de popup (module pur)

**Files:**
- Create: `shell/src/map/popupTemplate.ts`
- Test: `shell/src/map/popupTemplate.test.ts`

**Interfaces:**
- Consumes: `evaluateExpression`, `type ExprContext` de `shell/src/builder/expr.ts` ; `sanitizeMarkdown` de `shell/src/builder/widgets/sanitizeMarkdown.ts`.
- Produces:
  - `interpolatePopupTemplate(template: string, ctx: ExprContext): string` — markdown interpolé, **non** assaini.
  - `renderPopupTemplate(template: string, ctx: ExprContext): string` — HTML assaini, prêt à insérer.

- [ ] **Step 1: Write the failing tests**

`shell/src/map/popupTemplate.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
import { interpolatePopupTemplate, renderPopupTemplate } from "./popupTemplate";

const ctx = (record: Record<string, unknown>) => ({
  vars: {},
  user: { name: "t" },
  record,
});

test("interpolates a CEL placeholder against the clicked feature", () => {
  expect(interpolatePopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toBe("## Tulle");
});

test("counts brace depth so a CEL map literal survives", () => {
  const out = interpolatePopupTemplate("${ {'a': 1}['a'] }", ctx({}));
  expect(out).toBe("1");
});

test("leaves an unclosed placeholder literal instead of throwing", () => {
  expect(interpolatePopupTemplate("nom: ${record.nom", ctx({ nom: "Tulle" }))).toBe(
    "nom: ${record.nom",
  );
});

test("renders an invalid expression as an empty string", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(interpolatePopupTemplate("[${(((}]", ctx({}))).toBe("[]");
  warn.mockRestore();
});

test("renders a missing field as an empty string", () => {
  expect(interpolatePopupTemplate("x${record.absent}y", ctx({}))).toBe("xy");
});

test("serializes an object value as JSON", () => {
  expect(interpolatePopupTemplate("${record.o}", ctx({ o: { a: 1 } }))).toBe('{"a":1}');
});

test("keeps several placeholders on one line", () => {
  expect(
    interpolatePopupTemplate("${record.a} / ${record.b}", ctx({ a: "x", b: "y" })),
  ).toBe("x / y");
});

test("a template with no placeholder is returned unchanged", () => {
  expect(interpolatePopupTemplate("texte simple", ctx({}))).toBe("texte simple");
});

test("renderPopupTemplate turns markdown into html", () => {
  expect(renderPopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toContain("Tulle");
  expect(renderPopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toMatch(/<h2/);
});

test("renderPopupTemplate neutralizes html injected through a property value", () => {
  // La valeur vient de la donnée, potentiellement d'un tiers. On interpole
  // d'abord, on assainit ensuite : DOMPurify est la garantie (spec §3.5).
  const html = renderPopupTemplate("${record.nom}", ctx({ nom: '<img src=x onerror="alert(1)">' }));
  expect(html).not.toContain("onerror");
});

test("renderPopupTemplate strips a script tag injected through a property value", () => {
  const html = renderPopupTemplate("${record.nom}", ctx({ nom: "<script>alert(1)</script>" }));
  expect(html.toLowerCase()).not.toContain("<script");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/popupTemplate.test.ts`
Expected: FAIL — `Failed to resolve import "./popupTemplate"`

- [ ] **Step 3: Write the implementation**

`shell/src/map/popupTemplate.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { evaluateExpression, type ExprContext } from "../builder/expr";
import { sanitizeMarkdown } from "../builder/widgets/sanitizeMarkdown";

// Le gabarit de popup (SP-24 §3.5) est du markdown où chaque ${expression} est
// évaluée en CEL. C'est la SECONDE syntaxe d'expression du dépôt, à côté du
// binding JSON { $expr } de builder/exprBindings.ts — divergence assumée par la
// spec : c'est la seule forme qui donne une mise en forme libre.
//
// Deux règles non négociables :
//  - un placeholder mal formé ou une expression invalide ne lève jamais ;
//  - on interpole d'abord et on assainit ensuite (renderPopupTemplate), donc
//    une valeur de propriété est traitée comme du markdown et DOMPurify est
//    ce qui rend l'opération sûre.

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// Index du "}" fermant le "${" ouvert à `start`, en comptant la profondeur —
// une expression CEL peut contenir un littéral de map ({'a': 1}). -1 si le
// placeholder n'est jamais fermé.
function closingBrace(template: string, start: number): number {
  let depth = 0;
  for (let i = start + 2; i < template.length; i += 1) {
    const ch = template[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      if (depth === 0) return i;
      depth -= 1;
    }
  }
  return -1;
}

export function interpolatePopupTemplate(template: string, ctx: ExprContext): string {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf("${", i);
    if (open === -1) {
      out += template.slice(i);
      break;
    }
    const close = closingBrace(template, open);
    if (close === -1) {
      // Placeholder non fermé : le reste du gabarit est laissé littéral.
      out += template.slice(i);
      break;
    }
    out += template.slice(i, open);
    out += stringify(evaluateExpression(template.slice(open + 2, close).trim(), ctx));
    i = close + 1;
  }
  return out;
}

export function renderPopupTemplate(template: string, ctx: ExprContext): string {
  return sanitizeMarkdown(interpolatePopupTemplate(template, ctx));
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/popupTemplate.test.ts`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/popupTemplate.ts shell/src/map/popupTemplate.test.ts
git commit -m "feat(shell): interpole un gabarit de popup en cel puis l'assainit"
```

---

## Task 9 : contenu et rendu du popup

**Files:**
- Create: `shell/src/map/popupContent.ts`
- Create: `shell/src/map/MapPopup.tsx`
- Modify: `shell/eslint.config.js:88-91`
- Test: `shell/src/map/popupContent.test.ts`
- Test: `shell/src/map/MapPopup.test.tsx`

**Interfaces:**
- Consumes: `PopupConfig`, `PopupField` (Task 6) ; `CollectionSchemaField` de `shell/src/api/types.ts` ; `renderPopupTemplate` (Task 8).
- Produces:
  - `type PopupRow = { label: string; value: string }`
  - `type PopupContent = { title: string | null; rows: PopupRow[]; html: string | null }`
  - `resolvePopupContent(config: PopupConfig | undefined, properties: Record<string, unknown>, ctx: ExprContext): PopupContent`
  - `MapPopup({ content, x, y, onClose }: { content: PopupContent; x: number; y: number; onClose: () => void })`

- [ ] **Step 1: Write the failing tests**

`shell/src/map/popupContent.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { resolvePopupContent } from "./popupContent";

const ctx = { vars: {}, user: { name: "t" } };
const props = { id: 1, nom: "Tulle", population: 14000 };

test("without configuration every property becomes a row, in order", () => {
  const c = resolvePopupContent(undefined, props, ctx);
  expect(c.rows.map((r) => r.label)).toEqual(["id", "nom", "population"]);
  expect(c.rows.map((r) => r.value)).toEqual(["1", "Tulle", "14000"]);
  expect(c.title).toBeNull();
  expect(c.html).toBeNull();
});

test("the configured field list drives the order and the labels", () => {
  const c = resolvePopupContent(
    { titleField: "nom", fields: [{ name: "population", label: "Habitants" }, { name: "id" }] },
    props,
    ctx,
  );
  expect(c.title).toBe("Tulle");
  expect(c.rows).toEqual([
    { label: "Habitants", value: "14000" },
    { label: "id", value: "1" },
  ]);
});

test("a configured field absent from the properties is dropped, not rendered empty", () => {
  const c = resolvePopupContent({ fields: [{ name: "absent" }, { name: "nom" }] }, props, ctx);
  expect(c.rows).toEqual([{ label: "nom", value: "Tulle" }]);
});

test("a non-empty template wins over titleField and fields", () => {
  const c = resolvePopupContent(
    { titleField: "nom", fields: [{ name: "id" }], template: "**${record.nom}**" },
    props,
    ctx,
  );
  expect(c.rows).toEqual([]);
  expect(c.title).toBeNull();
  expect(c.html).toContain("Tulle");
});

test("an empty or blank template falls back to the field list", () => {
  const c = resolvePopupContent({ fields: [{ name: "nom" }], template: "   " }, props, ctx);
  expect(c.html).toBeNull();
  expect(c.rows).toEqual([{ label: "nom", value: "Tulle" }]);
});

test("a null property value renders as an em dash, never as \"null\"", () => {
  const c = resolvePopupContent({ fields: [{ name: "nom" }] }, { nom: null }, ctx);
  expect(c.rows).toEqual([{ label: "nom", value: "—" }]);
});
```

`shell/src/map/MapPopup.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapPopup } from "./MapPopup";

test("renders the title and the rows", () => {
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={10}
      y={20}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText("Tulle")).toBeInTheDocument();
  expect(screen.getByText("Habitants")).toBeInTheDocument();
  expect(screen.getByText("14000")).toBeInTheDocument();
});

test("renders the sanitized html of a template popup", () => {
  render(
    <MapPopup
      content={{ title: null, rows: [], html: "<strong>Tulle</strong>" }}
      x={0}
      y={0}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText("Tulle").tagName).toBe("STRONG");
});

test("is positioned where the map projected the clicked point", () => {
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={42} y={7} onClose={() => {}} />,
  );
  const popup = screen.getByRole("dialog");
  expect(popup.style.left).toBe("42px");
  expect(popup.style.top).toBe("7px");
});

test("closes on the close button", async () => {
  const onClose = vi.fn();
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={0} y={0} onClose={onClose} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(onClose).toHaveBeenCalledOnce();
});

test("shows an explicit message when the feature carries no attribute", () => {
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={0} y={0} onClose={() => {}} />,
  );
  expect(screen.getByText("Aucun attribut")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/popupContent.test.ts src/map/MapPopup.test.tsx`
Expected: FAIL — imports non résolus

- [ ] **Step 3: Write the implementations**

`shell/src/map/popupContent.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import type { ExprContext } from "../builder/expr";
import type { PopupConfig } from "../api/types";
import { renderPopupTemplate } from "./popupTemplate";

export type PopupRow = { label: string; value: string };
export type PopupContent = { title: string | null; rows: PopupRow[]; html: string | null };

const EMPTY = "—";

function display(value: unknown): string {
  if (value === null || value === undefined) return EMPTY;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// Résolution d'un PopupConfig contre les propriétés de l'entité cliquée.
// Deux modes exclusifs : gabarit (s'il est non vide) ou liste de champs.
// Sans configuration du tout : tous les champs présents, dans leur ordre.
export function resolvePopupContent(
  config: PopupConfig | undefined,
  properties: Record<string, unknown>,
  ctx: Omit<ExprContext, "record">,
): PopupContent {
  const template = config?.template?.trim();
  if (template) {
    return {
      title: null,
      rows: [],
      html: renderPopupTemplate(template, { ...ctx, record: properties }),
    };
  }
  const names = config?.fields?.length
    ? config.fields.filter((f) => f.name in properties).map((f) => f.name)
    : Object.keys(properties);
  const labels = new Map((config?.fields ?? []).map((f) => [f.name, f.label]));
  return {
    title:
      config?.titleField && config.titleField in properties
        ? display(properties[config.titleField])
        : null,
    rows: names
      .filter((n) => n !== config?.titleField)
      .map((n) => ({ label: labels.get(n) || n, value: display(properties[n]) })),
    html: null,
  };
}
```

`shell/src/map/MapPopup.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { PopupContent } from "./popupContent";

// Composant purement présentationnel : il ne connaît ni MapLibre ni la
// configuration, seulement un contenu déjà résolu et une position déjà
// projetée. C'est ce qui le rend testable sans carte.
//
// dangerouslySetInnerHTML est ici le second usage légitime du dépôt : `html`
// sort TOUJOURS de renderPopupTemplate, donc de sanitizeMarkdown() (DOMPurify).
// Ce fichier est pour cette raison dans le bloc d'exception d'eslint.config.js.
export function MapPopup({
  content,
  x,
  y,
  onClose,
}: {
  content: PopupContent;
  x: number;
  y: number;
  onClose: () => void;
}) {
  const empty = !content.html && content.rows.length === 0 && !content.title;
  return (
    <div
      role="dialog"
      aria-label="Attributs de l'entité"
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-white p-2 text-xs shadow-lg"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
      <button
        type="button"
        aria-label="Fermer"
        className="absolute right-1 top-1 px-1 text-slate-400"
        onClick={onClose}
      >
        ✕
      </button>
      {content.title && <p className="mb-1 pr-4 font-medium">{content.title}</p>}
      {content.html !== null ? (
        <div dangerouslySetInnerHTML={{ __html: content.html }} />
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-2">
          {content.rows.map((r) => (
            <div key={r.label} className="col-span-2 grid grid-cols-subgrid">
              <dt className="text-slate-500">{r.label}</dt>
              <dd className="break-words">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {empty && <p className="text-slate-400">Aucun attribut</p>}
    </div>
  );
}
```

Dans `shell/eslint.config.js`, remplacer le bloc des lignes 88-91 :

```js
  {
    // Deux consommateurs légitimes de sanitizeMarkdown() : le widget
    // RichSection et le popup de carte (SP-24). Tout autre fichier reste
    // interdit par la règle no-restricted-syntax ci-dessus.
    files: ["src/builder/widgets/richSection.tsx", "src/map/MapPopup.tsx"],
    rules: { "no-restricted-syntax": "off" },
  },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/popupContent.test.ts src/map/MapPopup.test.tsx`
Expected: PASS (11 tests)

- [ ] **Step 5: Verify the lint rule is still doing its job**

Run: `cd shell && npx eslint src/map/MapPopup.tsx && echo 'const x = <div dangerouslySetInnerHTML={{__html: ""}} />;' > src/map/__probe.tsx && npx eslint src/map/__probe.tsx; rm src/map/__probe.tsx`
Expected: `MapPopup.tsx` passe ; le fichier sonde **échoue** sur `no-restricted-syntax` (preuve que l'exception est bien limitée aux deux fichiers nommés)

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/popupContent.ts shell/src/map/popupContent.test.ts shell/src/map/MapPopup.tsx shell/src/map/MapPopup.test.tsx shell/eslint.config.js
git commit -m "feat(shell): résout et rend le contenu d'un popup de carte"
```

---

## Task 10 : `MapView` — couches tuilées rendues et cliquables

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/test/MockMaplibreMap.ts`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `MapLayer` avec `geometryKind`/`pkColumn` (Task 6) ; `isHostedCoreUrl` (déjà dans `MapView.tsx:31`).
- Produces: `MapView` pose désormais un handler de clic sur les couches `kind: "vector"` et dérive leur type MapLibre ; `onFeatureClick` reçoit un `DataRecord` dont l'`id` retombe sur `properties[pkColumn]`.
  - `layerTypeFor(geometryKind: "point" | "line" | "polygon" | undefined): "circle" | "line" | "fill"`
  - `makeFeatureClickHandler(pkColumn: string | undefined, onFeatureClick: (r: DataRecord) => void)` — **la Task 11 lui ajoute un troisième paramètre `onPopup`** ; c'est la même fonction, étendue, jamais une seconde.
  - `isHostedCollectionUrl(url: string, coreUrl: string | undefined): boolean`

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/map/MapView.test.tsx` :

```tsx
const tiled = (extra: Partial<Extract<MapLayer, { kind: "vector" }>> = {}) => ({
  ...config,
  layers: [
    {
      id: "communes",
      title: "Communes",
      visible: true,
      kind: "vector" as const,
      tilesUrl: "http://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
      sourceLayer: "communes",
      collectionId: "communes",
      ...extra,
    },
  ],
});

test("a tiled point collection is rendered as circles, not as a fill", () => {
  render(<MapView config={tiled({ geometryKind: "point" })} />);
  expect(mapInstances[0].getLayer("communes")).toMatchObject({ type: "circle" });
});

test("a tiled line collection is rendered as lines", () => {
  render(<MapView config={tiled({ geometryKind: "line" })} />);
  expect(mapInstances[0].getLayer("communes")).toMatchObject({ type: "line" });
});

test("a tiled layer without geometryKind still falls back to a fill", () => {
  render(<MapView config={tiled()} />);
  expect(mapInstances[0].getLayer("communes")).toMatchObject({ type: "fill" });
});

test("clicking a tiled feature reports it, like a geojson one", () => {
  const onFeatureClick = vi.fn();
  render(<MapView config={tiled({ geometryKind: "polygon" })} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "communes", {
    features: [{ id: 7, properties: { nom: "Tulle" }, geometry: { type: "Point" } }],
    lngLat: { lng: 1, lat: 2 },
  });
  expect(onFeatureClick).toHaveBeenCalledWith(
    expect.objectContaining({ id: 7, properties: { nom: "Tulle" } }),
  );
});

test("a tiled feature with a text primary key falls back to the pk property", () => {
  // ST_AsMVT ne pose un feature id que sur une PK entière (core/app/features/
  // tiles.py) : sans repli, une collection à PK texte serait inerte.
  const onFeatureClick = vi.fn();
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", pkColumn: "code" })}
      onFeatureClick={onFeatureClick}
    />,
  );
  mapInstances[0].fireOnLayer("click", "communes", {
    features: [{ id: null, properties: { code: "19272", nom: "Tulle" } }],
    lngLat: { lng: 1, lat: 2 },
  });
  expect(onFeatureClick).toHaveBeenCalledWith(expect.objectContaining({ id: "19272" }));
});

test("the click handler of a removed tiled layer is detached", () => {
  const { rerender } = render(<MapView config={tiled({ geometryKind: "polygon" })} />);
  rerender(<MapView config={config} />);
  expect(mapInstances[0].layerHandlers["click:communes"] ?? []).toHaveLength(0);
});

test("core collection tile requests carry the session bearer token", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "http://core.test"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("http://core.test/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "http://core.test/collections/communes/tiles/1/2/3.mvt",
    headers: { Authorization: "Bearer tok" },
  });
});

test("an external url that merely looks like ours gets no token", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "http://core.test"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("https://attacker.test/collections/x/tiles/1/2/3.mvt")).toEqual({
    url: "https://attacker.test/collections/x/tiles/1/2/3.mvt",
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL — la couche tuilée est en `type: "fill"` quel que soit `geometryKind`, aucun handler `click:communes`, et pas de token sur l'URL de tuile

- [ ] **Step 3: Write the implementation**

Dans `shell/src/map/MapView.tsx` :

a) une constante et un prédicat, à côté des deux existants (l.17-48) :

```ts
const HOSTED_COLLECTION_PATH = "/collections/";

// Les tuiles MVT d'une collection (SP-24) et le GeoJSON /items sont servis par
// le cœur sous can() : ils doivent porter le jeton de session, sinon une
// collection non publique n'est pas lisible du tout. Même vérification
// d'origine réelle que pour tileset3d/terrain3d — jamais un includes().
function isHostedCollectionUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_COLLECTION_PATH);
}
```

b) un helper de type de couche, au-dessus d'`applyLayers` :

```ts
// Une couche tuilée était jusqu'ici ajoutée en "fill" quel que soit son
// contenu : une collection de points ne s'affichait donc pas du tout. Le type
// MapLibre suit désormais la géométrie déclarée par la couche.
function layerTypeFor(geometryKind: "point" | "line" | "polygon" | undefined) {
  if (geometryKind === "point") return "circle" as const;
  if (geometryKind === "line") return "line" as const;
  return "fill" as const;
}
```

c) dans `applyLayers`, la branche `vector` devient :

```ts
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({
          id: layer.id,
          type: layerTypeFor(layer.geometryKind),
          source: layer.id,
          "source-layer": layer.sourceLayer,
          paint: layer.paint ?? {},
        });
        const handler = makeFeatureClickHandler(layer.pkColumn, onFeatureClick);
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      } else if (layer.kind === "raster") {
```

d) le handler partagé par les branches `vector` et `feature`, au-dessus
d'`applyLayers` — la branche `feature` remplace son handler inline par celui-ci :

```ts
// Partagé par les couches tuilées et GeoJSON : une seule définition du "que
// vaut l'identité d'une entité cliquée". ST_AsMVT ne pose un feature id que
// sur une PK entière, d'où le repli sur la propriété de PK.
function makeFeatureClickHandler(
  pkColumn: string | undefined,
  onFeatureClick: (record: DataRecord) => void,
) {
  return (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f) return;
    const properties = (f.properties ?? {}) as Record<string, unknown>;
    const fallback = pkColumn ? properties[pkColumn] : undefined;
    const id = (f.id ?? fallback) as string | number | undefined;
    if (id == null) return;
    onFeatureClick({ id, properties, geometry: f.geometry });
  };
}
```

e) dans `transformRequest` (l.348-354), ajouter la branche :

```ts
      transformRequest: (url: string) => {
        const coreUrl = getCoreUrlRef.current?.();
        if (isHostedTerrainUrl(url, coreUrl) || isHostedCollectionUrl(url, coreUrl)) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
```

Dans `shell/src/test/MockMaplibreMap.ts`, ajouter à `MockMap` :

```ts
  // MapView projette le point cliqué pour positionner le popup ; la valeur
  // exacte n'a pas de sens en test, seule sa propagation compte.
  project(lngLat: { lng: number; lat: number }) {
    return { x: Math.round(lngLat.lng), y: Math.round(lngLat.lat) };
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS — l'ensemble du fichier, y compris les tests pré-existants (dont « adds a vector source and fill layer for a vector layer », qui reste vert grâce au repli `fill`)

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/test/MockMaplibreMap.ts
git commit -m "fix(shell): rend et rend cliquable une couche tuilée selon sa géométrie"
```

---

## Task 11 : brancher le popup dans `MapView`

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `MapPopup`, `resolvePopupContent` (Task 9) ; le handler de clic de la Task 10 ; `MockMap.project` (Task 10).
- Produces: `MapView` accepte une prop optionnelle `exprContext?: Omit<ExprContext, "record">` (défaut `{ vars: {}, user: { name: "" } }`) et ouvre un popup quand la couche cliquée porte un `popup`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/map/MapView.test.tsx` :

```tsx
import { screen } from "@testing-library/react";

const clickPayload = {
  features: [{ id: 7, properties: { nom: "Tulle", population: 14000 } }],
  lngLat: { lng: 12, lat: 34 },
};

test("clicking a feature of a layer with a popup opens it", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })} />);
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText("Tulle")).toBeInTheDocument();
  expect(screen.getByText("population")).toBeInTheDocument();
});

test("the popup is positioned at the projected click point", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  const popup = screen.getByRole("dialog");
  expect(popup.style.left).toBe("12px");
  expect(popup.style.top).toBe("34px");
});

test("no popup opens for a layer that does not declare one", () => {
  render(<MapView config={tiled({ geometryKind: "polygon" })} />);
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the click stays additive: onFeatureClick still fires with a popup configured", () => {
  const onFeatureClick = vi.fn();
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })}
      onFeatureClick={onFeatureClick}
    />,
  );
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  expect(onFeatureClick).toHaveBeenCalledOnce();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("the popup closes on its close button", async () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the popup follows the map when it moves", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  const map = mapInstances[0];
  map.fireOnLayer("click", "communes", clickPayload);
  map.project = (ll: { lng: number; lat: number }) => ({ x: ll.lng + 100, y: ll.lat + 100 });
  map.fire("move");
  expect(screen.getByRole("dialog").style.left).toBe("112px");
});

test("the popup closes when the layer that opened it disappears from the config", () => {
  const { rerender } = render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  rerender(<MapView config={config} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("a template popup renders its sanitized html", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { template: "**${record.nom}**" } })}
    />,
  );
  mapInstances[0].fireOnLayer("click", "communes", clickPayload);
  expect(screen.getByText("Tulle").tagName).toBe("STRONG");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t popup`
Expected: FAIL — aucun `role="dialog"` n'apparaît

- [ ] **Step 3: Write the implementation**

Dans `shell/src/map/MapView.tsx` :

a) l'état, dans le composant :

```tsx
  // Popup ouvert : la couche qui l'a ouvert, les propriétés de l'entité, et le
  // point géographique cliqué (reprojeté à chaque déplacement de la carte).
  const [popup, setPopup] = useState<{
    layerId: string;
    properties: Record<string, unknown>;
    lngLat: { lng: number; lat: number };
  } | null>(null);
  const [popupPoint, setPopupPoint] = useState<{ x: number; y: number } | null>(null);
```

b) `makeFeatureClickHandler` (Task 10) prend un troisième paramètre — la
signature produite par cette tâche remplace celle de la Task 10 :

```ts
function makeFeatureClickHandler(
  pkColumn: string | undefined,
  onFeatureClick: (record: DataRecord) => void,
  onPopup: (properties: Record<string, unknown>, lngLat: { lng: number; lat: number }) => void,
) {
  return (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f) return;
    const properties = (f.properties ?? {}) as Record<string, unknown>;
    // Le popup s'ouvre même sans identité utilisable : les attributs sont là,
    // c'est la seule chose dont il a besoin. Le repli d'id ne conditionne que
    // la sélection et le cross-filter.
    onPopup(properties, e.lngLat);
    const fallback = pkColumn ? properties[pkColumn] : undefined;
    const id = (f.id ?? fallback) as string | number | undefined;
    if (id == null) return;
    onFeatureClick({ id, properties, geometry: f.geometry });
  };
}
```

`applyLayers` reçoit une callback `onPopup` supplémentaire, qu'elle passe aux
deux branches (`vector` et `feature`) : elle n'est appelée que si la couche
porte un `popup`.

```ts
        const handler = makeFeatureClickHandler(
          layer.pkColumn,
          onFeatureClick,
          (properties, lngLat) => {
            if (layer.popup) onPopup(layer.id, properties, lngLat);
          },
        );
```

c) la reprojection, dans un effet :

```tsx
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !popup) {
      setPopupPoint(null);
      return;
    }
    const reproject = () => setPopupPoint(map.project(popup.lngLat));
    reproject();
    map.on("move", reproject);
    return () => {
      map.off("move", reproject);
    };
  }, [popup]);
```

`MockMap.off` n'accepte aujourd'hui que la forme à trois arguments
(`event, layerId, cb`) : ajouter dans `MockMaplibreMap.ts` la forme à deux
arguments utilisée ici.

```ts
  off(event: string, arg2: string | ((e: unknown) => void), cb?: (e: unknown) => void) {
    if (typeof arg2 === "function") {
      this.handlers[event] = (this.handlers[event] ?? []).filter((h) => h !== arg2);
      return this;
    }
    const key = `${event}:${arg2}`;
    this.layerHandlers[key] = (this.layerHandlers[key] ?? []).filter((h) => h !== cb);
    return this;
  }
```

d) fermeture quand la couche disparaît de la config :

```tsx
  useEffect(() => {
    if (popup && !config.layers.some((l) => l.id === popup.layerId)) setPopup(null);
  }, [config.layers, popup]);
```

e) le rendu, dans le conteneur de la carte :

```tsx
      {popup && popupPoint && (
        <MapPopup
          content={resolvePopupContent(
            config.layers.find((l) => l.id === popup.layerId)?.popup,
            popup.properties,
            exprContext ?? { vars: {}, user: { name: "" } },
          )}
          x={popupPoint.x}
          y={popupPoint.y}
          onClose={() => setPopup(null)}
        />
      )}
```

Note : `config.layers.find(...)?.popup` n'est typé que sur les variantes qui
portent `popup` — utiliser un accès défensif (`"popup" in layer ? layer.popup : undefined`)
pour rester compilable sur l'union complète de `MapLayer`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, fichier complet

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/test/MockMaplibreMap.ts
git commit -m "feat(shell): ouvre un popup d'attributs au clic sur une entité"
```

---

## Task 12 : l'éditeur de popup, monté dans l'éditeur de cartes

**Files:**
- Create: `shell/src/map/PopupEditor.tsx`
- Modify: `shell/src/map/LayersPanel.tsx`
- Test: `shell/src/map/PopupEditor.test.tsx`
- Test: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `PopupConfig`, `PopupField` (Task 6) ; `validateExpression` de `shell/src/builder/expr.ts`.
- Produces: `PopupEditor({ value, availableFields, onChange }: { value: PopupConfig | undefined; availableFields: string[]; onChange: (next: PopupConfig | undefined) => void })`. **`onChange(undefined)` est l'état désactivé** — il n'y a pas de drapeau `enabled`.

- [ ] **Step 1: Write the failing tests**

`shell/src/map/PopupEditor.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { PopupEditor } from "./PopupEditor";

const fields = ["id", "nom", "population"];

test("enabling the popup posts an empty config, disabling it clears the field", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <PopupEditor value={undefined} availableFields={fields} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith({});
  rerender(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});

test("the field controls are hidden while the popup is disabled", () => {
  render(<PopupEditor value={undefined} availableFields={fields} onChange={() => {}} />);
  expect(screen.queryByLabelText("Champ titre")).not.toBeInTheDocument();
});

test("typing a title field posts it", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Champ titre"), "n");
  expect(onChange).toHaveBeenLastCalledWith({ titleField: "n" });
});

test("an arbitrary field name can be added when no schema is available", async () => {
  // Surface du widget carte : PropsPanel ne reçoit ni schéma ni
  // enregistrements (registry.ts:33-37), donc availableFields est vide et
  // l'auteur saisit le nom du champ — comme les champs « Champ couleur » et
  // « Champ taille » voisins, qui sont déjà des saisies libres.
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={[]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "nom" }] });
});

test("adding a blank field name does nothing", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("adding a field already in the list does not duplicate it", async () => {
  const onChange = vi.fn();
  render(
    <PopupEditor value={{ fields: [{ name: "nom" }] }} availableFields={[]} onChange={onChange} />,
  );
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("checking a field adds it to the list, unchecking removes it", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <PopupEditor value={{}} availableFields={fields} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "population" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "population" }] });
  rerender(
    <PopupEditor
      value={{ fields: [{ name: "population" }] }}
      availableFields={fields}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "population" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [] });
});

test("a field label can be overridden", async () => {
  const onChange = vi.fn();
  render(
    <PopupEditor
      value={{ fields: [{ name: "population" }] }}
      availableFields={fields}
      onChange={onChange}
    />,
  );
  await userEvent.type(screen.getByLabelText("Libellé de population"), "H");
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "population", label: "H" }] });
});

test("the advanced mode posts a template", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Avancé (gabarit)" }));
  await userEvent.type(screen.getByLabelText("Gabarit"), "x");
  expect(onChange).toHaveBeenLastCalledWith({ template: "x" });
});

test("an invalid placeholder is reported without blocking typing", async () => {
  render(
    <PopupEditor value={{ template: "${(((}" }} availableFields={fields} onChange={() => {}} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Expression invalide");
});

test("an unclosed placeholder is reported", () => {
  render(
    <PopupEditor value={{ template: "${record.nom" }} availableFields={fields} onChange={() => {}} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Expression non fermée");
});

test("a valid template reports nothing", () => {
  render(
    <PopupEditor
      value={{ template: "${record.nom}" }}
      availableFields={fields}
      onChange={() => {}}
    />,
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
```

Ajouter à `shell/src/map/LayersPanel.test.tsx` :

```tsx
test("the layers panel exposes the popup editor of each layer", async () => {
  const onChange = vi.fn();
  render(
    <LayersPanel
      layers={[
        {
          id: "l1",
          title: "Communes",
          visible: true,
          kind: "vector",
          tilesUrl: "u",
          sourceLayer: "communes",
          collectionId: "communes",
        },
      ]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ popup: {} })]);
});

test("a raster layer has no popup editor", () => {
  render(
    <LayersPanel
      layers={[{ id: "r", title: "Fond", visible: true, kind: "raster", tilesUrl: "u" }]}
      onChange={() => {}}
    />,
  );
  expect(
    screen.queryByRole("checkbox", { name: "Afficher les attributs au clic" }),
  ).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/PopupEditor.test.tsx src/map/LayersPanel.test.tsx`
Expected: FAIL — module `./PopupEditor` non résolu

- [ ] **Step 3: Write the implementation**

`shell/src/map/PopupEditor.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import type { PopupConfig, PopupField } from "../api/types";
import { validateExpression } from "../builder/expr";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";

// Vérifie les placeholders d'un gabarit sans le rendre : même découpage que
// interpolatePopupTemplate (popupTemplate.ts), mais on ne garde que l'erreur.
function templateError(template: string): string | null {
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf("${", i);
    if (open === -1) return null;
    let depth = 0;
    let close = -1;
    for (let j = open + 2; j < template.length; j += 1) {
      const ch = template[j];
      if (ch === "{") depth += 1;
      else if (ch === "}") {
        if (depth === 0) {
          close = j;
          break;
        }
        depth -= 1;
      }
    }
    if (close === -1) return "Expression non fermée";
    const err = validateExpression(template.slice(open + 2, close).trim());
    if (err) return `Expression invalide : ${err}`;
    i = close + 1;
  }
  return null;
}

// Éditeur partagé par les DEUX surfaces d'auteur (éditeur de cartes et
// PropsPanel du widget carte) : l'écart I2 de la revue finale SP-23 était un
// garde-fou écrit pour une surface et jamais reporté sur sa jumelle.
export function PopupEditor({
  value,
  availableFields,
  onChange,
}: {
  value: PopupConfig | undefined;
  availableFields: string[];
  onChange: (next: PopupConfig | undefined) => void;
}) {
  const [advanced, setAdvanced] = useState(Boolean(value?.template));
  const [draftField, setDraftField] = useState("");
  const listId = useId();
  const selected = value?.fields;
  const error = value?.template ? templateError(value.template) : null;

  function toggleField(name: string) {
    const current: PopupField[] = selected ?? [];
    const next = current.some((f) => f.name === name)
      ? current.filter((f) => f.name !== name)
      : [...current, { name }];
    onChange({ ...value, fields: next });
  }

  function addDraftField() {
    const name = draftField.trim();
    if (!name || (selected ?? []).some((f) => f.name === name)) return;
    onChange({ ...value, fields: [...(selected ?? []), { name }] });
    setDraftField("");
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          aria-label="Afficher les attributs au clic"
          checked={value !== undefined}
          onChange={(e) => onChange(e.target.checked ? {} : undefined)}
        />
        Afficher les attributs au clic
      </label>
      {value !== undefined && !advanced && (
        <>
          <label className={labelCls}>
            Champ titre
            {/* Une saisie avec datalist plutôt qu'un <select> : le même
                contrôle marche quand availableFields est vide (surface du
                widget carte, où PropsPanel n'a ni schéma ni
                enregistrements) et quand il est renseigné (éditeur de
                cartes, où le schéma de la collection est chargé). */}
            <input
              aria-label="Champ titre"
              list={`${listId}-titre`}
              className={inputCls}
              value={value.titleField ?? ""}
              onChange={(e) => onChange({ ...value, titleField: e.target.value || undefined })}
            />
            <datalist id={`${listId}-titre`}>
              {availableFields.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </label>
          <p className="text-xs text-slate-500">
            Sans sélection, tous les champs sont affichés.
          </p>
          <ul className="flex flex-col gap-1">
            {availableFields.map((f) => {
              const entry = selected?.find((s) => s.name === f);
              return (
                <li key={f} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={f}
                    checked={Boolean(entry)}
                    onChange={() => toggleField(f)}
                  />
                  <span className="flex-1 truncate">{f}</span>
                  {entry && (
                    <input
                      aria-label={`Libellé de ${f}`}
                      className={`${inputCls} w-28`}
                      value={entry.label ?? ""}
                      onChange={(e) =>
                        onChange({
                          ...value,
                          fields: (selected ?? []).map((s) =>
                            s.name === f ? { ...s, label: e.target.value || undefined } : s,
                          ),
                        })
                      }
                    />
                  )}
                </li>
              );
            })}
            {(selected ?? [])
              .filter((f) => !availableFields.includes(f.name))
              .map((f) => (
                <li key={f.name} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={f.name}
                    checked
                    onChange={() => toggleField(f.name)}
                  />
                  <span className="flex-1 truncate">{f.name}</span>
                  <input
                    aria-label={`Libellé de ${f.name}`}
                    className={`${inputCls} w-28`}
                    value={f.label ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        fields: (selected ?? []).map((s) =>
                          s.name === f.name ? { ...s, label: e.target.value || undefined } : s,
                        ),
                      })
                    }
                  />
                </li>
              ))}
          </ul>
          <div className="flex items-center gap-2">
            <input
              aria-label="Nom du champ à ajouter"
              list={`${listId}-titre`}
              className={`${inputCls} flex-1`}
              value={draftField}
              onChange={(e) => setDraftField(e.target.value)}
            />
            <button
              type="button"
              className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              onClick={addDraftField}
            >
              Ajouter le champ
            </button>
          </div>
        </>
      )}
      {value !== undefined && (
        <button
          type="button"
          className="self-start text-xs text-blue-700 underline"
          onClick={() => setAdvanced((a) => !a)}
        >
          {advanced ? "Liste de champs" : "Avancé (gabarit)"}
        </button>
      )}
      {value !== undefined && advanced && (
        <label className={labelCls}>
          Gabarit
          <textarea
            aria-label="Gabarit"
            className="min-h-24 rounded-md border border-slate-300 p-2 font-mono text-xs"
            value={value.template ?? ""}
            onChange={(e) => onChange({ ...value, template: e.target.value })}
          />
          <span className="text-xs text-slate-500">
            Markdown ; chaque {"${expression}"} est évaluée sur l&apos;entité cliquée, par
            exemple {"${record.nom}"}.
          </span>
        </label>
      )}
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
```

Dans `shell/src/map/LayersPanel.tsx`, un composant enfant qui charge le schéma
de la collection quand la couche en déclare une. Le patron est **déjà établi**
par `shell/src/builder/CrossFilterLinkEditor.tsx:28-34` : un `useQuery` inline
sur `client.getCollectionSchema`, clé `["collection-schema", id]`. Ne pas
ajouter de hook à `shell/src/api/hooks.ts` — il n'y en a pas pour ce besoin
aujourd'hui et ce patron-là est celui du dépôt.

```tsx
function LayerPopupEditor({
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
  return (
    <PopupEditor
      value={layer.popup}
      // Sans collectionId (tuiles externes, couche GeoJSON), la liste est
      // vide et l'auteur saisit les noms de champs à la main : PopupEditor
      // gère les deux cas avec le même contrôle.
      availableFields={schema.data?.fields.map((f) => f.name) ?? []}
      onChange={(popup) => onChangeLayer({ ...layer, popup })}
    />
  );
}
```

et, sous chaque `<li>` de couche, pour les seuls kinds qui portent un popup :

```tsx
            {(layer.kind === "vector" || layer.kind === "feature") && (
              <div className="basis-full pl-2">
                <LayerPopupEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
              </div>
            )}
```

`LayersPanel` gagne donc deux imports (`useQuery` de `@tanstack/react-query`,
`useItemClient` de `../api/ItemClientProvider`). Ses tests existants montent
`LayersPanel` sans `QueryClientProvider` : les envelopper, comme le font déjà
les tests de `CrossFilterLinkEditor`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/PopupEditor.test.tsx src/map/LayersPanel.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/PopupEditor.tsx shell/src/map/PopupEditor.test.tsx shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "feat(shell): laisse un auteur configurer le popup de chaque couche"
```

---

## Task 13 : la même surface dans le widget carte

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `PopupEditor` (Task 12), `PopupConfig` (Task 6).
- Produces: rien de nouveau — le widget porte `props.popup` et le pose sur la couche `feature` qu'il construit.

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/builder/widgets/mapWidget.test.tsx` :

```tsx
test("the props panel exposes the shared popup editor", async () => {
  const onChange = vi.fn();
  renderPropsPanel({ props: { dataSourceId: "ds1" }, onChange });
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ popup: {} }));
});

test("the popup editor accepts a hand-typed field name", async () => {
  // PropsPanel ne reçoit que { props, onChange, dataSources }
  // (builder/registry.ts:33-37) : ni schéma ni enregistrements. La saisie
  // libre est donc le seul chemin ici — le même que les champs « Champ
  // couleur » et « Champ taille » voisins.
  const onChange = vi.fn();
  renderPropsPanel({ props: { dataSourceId: "ds1", popup: {} }, onChange });
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ popup: { fields: [{ name: "nom" }] } }),
  );
});

test("the configured popup reaches the layer the widget builds", () => {
  renderWidget({ props: { dataSourceId: "ds1", popup: { titleField: "nom" } } });
  expect(lastMapConfig().layers[0]).toMatchObject({ popup: { titleField: "nom" } });
});

test("no popup configured means no popup on the layer", () => {
  renderWidget({ props: { dataSourceId: "ds1" } });
  expect(lastMapConfig().layers[0].popup).toBeUndefined();
});
```

Les helpers `renderPropsPanel`, `renderWidget` et `lastMapConfig` suivent le
patron déjà en place dans ce fichier — le lire avant d'écrire, ne pas en
inventer un second.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL — aucune case « Afficher les attributs au clic », `popup` absent de la couche

- [ ] **Step 3: Write the implementation**

**`configSchema` n'est PAS touché.** `WidgetPropDescriptor.type`
(`shell/src/builder/widgetPropSchema.ts`) n'accepte que
`"string" | "number" | "boolean" | "dataSource"` — il n'y a pas de type pour un
objet imbriqué, et en ajouter un se propagerait dans `clientTools.ts` et dans
la forme des manifestes de widgets WC (SP-8). Conséquence assumée, à écrire
dans les suivis de CLAUDE.md (tâche 17) : **le copilote SP-20 ne peut pas
écrire `popup`**, puisque `applyClientOp` filtre tout patch de prop par le
`configSchema` du widget. L'auteur humain, lui, l'édite normalement.

Dans le `PropsPanel`, après le champ « Champ taille » :

```tsx
          <PopupEditor
            value={props.popup as PopupConfig | undefined}
            // PropsPanel ne reçoit ni schéma ni enregistrements
            // (registry.ts:33-37) : la liste proposée est vide et l'auteur
            // saisit les noms de champs, exactement comme pour « Champ
            // couleur » juste au-dessus. Aucun appel réseau ajouté ici.
            availableFields={[]}
            onChange={(popup) => onChange({ ...props, popup })}
          />
```

Dans le `Component`, sur la couche construite (l.238-249) :

```ts
                popup: props.popup as PopupConfig | undefined,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): porte le popup sur le widget carte des apps et des sites"
```

---

## Task 14 : le sélecteur de couches ne propose plus qu'une entrée tuilée

**Files:**
- Modify: `shell/src/api/itemClient.ts:393-431,619-633`
- Modify: `shell/src/api/types.ts` (`LayerSource`)
- Modify: `shell/src/map/LayerPicker.tsx:6-32`
- Test: `shell/src/api/itemClient.test.ts:195-320`
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Produces: `LayerSource` gagne `collectionId?`, `geometryKind?`, `pkColumn?` et perd `"martin"` de son union `service` ; `toMapLayer` propage les trois.

- [ ] **Step 1: Write the failing tests**

Remplacer, dans `shell/src/api/itemClient.test.ts`, le test
« listLayerSources aggregates Martin vector sources and core collections » par :

```ts
test("listLayerSources returns one tiled entry per core collection, and no Martin source", async () => {
  // Martin sort du sélecteur (spec SP-24 §3.7) : il se connecte en
  // propriétaire des tables, donc hors RLS, et n'a aucune notion de
  // collection. Une même collection n'apparaît plus qu'une fois.
  const sources = await makeClient("abc").listLayerSources();
  expect(sources.map((s) => s.service)).not.toContain("martin");
  const communes = sources.find((s) => s.id === "communes")!;
  expect(communes).toMatchObject({
    service: "core",
    kind: "vector",
    collectionId: "communes",
    geometryKind: "polygon",
    pkColumn: "id",
    tilesUrl: "http://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
  });
  expect(communes.sourceLayer).toBe("communes");
});

test("a collection without geometry type yields no geometryKind rather than a wrong one", async () => {
  const sources = await makeClient().listLayerSources();
  expect(sources.find((s) => s.id === "sans_geom")?.geometryKind).toBeUndefined();
});

test("the Martin catalog is never fetched any more", async () => {
  await makeClient().listLayerSources();
  expect(fetchMock.mock.calls.map(([u]) => String(u))).not.toContain(
    expect.stringContaining("/catalog"),
  );
});
```

Adapter la fixture de réponse `/collections` du fichier pour qu'elle porte
`geometryType`, `pkColumn` et une collection sans géométrie — la vraie route les
renvoie déjà (`core/app/collections/routes.py:132-146`).

Ajouter à `shell/src/map/LayerPicker.test.tsx` :

```tsx
test("adding a collection produces a tiled layer bound to it", async () => {
  const onAdd = vi.fn();
  render(<LayerPicker onAdd={onAdd} />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter Communes" }));
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({
      kind: "vector",
      collectionId: "communes",
      geometryKind: "polygon",
      pkColumn: "id",
    }),
  );
});
```

Le nom exact du bouton se lit dans le fichier existant — ne pas le deviner.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/map/LayerPicker.test.tsx`
Expected: FAIL — les sources Martin sont toujours là, la collection sort en `kind: "feature"`

- [ ] **Step 3: Write the implementation**

Dans `shell/src/api/types.ts` :

```ts
export type LayerSource = {
  id: string;
  title: string;
  service: "core" | "external" | "tileset3d";
  kind: "vector" | "feature" | "raster" | "tiles3d";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
  collectionId?: string;
  geometryKind?: "point" | "line" | "polygon";
  pkColumn?: string;
};
```

Dans `shell/src/api/itemClient.ts` : supprimer `fetchMartinSources` (l.393-411)
et son entrée dans `Promise.allSettled` (l.621), puis remplacer le corps de
`fetchCoreCollections` :

```ts
  // Une collection sort désormais en couche TUILÉE servie par le cœur (SP-24) :
  // elle passe à l'échelle, elle est autorisée par can(), et elle porte son
  // collectionId — ce dont le popup et la symbologie SP-25 ont besoin.
  const GEOMETRY_KINDS: Record<string, "point" | "line" | "polygon"> = {
    Point: "point",
    MultiPoint: "point",
    LineString: "line",
    MultiLineString: "line",
    Polygon: "polygon",
    MultiPolygon: "polygon",
  };

  async function fetchCoreCollections(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/collections${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: {
        id: string;
        title?: string;
        featureCount?: number | null;
        geometryType?: string | null;
        pkColumn?: string | null;
      }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "vector" as const,
      tilesUrl: `${coreUrl}/collections/${c.id}/tiles/{z}/{x}/{y}.mvt`,
      sourceLayer: c.id,
      collectionId: c.id,
      geometryKind: c.geometryType ? GEOMETRY_KINDS[c.geometryType] : undefined,
      pkColumn: c.pkColumn ?? undefined,
      featureCount: c.featureCount,
    }));
  }
```

Le nom de la couche source MVT est `col.id`, exactement le second argument de
`ST_AsMVT` côté cœur (`:layer` dans `build_mvt_sql`, Task 1) — les deux doivent
rester égaux.

Dans `shell/src/map/LayerPicker.tsx`, la branche `vector` de `toMapLayer` :

```ts
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
      collectionId: source.collectionId,
      geometryKind: source.geometryKind,
      pkColumn: source.pkColumn,
    };
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api src/map`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "feat(shell): propose une seule entrée tuilée par collection"
```

---

## Task 15 : retirer le câblage de Martin

**Files:**
- Modify: `docker-compose.prod.yml:33-43,147`
- Modify: `shell/src/config.ts:55`
- Modify: `shell/playwright.config.ts:15`
- Modify: `.env.example` (si un nom y devient inerte)
- Test: `core/tests/test_deployability.py` (exécution, pas modification)

**Interfaces:** aucune.

- [ ] **Step 1: Constater l'état de départ**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -n "tiles\|MARTIN"`
Expected: les labels Traefik `/tiles` et `VITE_MARTIN_URL` apparaissent.
Noter la sortie : c'est la preuve « avant » du retrait.

- [ ] **Step 2: Retirer**

Dans `docker-compose.prod.yml`, le service `martin` perd son bloc `labels:`
entier (l.36-43) et garde `restart` + `ports: !reset []` :

```yaml
  martin:
    restart: unless-stopped
    ports: !reset []
    # Plus de route publique depuis SP-24 : Martin se connecte en propriétaire
    # des tables (donc hors RLS) et n'a aucune notion de collection ni de
    # can(). Les tuiles vectorielles d'une collection passent désormais par
    # GET /collections/{id}/tiles/{z}/{x}/{y}.mvt, servi par le cœur. Le
    # service reste joignable sur le réseau interne.
```

et le service `shell` perd sa ligne `VITE_MARTIN_URL` (l.147).

Dans `shell/src/config.ts`, retirer `martinUrl` (l.55) et son type ; dans
`shell/playwright.config.ts`, retirer `VITE_MARTIN_URL` (l.15).

- [ ] **Step 3: Vérifier par valeur, pas seulement « ça parse »**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -c "strip-tiles\|VITE_MARTIN_URL"`
Expected: `0`

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -A3 "martin:"`
Expected: le service existe toujours, sans labels.

- [ ] **Step 4: Vérifier que le garde-fou de déployabilité reste vert**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: 9 PASSED. En cas d'échec sur la 8ᵉ règle (« documenté ⇒ câblé ou déclaré inerte »), c'est qu'un nom de `.env.example` est devenu inerte : le commenter avec sa raison, comme le bloc S3 existant.

- [ ] **Step 5: Vérifier que le shell compile et que rien ne lit plus martinUrl**

Run: `cd shell && grep -rn "martinUrl\|MARTIN_URL" src e2e *.ts | grep -v node_modules; npm run build`
Expected: aucune occurrence hors `MARTIN_SECRET` de `.env.example` (orpheline documentée depuis SP-1d3) ; build vert

- [ ] **Step 6: Commit**

```bash
git add docker-compose.prod.yml shell/src/config.ts shell/playwright.config.ts .env.example
git commit -m "fix(deploy): retire la route publique non authentifiée des tuiles martin"
```

---

## Task 16 : la preuve de sortie, en E2E

**Files:**
- Create: `core/scripts/dump_mvt_fixture.py`
- Create: `shell/e2e/fixtures/world-tile.mvt` (binaire, produit une fois par le script ci-dessus)
- Create: `shell/e2e/map-popup.spec.ts`
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: la preuve de sortie du chantier 4.1 du plan d'action.

Le clic réel sur un canvas MapLibre est un chemin **déjà prouvé** dans ce dépôt :
`shell/e2e/analytics-context.spec.ts:299-318` pilote la vraie carte à la souris,
avec commentaire explicite « Chromium a WebGL » dans `map-editor.spec.ts:16`. On
ne pose donc **aucune** porte de test dans le code de production : on sert une
vraie tuile MVT et on clique.

- [ ] **Step 1: Écrire le script de génération de la fixture**

`core/scripts/dump_mvt_fixture.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Produit shell/e2e/fixtures/world-tile.mvt : une tuile MVT à une entité
polygonale couvrant presque toute la tuile 0/0/0, portant les propriétés que la
spec E2E attend. À exécuter UNE FOIS contre un PostGIS réel ; le résultat est
committé et n'a pas à être régénéré.

    CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run python scripts/dump_mvt_fixture.py

Le nom de la couche ("communes") doit rester égal au `sourceLayer` de la couche
de test dans shell/e2e/mocks.ts, et au :layer que la route passe à ST_AsMVT."""

import os
import pathlib
import sys

from sqlalchemy import create_engine, text

SQL = """
SELECT ST_AsMVT(tile, 'communes', 4096, 'geom', 'id') FROM (
  SELECT ST_AsMVTGeom(
           ST_Transform(ST_SetSRID(ST_MakeEnvelope(-170, -80, 170, 80), 4326), 3857),
           ST_TileEnvelope(0, 0, 0), 4096, 64, true) AS geom,
         1 AS id, 'Tulle' AS nom, 14000 AS population
) AS tile WHERE tile.geom IS NOT NULL
"""

OUT = (
    pathlib.Path(__file__).parent.parent.parent
    / "shell"
    / "e2e"
    / "fixtures"
    / "world-tile.mvt"
)


def main() -> int:
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        print("CORE_TEST_DATABASE_URL est requis (PostGIS réel)", file=sys.stderr)
        return 1
    with create_engine(url).connect() as conn:
        tile = conn.execute(text(SQL)).scalar()
    if not tile:
        print("la requête n'a produit aucune tuile", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(tile))
    print(f"{OUT} — {len(bytes(tile))} octets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Générer la fixture et la committer**

Run: `cd core && CORE_TEST_DATABASE_URL=<url PostGIS> uv run python scripts/dump_mvt_fixture.py`
Expected: un fichier de quelques dizaines d'octets à `shell/e2e/fixtures/world-tile.mvt`, et `xxd shell/e2e/fixtures/world-tile.mvt | grep -c communes` ≥ 1.

**Si aucun PostGIS n'est disponible, cette tâche est bloquée** : le dire en
clair dans le rapport, ne pas la remplacer par une couche GeoJSON qui ne
prouverait pas D2 — c'est-à-dire précisément le constat que SP-24 existe pour
fermer. Précédent à ne pas rejouer : les 5 tests `@pytest.mark.qgis` de SP-15d,
jamais exécutés.

- [ ] **Step 3: Ajouter la carte de test au mock**

Dans `shell/e2e/mocks.ts`, la config de carte servie pour `map-1` porte une
couche tuilée avec son popup (lire le fichier avant : la forme exacte de la
réponse `/configs/{id}` s'y trouve déjà pour `map-editor.spec.ts`) :

```ts
{
  id: "communes",
  title: "Communes",
  visible: true,
  kind: "vector",
  tilesUrl: "http://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
  sourceLayer: "communes",
  collectionId: "communes",
  geometryKind: "polygon",
  pkColumn: "id",
  popup: { titleField: "nom", fields: [{ name: "population", label: "Habitants" }] },
}
```

- [ ] **Step 4: Write the failing spec**

`shell/e2e/map-popup.spec.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(
  fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)),
);

// La preuve de sortie du chantier 4.1 du plan d'action : cliquer une entité
// d'une collection servie en tuiles MVT ouvre un popup renseigné, sur une
// carte publiée, sans widget d'app à côté.
test("un lecteur clique une entité tuilée et voit ses attributs", async ({ page }) => {
  await mockCore(page);
  // Toute tuile demandée renvoie la même fixture : un polygone couvrant
  // presque toute la tuile, donc un clic au centre du canvas le touche
  // quel que soit le niveau de zoom courant.
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

  const popup = page.getByRole("dialog", { name: "Attributs de l'entité" });
  await expect(popup).toBeVisible();
  await expect(popup.getByText("Tulle")).toBeVisible();
  await expect(popup.getByText("Habitants")).toBeVisible();
  await expect(popup.getByText("14000")).toBeVisible();
  // Le champ titre n'est pas répété en ligne d'attribut.
  await expect(popup.getByText("nom")).toHaveCount(0);

  await popup.getByRole("button", { name: "Fermer" }).click();
  await expect(popup).toHaveCount(0);
});

test("la requête de tuile porte le jeton de session", async ({ page }) => {
  await mockCore(page);
  const tileRequest = page.waitForRequest((r) =>
    r.url().includes("/collections/communes/tiles/"),
  );
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );
  await page.goto("/maps/map-1");
  const req = await tileRequest;
  expect(req.headers()["authorization"]).toMatch(/^Bearer /);
});
```

- [ ] **Step 5: Run the spec to verify it fails, then make it pass**

Run: `cd shell && npx playwright test e2e/map-popup.spec.ts`
Expected d'abord: FAIL. Puis PASS après correction de ce que la spec révèle
(elle exerce du code déjà écrit par les tâches 6 à 15 : tout échec ici est un
défaut réel de l'une d'elles, à corriger là où il est).

- [ ] **Step 6: Run the whole E2E suite**

Run: `cd shell && npm run e2e`
Expected: 107 passed / 4 skipped / 0 failed (105 + les 2 nouvelles).
Une spec pré-existante qui casserait sur un texte devenu ambigu se corrige par
`.last()`, comme les six corrigées par SP-23 tâche 18.

- [ ] **Step 7: Commit**

```bash
git add core/scripts/dump_mvt_fixture.py shell/e2e/fixtures/world-tile.mvt shell/e2e/map-popup.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): prouve le popup au clic sur une entité tuilée"
```

---

## Task 17 : clôture — portes complètes et CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** aucune.

- [ ] **Step 1: Toutes les portes du cœur**

```bash
cd core
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
```
Expected: pas de baisse par rapport à 1675 passed / 154 skipped ; tout vert ; `Contracts: 1 kept, 0 broken.`
**Reporter le nombre de SKIPPED par marqueur** : si les tests `postgis` des tâches 3/4/5 n'ont pas tourné pour de vrai, le dire en clair — précédent SP-15d.

- [ ] **Step 2: Couverture du cœur**

Run: `cd core && uv run pytest --cov=app --cov-report=term-missing -q && uv run python scripts/check_coverage.py`
Expected: ≥ 85

- [ ] **Step 3: Toutes les portes du shell**

```bash
cd shell
rm -rf dist dist-export   # artefacts locaux gitignorés comptés comme source non couverte
npm run lint
npm run format:check
npm run test
npm run build
npm run e2e
```
Expected: lint/format verts ; tests ≥ 155 fichiers / 1302 tests ; build vert ; e2e 106 passed / 4 skipped ; couverture ≥ 88

- [ ] **Step 4: Pre-commit sur tout le dépôt**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 verts. Rappel : `--all-files` n'exerce **pas** `commitlint` (étage `commit-msg`) — ne pas lire ce vert comme couvrant les 6 hooks.

- [ ] **Step 5: Confirmer que les artefacts générés sont synchronisés**

Run: `git status --porcelain core/openapi.json shell/src/api/generated/`
Expected: vide. Si non, la Task 7 a été faite trop tôt : régénérer et committer.

- [ ] **Step 6: Mettre CLAUDE.md à jour**

Ajouter une entrée `- **SP-24** — …` dans `### Fait`, écrite comme les
précédentes : ce qui est livré, les deux élargissements de périmètre et leur
raison, le changement cassant du retrait de `/tiles`, et ce qui reste ouvert.
Ajouter à `### Suivis non bloquants ouverts` :

- D2 reste vrai dans le widget carte d'app (couche `feature`, plafond
  silencieux de 100 entités) ;
- aucun `audit_log` par tuile, donc aucune trace d'une lecture massive par le
  chemin tuilé ;
- une valeur de propriété est interprétée comme du markdown dans un popup à
  gabarit ;
- la seconde syntaxe d'expression (`${…}`) coexiste avec le binding `{ $expr }` ;
- le copilote SP-20 ne peut pas écrire `popup` sur le widget carte
  (`WidgetPropDescriptor.type` n'a pas de forme pour un objet imbriqué, et
  `applyClientOp` filtre par `configSchema`) — décision de la tâche 13 ;
- une table PostGIS ajoutée à la main hors registre n'a plus de chemin de
  service depuis le retrait de `/tiles` ;
- aucune mesure de latence par tuile n'a été produite.

Retirer de `### À venir` ce que SP-24 ferme (le chantier 4.1) et noter que le
lot Carte continue en SP-25 (4.2/4.3).

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(sp24): consigne la carte interrogeable et ses suivis"
```

---

## Revue finale de branche

Après la tâche 17, **avant tout merge** : lancer une revue finale de branche sur
l'ensemble des commits SP-24, pas tâche par tâche. Les défauts les plus graves
de ce dépôt (SP-17a, SP-18a, SP-21, SP-23) ont tous été trouvés à ce
niveau-là et étaient invisibles à une revue par tâche. Points à croiser
explicitement, parce qu'ils sont à l'intersection de plusieurs tâches :

1. Le nom de couche MVT côté cœur (`:layer` = `col.id`, Task 1/2) et le
   `sourceLayer` côté shell (Task 14) doivent être égaux — sinon la couche est
   muette, sans erreur.
2. `transformRequest` porte le jeton sur tout `/collections/` (Task 10) : vérifier
   qu'aucune requête sortante vers une autre origine n'en reçoit, et que le
   GeoJSON `/items` d'une couche `feature` en bénéficie bien lui aussi.
3. Le repli `properties[pkColumn]` (Task 10) et le `mvt_feature_id_column`
   (Task 1) sont les deux moitiés d'une même décision : une PK texte doit
   rester cliquable de bout en bout.
4. `PopupEditor` est monté sur les deux surfaces (Tasks 12 et 13) avec le même
   comportement d'activation — c'est exactement l'écart I2 de SP-23.
5. L'index GiST (Task 4) et le `&&` sur géométrie brute (Task 1) : vérifier par
   `EXPLAIN` sur PostGIS réel que le plan utilise bien l'index.
6. Le retrait de Martin (Tasks 14 et 15) est-il complet — aucun code, aucune
   config, aucun test ne le référence plus ?
