# SP-6c — Nombre d'entités par collection : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stocker `feature_count` sur `Collection`, le tenir à jour à chaque écriture OGC API Features (create/delete), l'exposer sur `GET /collections`/`GET /collections/{id}`, et l'afficher comme badge (« N entités ») dans le sélecteur de source de couche du builder (`LayerPicker`).

**Architecture:** Ajout net sur SP-6a/SP-6b — mêmes tables, même pipeline d'ingestion. Une nouvelle colonne nullable `feature_count` sur `Collection`, initialisée à l'ingestion (gratuit, déjà en mémoire), à l'enregistrement admin (un `COUNT(*)` via une dépendance injectable au même patron que `get_extent_provider`), et rétroactivement par la migration elle-même (backfill des collections existantes). Maintenue ensuite par des `UPDATE ... SET feature_count = feature_count ± 1` atomiques dans les routes d'écriture OGC Features — jamais un cycle lire-l'attribut-ORM-puis-réécrire.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (Tasks 1-4), React 19 + TypeScript + Vitest (Tasks 5-6).

## Global Constraints

- **Ajout net sur SP-6a/SP-6b** (cf. `docs/superpowers/specs/2026-07-12-sp6c-feature-count-design.md`) : aucun refactor du code existant au-delà de ce que le plan liste.
- **Hors périmètre** (tranché en brainstorm, ne pas re-débattre) : l'emprise (bbox) et le schéma des champs restent tels quels (déjà servis en live par `extent_provider`/`GET /collections/{id}/schema`, non touchés par SP-6c) ; aucun badge sur `ItemCard` (un item carte référence 0..N collections, pas de relation 1:1) ; aucun catalogue STAC complet.
- **Le compteur est un snapshot maintenu par delta atomique**, jamais un `COUNT(*)` recalculé à la demande — contrairement à l'emprise, qui reste volontairement live.
- **Toute collection a un `feature_count` non-`NULL` après la migration 0011** (backfill inclus dans la migration elle-même, pas de script séparé) ; les routes d'écriture n'ont donc pas de cas `NULL` particulier à gérer explicitement (dégradation SQL silencieuse acceptable pour un résidu `NULL` non bloquant si une table backing a disparu).
- **Pas de régénération OpenAPI nécessaire** : `register_collection`/`get_collection`/`list_collections` n'ont pas de `response_model` Pydantic (vérifié : leur schéma OpenAPI actuel est `{}`, vide) — `featureCount` n'apparaîtra pas dans `core/openapi.json` ni dans `core-schema.d.ts`, et ce n'est pas un défaut de ce plan. Le typage côté shell pour `/collections` est un type TypeScript écrit à la main dans `itemClient.ts` (pas généré) — c'est lui qu'on étend.
- Aucune régression : `cd core && uv run pytest` et `cd shell && npm run test` + `npm run build` doivent rester verts après chaque tâche.
- Docs et messages utilisateur en français ; code/identifiants en anglais. TDD systématique ; commits conventional en français.
- Comme en SP-6b, certains tests nécessitent un PostGIS réel (`CORE_TEST_DATABASE_URL`, marqueur `pytest.mark.postgis`, skippés sinon) — vérifier réellement contre un conteneur PostGIS jetable plutôt que de se fier au skip local, comme établi en SP-6a/SP-6b.

---

## Task 1: `collections.feature_count` — migration + backfill, modèle, repository

**Files:**
- Create: `core/alembic/versions/0011_collections_feature_count.py`
- Modify: `core/app/collections/models.py`
- Modify: `core/app/collections/repository.py`
- Modify: `core/tests/test_collections_models.py`

**Interfaces:**
- Produces: `Collection.feature_count: int | None` ; `repository.create_collection(..., feature_count: int | None = None) -> Collection` (nouveau kwarg optionnel, défaut `None`, appelants existants inchangés tant que leur propre tâche ne les met pas à jour).
- Consumes: rien de nouveau.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `core/tests/test_collections_models.py` :

```python
def test_collection_row_stores_feature_count():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        session.add(Collection(
            id="incidents", tenant_id=tenant.id, owner_id=user.id,
            table_name="incidents", title="Incidents", pk_column="id",
            geometry_column="geom", geometry_type="Point", srid=4326,
            feature_count=42,
        ))
        session.commit()
        row = session.get(Collection, "incidents")
        assert row.feature_count == 42


def test_create_collection_defaults_feature_count_to_none():
    from app.collections.repository import create_collection
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        col = create_collection(
            session, tenant_id=tenant.id, owner_id=user.id, table_name="incidents",
            title="Incidents", description="", is_public=False, pk_column="id",
            geometry_column="geom", geometry_type="Point", srid=4326,
        )
        assert col.feature_count is None


def test_create_collection_stores_feature_count():
    from app.collections.repository import create_collection
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        col = create_collection(
            session, tenant_id=tenant.id, owner_id=user.id, table_name="incidents",
            title="Incidents", description="", is_public=False, pk_column="id",
            geometry_column="geom", geometry_type="Point", srid=4326,
            feature_count=7,
        )
        assert col.feature_count == 7
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_models.py -v`
Expected: FAIL — `TypeError: 'feature_count' is an invalid keyword argument for Collection` sur le premier nouveau test ; `TypeError: create_collection() got an unexpected keyword argument 'feature_count'` sur les deux suivants.

- [ ] **Step 3: Modèle**

Dans `core/app/collections/models.py`, ajouter la colonne juste après `srid` :

```python
    srid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

(`Integer` est déjà importé en tête de fichier — aucun nouvel import.)

- [ ] **Step 4: Repository**

Dans `core/app/collections/repository.py`, modifier `create_collection` :

```python
def create_collection(session: Session, *, tenant_id: str, owner_id: str, table_name: str,
                      title: str, description: str, is_public: bool,
                      pk_column: str, geometry_column: str | None,
                      geometry_type: str | None, srid: int | None,
                      feature_count: int | None = None) -> Collection:
    col = Collection(
        id=table_name, tenant_id=tenant_id, owner_id=owner_id, table_name=table_name,
        title=title, description=description, is_public=is_public, pk_column=pk_column,
        geometry_column=geometry_column, geometry_type=geometry_type, srid=srid,
        feature_count=feature_count,
    )
    session.add(col)
    session.flush()
    return col
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_models.py -v`
Expected: 6 passed (3 existants + 3 nouveaux).

- [ ] **Step 6: Migration avec backfill**

Créer `core/alembic/versions/0011_collections_feature_count.py` :

```python
"""collections.feature_count (SP-6c) — backfill via COUNT(*) sur chaque
collection déjà enregistrée

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("feature_count", sa.Integer(), nullable=True)
    )
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    existing_tables = {
        row[0] for row in conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )).all()
    }
    quote = conn.dialect.identifier_preparer.quote
    rows = conn.execute(sa.text("SELECT id, table_name FROM collections")).all()
    for collection_id, table_name in rows:
        if table_name not in existing_tables:
            logger.warning(
                "SP-6c backfill: table public.%s introuvable pour la collection "
                "%s, feature_count laissé NULL", table_name, collection_id,
            )
            continue
        t = quote(table_name)
        count = conn.execute(sa.text(f"SELECT count(*) FROM public.{t}")).scalar_one()
        conn.execute(
            sa.text("UPDATE collections SET feature_count = :n WHERE id = :id"),
            {"n": count, "id": collection_id},
        )


def downgrade() -> None:
    op.drop_column("collections", "feature_count")
```

Note : la vérification d'existence via `information_schema.tables` (plutôt qu'un
`try/except` autour du `SELECT count(*)`) évite qu'une table manquante laisse la
transaction Postgres de la migration dans un état avorté (`current transaction is
aborted`) qui ferait échouer tous les `UPDATE` suivants — c'est une garde
préventive, pas juste un ajout défensif.

- [ ] **Step 7: Valider la migration et le backfill contre un PostGIS jetable réel**

Spin up un conteneur PostGIS jetable (même patron que SP-6b Tasks 3-5, image
`postgis/postgis:16-3.4`, `POSTGRES_USER=gis`/`POSTGRES_PASSWORD=test`/
`POSTGRES_DB=gis_test`, port libre — vérifier `docker ps` d'abord).

```bash
export CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:test@localhost:<port>/gis_test"
cd core && uv run alembic upgrade 0010
```

Insérer une collection « historique » (créée avant SP-6c) avec sa table backing
et des lignes réelles, pour vérifier que le backfill la retrouve. Écrire ce
script dans un fichier plutôt qu'un `-c` en ligne (évite l'imbrication de
guillemets sur du SQL qui en contient déjà) :

```bash
cat > /tmp/sp6c_seed_legacy.py <<'EOF'
import os

from sqlalchemy import text

from app.db import make_engine

engine = make_engine(os.environ["CORE_TEST_DATABASE_URL"])
with engine.begin() as conn:
    conn.execute(text(
        "INSERT INTO tenants (id, slug, name, created_at) VALUES "
        "('t1', 't1', 'Tenant 1', now())"
    ))
    conn.execute(text(
        "INSERT INTO users (id, tenant_id, oidc_sub, username, email, first_name, "
        "last_name, is_admin, created_at, updated_at) VALUES "
        "('u1', 't1', 'sub1', 'alice', NULL, '', '', true, now(), now())"
    ))
    conn.execute(text(
        "CREATE TABLE public.legacy_villes (id serial PRIMARY KEY, "
        "tenant_id text NOT NULL DEFAULT 'default', nom text, "
        "geom geometry(Point,4326))"
    ))
    conn.execute(text(
        "INSERT INTO legacy_villes (nom, geom) VALUES "
        "('A', ST_SetSRID(ST_MakePoint(1,45),4326)), "
        "('B', ST_SetSRID(ST_MakePoint(2,46),4326))"
    ))
    conn.execute(text(
        "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
        "description, pk_column, geometry_column, geometry_type, srid, "
        "is_public, editable, created_at, updated_at) VALUES "
        "('legacy_villes', 't1', 'u1', 'legacy_villes', 'Villes historiques', "
        "'', 'id', 'geom', 'Point', 4326, false, true, now(), now())"
    ))
EOF
uv run python /tmp/sp6c_seed_legacy.py
uv run alembic upgrade head
cat > /tmp/sp6c_check_backfill.py <<'EOF'
import os

from sqlalchemy import text

from app.db import make_engine

engine = make_engine(os.environ["CORE_TEST_DATABASE_URL"])
with engine.begin() as conn:
    print(conn.execute(text(
        "SELECT feature_count FROM collections WHERE id = 'legacy_villes'"
    )).scalar_one())
EOF
uv run python /tmp/sp6c_check_backfill.py
```

Expected: la dernière commande affiche `2` (le backfill a compté les 2 lignes
de `legacy_villes`). Consigner cette sortie dans le rapport de tâche — c'est
la preuve empirique que le backfill fonctionne, pas seulement que la colonne
existe.

Puis lancer la suite complète contre le même conteneur pour confirmer
l'absence de régression, et démonter le conteneur :

Run: `cd core && uv run pytest`
Expected: tous les tests passent (avec `CORE_TEST_DATABASE_URL` défini, y
compris les tests `postgis`).

- [ ] **Step 8: Suite complète sans DB + commit**

Run: `cd core && unset CORE_TEST_DATABASE_URL && uv run pytest`
Expected: aucune régression (tests postgis skippés proprement).

```bash
git add core/alembic/versions/0011_collections_feature_count.py \
        core/app/collections/models.py core/app/collections/repository.py \
        core/tests/test_collections_models.py
git commit -m "feat(core): collections.feature_count — migration + backfill, modèle, repository (SP-6c)"
```

---

## Task 2: Ingestion — `run_import` fixe `feature_count`

**Files:**
- Modify: `core/app/ingestion/importer.py`
- Modify: `core/tests/test_ingestion_importer.py`

**Interfaces:**
- Consumes: `collections_repo.create_collection(..., feature_count=None)` (Task 1).
- Produces: rien de nouveau — `run_import` passe simplement `feature_count=len(rows)`, déjà calculable sans requête supplémentaire (`rows` est une liste déjà entièrement matérialisée en mémoire avant l'insertion PostGIS, cf. `core/app/ingestion/importer.py` ligne ~85).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `core/tests/test_ingestion_importer.py` :

```python
def test_geojson_import_stores_feature_count(env):
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.geojson",
            content=GEOJSON, collection_title="Villes", lat_field=None, lon_field=None,
        )
        s.commit()
    with Session() as s:
        col = collections_repo.get_collection(
            s, tenant_id=tenant.id, collection_id=result.collection_id)
        assert col.feature_count == 2  # GEOJSON contient 2 features (A, B)
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_importer.py -v -k feature_count`
(sans `CORE_TEST_DATABASE_URL` : le test est skippé, pas d'échec visible —
lancer contre un PostGIS jetable réel comme en Task 1 Step 7, ou réutiliser
le même conteneur s'il tourne encore.)
Expected: FAIL — `AssertionError: assert None == 2` (le champ existe depuis
Task 1 mais `run_import` ne le remplit pas encore).

- [ ] **Step 3: Passer `feature_count` à `create_collection`**

Dans `core/app/ingestion/importer.py`, modifier l'appel à `create_collection` :

```python
    col = collections_repo.create_collection(
        session, tenant_id=tenant_id, owner_id=created_by, table_name=table_name,
        title=collection_title, description="", is_public=False,
        pk_column=info.pk_column, geometry_column=info.geometry_column,
        geometry_type=info.geometry_type, srid=info.srid, feature_count=len(rows),
    )
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_importer.py -v`
Expected: tous les tests passent (existants + le nouveau).

- [ ] **Step 5: Suite complète + commit**

Run: `cd core && uv run pytest` (avec puis sans `CORE_TEST_DATABASE_URL`, comme en Task 1).

```bash
git add core/app/ingestion/importer.py core/tests/test_ingestion_importer.py
git commit -m "feat(core): run_import — fixe feature_count à l'ingestion (SP-6c)"
```

---

## Task 3: Enregistrement admin — `get_feature_counter`, `register_collection`, API, `seed_demo.py`

**Files:**
- Modify: `core/app/collections/routes.py`
- Modify: `core/scripts/seed_demo.py`
- Modify: `core/tests/test_collections_routes.py`
- Modify: `core/tests/test_seed_demo.py`
- Modify: `core/tests/test_features_integration.py`

**Interfaces:**
- Produces: `collections_routes.get_feature_counter()` — dépendance FastAPI (même patron que `get_extent_provider`) fournissant `counter(session, table_name) -> int | None` ; `None` hors PostgreSQL (tests SQLite). `_collection_json` gagne la clé `"featureCount"`.
- Consumes: `repository.create_collection(..., feature_count=...)` (Task 1).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_collections_routes.py`, étendre `test_register_and_get` :

```python
def test_register_and_get(env):
    app, client, _, admin, _regular, ddl_calls = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "incidents", "title": "Incidents"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "incidents" and body["geometryType"] == "Point"
    assert body["featureCount"] is None  # hors PostgreSQL (SQLite) : pas de vrai COUNT(*)
    assert ddl_calls == ["incidents"]  # la RLS est appliquée à l'enregistrement
    assert client.get("/collections/incidents").status_code == 200
```

Dans `core/tests/test_seed_demo.py`, étendre `test_seed_registers_demo_collections` :

```python
def test_seed_registers_demo_collections(pg_core):
    with pg_core() as session:
        created = seed(session)
        session.commit()
    assert set(created) == {"incidents", "points_interet"}
    with pg_core() as session:
        rows = session.execute(text(
            "SELECT id, is_public, editable, feature_count FROM collections ORDER BY id")).all()
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [
        ("incidents", True, True, 0), ("points_interet", True, True, 0)]
```

(Les tables `incidents`/`points_interet` créées par la fixture `pg_core` sont
vides — `feature_count` attendu à `0`, pas `None`, car `seed_demo.py` appellera
un vrai `COUNT(*)` sur du PostgreSQL réel.)

Dans `core/tests/test_features_integration.py`, étendre `test_full_crud_roundtrip`
juste après la ligne `assert client.post("/collections", ...).status_code == 201` :

```python
def test_full_crud_roundtrip(pg_app):
    client = pg_app
    assert client.post("/collections", json={"tableName": "demo_incidents"}).status_code == 201
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 0
    r = client.post("/collections/demo_incidents/items", json={
    ...  # reste du test inchangé
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k register_and_get`
Expected: FAIL — `KeyError: 'featureCount'`.

Run (PostGIS réel, comme en Task 1 Step 7) : `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_seed_demo.py tests/test_features_integration.py -v`
Expected: FAIL sur les deux assertions `feature_count`/`featureCount` (`0` attendu, `None` obtenu — `register_collection`/`seed_demo.py` ne calculent pas encore le compte).

- [ ] **Step 3: `get_feature_counter` + `register_collection` + `_collection_json`**

Dans `core/app/collections/routes.py`, ajouter la dépendance juste après
`get_extent_provider` :

```python
def get_feature_counter():
    """Défaut : COUNT(*) réel sur la table backing. None hors PostgreSQL
    (tests SQLite) : la collection reste avec feature_count=None, cohérent
    avec le comportement documenté pour les collections pré-SP-6c non
    encore backfillées. Pas de scope RLS ici (contrairement à
    get_extent_provider) : à l'enregistrement, on veut le compte physique
    total de la table, pas une vue filtrée par tenant — RLS ne s'applique
    de toute façon qu'après apply_ddl, déjà passé à ce stade."""
    from sqlalchemy import text as _text

    from app.collections.ddl import quote_ident

    def counter(session, table_name):
        if session.get_bind().dialect.name != "postgresql":
            return None
        t = quote_ident(session, table_name)
        return session.execute(_text(f"SELECT count(*) FROM public.{t}")).scalar_one()

    return counter
```

Modifier `_collection_json` :

```python
def _collection_json(col, can_write: bool) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": col.editable,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
        "canWrite": can_write, "featureCount": col.feature_count,
    }
```

Modifier la signature et le corps de `register_collection` :

```python
@router.post("/collections", status_code=201)
def register_collection(
    body: CollectionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
    count_features=Depends(get_feature_counter),
):
    _require_admin(user)
    if body.tableName in _core_tables():
        raise HTTPException(status_code=400, detail="core table cannot be registered")
    if repo.get_collection(session, tenant_id=user.tenant_id, collection_id=body.tableName):
        raise HTTPException(status_code=409, detail="table already registered")
    try:
        info = introspect(session, body.tableName)
    except TableNotFound:
        raise HTTPException(status_code=400, detail="table not found in schema public")
    except UnsupportedTable as exc:
        raise HTTPException(status_code=400, detail=exc.reason)
    apply_ddl(session, info.table_name)
    col = repo.create_collection(
        session, tenant_id=user.tenant_id, owner_id=user.id, table_name=info.table_name,
        title=body.title or info.table_name, description=body.description,
        is_public=body.isPublic, pk_column=info.pk_column,
        geometry_column=info.geometry_column, geometry_type=info.geometry_type,
        srid=info.srid, feature_count=count_features(session, info.table_name),
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.create", object_type="collection", object_id=col.id,
                payload={"tableName": col.table_name})
    return _collection_json(col, _can_write_collection(session, user, col))
```

(Seule la ligne `count_features=Depends(...)` et le kwarg `feature_count=...`
sont nouveaux — le reste de la fonction est inchangé, reproduit ici en
entier pour éviter toute ambiguïté sur le point d'insertion.)

- [ ] **Step 4: `seed_demo.py`**

Dans `core/scripts/seed_demo.py`, l'en-tête importe déjà `from sqlalchemy
import select` et `from app.collections.ddl import apply_collection_ddl` —
étendre ces deux lignes :

```python
from sqlalchemy import select, text
```

```python
from app.collections.ddl import apply_collection_ddl, quote_ident
```

Puis calculer le compte avant l'appel à `create_collection` :

```python
        apply_collection_ddl(session, table)
        t = quote_ident(session, table)
        feature_count = session.execute(
            text(f"SELECT count(*) FROM public.{t}")
        ).scalar_one()
        create_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, table_name=table,
            title=title, description="Collection de démonstration", is_public=True,
            pk_column=info.pk_column, geometry_column=info.geometry_column,
            geometry_type=info.geometry_type, srid=info.srid,
            feature_count=feature_count,
        )
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: tous passent.

Run (PostGIS réel) : `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_seed_demo.py tests/test_features_integration.py -v`
Expected: tous passent.

- [ ] **Step 6: Suite complète + commit**

Run: `cd core && uv run pytest` (avec puis sans `CORE_TEST_DATABASE_URL`).

```bash
git add core/app/collections/routes.py core/scripts/seed_demo.py \
        core/tests/test_collections_routes.py core/tests/test_seed_demo.py \
        core/tests/test_features_integration.py
git commit -m "feat(core): featureCount à l'enregistrement admin et sur l'API collections (SP-6c)"
```

---

## Task 4: Écritures OGC Features — maintien atomique de `feature_count`

**Files:**
- Modify: `core/app/features/routes.py`
- Modify: `core/tests/test_features_routes_write.py`
- Modify: `core/tests/test_features_integration.py`

**Interfaces:**
- Consumes: `Collection.feature_count` (Task 1), `collections_routes.get_feature_counter` (Task 3, overridé en test).
- Produces: rien de nouveau côté interface — effet de bord transactionnel sur `create_feature`/`remove_feature`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_features_routes_write.py`, l'en-tête importe déjà
`from app.collections import routes as collections_routes` (pas de doublon à
ajouter) mais ni `text` ni `get_collection` — ajouter :

```python
from sqlalchemy import text
```

(à fusionner avec `from sqlalchemy.exc import IntegrityError` existant en un
bloc `sqlalchemy`/`sqlalchemy.exc` cohérent, ou en ligne séparée — au choix.)

```python
from app.collections.repository import get_collection
```

Puis étendre la fixture `env` pour que `register_collection` parte d'un
`feature_count` connu (`0`) plutôt que `None` (SQLite : la dépendance par
défaut renvoie `None`, ce qui empêcherait d'observer un incrément —
`NULL + 1` reste `NULL`). Ajouter dans la fixture `env`, juste après l'override de
`collections_routes.get_ddl_applier` :

```python
    app.dependency_overrides[collections_routes.get_feature_counter] = (
        lambda: (lambda session, table_name: 0)
    )
```

Ajouter à la fin du fichier :

```python
def _feature_count(Session, collection_id="incidents"):
    with Session() as s:
        return get_collection(s, tenant_id="default", collection_id=collection_id).feature_count


def test_create_and_delete_maintain_feature_count(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    assert _feature_count(Session) == 0
    client.post("/collections/incidents/items", json=VALID)
    assert _feature_count(Session) == 1
    client.delete("/collections/incidents/items/1")
    assert _feature_count(Session) == 0


def test_put_does_not_change_feature_count(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.put("/collections/incidents/items/1", json=VALID)
    assert _feature_count(Session) == 0  # remplacement, pas de création
```

(`tenant_id="default"` : `get_or_create_default_tenant` fixe
`Tenant.id = DEFAULT_TENANT_SLUG = "default"`, `core/app/tenants/repository.py`
— stable et immuable par construction, valable en dur ici.)

Dans `core/tests/test_features_integration.py`, étendre `test_full_crud_roundtrip`
(déjà modifié en Task 3) pour vérifier le compte après chaque écriture :

```python
def test_full_crud_roundtrip(pg_app):
    client = pg_app
    assert client.post("/collections", json={"tableName": "demo_incidents"}).status_code == 201
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 0
    r = client.post("/collections/demo_incidents/items", json={
        "type": "Feature", "properties": {"titre": "Nid de poule"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 1
    desc = client.get("/collections/demo_incidents").json()
    assert desc["extent"]["spatial"]["bbox"] == [[1.85, 45.27, 1.85, 45.27]]
    body = client.get("/collections/demo_incidents/items").json()
    assert body["numberMatched"] == 1
    assert body["features"][0]["properties"]["titre"] == "Nid de poule"
    assert client.put(f"/collections/demo_incidents/items/{fid}", json={
        "type": "Feature", "properties": {"titre": "Réparé"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}}).status_code == 204
    assert client.get(f"/collections/demo_incidents/items/{fid}").json()[
        "properties"]["titre"] == "Réparé"
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 1  # PUT inchangé
    assert client.delete(f"/collections/demo_incidents/items/{fid}").status_code == 204
    assert client.get("/collections/demo_incidents/items").json()["numberMatched"] == 0
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 0
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_features_routes_write.py -v -k feature_count`
Expected: FAIL — `assert None == 0` sur la première assertion (`create_feature`
ne touche pas encore `feature_count`).

- [ ] **Step 3: Maintenir le compteur dans `create_feature`/`remove_feature`**

Dans `core/app/features/routes.py`, ajouter `text` à l'import SQLAlchemy déjà
présent :

```python
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
```

Dans `create_feature`, après le bloc `try/except IntegrityError` (l'insertion
a réussi) et avant `write_audit` :

```python
    try:
        with rls(session, col.tenant_id):
            fid = repo.insert_feature(session, info,
                                      properties=payload.get("properties") or {},
                                      geometry=payload.get("geometry"))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="feature conflicts with an existing row")
    session.execute(
        text("UPDATE collections SET feature_count = feature_count + 1 WHERE id = :id"),
        {"id": col.id},
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.create", object_type="feature", object_id=str(fid),
                payload={"collection": col.id, "fid": str(fid)})
```

Dans `remove_feature`, après confirmation que `ok` est vrai et avant
`write_audit` :

```python
    with rls(session, col.tenant_id):
        ok = repo.delete_feature(session, info, fid=fid)
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    session.execute(
        text("UPDATE collections SET feature_count = feature_count - 1 WHERE id = :id"),
        {"id": col.id},
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.delete", object_type="feature", object_id=fid,
                payload={"collection": col.id, "fid": fid})
```

`put_feature` reste inchangé — aucun ajout.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_features_routes_write.py -v`
Expected: tous passent.

Run (PostGIS réel) : `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_features_integration.py -v`
Expected: passe, `featureCount` observé à `0 → 1 → 1 (après PUT) → 0`.

- [ ] **Step 5: Suite complète + commit**

Run: `cd core && uv run pytest` (avec puis sans `CORE_TEST_DATABASE_URL`).

```bash
git add core/app/features/routes.py core/tests/test_features_routes_write.py \
        core/tests/test_features_integration.py
git commit -m "feat(core): create/delete feature — maintien atomique de feature_count (SP-6c)"
```

---

## Task 5: Shell — types et `itemClient.ts`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `LayerSource.featureCount?: number | null`.
- Consumes: `featureCount` dans la réponse JSON de `GET /collections` (Task 3) — champ ajouté à un type TypeScript écrit à la main (pas généré depuis l'OpenAPI, cf. Global Constraints), donc pas de régénération à lancer pour cette tâche.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `shell/src/api/itemClient.test.ts`, étendre le test
`"listLayerSources aggregates Martin vector sources and core collections"` :

```ts
test("listLayerSources aggregates Martin vector sources and core collections", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { content_type: "application/x-protobuf", description: "Communes" },
          routes: { content_type: "application/x-protobuf" },
        },
      }),
    ),
    http.get("https://core.test/collections", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        collections: [{ id: "public.parcs", title: "Parcs", featureCount: 42 }],
      });
    }),
  );
  const sources = await makeClient("abc").listLayerSources();
  expect(auth).toBe("Bearer abc");
  const martin = sources.find((s) => s.id === "communes");
  expect(martin).toMatchObject({
    title: "Communes",
    service: "martin",
    kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  expect(martin?.featureCount).toBeUndefined();
  // Martin source without a description falls back to its id for the title.
  expect(sources.find((s) => s.id === "routes")?.title).toBe("routes");
  const feature = sources.find((s) => s.id === "public.parcs");
  expect(feature).toMatchObject({
    title: "Parcs",
    service: "core",
    kind: "feature",
    url: "https://core.test/collections/public.parcs/items",
    featureCount: 42,
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npm run test -- itemClient -t "aggregates Martin"`
Expected: FAIL — `expect(feature).toMatchObject(...)` échoue sur `featureCount:
undefined` reçu au lieu de `42` (le champ n'est pas encore mappé).

- [ ] **Step 3: Étendre `LayerSource` et le mapping**

Dans `shell/src/api/types.ts`, modifier `LayerSource` :

```ts
export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "core";
  kind: "vector" | "feature";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
};
```

Dans `shell/src/api/itemClient.ts`, modifier `fetchCoreCollections` :

```ts
  async function fetchCoreCollections(): Promise<LayerSource[]> {
    const token = getToken();
    const res = await fetch(`${coreUrl}/collections`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string; featureCount?: number | null }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "feature" as const,
      url: `${coreUrl}/collections/${c.id}/items`,
      featureCount: c.featureCount,
    }));
  }
```

(La branche `fetchMartinLayers`/Martin, non montrée ici, reste inchangée —
ses objets `LayerSource` n'incluent pas `featureCount`, cohérent avec le champ
optionnel.)

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd shell && npm run test -- itemClient -t "aggregates Martin"`
Expected: PASS.

- [ ] **Step 5: Suite complète + build + commit**

Run: `cd shell && npm run test && npm run build`
Expected: tous les tests passent, build OK.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): featureCount sur LayerSource et itemClient (SP-6c)"
```

---

## Task 6: Shell — badge « N entités » dans `LayerPicker`

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx`
- Modify: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `LayerSource.featureCount` (Task 5).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/map/LayerPicker.test.tsx`, étendre le tableau `sources` et
ajouter deux tests :

```tsx
const sources: LayerSource[] = [
  { id: "communes", title: "Communes", service: "martin", kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}", sourceLayer: "communes" },
  { id: "public.parcs", title: "Parcs", service: "core", kind: "feature",
    url: "https://core.test/collections/public.parcs/items", featureCount: 128 },
  { id: "public.legacy", title: "Legacy", service: "core", kind: "feature",
    url: "https://core.test/collections/public.legacy/items", featureCount: null },
];
```

```tsx
test("shows a feature-count badge for a core source with a known count", async () => {
  renderPicker(vi.fn());
  const item = (await screen.findByRole("button", { name: /Parcs/ })).closest("li")!;
  expect(item).toHaveTextContent("128 entités");
});

test("shows no feature-count badge for a martin source or an unknown count", async () => {
  renderPicker(vi.fn());
  const martinItem = (await screen.findByRole("button", { name: /Communes/ })).closest("li")!;
  expect(martinItem).not.toHaveTextContent(/entités/);
  const legacyItem = (await screen.findByRole("button", { name: /Legacy/ })).closest("li")!;
  expect(legacyItem).not.toHaveTextContent(/entités/);
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npm run test -- LayerPicker`
Expected: FAIL — les deux nouveaux tests échouent (`expect(item).toHaveTextContent("128 entités")` : le badge n'existe pas encore).

- [ ] **Step 3: Ajouter le badge**

Dans `shell/src/map/LayerPicker.tsx`, modifier le rendu de chaque source :

```tsx
  return (
    <ul className="flex flex-col gap-1">
      {data.map((source) => (
        <li key={`${source.service}:${source.id}`}>
          <button
            type="button"
            className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
            onClick={() => onAdd(toMapLayer(source))}
          >
            {source.title}
            <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
            {typeof source.featureCount === "number" && (
              <span className="ml-2 text-xs text-slate-400">
                {source.featureCount} entités
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
```

(`typeof source.featureCount === "number"` exclut à la fois `undefined`
— sources Martin — et `null` — collection pas encore backfillée.)

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npm run test -- LayerPicker`
Expected: tous passent (5 : 3 existants + 2 nouveaux).

- [ ] **Step 5: Suite complète + build + commit**

Run: `cd shell && npm run test && npm run build`
Expected: tous les tests passent, build OK.

```bash
git add shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "feat(shell): badge nombre d'entités dans LayerPicker (SP-6c)"
```

---

## Revue finale de branche

Après la Task 6, lancer une revue finale de branche (modèle opus, même patron
que SP-6a/SP-6b) avant merge vers `main` : porter une attention particulière à
(a) l'atomicité réelle des `UPDATE ... SET feature_count = feature_count ± 1`
(pas de lecture-puis-écriture ORM qui perdrait des incréments sous écritures
concurrentes),
(b) la cohérence du backfill de la migration 0011 rejouée réellement contre un
PostGIS jetable (pas seulement vérifiée une fois en Task 1 — revalider que
rien dans les tâches suivantes n'a cassé son comportement),
(c) que `feature_count` ne peut jamais devenir négatif ou incohérent sur un
scénario d'écritures concurrentes raisonnable (revue de code de la forme SQL,
pas nécessairement un test de concurrence — cf. Global Constraints du design),
(d) qu'aucun appelant existant de `create_collection` n'a été oublié (Task 1
Global Constraints liste 3 appelants : `run_import` Task 2, `register_collection`
et `seed_demo.py` Task 3 — vérifier que les 3 sont bien à jour).
