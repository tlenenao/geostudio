# SP-3b — CRUD features OGC API + RLS en chemin de requête : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le cœur lit et écrit des features GeoJSON conformes OGC API Features (Part 1 + Part 4) sur les collections enregistrées en SP-3a, chaque requête bornée au tenant par la RLS — deuxième sous-phase de la spec [SP-3](../specs/2026-07-09-sp3-collections-features-design.md) (§2/§4/§5 + « Notes de revue SP-3a »).

**Architecture:** Nouveau module `app/features` (validation pure, helper RLS, repository SQL brut paramétré, routes OGC) au-dessus d'`app/collections` (qui gagne `extent.py` et expose son helper de lecture). Le pattern SP-3a est reconduit : dépendances FastAPI injectables (introspecteur, repository features) — tests d'authz/liens sur SQLite avec fakes, CRUD/RLS réels sur PostGIS (marqueur `postgis`). La lecture publique anonyme passe par `get_current_user_optional` ; l'écriture exige un Bearer.

**Tech Stack:** FastAPI + SQLAlchemy 2 sync (existant), SQL brut `text()` paramétré + `ST_AsGeoJSON`/`ST_GeomFromGeoJSON` (pas de geoalchemy2), pytest (SQLite + marqueur `postgis`), import-linter.

## Global Constraints

- **Préalable git** : PR #16 (SP-3a) mergée dans `dev` ; brancher `sp3b-features-ogc` depuis `dev` à jour, **travailler dans un worktree dédié** `.worktrees/sp3b-features-ogc` (règle de session : le checkout principal reste sur `dev`).
- Commandes : `cd core && uv run pytest` (+ `CORE_TEST_DATABASE_URL` pour les tests `postgis`), `uv run lint-imports`. Tout vert à la fin de chaque tâche. TDD ; commits conventional en français ; code/identifiants en anglais.
- **Tenant (décision 2026-07-10, spec « Notes de revue » n°1)** : `tenants.id` est l'identifiant lisible immuable ; le chemin features pose `app.tenant_id = user.tenant_id` **via `set_config('app.tenant_id', :tid, true)` paramétré** — jamais de littéral interpolé dans un SET.
- **Rôle RLS borné** : les requêtes sur les tables métier s'exécutent sous `SET LOCAL ROLE gis_rls` ; **`RESET ROLE` obligatoire avant tout retour aux tables du cœur** dans la même transaction (`audit_log` n'est pas grantée à `gis_rls`).
- Identifiants SQL quotés via le preparer (helper `quote_ident` de `app/collections/ddl.py`) ; les valeurs sont TOUJOURS des paramètres bindés.
- Erreurs de validation d'écriture : `400` avec `{"detail": {"errors": [{"field", "code", "message"}]}}` (consommé par SP-4). Motif « 404 avant 403 » conservé ; écriture anonyme → `401` ; collection `editable=false` → `403`.
- Lecture : `limit` défaut 100, **plafonné à 1000 sans erreur** ; `offset` ≥ 0 ; `bbox` CRS84 ; filtres = égalité `propriété=valeur` (compat pg_featureserv) ; propriété de filtre inconnue → `400`.
- `can()` reste l'unique porte d'autorisation ; toute mutation écrit `write_audit(...)` (`feature.create/update/delete`, payload `{"collection", "fid"}`), même transaction.
- Aucune nouvelle dépendance Python. Frontières : `app.features` s'insère entre `app.public` et `app.collections` dans le contrat layers.
- PostGIS de test local (cf. ledger SP-3a) : `export CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:$(grep '^PG_PASSWORD=' ../.env | cut -d= -f2)@127.0.0.1:25432/gis_test"` (proxy socat `gis-test-proxy`).

---

## Task 1: Spike PgBouncer × RLS (gate d'ouverture — peut invalider la suite)

**Files:**
- Create: `core/scripts/spike_pgbouncer_rls.py`

**Interfaces:**
- Produces: un verdict PASS/FAIL documenté. **Si FAIL : STOP — escalade humaine** (repli prévu par la spec : RLS différée avec `can()` seul + amendement explicite d'A3 ; c'est la décision de Tanguy, pas celle de l'exécutant). Les tâches 5+ supposent PASS.

- [ ] **Step 1: Préparer l'accès PgBouncer local**

Les tests SP-3a attaquent PostGIS en direct ; le compose réel passe par PgBouncer en pool `transaction` — c'est CE chemin que le spike valide. Depuis la racine du repo principal :

```bash
docker compose up -d postgis pgbouncer
docker rm -f gis-pgb-proxy 2>/dev/null
docker run -d --rm --name gis-pgb-proxy --network geostudio_gis-net \
  -p 127.0.0.1:26432:5432 alpine/socat \
  tcp-listen:5432,fork,reuseaddr tcp:pgbouncer:6432
```

PgBouncer n'expose que la base `gis` (sa config compose) — le spike travaille donc sur `gis` avec une table jetable, pas sur `gis_test`.

- [ ] **Step 2: Écrire le script de spike**

```python
# core/scripts/spike_pgbouncer_rls.py
"""Spike SP-3b : SET LOCAL ROLE gis_rls + set_config('app.tenant_id') à
travers PgBouncer en pool 'transaction'.

Vérifie, DANS L'ORDRE, sur une table jetable RLS :
1. isolation lecture/écriture sous le rôle + GUC via pgbouncer ;
2. AUCUNE fuite de rôle ni de GUC dans la transaction suivante sur la même
   connexion poolée (le point qui peut invalider l'architecture) ;
3. RESET ROLE en milieu de transaction rend l'accès aux tables du cœur
   (pattern write_audit).

Usage :
  SPIKE_DATABASE_URL=postgresql+psycopg://gis:<PG_PASSWORD>@127.0.0.1:26432/gis \
    uv run python -m scripts.spike_pgbouncer_rls
Sort avec code 0 (PASS) ou 1 (FAIL, assertion affichée).
"""
import os
import sys

from sqlalchemy import create_engine, text

DDL = [
    "DROP TABLE IF EXISTS spike_rls",
    "CREATE TABLE spike_rls (id serial PRIMARY KEY, v text, tenant_id text NOT NULL)",
    "ALTER TABLE spike_rls ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS tenant_isolation ON spike_rls",
    "CREATE POLICY tenant_isolation ON spike_rls "
    "USING (tenant_id = current_setting('app.tenant_id')) "
    "WITH CHECK (tenant_id = current_setting('app.tenant_id'))",
    "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gis_rls') "
    "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$",
    "GRANT gis_rls TO current_user",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON spike_rls TO gis_rls",
    "GRANT USAGE, SELECT ON SEQUENCE spike_rls_id_seq TO gis_rls",
    "INSERT INTO spike_rls (v, tenant_id) VALUES ('a', 'default'), ('b', 'other')",
    "DROP TABLE IF EXISTS spike_core",
    "CREATE TABLE spike_core (id serial PRIMARY KEY, note text)",  # non grantée à gis_rls
]


def main() -> int:
    engine = create_engine(os.environ["SPIKE_DATABASE_URL"], pool_size=1, max_overflow=0)
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    with engine.begin() as c:
        for stmt in DDL:
            c.execute(text(stmt))

    # 1. Isolation sous rôle + GUC, à travers pgbouncer (pool transaction).
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": "default"})
        c.execute(text("SET LOCAL ROLE gis_rls"))
        rows = c.execute(text("SELECT v FROM spike_rls ORDER BY v")).scalars().all()
        check("lecture bornée au tenant via pgbouncer", rows == ["a"])
        try:
            c.execute(text("INSERT INTO spike_rls (v, tenant_id) VALUES ('x', 'other')"))
            check("WITH CHECK rejette l'écriture hors tenant", False)
        except Exception:
            check("WITH CHECK rejette l'écriture hors tenant", True)
        c.execute(text("RESET ROLE"))  # l'exception a invalidé ? non : psycopg lève, on re-teste proprement

    # 2. Pas de fuite de rôle/GUC dans la transaction suivante (même connexion, pool_size=1).
    with engine.begin() as c:
        who = c.execute(text("SELECT current_user")).scalar()
        guc = c.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
        check("pas de fuite de rôle entre transactions", who == "gis")
        check("pas de fuite de GUC entre transactions", guc in (None, ""))
        rows = c.execute(text("SELECT count(*) FROM spike_rls")).scalar()
        check("le propriétaire voit tout hors scope RLS", rows == 2)

    # 3. Pattern write_audit : rôle rendu en milieu de transaction.
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": "default"})
        c.execute(text("SET LOCAL ROLE gis_rls"))
        c.execute(text("INSERT INTO spike_rls (v, tenant_id) VALUES ('c', 'default')"))
        c.execute(text("RESET ROLE"))
        c.execute(text("INSERT INTO spike_core (note) VALUES ('audit ok')"))
        check("RESET ROLE rend l'accès aux tables du cœur dans la même tx", True)

    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS spike_rls, spike_core"))

    print("\nRésultat spike :", "PASS" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
```

Note : au point 1, l'INSERT rejeté met la transaction en état d'erreur — le
`with engine.begin()` se termine par rollback, c'est voulu ; le point 3 refait
le chemin nominal dans une transaction propre.

- [ ] **Step 3: Exécuter et documenter**

Run: `cd core && SPIKE_DATABASE_URL="postgresql+psycopg://gis:$(grep '^PG_PASSWORD=' ../.env | cut -d= -f2)@127.0.0.1:26432/gis" uv run python -m scripts.spike_pgbouncer_rls`
Expected: chaque check `[PASS]`, sortie finale `Résultat spike : PASS`, code retour 0.

**Si un check échoue : STOP.** Rapporter la sortie exacte — ne pas continuer le plan, ne pas improviser de contournement.

- [ ] **Step 4: Commit**

```bash
git add core/scripts/spike_pgbouncer_rls.py
git commit -m "test(core): spike SET LOCAL ROLE + GUC via PgBouncer (gate SP-3b) — PASS"
```

---

## Task 2: Durcissement DDL hérité (index tenant_id, séquence qualifiée, `quote_ident` public, test RLS UPDATE)

**Files:**
- Modify: `core/app/collections/ddl.py`
- Test: `core/tests/test_collections_ddl.py` (étendre)

**Interfaces:**
- Consumes: `apply_collection_ddl(session, table_name)` (SP-3a).
- Produces: `quote_ident(session, identifier) -> str` (public, remplace `_qi` — alias `_qi = quote_ident` conservé) — consommé par le repository features (tasks 6/8) ; index `ix_<table>_tenant_id` créé à l'enregistrement.

- [ ] **Step 1: Étendre les tests postgis (rouges)**

Ajouter à `core/tests/test_collections_ddl.py` (fixture `pg_table` existante) :

```python
def test_ddl_creates_tenant_index(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        idx = session.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 't_rls'")).scalars().all()
        assert "ix_t_rls_tenant_id" in idx


def test_rls_blocks_update_across_tenants(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text(
            "INSERT INTO t_rls (titre, tenant_id) VALUES ('a', 'default')"))
        session.commit()
    with pg_session_factory() as session:
        # Mauvais tenant : l'UPDATE ne voit aucune ligne (USING) — 0 modifiée.
        session.execute(text("SELECT set_config('app.tenant_id', 'other', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls"))
        r = session.execute(text("UPDATE t_rls SET titre = 'hack'"))
        assert r.rowcount == 0
    with pg_session_factory() as session:
        # Bon tenant : impossible de réécrire tenant_id vers un autre (WITH CHECK).
        session.execute(text("SELECT set_config('app.tenant_id', 'default', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls"))
        import sqlalchemy.exc
        with pytest.raises(sqlalchemy.exc.DBAPIError):
            session.execute(text("UPDATE t_rls SET tenant_id = 'other'"))
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_collections_ddl.py -v`
Expected: `test_ddl_creates_tenant_index` FAIL (index absent) ; `test_rls_blocks_update_across_tenants` PASS ou FAIL selon l'ordre — l'index est le seul manque produit.

- [ ] **Step 3: Implémenter dans `ddl.py`**

```python
# Renommer _qi en public (alias conservé pour les appels existants) :
def quote_ident(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)

_qi = quote_ident

# Dans apply_collection_ddl, après le CREATE POLICY, ajouter aux stmts :
#   (l'index sert toutes les requêtes RLS — current_setting est comparé à
#    chaque ligne sinon ; nom borné à 63 octets par construction v1)
        f"CREATE INDEX IF NOT EXISTS {quote_ident(session, 'ix_' + table_name + '_tenant_id')} "
        f"ON public.{t} (tenant_id)",

# Et qualifier la séquence (cohérence avec la requête regclass au-dessus) :
        text("SELECT pg_get_serial_sequence('public.' || quote_ident(:t), a.attname) FROM pg_index i "
             ...  # reste de la requête inchangé
```

- [ ] **Step 4: Vérifier**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_collections_ddl.py -v && uv run pytest -q && uv run lint-imports`
Expected: tous PASS (les tests existants d'idempotence couvrent le re-run de l'index `IF NOT EXISTS`).

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/ddl.py core/tests/test_collections_ddl.py
git commit -m "feat(core): index tenant_id + séquence qualifiée + test RLS UPDATE (backlog SP-3a)"
```

---

## Task 3: Durcissement introspection (enum schema-qualifié, gardes 0-PK / 2-géométries testées)

**Files:**
- Modify: `core/app/collections/introspection_pg.py`
- Test: `core/tests/test_introspection_pg.py` (étendre)

**Interfaces:**
- Consumes/Produces: `introspect_table(session, table_name) -> TableInfo` (signature inchangée).

- [ ] **Step 1: Tests postgis (rouges pour l'enum, verts attendus pour les gardes — on les fige)**

Ajouter à `core/tests/test_introspection_pg.py` :

```python
def test_enum_lookup_is_schema_qualified(pg_session, pg_engine):
    # Un type homonyme dans un autre schéma ne doit pas polluer les valeurs.
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS decoy"))
        conn.execute(text("DROP TYPE IF EXISTS decoy.t_gravite"))
        conn.execute(text("CREATE TYPE decoy.t_gravite AS ENUM ('polluee')"))
    try:
        info = introspect_table(pg_session, "t_incidents")
        by_name = {c.name: c for c in info.columns}
        assert by_name["gravite"].enum_values == ["faible", "moyenne", "haute"]
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TYPE IF EXISTS decoy.t_gravite"))
            conn.execute(text("DROP SCHEMA IF EXISTS decoy"))


def test_table_without_pk_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_nopk"))
        conn.execute(text("CREATE TABLE t_nopk (a int)"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_nopk")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_nopk"))


def test_two_geometry_columns_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_twogeom"))
        conn.execute(text(
            "CREATE TABLE t_twogeom (id serial PRIMARY KEY, "
            "g1 geometry(Point,4326), g2 geometry(Point,4326))"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_twogeom")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_twogeom"))
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_introspection_pg.py -v`
Expected: `test_enum_lookup_is_schema_qualified` FAIL (valeurs polluées possibles — si la jointure actuelle matche par hasard le bon type, le test documente quand même l'invariant et le Step 3 s'applique) ; les deux gardes PASS (déjà implémentées, jamais testées).

- [ ] **Step 3: Qualifier le lookup enum**

Dans `introspect_table`, la requête colonnes lit déjà `udt_name` — ajouter `udt_schema` au SELECT d'`information_schema.columns`, puis :

```python
        if data_type == "USER-DEFINED":
            enum_values = session.execute(text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE t.typname = :ty AND n.nspname = :ns "
                "ORDER BY e.enumsortorder"
            ), {"ty": udt_name, "ns": udt_schema}).scalars().all()
```

(adapter le dépaquetage du `for` de la requête colonnes pour inclure `udt_schema`).

- [ ] **Step 4: Vérifier + commit**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_introspection_pg.py -v && uv run pytest -q`
Expected: PASS.

```bash
git add core/app/collections/introspection_pg.py core/tests/test_introspection_pg.py
git commit -m "fix(core): lookup enum schema-qualifié + gardes introspection testées (backlog SP-3a)"
```

---

## Task 4: Module `app/features` — validation pure + frontières

**Files:**
- Create: `core/app/features/__init__.py` (vide)
- Create: `core/app/features/validation.py`
- Modify: `core/pyproject.toml` (layers : insérer `"app.features",` entre `"app.public",` et `"app.collections",`)
- Test: `core/tests/test_features_validation.py`

**Interfaces:**
- Consumes: `TableInfo`/`ColumnInfo` (`app.collections.introspection`).
- Produces: `validate_feature(info: TableInfo, feature: dict) -> list[dict]` — liste d'erreurs `{"field", "code", "message"}`, vide si valide. Codes : `invalid_feature`, `unknown_property`, `missing_required`, `invalid_type`, `invalid_enum`, `unsupported_type`, `geometry_mismatch`, `unexpected_geometry`. Consommé par la task 9.

- [ ] **Step 1: Tests purs (rouges)**

```python
# core/tests/test_features_validation.py
from app.collections.introspection import ColumnInfo, TableInfo
from app.features.validation import validate_feature

INFO = TableInfo(
    table_name="incidents", pk_column="id", geometry_column="geom",
    geometry_type="Point", srid=4326,
    columns=[
        ColumnInfo(name="titre", type="string", required=True, max_length=200),
        ColumnInfo(name="gravite", type="enum", required=False,
                   enum_values=["faible", "moyenne", "haute"]),
        ColumnInfo(name="nb", type="integer", required=False),
        ColumnInfo(name="date_incident", type="date", required=False),
        ColumnInfo(name="resolu", type="boolean", required=False),
        ColumnInfo(name="payload", type="unsupported", required=False),
    ],
)


def _f(props, geometry=None):
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _codes(errors):
    return {(e["field"], e["code"]) for e in errors}


def test_valid_feature_passes():
    errors = validate_feature(INFO, _f(
        {"titre": "Nid de poule", "gravite": "haute", "nb": 3,
         "date_incident": "2026-07-10", "resolu": False},
        {"type": "Point", "coordinates": [1.5, 45.2]},
    ))
    assert errors == []


def test_not_a_feature():
    assert _codes(validate_feature(INFO, {"type": "Polygon"})) == {("", "invalid_feature")}


def test_unknown_property_and_pk_and_tenant_refused():
    errors = validate_feature(INFO, _f({"titre": "x", "inconnu": 1, "id": 9, "tenant_id": "y"}))
    assert ("inconnu", "unknown_property") in _codes(errors)
    assert ("id", "unknown_property") in _codes(errors)
    assert ("tenant_id", "unknown_property") in _codes(errors)


def test_missing_required():
    assert ("titre", "missing_required") in _codes(validate_feature(INFO, _f({"nb": 1})))


def test_type_checks():
    errors = validate_feature(INFO, _f(
        {"titre": "x", "nb": "trois", "resolu": "oui", "date_incident": "pas-une-date"}))
    codes = _codes(errors)
    assert ("nb", "invalid_type") in codes
    assert ("resolu", "invalid_type") in codes
    assert ("date_incident", "invalid_type") in codes


def test_bool_is_not_an_integer():
    assert ("nb", "invalid_type") in _codes(validate_feature(INFO, _f({"titre": "x", "nb": True})))


def test_enum_and_unsupported():
    errors = validate_feature(INFO, _f({"titre": "x", "gravite": "extreme", "payload": {}}))
    assert ("gravite", "invalid_enum") in _codes(errors)
    assert ("payload", "unsupported_type") in _codes(errors)


def test_geometry_type_mismatch_and_unexpected():
    assert ("geometry", "geometry_mismatch") in _codes(validate_feature(
        INFO, _f({"titre": "x"}, {"type": "Polygon", "coordinates": []})))
    no_geom = TableInfo(table_name="notes", pk_column="id", geometry_column=None,
                        geometry_type=None, srid=None,
                        columns=[ColumnInfo(name="titre", type="string", required=True)])
    assert ("geometry", "unexpected_geometry") in _codes(validate_feature(
        no_geom, _f({"titre": "x"}, {"type": "Point", "coordinates": [0, 0]})))


def test_geometry_is_optional():
    assert validate_feature(INFO, _f({"titre": "x"})) == []
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_features_validation.py -v`
Expected: FAIL `ModuleNotFoundError: app.features`

- [ ] **Step 3: Implémenter**

```python
# core/app/features/validation.py
"""Validation d'un GeoJSON Feature contre le schéma introspecté (SP-3 §4).
Pur : aucune DB. Les erreurs structurées sont le contrat consommé par les
formulaires SP-4 ({"field", "code", "message"})."""
from datetime import date, datetime

from app.collections.introspection import ColumnInfo, TableInfo


def _err(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _type_ok(col: ColumnInfo, value) -> bool:
    if value is None:
        return True  # l'absence de valeur relève de missing_required, pas du type
    if col.type == "string":
        return isinstance(value, str)
    if col.type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if col.type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if col.type == "boolean":
        return isinstance(value, bool)
    if col.type in ("date", "datetime"):
        if not isinstance(value, str):
            return False
        try:
            (date if col.type == "date" else datetime).fromisoformat(value)
            return True
        except ValueError:
            return False
    return False  # enum géré à part ; unsupported refusé à part


def validate_feature(info: TableInfo, feature: dict) -> list[dict]:
    if not isinstance(feature, dict) or feature.get("type") != "Feature" \
            or not isinstance(feature.get("properties", {}), dict):
        return [_err("", "invalid_feature", "payload must be a GeoJSON Feature")]

    errors: list[dict] = []
    props = feature.get("properties") or {}
    by_name = {c.name: c for c in info.columns}
    reserved = {info.pk_column, "tenant_id", info.geometry_column}

    for name, value in props.items():
        col = by_name.get(name)
        if col is None or name in reserved:
            errors.append(_err(name, "unknown_property", f"unknown property '{name}'"))
            continue
        if col.type == "unsupported":
            errors.append(_err(name, "unsupported_type",
                               f"'{name}' is read-only (unsupported type)"))
            continue
        if col.type == "enum":
            if value is not None and value not in (col.enum_values or []):
                errors.append(_err(name, "invalid_enum",
                                   f"'{value}' not in {col.enum_values}"))
            continue
        if not _type_ok(col, value):
            errors.append(_err(name, "invalid_type", f"expected {col.type}"))

    for col in info.columns:
        if col.required and props.get(col.name) is None:
            errors.append(_err(col.name, "missing_required", f"'{col.name}' is required"))

    geometry = feature.get("geometry")
    if geometry is not None:
        if info.geometry_column is None:
            errors.append(_err("geometry", "unexpected_geometry",
                               "collection has no geometry column"))
        elif geometry.get("type") != info.geometry_type:
            errors.append(_err("geometry", "geometry_mismatch",
                               f"expected {info.geometry_type}"))
    return errors
```

`core/pyproject.toml` : insérer `"app.features",` entre `"app.public",` et `"app.collections",` dans le contrat layers.

- [ ] **Step 4: Vérifier + commit**

Run: `uv run pytest tests/test_features_validation.py -v && uv run lint-imports`
Expected: 9 PASS ; layers OK.

```bash
git add core/app/features core/pyproject.toml core/tests/test_features_validation.py
git commit -m "feat(core): module features — validation pure des payloads GeoJSON"
```

---

## Task 5: Helper d'exécution RLS (`rls_scope`)

**Files:**
- Create: `core/app/features/rls.py`
- Test: `core/tests/test_features_rls.py` (postgis)

**Interfaces:**
- Consumes: rôle `gis_rls` + policies (SP-3a/task 2), verdict PASS du spike (task 1).
- Produces: `rls_scope(session, tenant_id)` — context manager : `set_config('app.tenant_id', tid, true)` + `SET LOCAL ROLE gis_rls`, `RESET ROLE` en sortie (succès OU exception). Consommé par les tasks 6–10.

- [ ] **Step 1: Tests postgis (rouges)**

```python
# core/tests/test_features_rls.py
import pytest
from sqlalchemy import text

from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_rls_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope, t_core_like"))
        conn.execute(text(
            "CREATE TABLE t_scope (id serial PRIMARY KEY, v text, tenant_id text NOT NULL)"))
        conn.execute(text("ALTER TABLE t_scope ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(
            "CREATE POLICY tenant_isolation ON t_scope "
            "USING (tenant_id = current_setting('app.tenant_id')) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_scope TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_scope_id_seq TO gis_rls"))
        conn.execute(text("CREATE TABLE t_core_like (id serial PRIMARY KEY, note text)"))
        conn.execute(text(
            "INSERT INTO t_scope (v, tenant_id) VALUES ('mine', 'default'), ('theirs', 'other')"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope, t_core_like"))


def test_scope_filters_and_releases_role(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            rows = session.execute(text("SELECT v FROM t_scope")).scalars().all()
            assert rows == ["mine"]
        # Après le scope, même transaction : le rôle est rendu →
        # la table « cœur » (non grantée à gis_rls) est accessible (pattern audit).
        session.execute(text("INSERT INTO t_core_like (note) VALUES ('audit')"))
        session.commit()


def test_scope_releases_role_on_exception(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with pytest.raises(RuntimeError):
            with rls_scope(session, "default"):
                raise RuntimeError("boom")
        # La transaction n'est pas en erreur SQL : le rôle est rendu.
        assert session.execute(text("SELECT current_user")).scalar() == "gis"


def test_scope_write_stamps_current_tenant(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            session.execute(text(
                "INSERT INTO t_scope (v, tenant_id) "
                "VALUES ('new', current_setting('app.tenant_id'))"))
        session.commit()
    with pg_session_factory() as session:
        assert session.execute(text(
            "SELECT tenant_id FROM t_scope WHERE v = 'new'")).scalar() == "default"
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_rls.py -v`
Expected: FAIL `ModuleNotFoundError: app.features.rls`

- [ ] **Step 3: Implémenter**

```python
# core/app/features/rls.py
"""Scope d'exécution RLS (spec SP-3 §2/§5, décision tenant 2026-07-10).

Toute requête sur une table métier s'exécute sous le rôle NON-propriétaire
gis_rls, borné au tenant courant par le GUC transactionnel app.tenant_id
(set_config(..., true) — paramétré, jamais interpolé). Le RESET ROLE en
sortie est OBLIGATOIRE : audit_log et les tables du cœur ne sont pas
grantées à gis_rls, et la suite de la requête (write_audit) s'exécute dans
la même transaction. Validé à travers PgBouncer pool=transaction par
scripts/spike_pgbouncer_rls.py."""
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session


@contextmanager
def rls_scope(session: Session, tenant_id: str):
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id}
    )
    session.execute(text("SET LOCAL ROLE gis_rls"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))
```

- [ ] **Step 4: Vérifier + commit**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_rls.py -v && uv run pytest -q && uv run lint-imports`
Expected: 3 PASS, suite verte.

```bash
git add core/app/features/rls.py core/tests/test_features_rls.py
git commit -m "feat(core): rls_scope — GUC tenant paramétré + rôle gis_rls borné à la requête métier"
```

---

## Task 6: Repository features — lecture (+ `extent` côté collections)

**Files:**
- Create: `core/app/features/repository.py`
- Create: `core/app/collections/extent.py`
- Test: `core/tests/test_features_repository.py` (postgis)

**Interfaces:**
- Consumes: `TableInfo` ; `quote_ident` (task 2) ; `rls_scope` appliqué par l'APPELANT (les fonctions du repository supposent le scope déjà posé — elles sont pures SQL).
- Produces (consommé par les tasks 7–10) :
  - `FeaturePage` (dataclass) : `features: list[dict]` (GeoJSON Features), `number_matched: int`, `number_returned: int`.
  - `FilterError(field, message)` (exception) — filtre inconnu ou valeur inconvertible.
  - `select_features(session, info, *, limit, offset, bbox=None, filters=None) -> FeaturePage` — `bbox: tuple[float,float,float,float]|None`, `filters: dict[str,str]|None` (valeurs brutes d'URL, coercées par type).
  - `get_feature(session, info, *, fid: str) -> dict | None` (fid coercé vers le type de la PK ; inconvertible → None).
  - `app.collections.extent.table_extent(session, info) -> list[float] | None` — `[minx,miny,maxx,maxy]` ou None (vide/sans géométrie). Placé dans `app.collections` (pas features) : la description OGC de collection (task 10) vit dans `app.collections.routes`, qui ne peut pas importer vers le haut.

- [ ] **Step 1: Tests postgis (rouges)**

```python
# core/tests/test_features_repository.py
import pytest
from sqlalchemy import text

from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.features.repository import FilterError, get_feature, select_features
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_incidents(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))
        conn.execute(text(
            "CREATE TABLE t_feat (id serial PRIMARY KEY, titre text NOT NULL, "
            "nb integer, tenant_id text NOT NULL DEFAULT 'default', "
            "geom geometry(Point, 4326))"))
        conn.execute(text("ALTER TABLE t_feat ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(
            "CREATE POLICY tenant_isolation ON t_feat "
            "USING (tenant_id = current_setting('app.tenant_id')) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_feat TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_feat_id_seq TO gis_rls"))
        conn.execute(text(
            "INSERT INTO t_feat (titre, nb, tenant_id, geom) VALUES "
            "('a', 1, 'default', ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326)), "
            "('b', 2, 'default', ST_SetSRID(ST_MakePoint(2.0, 46.0), 4326)), "
            "('c', 3, 'other',   ST_SetSRID(ST_MakePoint(3.0, 47.0), 4326))"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))


@pytest.fixture()
def info(pg_incidents, pg_session_factory):
    with pg_session_factory() as session:
        yield introspect_table(session, "t_feat")


def test_select_is_tenant_bound_and_geojson(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=100, offset=0)
    assert page.number_matched == 2 and page.number_returned == 2
    f = page.features[0]
    assert f["type"] == "Feature" and f["id"] == 1
    assert f["geometry"] == {"type": "Point", "coordinates": [1.0, 45.0]}
    assert f["properties"] == {"titre": "a", "nb": 1}  # ni pk, ni tenant_id, ni geom


def test_pagination_and_bbox_and_filters(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=1, offset=1)
        assert page.number_matched == 2 and [f["id"] for f in page.features] == [2]
        page = select_features(session, info, limit=10, offset=0,
                               bbox=(0.5, 44.5, 1.5, 45.5))
        assert [f["id"] for f in page.features] == [1]
        page = select_features(session, info, limit=10, offset=0, filters={"nb": "2"})
        assert [f["id"] for f in page.features] == [2]


def test_filter_errors(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"inconnu": "x"})
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"nb": "pas-un-nombre"})


def test_get_feature(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        assert get_feature(session, info, fid="1")["properties"]["titre"] == "a"
        assert get_feature(session, info, fid="999") is None
        assert get_feature(session, info, fid="3") is None  # autre tenant : invisible
        assert get_feature(session, info, fid="abc") is None  # inconvertible


def test_table_extent(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        assert table_extent(session, info) == [1.0, 45.0, 2.0, 46.0]
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_repository.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implémenter**

```python
# core/app/features/repository.py
"""Lecture des features : SQL brut paramétré, identifiants quotés. Les
fonctions supposent que l'appelant a posé rls_scope() — elles ne gèrent ni
rôle ni tenant. fid et filtres arrivent en str (URL) et sont coercés selon
le type introspecté."""
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import ColumnInfo, TableInfo


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int
    number_returned: int


class FilterError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _property_columns(info: TableInfo) -> list[ColumnInfo]:
    return [c for c in info.columns
            if c.name not in (info.pk_column, "tenant_id", info.geometry_column)]


def _coerce(col: ColumnInfo, raw: str):
    try:
        if col.type == "integer":
            return int(raw)
        if col.type == "number":
            return float(raw)
        if col.type == "boolean":
            if raw.lower() in ("true", "t", "1"):
                return True
            if raw.lower() in ("false", "f", "0"):
                return False
            raise ValueError(raw)
        return raw  # string/enum/date/datetime : PG caste text implicitement
    except ValueError:
        raise FilterError(col.name, f"cannot parse '{raw}' as {col.type}") from None


def _where(session: Session, info: TableInfo, bbox, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (name, raw) in enumerate(sorted(filters.items())):
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            clauses.append(f"{quote_ident(session, name)} = :f{i}")
            params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(f"{g} && ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, :bsrid)")
        params.update({"bx0": bbox[0], "by0": bbox[1], "bx1": bbox[2],
                       "by1": bbox[3], "bsrid": info.srid or 4326})
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _select_list(session: Session, info: TableInfo) -> str:
    cols = [quote_ident(session, info.pk_column)]
    cols += [quote_ident(session, c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"ST_AsGeoJSON({quote_ident(session, info.geometry_column)}) AS __geo")
    return ", ".join(cols)


def _row_to_feature(info: TableInfo, row) -> dict:
    m = row._mapping
    props = {c.name: m[c.name] for c in _property_columns(info)}
    geometry = None
    if info.geometry_column and m.get("__geo"):
        geometry = json.loads(m["__geo"])
    return {"type": "Feature", "id": m[info.pk_column],
            "geometry": geometry, "properties": props}


def select_features(session: Session, info: TableInfo, *, limit: int, offset: int,
                    bbox=None, filters=None) -> FeaturePage:
    t = quote_ident(session, info.table_name)
    where, params = _where(session, info, bbox, filters)
    matched = session.execute(
        text(f"SELECT count(*) FROM public.{t}{where}"), params).scalar()
    rows = session.execute(text(
        f"SELECT {_select_list(session, info)} FROM public.{t}{where} "
        f"ORDER BY {quote_ident(session, info.pk_column)} LIMIT :__l OFFSET :__o"
    ), {**params, "__l": limit, "__o": offset}).all()
    features = [_row_to_feature(info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched,
                       number_returned=len(features))


def _coerce_fid(info: TableInfo, fid: str):
    pk = next((c for c in info.columns if c.name == info.pk_column), None)
    if pk is not None and pk.type == "integer":
        try:
            return int(fid)
        except ValueError:
            return None
    return fid


def get_feature(session: Session, info: TableInfo, *, fid: str) -> dict | None:
    value = _coerce_fid(info, fid)
    if value is None:
        return None
    t = quote_ident(session, info.table_name)
    row = session.execute(text(
        f"SELECT {_select_list(session, info)} FROM public.{t} "
        f"WHERE {quote_ident(session, info.pk_column)} = :fid"
    ), {"fid": value}).one_or_none()
    return _row_to_feature(info, row) if row else None
```

Note : la PK introspectée sur `serial` a `type="integer"` mais elle n'apparaît
pas dans `_property_columns` — `_coerce_fid` la retrouve dans `info.columns`
(l'introspection liste toutes les colonnes hors géométrie, PK comprise).

```python
# core/app/collections/extent.py
"""Emprise spatiale d'une collection (description OGC). Dans app.collections
(pas app.features) : consommé par collections.routes, qui ne peut pas
importer vers le haut. L'appelant pose rls_scope() si l'emprise doit être
bornée au tenant."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import TableInfo


def table_extent(session: Session, info: TableInfo) -> list[float] | None:
    if info.geometry_column is None:
        return None
    t = quote_ident(session, info.table_name)
    g = quote_ident(session, info.geometry_column)
    box = session.execute(text(
        f"SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) "
        f"FROM (SELECT ST_Extent({g}) AS e FROM public.{t}) s WHERE e IS NOT NULL"
    )).one_or_none()
    return [box[0], box[1], box[2], box[3]] if box else None
```

- [ ] **Step 4: Vérifier + commit**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_repository.py -v && uv run pytest -q && uv run lint-imports`
Expected: 6 PASS (features importe collections : sens autorisé).

```bash
git add core/app/features/repository.py core/app/collections/extent.py \
  core/tests/test_features_repository.py
git commit -m "feat(core): repository features lecture (GeoJSON, bbox, filtres, pagination) + extent"
```

---

## Task 7: Routes lecture OGC — `/collections/{cid}/items` et `/items/{fid}`

**Files:**
- Create: `core/app/features/routes.py`
- Modify: `core/app/collections/routes.py` (renommer `_get_readable` → `get_readable_collection`, public ; mettre à jour ses appels internes)
- Modify: `core/app/main.py` (include `features_routes.router` avant le mount MCP)
- Test: `core/tests/test_features_routes_read.py` (SQLite, fake repo) + `core/tests/test_features_integration.py` (postgis, sera étendu en task 9)

**Interfaces:**
- Consumes: `get_readable_collection(session, user, collection_id)` (renommage) ; `get_introspector` (`app.collections.routes`) ; `rls_scope` ; `select_features`/`get_feature`/`FilterError`/`FeaturePage`.
- Produces: `GET /collections/{cid}/items` → FeatureCollection GeoJSON `{type, features, numberMatched, numberReturned, timeStamp, links}` ; `GET /collections/{cid}/items/{fid}` → Feature | 404. Dépendance injectable `get_features_repo()` (module-like : `select_features`, `get_feature`) pour les tests SQLite. Consommé par la task 9 (même fichier routes).

- [ ] **Step 1: Tests SQLite avec fake repo (rouges)**

```python
# core/tests/test_features_routes_read.py
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FeaturePage, FilterError
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="incidents", pk_column="id", geometry_column="geom",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="titre", type="string", required=True)])

FEAT = {"type": "Feature", "id": 1, "geometry": None, "properties": {"titre": "a"}}


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox, filters=filters)
        if filters and "inconnu" in filters:
            raise FilterError("inconnu", "unknown filter property 'inconnu'")
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature,
                           calls=calls)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r",
                                     username="regular", email=None,
                                     first_name="", last_name="")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None)
    fake_repo = make_fake_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo
    # SQLite ne connaît ni SET LOCAL ROLE ni set_config : neutraliser le scope.
    app.dependency_overrides[features_routes.get_rls_scope] = (
        lambda: features_routes.null_rls_scope)
    client = TestClient(app)
    return app, client, admin, regular, fake_repo


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_items_returns_feature_collection_with_links(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    r = client.get("/collections/incidents/items?limit=1&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["numberMatched"] == 3 and body["numberReturned"] == 1
    rels = {l["rel"]: l["href"] for l in body["links"]}
    assert "offset=2" in rels["next"] and "offset=0" in rels["prev"]
    assert repo.calls["limit"] == 1 and repo.calls["offset"] == 1


def test_limit_is_capped_not_rejected(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    assert client.get("/collections/incidents/items?limit=99999").status_code == 200
    assert repo.calls["limit"] == 1000


def test_filters_forwarded_and_unknown_is_400(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    client.get("/collections/incidents/items?titre=a&f=json")
    assert repo.calls["filters"] == {"titre": "a"}  # f/limit/offset/bbox réservés, exclus
    r = client.get("/collections/incidents/items?inconnu=x")
    assert r.status_code == 400
    assert r.json()["detail"]["errors"][0]["code"] == "unknown_filter"


def test_bbox_parsing(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    client.get("/collections/incidents/items?bbox=0.5,44.5,1.5,45.5")
    assert repo.calls["bbox"] == (0.5, 44.5, 1.5, 45.5)
    assert client.get("/collections/incidents/items?bbox=zzz").status_code == 400


def test_single_feature_and_404(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    assert client.get("/collections/incidents/items/1").json()["id"] == 1
    assert client.get("/collections/incidents/items/999").status_code == 404


def test_anonymous_reads_public_only(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/collections/incidents/items").status_code == 404
    _register(app, client, admin, public=True)  # re-register échoue (409) mais PATCH ok :
    _as(app, admin)
    client.patch("/collections/incidents", json={"isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/collections/incidents/items").status_code == 200
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: FAIL `ImportError` (features.routes inexistant, `get_readable_collection` inexistant).

- [ ] **Step 3: Implémenter**

`core/app/collections/routes.py` : renommer `_get_readable` en
`get_readable_collection` (mêmes corps et sémantique 404-avant-tout) et mettre
à jour les appels internes (get/patch/delete/sharing/schema).

```python
# core/app/features/routes.py
"""Routes OGC API Features (Part 1 lecture ; Part 4 écriture en task 9).
Le repository et le scope RLS sont injectables : les tests SQLite substituent
un fake et un scope nul ; le vrai chemin est PostGIS-only."""
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.repository import FilterError

router = APIRouter()

RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "f"}
MAX_LIMIT = 1000


def get_features_repo():  # overridé en test SQLite
    from app.features import repository
    return repository


@contextmanager
def null_rls_scope(session, tenant_id):  # pour SQLite (pas de rôles/GUC)
    yield


def get_rls_scope():  # overridé en test SQLite
    from app.features.rls import rls_scope
    return rls_scope


def _validation_error(errors: list[dict], status: int = 400):
    return HTTPException(status_code=status, detail={"errors": errors})


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    try:
        if len(parts) != 4:
            raise ValueError(raw)
        return tuple(float(p) for p in parts)
    except ValueError:
        raise _validation_error(
            [{"field": "bbox", "code": "invalid_bbox",
              "message": "bbox must be minx,miny,maxx,maxy"}])


def _collect_filters(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items()
            if k not in RESERVED_QUERY_PARAMS}


def _page_links(request: Request, *, limit: int, offset: int, page) -> list[dict]:
    def href(o: int) -> str:
        return str(request.url.include_query_params(limit=limit, offset=o))

    links = [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}]
    if offset + page.number_returned < page.number_matched:
        links.append({"rel": "next", "type": "application/geo+json",
                      "href": href(offset + limit)})
    if offset > 0:
        links.append({"rel": "prev", "type": "application/geo+json",
                      "href": href(max(0, offset - limit))})
    return links


@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    filters = _collect_filters(request)
    try:
        with rls(session, col.tenant_id):
            page = repo.select_features(session, info, limit=limit, offset=offset,
                                        bbox=parsed_bbox, filters=filters or None)
    except FilterError as exc:
        raise _validation_error(
            [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
    return {
        "type": "FeatureCollection",
        "features": page.features,
        "numberMatched": page.number_matched,
        "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": _page_links(request, limit=limit, offset=offset, page=page),
    }


@router.get("/collections/{collection_id}/items/{fid}")
def get_single_feature(
    collection_id: str, fid: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        feature = repo.get_feature(session, info, fid=fid)
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return feature
```

Note tenant : le scope est posé avec `col.tenant_id` (le tenant de la
collection, = celui du user par construction mono-tenant ; pour un anonyme il
n'y a pas de user — le tenant de la collection est la seule référence juste).

`core/app/main.py` : ajouter `from app.features import routes as features_routes`
et `app.include_router(features_routes.router)` **avant** le mount MCP.

- [ ] **Step 4: Vérifier + commit**

Run: `uv run pytest tests/test_features_routes_read.py -v && uv run pytest -q && uv run lint-imports`
Expected: 6 PASS ; suite verte ; layers OK.

```bash
git add core/app/features/routes.py core/app/collections/routes.py core/app/main.py \
  core/tests/test_features_routes_read.py
git commit -m "feat(core): lecture OGC des features — items, liens next/prev, bbox, filtres, anonyme"
```

---

## Task 8: Repository features — écriture (insert/update/delete)

**Files:**
- Modify: `core/app/features/repository.py`
- Test: `core/tests/test_features_repository.py` (étendre)

**Interfaces:**
- Consumes: `rls_scope` posé par l'appelant ; `TableInfo`, `quote_ident`.
- Produces (consommé par la task 9) :
  - `insert_feature(session, info, *, properties: dict, geometry: dict | None) -> int | str` — retourne le fid ; **stampe `tenant_id = current_setting('app.tenant_id')` explicitement** (pas le DEFAULT — un futur tenant non-'default' doit écrire chez lui) ; laisse remonter `IntegrityError` (conflit PK → 409 en route).
  - `replace_feature(session, info, *, fid: str, properties: dict, geometry: dict | None) -> bool` — remplacement complet : toute colonne inscriptible absente de `properties` passe à NULL ; False si fid introuvable (dans le scope RLS).
  - `delete_feature(session, info, *, fid: str) -> bool`.

- [ ] **Step 1: Tests postgis (rouges)**

Ajouter à `core/tests/test_features_repository.py` :

```python
from app.features.repository import delete_feature, insert_feature, replace_feature


def test_insert_stamps_current_tenant_and_returns_fid(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            fid = insert_feature(session, info, properties={"titre": "d", "nb": 4},
                                 geometry={"type": "Point", "coordinates": [4.0, 48.0]})
        session.commit()
    assert isinstance(fid, int)
    with pg_session_factory() as session:
        row = session.execute(text(
            "SELECT tenant_id, titre, ST_X(geom) FROM t_feat WHERE id = :i"), {"i": fid}).one()
        assert row[0] == "default" and row[1] == "d" and row[2] == 4.0


def test_replace_is_full_and_scoped(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            ok = replace_feature(session, info, fid="1",
                                 properties={"titre": "a2"}, geometry=None)
            assert ok is True
            assert replace_feature(session, info, fid="3",  # autre tenant
                                   properties={"titre": "hack"}, geometry=None) is False
            assert replace_feature(session, info, fid="999",
                                   properties={"titre": "x"}, geometry=None) is False
        session.commit()
    with pg_session_factory() as session:
        row = session.execute(text(
            "SELECT titre, nb, geom FROM t_feat WHERE id = 1")).one()
        assert row[0] == "a2" and row[1] is None and row[2] is None  # remplacement complet
        assert session.execute(text(
            "SELECT titre FROM t_feat WHERE id = 3")).scalar() == "c"  # intact


def test_delete_scoped(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            assert delete_feature(session, info, fid="2") is True
            assert delete_feature(session, info, fid="3") is False  # autre tenant
            assert delete_feature(session, info, fid="zzz") is False
        session.commit()
    with pg_session_factory() as session:
        assert session.execute(text("SELECT count(*) FROM t_feat")).scalar() == 2
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_repository.py -v`
Expected: FAIL `ImportError: insert_feature`

- [ ] **Step 3: Implémenter (ajouts à `repository.py`)**

```python
def _geometry_sql(info: TableInfo) -> str:
    return "ST_SetSRID(ST_GeomFromGeoJSON(:__geom), :__srid)"


def insert_feature(session: Session, info: TableInfo, *, properties: dict,
                   geometry: dict | None):
    t = quote_ident(session, info.table_name)
    cols, values, params = ["tenant_id"], ["current_setting('app.tenant_id')"], {}
    for i, col in enumerate(_property_columns(info)):
        if col.name in properties:
            cols.append(quote_ident(session, col.name))
            values.append(f":p{i}")
            params[f"p{i}"] = properties[col.name]
    if geometry is not None and info.geometry_column:
        cols.append(quote_ident(session, info.geometry_column))
        values.append(_geometry_sql(info))
        params.update(__geom=json.dumps(geometry), __srid=info.srid or 4326)
    fid = session.execute(text(
        f"INSERT INTO public.{t} ({', '.join(cols)}) VALUES ({', '.join(values)}) "
        f"RETURNING {quote_ident(session, info.pk_column)}"
    ), params).scalar()
    return fid


def replace_feature(session: Session, info: TableInfo, *, fid: str,
                    properties: dict, geometry: dict | None) -> bool:
    value = _coerce_fid(info, fid)
    if value is None:
        return False
    t = quote_ident(session, info.table_name)
    sets, params = [], {"__fid": value}
    for i, col in enumerate(_property_columns(info)):
        sets.append(f"{quote_ident(session, col.name)} = :p{i}")
        params[f"p{i}"] = properties.get(col.name)  # absent → NULL (remplacement complet)
    if info.geometry_column:
        if geometry is not None:
            sets.append(f"{quote_ident(session, info.geometry_column)} = {_geometry_sql(info)}")
            params.update(__geom=json.dumps(geometry), __srid=info.srid or 4326)
        else:
            sets.append(f"{quote_ident(session, info.geometry_column)} = NULL")
    r = session.execute(text(
        f"UPDATE public.{t} SET {', '.join(sets)} "
        f"WHERE {quote_ident(session, info.pk_column)} = :__fid"
    ), params)
    return r.rowcount == 1


def delete_feature(session: Session, info: TableInfo, *, fid: str) -> bool:
    value = _coerce_fid(info, fid)
    if value is None:
        return False
    t = quote_ident(session, info.table_name)
    r = session.execute(text(
        f"DELETE FROM public.{t} WHERE {quote_ident(session, info.pk_column)} = :__fid"
    ), {"__fid": value})
    return r.rowcount == 1
```

- [ ] **Step 4: Vérifier + commit**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_repository.py -v && uv run pytest -q`
Expected: 9 PASS.

```bash
git add core/app/features/repository.py core/tests/test_features_repository.py
git commit -m "feat(core): repository features écriture — insert/replace/delete sous RLS, tenant stampé"
```

---

## Task 9: Routes écriture Part 4 (POST/PUT/DELETE + validation + audit + matrice d'authz)

**Files:**
- Modify: `core/app/features/routes.py`
- Test: `core/tests/test_features_routes_write.py` (SQLite fake repo) ; `core/tests/test_features_integration.py` (postgis, bout en bout)

**Interfaces:**
- Consumes: `validate_feature` (task 4) ; `insert_feature`/`replace_feature`/`delete_feature` (task 8 — le fake du test les mime) ; `can` (`kind="collection"`) ; `write_audit`.
- Produces: `POST /collections/{cid}/items` → 201 + header `Location` ; `PUT /collections/{cid}/items/{fid}` → 204 ; `DELETE …/{fid}` → 204. Règles : anonyme → 401 (routes en `get_current_user` strict) ; lisible mais pas editor → 403 ; `col.editable == False` → 403 `"collection is not editable"` ; erreurs validation → 400 `{"errors": [...]}` ; `IntegrityError` sur POST → 409 ; fid introuvable → 404. Audit `feature.create/update/delete` payload `{"collection": cid, "fid": str(fid)}`.

- [ ] **Step 1: Tests SQLite (rouges)**

```python
# core/tests/test_features_routes_write.py
# Fixture : copier depuis core/tests/test_features_routes_read.py (qui existe
# dans le repo à ce stade, task 7) la fixture `env`, les helpers `_as` et
# `_register`, `INFO` et `fake_introspector` — pattern maison : fixtures par
# fichier. DEUX adaptations : (1) la fixture retourne AUSSI `Session` (la
# factory) pour relire l'audit ; (2) le fake repo est celui-ci :
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError


def make_fake_write_repo():
    state = {"rows": {1: {"titre": "a"}}, "next": 2}

    def insert_feature(session, info, *, properties, geometry):
        if properties.get("titre") == "conflit":
            raise IntegrityError("dup", None, Exception("pk"))
        fid = state["next"]
        state["next"] += 1
        state["rows"][fid] = properties
        return fid

    def replace_feature(session, info, *, fid, properties, geometry):
        if fid == "1":
            state["rows"][1] = properties
            return True
        return False

    def delete_feature(session, info, *, fid):
        if fid == "1" and 1 in state["rows"]:
            del state["rows"][1]
            return True
        return False

    def select_features(session, info, **kw):  # inutilisé dans ce fichier
        raise AssertionError("read path should not be called")

    def get_feature(session, info, *, fid):
        return None

    return SimpleNamespace(
        insert_feature=insert_feature, replace_feature=replace_feature,
        delete_feature=delete_feature, select_features=select_features,
        get_feature=get_feature, state=state,
    )


VALID = {"type": "Feature", "properties": {"titre": "Nid de poule"}, "geometry": None}


def test_anonymous_write_is_401(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.post("/collections/incidents/items", json=VALID).status_code == 401


def test_viewer_write_is_403_editor_ok(env):
    # regular lisible via isPublic mais sans rôle editor → 403 ;
    # admin (pleins droits collections) → 201 + Location.
    app, client, admin, regular, _repo = env
    _register(app, client, admin, public=True)
    _as(app, regular)
    assert client.post("/collections/incidents/items", json=VALID).status_code == 403
    _as(app, admin)
    r = client.post("/collections/incidents/items", json=VALID)
    assert r.status_code == 201
    assert r.headers["Location"].endswith("/collections/incidents/items/2")


def test_not_editable_collection_is_403(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/collections/incidents", json={"editable": False})
    r = client.post("/collections/incidents/items", json=VALID)
    assert r.status_code == 403 and r.json()["detail"] == "collection is not editable"


def test_validation_errors_are_structured_400(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    r = client.post("/collections/incidents/items",
                    json={"type": "Feature", "properties": {"inconnu": 1}})
    assert r.status_code == 400
    codes = {(e["field"], e["code"]) for e in r.json()["detail"]["errors"]}
    assert ("inconnu", "unknown_property") in codes and ("titre", "missing_required") in codes


def test_pk_conflict_is_409(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    r = client.post("/collections/incidents/items",
                    json={"type": "Feature", "properties": {"titre": "conflit"}})
    assert r.status_code == 409


def test_put_and_delete(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    assert client.put("/collections/incidents/items/1", json=VALID).status_code == 204
    assert client.put("/collections/incidents/items/999", json=VALID).status_code == 404
    assert client.delete("/collections/incidents/items/1").status_code == 204
    assert client.delete("/collections/incidents/items/999").status_code == 404


def test_writes_are_audited(env):
    # `Session` est la factory retournée par la fixture (adaptation n°1).
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.post("/collections/incidents/items", json=VALID)
    client.put("/collections/incidents/items/1", json=VALID)
    client.delete("/collections/incidents/items/1")
    from sqlalchemy import select

    from app.audit.models import AuditLog
    with Session() as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"feature.create", "feature.update", "feature.delete"} <= actions
```

(Les autres tests du fichier dépaquettent donc
`app, client, Session, admin, regular, repo = env` — ajuster uniformément.)

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_features_routes_write.py -v`
Expected: FAIL — 404/405 (routes POST/PUT/DELETE inexistantes).

- [ ] **Step 3: Implémenter (ajouts à `features/routes.py`)**

```python
from fastapi import Response
from sqlalchemy.exc import IntegrityError

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections.repository import get_access_facts
from app.features.validation import validate_feature
from app.sharing.authorization import can


def _get_writable(session, user, collection_id):
    col = get_readable_collection(session, user, collection_id)
    if not can(session, user_id=user.id, action="write", item=get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="write access required")
    if not col.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    return col


def _validated(introspect, session, col, payload):
    info = introspect(session, col.table_name)
    errors = validate_feature(info, payload)
    if errors:
        raise _validation_error(errors)
    return info


@router.post("/collections/{collection_id}/items", status_code=201)
def create_feature(
    collection_id: str, payload: dict, request: Request, response: Response,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = _validated(introspect, session, col, payload)
    try:
        with rls(session, col.tenant_id):
            fid = repo.insert_feature(session, info,
                                      properties=payload.get("properties") or {},
                                      geometry=payload.get("geometry"))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="feature conflicts with an existing row")
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.create", object_type="feature", object_id=str(fid),
                payload={"collection": col.id, "fid": str(fid)})
    response.headers["Location"] = str(
        request.url_for("get_single_feature", collection_id=col.id, fid=str(fid)))
    return {"id": fid}


@router.put("/collections/{collection_id}/items/{fid}", status_code=204)
def put_feature(
    collection_id: str, fid: str, payload: dict,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = _validated(introspect, session, col, payload)
    with rls(session, col.tenant_id):
        ok = repo.replace_feature(session, info, fid=fid,
                                  properties=payload.get("properties") or {},
                                  geometry=payload.get("geometry"))
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.update", object_type="feature", object_id=fid,
                payload={"collection": col.id, "fid": fid})


@router.delete("/collections/{collection_id}/items/{fid}", status_code=204)
def remove_feature(
    collection_id: str, fid: str,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        ok = repo.delete_feature(session, info, fid=fid)
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.delete", object_type="feature", object_id=fid,
                payload={"collection": col.id, "fid": fid})
```

- [ ] **Step 4: Test d'intégration bout en bout (postgis)**

```python
# core/tests/test_features_integration.py
"""Bout en bout sur PostGIS réel : enregistrement (vrai introspecteur + vraie
DDL RLS) puis CRUD via l'API — le critère d'acceptation §9 de la spec.
Fixture : même pattern que test_seed_demo.py (Base.metadata.create_all sur
pg_engine, teardown TRUNCATE ciblé + DROP des tables jetables), app câblée
sur la session factory PostGIS SANS override du repo ni du scope RLS."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(text(
            "CREATE TABLE demo_incidents (id serial PRIMARY KEY, "
            "titre text NOT NULL, geom geometry(Point, 4326))"))
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    yield TestClient(app)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def test_full_crud_roundtrip(pg_app):
    client = pg_app
    assert client.post("/collections", json={"tableName": "demo_incidents"}).status_code == 201
    r = client.post("/collections/demo_incidents/items", json={
        "type": "Feature", "properties": {"titre": "Nid de poule"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}})
    assert r.status_code == 201
    fid = r.json()["id"]
    body = client.get("/collections/demo_incidents/items").json()
    assert body["numberMatched"] == 1
    assert body["features"][0]["properties"]["titre"] == "Nid de poule"
    assert client.put(f"/collections/demo_incidents/items/{fid}", json={
        "type": "Feature", "properties": {"titre": "Réparé"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}}).status_code == 204
    assert client.get(f"/collections/demo_incidents/items/{fid}").json()[
        "properties"]["titre"] == "Réparé"
    assert client.delete(f"/collections/demo_incidents/items/{fid}").status_code == 204
    assert client.get("/collections/demo_incidents/items").json()["numberMatched"] == 0
```

- [ ] **Step 5: Vérifier + commit**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_routes_write.py tests/test_features_integration.py -v && uv run pytest -q && uv run lint-imports`
Expected: tout PASS.

```bash
git add core/app/features/routes.py core/tests/test_features_routes_write.py \
  core/tests/test_features_integration.py
git commit -m "feat(core): écriture OGC Part 4 — POST/PUT/DELETE validés, audités, sous RLS"
```

---

## Task 10: Landing page, conformance, description OGC de collection (extent + links)

**Files:**
- Modify: `core/app/features/routes.py` (landing + conformance)
- Modify: `core/app/collections/routes.py` (`_collection_json` enrichi : `links`, `extent`, `itemType`)
- Test: `core/tests/test_ogc_discovery.py` (SQLite) + assertion extent dans `core/tests/test_features_integration.py`

**Interfaces:**
- Consumes: `table_extent` (`app.collections.extent`, task 6) ; `rls_scope`.
- Produces: `GET /` → landing `{title, links: self/conformance/data/service-desc}` ; `GET /conformance` → `{"conformsTo": [...]}` ; `GET /collections/{cid}` enrichi : `links` (self + items), `itemType: "feature"`, `extent.spatial.bbox` (calculé, `None` omis). Dépendance injectable `get_extent_provider` dans `app.collections.routes` (défaut : `table_extent` sous `rls_scope`… voir note layering).

- [ ] **Step 1: Tests (rouges)**

```python
# core/tests/test_ogc_discovery.py
# Fixture env : reprendre intégralement celle de test_features_routes_read.py
# (mêmes imports, fake introspector, fake repo, scope nul), plus :
#   app.dependency_overrides[collections_routes.get_extent_provider] = (
#       lambda: lambda session, info, tenant_id: [1.0, 45.0, 2.0, 46.0])

CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
]


def test_landing_page_wins_over_mcp_mount(env):
    _app, client, *_ = env
    r = client.get("/")
    assert r.status_code == 200
    rels = {l["rel"] for l in r.json()["links"]}
    assert {"self", "conformance", "data", "service-desc"} <= rels
    assert client.get("/health").status_code == 200  # le mount MCP n'est pas cassé


def test_conformance(env):
    _app, client, *_ = env
    assert client.get("/conformance").json()["conformsTo"] == CONFORMANCE_CLASSES


def test_collection_description_is_ogc(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)
    body = client.get("/collections/incidents").json()
    assert body["itemType"] == "feature"
    assert body["extent"] == {"spatial": {"bbox": [[1.0, 45.0, 2.0, 46.0]]}}
    rels = {l["rel"]: l["href"] for l in body["links"]}
    assert rels["items"].endswith("/collections/incidents/items")
```

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_ogc_discovery.py -v`
Expected: FAIL (GET / → réponse MCP/404, conformance inexistante, description sans extent).

- [ ] **Step 3: Implémenter**

Dans `core/app/features/routes.py` :

```python
CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
]


@router.get("/")
def landing_page(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "title": "GeoStudio OGC API Features",
        "description": "Collections éditables du cœur GeoStudio",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
            {"rel": "service-desc", "type": "application/vnd.oai.openapi+json;version=3.0",
             "href": f"{base}/openapi.json"},
        ],
    }


@router.get("/conformance")
def conformance():
    return {"conformsTo": CONFORMANCE_CLASSES}
```

Dans `core/app/collections/routes.py` :

```python
def get_extent_provider():
    """Défaut : emprise réelle sous rls_scope. app.collections ne peut pas
    importer app.features (couche supérieure) — le scope RLS vit donc en
    double minimal ici : les deux SET sont inline (3 lignes), pas d'import."""
    from sqlalchemy import text as _text

    from app.collections.extent import table_extent

    def provider(session, info, tenant_id):
        if session.get_bind().dialect.name != "postgresql":
            return None
        session.execute(_text("SELECT set_config('app.tenant_id', :tid, true)"),
                        {"tid": tenant_id})
        session.execute(_text("SET LOCAL ROLE gis_rls"))
        try:
            return table_extent(session, info)
        finally:
            session.execute(_text("RESET ROLE"))

    return provider
```

et dans `get_collection` (la route détail uniquement — pas le listing, une
introspection + un ST_Extent par collection listée serait injustifié) :

```python
@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str, request: Request,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    extent_provider=Depends(get_extent_provider),
):
    col = get_readable_collection(session, user, collection_id)
    body = _collection_json(col)
    body["itemType"] = "feature"
    base = str(request.base_url).rstrip("/")
    body["links"] = [
        {"rel": "self", "type": "application/json",
         "href": f"{base}/collections/{col.id}"},
        {"rel": "items", "type": "application/geo+json",
         "href": f"{base}/collections/{col.id}/items"},
    ]
    try:
        info = introspect(session, col.table_name)
        bbox = extent_provider(session, info, col.tenant_id)
    except Exception:
        bbox = None  # description robuste : une table disparue ne casse pas le détail
    body["extent"] = {"spatial": {"bbox": [bbox]}} if bbox else None
    return body
```

Ajouter dans `test_features_integration.py::test_full_crud_roundtrip`, après le
POST de la feature :

```python
    desc = client.get("/collections/demo_incidents").json()
    assert desc["extent"]["spatial"]["bbox"] == [[1.85, 45.27, 1.85, 45.27]]
```

- [ ] **Step 4: Vérifier + commit**

Run: `uv run pytest tests/test_ogc_discovery.py -v && CORE_TEST_DATABASE_URL=… uv run pytest -q && uv run lint-imports`
Expected: PASS (le test landing vérifie aussi que `/health` et le mount MCP survivent).

```bash
git add core/app/features/routes.py core/app/collections/routes.py \
  core/tests/test_ogc_discovery.py core/tests/test_features_integration.py
git commit -m "feat(core): landing OGC, conformance, description de collection avec extent"
```

---

## Task 11: Fixes transverses hérités (doublons group_id, seed audité + tolérant)

**Files:**
- Modify: `core/app/sharing/schemas.py`
- Modify: `core/scripts/seed_demo.py`
- Test: `core/tests/test_sharing_schemas.py` (nouveau), `core/tests/test_collections_sharing_routes.py` (1 test), `core/tests/test_seed_demo.py` (étendre)

**Interfaces:**
- Consumes: `Sharing`/`GroupShare` (`app.sharing.schemas`) — utilisés par les routes sharing items ET collections ; `write_audit` ; `UnsupportedTable`.
- Produces: `Sharing.groups` rejette les `groupId` dupliqués (422 sur les deux chemins) ; `seed()` audite (`actor_kind="system"`) et saute les tables `UnsupportedTable` avec warning.

- [ ] **Step 1: Tests (rouges)**

```python
# core/tests/test_sharing_schemas.py
import pytest
from pydantic import ValidationError

from app.sharing.schemas import GroupShare, Sharing


def test_duplicate_group_ids_rejected():
    with pytest.raises(ValidationError):
        Sharing(public=False, groups=[
            GroupShare(groupId="g1", role="viewer"),
            GroupShare(groupId="g1", role="editor"),
        ])


def test_distinct_groups_ok():
    s = Sharing(public=True, groups=[
        GroupShare(groupId="g1", role="viewer"),
        GroupShare(groupId="g2", role="editor"),
    ])
    assert len(s.groups) == 2
```

Dans `core/tests/test_collections_sharing_routes.py`, ajouter :

```python
def test_put_sharing_duplicate_group_is_422(env):
    app, client, _s, admin, _r, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.put("/collections/incidents/sharing", json={
        "public": False,
        "groups": [{"groupId": group_id, "role": "viewer"},
                   {"groupId": group_id, "role": "editor"}]})
    assert r.status_code == 422
```

(adapter le dépaquetage de la fixture `env` à sa forme réelle dans ce fichier).

Dans `core/tests/test_seed_demo.py`, ajouter :

```python
def test_seed_writes_audit(pg_core):
    with pg_core() as session:
        seed(session)
        session.commit()
    with pg_core() as session:
        rows = session.execute(text(
            "SELECT action, actor_kind FROM audit_log")).all()
    assert ("collection.create", "system") in [(r[0], r[1]) for r in rows]
```

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_sharing_schemas.py -v`
Expected: FAIL (pas de validation des doublons).

- [ ] **Step 3: Implémenter**

`core/app/sharing/schemas.py` — ajouter au modèle `Sharing` :

```python
from pydantic import field_validator


    @field_validator("groups")
    @classmethod
    def no_duplicate_groups(cls, groups):
        seen = [g.groupId for g in groups]
        if len(seen) != len(set(seen)):
            raise ValueError("duplicate groupId in sharing payload")
        return groups
```

`core/scripts/seed_demo.py` — dans `seed()` :

```python
from app.audit.writer import write_audit
from app.collections.introspection import TableNotFound, UnsupportedTable

# dans la boucle, remplacer le except par :
        try:
            info = introspect_table(session, table)
        except TableNotFound:
            print(f"table '{table}' absente — ignorée")
            continue
        except UnsupportedTable as exc:
            print(f"table '{table}' non enregistrable ({exc.reason}) — ignorée")
            continue
# et après create_collection(...) :
        write_audit(session, tenant_id=tenant.id, actor_id=owner.id,
                    actor_kind="system", action="collection.create",
                    object_type="collection", object_id=table,
                    payload={"tableName": table, "seed": True})
```

- [ ] **Step 4: Vérifier + commit**

Run: `uv run pytest tests/test_sharing_schemas.py tests/test_collections_sharing_routes.py -v && CORE_TEST_DATABASE_URL=… uv run pytest -q`
Expected: PASS — y compris les tests sharing items existants (la validation vit dans le schéma partagé, elle couvre les deux chemins).

```bash
git add core/app/sharing/schemas.py core/scripts/seed_demo.py \
  core/tests/test_sharing_schemas.py core/tests/test_collections_sharing_routes.py \
  core/tests/test_seed_demo.py
git commit -m "fix(core): doublons de groupes rejetés (items+collections), seed audité et tolérant"
```

---

## Task 12: Contrat OpenAPI→TS, vérification complète, doc d'état

**Files:**
- Modify: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` (régénérés)
- Modify: `CLAUDE.md` (compte de tests ; bullet « SP-3b livré … Prochain chantier : SP-3c »)
- Modify: `docs/superpowers/specs/2026-07-09-sp3-collections-features-design.md` (notes de revue : items backlog 3b cochés)

**Interfaces:**
- Produces: contrat committé incluant `/`, `/conformance`, `/collections/{collection_id}/items*` — le job CI `api-types-drift` reste vert.

- [ ] **Step 1: Régénérer**

Run:
```bash
cd core && PYTHONPATH=. uv run python scripts/export_openapi.py
cd ../shell && npm ci && npm run gen:api-types
```
Expected: nouveaux paths features dans les deux fichiers générés.

- [ ] **Step 2: Vérification complète**

Run:
```bash
cd core && CORE_TEST_DATABASE_URL=… uv run pytest && uv run lint-imports
cd ../shell && npm run test && npm run build
```
Expected: tout PASS (le shell ne consomme pas encore ces endpoints — bascule en SP-3c).

- [ ] **Step 3: Doc d'état**

- `CLAUDE.md` : compte de tests core actualisé ; remplacer le bullet
  « Prochain chantier : SP-3b … » par : « **SP-3b livré** (date du jour) :
  OGC API Features Part 1+4 dans le cœur (landing, conformance, items
  GeoJSON — bbox, filtres, pagination avec liens —, POST/PUT/DELETE validés
  par schéma, audités), chaque requête métier sous `rls_scope` (rôle
  `gis_rls` + GUC tenant, validé à travers PgBouncer par
  `scripts/spike_pgbouncer_rls.py`). **Prochain chantier : SP-3c** (bascule
  du shell sur le cœur, retrait de pg_featureserv). »
- Spec SP-3, « Notes de revue SP-3a » : marquer ✅ les items du backlog 3b
  traités (test RLS UPDATE, index tenant_id, enum qualifié, gardes testées,
  doublons group_id, seed) — une ligne chacun, ne pas réécrire la section.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts CLAUDE.md \
  docs/superpowers/specs/2026-07-09-sp3-collections-features-design.md
git commit -m "chore(core): contrat OpenAPI/TS régénéré — endpoints OGC features (SP-3b)"
```

---

## Couverture spec → tâches (auto-vérification)

| Exigence (spec SP-3, périmètre 3b) | Tâche(s) |
|---|---|
| Spike RLS/PgBouncer en ouverture, repli documenté (risque §10) | 1 |
| Backlog SP-3a : index tenant_id, séquence qualifiée, test RLS UPDATE | 2 |
| Backlog SP-3a : enum qualifié, gardes 0-PK/2-géom testées | 3 |
| Validation par schéma, erreurs structurées `{field, code, message}` (§4) | 4, 9 |
| `SET LOCAL ROLE gis_rls` + GUC tenant paramétré, RESET avant audit (§2/§5) | 5, 9 |
| Items GeoJSON : limit/offset+liens, bbox, filtres égalité compat pg_featureserv (§2/§4) | 6, 7 |
| Lecture anonyme des collections publiques, 404-avant-403 (§2) | 7 |
| POST 201+Location / PUT 204 / DELETE 204 ; 401/403/404/409 ; `editable` (§4/§7) | 8, 9 |
| Audit `feature.create/update/delete` payload `{collection, fid}` (§2) | 9 |
| Landing `/`, `/conformance` (classes tenues), description collection + extent (§4) | 10 |
| Backlog SP-3a : doublons group_id (deux chemins), seed audité/tolérant | 11 |
| OpenAPI→TS (A11), doc d'état | 12 |

Hors périmètre (rappel) : bascule shell `queryDataSource`/`featuresUrl`/
`listLayerSources`, retrait pg_featureserv du compose, E2E re-mockées,
`response_model` sur collections/users → **SP-3c**. Reprojection CRS, PATCH
partiel, transactions multi-features → différés par la spec.
