# SP-11c — Endpoint SQL analyste read-only sandboxé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un utilisateur porteur du rôle *analyste* exécute du SQL read-only, via `POST /analytics/sql`, sur les collections qu'il a le droit de lire — chacune exposée comme une vue DuckDB déjà réduite à l'état courant sur le GeoParquet CDC ; un non-analyste reçoit 403 ; le SQL est confiné par construction aux seules vues autorisées, borné (timeout / lignes / mémoire) et audité. Livrer cette sous-partie **clôt SP-11**.

**Architecture:** Nouveau booléen `users.is_analyst` (miroir exact de `is_admin` : migration Alembic, bootstrap `CORE_ANALYST_SUBS`, `PATCH /users`, `GET /me`). Endpoint `POST /analytics/sql` (dans le routeur `app.features.routes`, aux côtés de `/collections/{id}/aggregate` déjà existant). Le moteur d'isolation vit dans un module pur `app/analytics/sql_sandbox.py` : par requête, une connexion DuckDB éphémère (réutilise `app/analytics/duckdb_conn.py`), on **matérialise en tables temporaires** les seules vues référencées par la requête (réduction état-courant de SP-11b, `app/analytics/aggregate.py::_dedup_cte`), puis on **verrouille la connexion** (`SET enable_external_access = false; SET lock_configuration = true`) de sorte que DuckDB lui-même refuse tout accès fichier/S3/`ATTACH`/`LOAD` au moment d'exécuter le SQL de l'analyste. La frontière de sécurité est DuckDB, pas un parseur maison.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy / Alembic ; DuckDB (déjà dépendance SP-11b, extensions `httpfs`+`spatial` embarquées dans l'image) ; geopandas/pyarrow (fixtures Parquet de test) ; OpenTelemetry (compteur) ; React/TypeScript côté shell (type `Me`, régénération OpenAPI).

## Global Constraints

- **`is_admin` n'implique PAS `is_analyst`** — capacités distinctes. Le cas 403 s'appuie sur un utilisateur ni admin ni analyste ; un admin non-analyste reçoit aussi 403.
- **Frontière de sécurité = DuckDB, jamais un parseur maison.** L'extraction d'AST (`json_serialize_sql`) sert uniquement à (a) rejeter le non-SELECT tôt et (b) choisir quelles vues matérialiser ; elle n'est PAS load-bearing pour la sécurité. La garantie dure est `SET enable_external_access = false` + `SET lock_configuration = true`.
- **Réutiliser SP-11b, ne pas dupliquer :** connexion via `app/analytics/duckdb_conn.py::open_connection` ; réduction état-courant via `app/analytics/aggregate.py::_dedup_cte` / `_qi` / `_has_any_file` ; facteurs d'injection `get_duckdb_connection_factory` / `get_analytics_base_uri` de `app/features/routes.py`.
- **`POST /analytics/sql` est une lecture** : il DOIT être exempté du middleware read-only/démo de `app/main.py`, exactement comme `POST /collections/{id}/aggregate` l'est déjà (`_AGGREGATE_PATH_RE`).
- **Valeurs de quota (réglables, définies une fois dans `sql_sandbox.py`) :** `ROW_CAP = 10_000`, `STATEMENT_TIMEOUT_S = 10.0`, `MEMORY_LIMIT = "512MB"`, `THREADS = 2`.
- **Nom de vue = identifiant de collection** (`Collection.id`, un slug = `table_name`). Les identifiants sont toujours cités via `_qi`.
- **Périmètre des données = `list_visible_collections`** (même surface de permission que `GET /items` / `POST /aggregate`), pas un nouveau modèle de permission.
- **Migrations :** dernière révision = `0013`. Cette sous-partie ajoute `0014`.
- **Discipline :** TDD, commits conventionnels petits (`feat(core):` / `feat(shell):` / `test(core):` / `docs:`), en-tête SPDX `# SPDX-License-Identifier: Apache-2.0` en tête de tout nouveau fichier source (`.py`) et `// SPDX-License-Identifier: Apache-2.0` pour tout nouveau `.ts`.
- **Commandes de test :** cœur `cd core && uv run pytest` (tests `postgis` skippés sans `CORE_TEST_DATABASE_URL`) ; shell `cd shell && npm run test` ; drift API `cd core && uv run python scripts/export_openapi.py openapi.json` puis `cd shell && npm run gen:api-types` (cf. Task 6).

---

## Task 1: Spike go/no-go — mécanisme d'isolation DuckDB (GATE)

Valide empiriquement, contre un MinIO réel et un GeoParquet réel, que le mécanisme d'isolation choisi (matérialisation + verrouillage) fonctionne **et** bloque tous les cas d'abus, AVANT d'investir dans le module complet. Même discipline que les spikes d'ouverture de SP-11a et SP-11b. **Si un cas d'abus ne peut être bloqué proprement, le plan s'arrête ici.**

**Files:**
- Create: `core/scripts/spike_duckdb_sql_sandbox.py`

**Interfaces:**
- Consumes: `app/analytics/duckdb_conn.py::open_connection`, un GeoParquet CDC réel écrit dans MinIO par le spike lui-même.
- Produces: **findings documentés en tête du script** (docstring) que Task 7/8 consomment : (a) les chaînes exactes de type de nœud AST de `json_serialize_sql` pour un SELECT (ex. `SELECT_NODE`, `SET_OPERATION_NODE`) et pour une référence de table de base (ex. `BASE_TABLE` + clé `table_name`) ; (b) confirmation que `SET enable_external_access = false; SET lock_configuration = true` bloque `read_parquet`/`read_csv`/`ATTACH`/`COPY TO`/`INSTALL`/`LOAD`/lecture locale tout en laissant fonctionner `SELECT`/`ST_*` sur une table temporaire déjà matérialisée ; (c) confirmation que `conn.interrupt()` depuis un `threading.Timer` interrompt une requête longue (exception attrapable) ; (d) confirmation que `SET memory_limit` / `SET threads` sont acceptés.

- [ ] **Step 1: Écrire le script de spike**

Le script est autonome (comme `core/scripts/spike_duckdb_geoparquet.py` de SP-11b). Il suppose un MinIO joignable via les variables `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_CDC_BUCKET` (mêmes que le compose). Il écrit un petit GeoParquet CDC sous `s3://<bucket>/cdc/tenant_id=t1/collection_id=villes/dt=2026-07-18/part-1.parquet`, puis exécute une série de checks PASS/FAIL.

```python
# SPDX-License-Identifier: Apache-2.0
"""Spike go/no-go SP-11c — isolation DuckDB pour le SQL analyste sandboxé.

FINDINGS (à remplir/confirmer en exécutant ce script — consommés par Task 7/8) :
- AST json_serialize_sql : type de nœud SELECT = ??? ; réf. table de base = ??? (clé table_name).
- Verrouillage : SET enable_external_access=false; SET lock_configuration=true bloque
  read_parquet/read_csv/ATTACH/COPY TO/INSTALL/LOAD/lecture locale : OUI/NON.
- ST_* + SELECT sur table temp matérialisée fonctionnent après verrouillage : OUI/NON.
- Timeout via threading.Timer(conn.interrupt) interruptible : OUI/NON, exception = ???.
- SET memory_limit / SET threads acceptés : OUI/NON.

Lancer : cd core && uv run python scripts/spike_duckdb_sql_sandbox.py
"""
import json
import os
import threading
import time
import uuid

import duckdb
import geopandas as gpd
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_connection

BUCKET = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
BASE = f"s3://{BUCKET}/cdc"
GLOB = f"{BASE}/tenant_id=t1/collection_id=villes/dt=2026-07-18/*.parquet"

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def _open():
    return open_connection(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def write_fixture():
    # Écrit un GeoParquet CDC réel via geopandas → MinIO (httpfs write).
    conn = _open()
    gdf = gpd.GeoDataFrame(
        [{"id": i, "region": "Nord" if i % 2 else "Sud", "pop": i,
          "_op": "insert", "_lsn": i, "_ts": 1.0, "geometry": Point(i, i)} for i in range(1, 6)],
        geometry="geometry", crs="EPSG:4326",
    )
    local = f"/tmp/spike-{uuid.uuid4().hex}.parquet"
    gdf.to_parquet(local)
    conn.execute(f"COPY (SELECT * FROM read_parquet('{local}')) TO '{GLOB.replace('*', 'part-1')}' (FORMAT parquet)")
    conn.close()


def probe_ast():
    conn = _open()
    doc = json.loads(conn.execute(
        "SELECT json_serialize_sql('SELECT region, count(*) FROM villes t JOIN autre a ON a.id=t.id GROUP BY region')"
    ).fetchone()[0])
    print("AST SAMPLE:", json.dumps(doc)[:2000])
    # Repérer visuellement les type de nœud SELECT et les nœuds de table de base (table_name).
    check("json_serialize_sql renvoie un AST exploitable", "statements" in doc, str(list(doc.keys())))
    conn.close()


def probe_materialize_then_lock():
    conn = _open()
    conn.execute("SET memory_limit='512MB'")
    conn.execute("SET threads=2")
    # 1) Matérialiser depuis le GeoParquet (accès externe encore autorisé).
    conn.execute(f"CREATE TEMP TABLE villes AS SELECT * FROM read_parquet('{GLOB}', hive_partitioning=true)")
    # 2) Verrouiller.
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")
    # 3) SELECT + ST_* sur la table temp doivent marcher.
    n = conn.execute("SELECT count(*) FROM villes WHERE ST_Intersects(geometry, ST_MakeEnvelope(0,0,10,10))").fetchone()[0]
    check("SELECT + ST_* sur table temp après verrouillage", n == 5, f"count={n}")

    # 4) Chaque cas d'abus doit LEVER une exception.
    for label, sql in [
        ("read_parquet chemin arbitraire (cross-tenant)", f"SELECT * FROM read_parquet('{BASE}/tenant_id=t2/collection_id=x/dt=*/*.parquet')"),
        ("read_csv arbitraire", "SELECT * FROM read_csv('/etc/hostname')"),
        ("lecture fichier local", "SELECT * FROM read_text('/etc/hostname')"),
        ("ATTACH base externe", "ATTACH 'x.db' AS x"),
        ("COPY TO (écriture)", "COPY (SELECT 1) TO '/tmp/out.parquet'"),
        ("INSTALL/LOAD extension", "INSTALL json; LOAD json"),
        ("re-SET pour ré-autoriser", "SET enable_external_access = true"),
    ]:
        try:
            conn.execute(sql)
            check(f"BLOQUE : {label}", False, "n'a PAS levé — TROU DE SÉCURITÉ")
        except duckdb.Exception:
            check(f"BLOQUE : {label}", True)
    conn.close()


def probe_timeout():
    conn = _open()
    timer = threading.Timer(0.5, conn.interrupt)
    timer.start()
    t0 = time.time()
    try:
        conn.execute("SELECT count(*) FROM range(100000000000) t1, range(100000) t2").fetchall()
        check("interrupt() interrompt une requête longue", False, "n'a pas été interrompue")
    except duckdb.Exception as exc:
        check("interrupt() interrompt une requête longue", (time.time() - t0) < 5, f"{type(exc).__name__}")
    finally:
        timer.cancel()
        conn.close()


if __name__ == "__main__":
    write_fixture()
    probe_ast()
    probe_materialize_then_lock()
    probe_timeout()
    failed = [r for r in results if not r[1]]
    print(f"\n{'GO' if not failed else 'NO-GO'} — {len(results) - len(failed)}/{len(results)} checks PASS")
    raise SystemExit(1 if failed else 0)
```

- [ ] **Step 2: Lancer le spike contre un MinIO réel**

Démarrer un MinIO jetable et exporter les variables, puis :

Run:
```bash
cd core && S3_ENDPOINT_URL=http://localhost:9000 S3_ACCESS_KEY=minioadmin \
  S3_SECRET_KEY=minioadmin S3_CDC_BUCKET=geostudio-cdc \
  uv run python scripts/spike_duckdb_sql_sandbox.py
```
Expected: `GO — N/N checks PASS`. En particulier, **tous** les checks `BLOQUE : …` doivent être PASS (chaque abus lève). Si `interrupt()` ou le verrouillage échoue, investiguer avant de continuer (NO-GO).

- [ ] **Step 3: Renseigner les FINDINGS dans le docstring**

À partir de la sortie `AST SAMPLE:`, remplir dans le docstring du script les chaînes exactes de type de nœud SELECT et de référence de table de base (elles pilotent `validate_select_only` et `collect_table_refs` en Task 7). Confirmer OUI/NON pour chaque ligne FINDINGS.

- [ ] **Step 4: Commit**

```bash
git add core/scripts/spike_duckdb_sql_sandbox.py
git commit -m "test(core): SP-11c — spike go/no-go isolation DuckDB SQL analyste (materialize + lock)"
```

**GATE :** ne continuer que si le spike est GO. Reporter les findings (types de nœuds AST, exception d'interruption) dans le rapport de tâche — Task 7/8 en dépendent.

---

## Task 2: Colonne `users.is_analyst` (migration + modèle)

**Files:**
- Create: `core/alembic/versions/0014_users_is_analyst.py`
- Modify: `core/app/users/models.py`
- Test: `core/tests/test_users_analyst.py`

**Interfaces:**
- Produces: `User.is_analyst: bool` (défaut `False`, `NOT NULL`), révision Alembic `0014` (down_revision `0013`).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_new_user_defaults_to_not_analyst():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(s, tenant_id=t.id, oidc_sub="x", username="x",
                               email=None, first_name="", last_name="")
        assert u.is_analyst is False
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_users_analyst.py -v`
Expected: FAIL (`AttributeError: 'User' object has no attribute 'is_analyst'`).

- [ ] **Step 3: Ajouter la colonne au modèle**

Dans `core/app/users/models.py`, juste après la ligne `is_admin`:

```python
    is_analyst: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 4: Écrire la migration 0014**

```python
# SPDX-License-Identifier: Apache-2.0
"""users.is_analyst — rôle analyste (SP-11c)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_analyst", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_analyst")
```

- [ ] **Step 5: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_users_analyst.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/users/models.py core/alembic/versions/0014_users_is_analyst.py core/tests/test_users_analyst.py
git commit -m "feat(core): SP-11c — colonne users.is_analyst (migration 0014, défaut false)"
```

---

## Task 3: Repository `users` — bootstrap & set analyst

**Files:**
- Modify: `core/app/users/repository.py`
- Test: `core/tests/test_users_analyst.py` (ajouts)

**Interfaces:**
- Consumes: `User.is_analyst` (Task 2).
- Produces: `get_or_create_user(..., bootstrap_analyst: bool = False)` (promotion par env uniquement, jamais de rétrogradation silencieuse — même sémantique que `bootstrap_admin`) ; `set_analyst(session, *, tenant_id, user_id, is_analyst) -> User | None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_users_analyst.py`:

```python
from app.users.repository import set_analyst


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_bootstrap_analyst_promotes_and_never_demotes():
    Session = _session()
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(s, tenant_id=t.id, oidc_sub="x", username="x",
                               email=None, first_name="", last_name="", bootstrap_analyst=True)
        assert u.is_analyst is True
        # Un appel ultérieur sans bootstrap ne rétrograde pas.
        u2 = get_or_create_user(s, tenant_id=t.id, oidc_sub="x", username="x",
                                email=None, first_name="", last_name="", bootstrap_analyst=False)
        assert u2.is_analyst is True


def test_set_analyst_toggles():
    Session = _session()
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(s, tenant_id=t.id, oidc_sub="y", username="y",
                               email=None, first_name="", last_name="")
        set_analyst(s, tenant_id=t.id, user_id=u.id, is_analyst=True)
        assert u.is_analyst is True
        set_analyst(s, tenant_id=t.id, user_id=u.id, is_analyst=False)
        assert u.is_analyst is False
        assert set_analyst(s, tenant_id=t.id, user_id="nope", is_analyst=True) is None
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_users_analyst.py -v`
Expected: FAIL (`bootstrap_analyst` inconnu / `set_analyst` non défini).

- [ ] **Step 3: Implémenter**

Dans `get_or_create_user`, ajouter le paramètre `bootstrap_analyst: bool = False` à la signature (après `bootstrap_admin`), et juste après le bloc `if bootstrap_admin and not user.is_admin:` :

```python
    if bootstrap_analyst and not user.is_analyst:
        # Promotion par env uniquement (retirer un sub de CORE_ANALYST_SUBS
        # ne doit pas destituer silencieusement) — miroir de bootstrap_admin.
        user.is_analyst = True
```

Ajouter la fonction (après `set_admin`) :

```python
def set_analyst(session: Session, *, tenant_id: str, user_id: str, is_analyst: bool) -> User | None:
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    )
    if user is None:
        return None
    user.is_analyst = is_analyst
    session.flush()
    return user
```

- [ ] **Step 4: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_users_analyst.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/users/repository.py core/tests/test_users_analyst.py
git commit -m "feat(core): SP-11c — get_or_create_user(bootstrap_analyst) + set_analyst"
```

---

## Task 4: `auth/dependency` — `analyst_subs()` + câblage bootstrap

**Files:**
- Modify: `core/app/auth/dependency.py`
- Test: `core/tests/test_auth.py` (ajouts)

**Interfaces:**
- Consumes: `get_or_create_user(bootstrap_analyst=...)` (Task 3).
- Produces: `analyst_subs() -> set[str]` (lit `CORE_ANALYST_SUBS`, même forme que `admin_subs()`). Le chemin OIDC passe `bootstrap_analyst=claims["sub"] in analyst_subs()`. Le chemin mock passe `bootstrap_analyst=True` (le `mockuser` de dev est admin ET analyste, cohérent avec `bootstrap_admin=True` déjà en place).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_auth.py`:

```python
def test_analyst_subs_parses_env(monkeypatch):
    from app.auth.dependency import analyst_subs
    monkeypatch.setenv("CORE_ANALYST_SUBS", " a , b ,, c ")
    assert analyst_subs() == {"a", "b", "c"}


def test_analyst_subs_empty_when_unset(monkeypatch):
    from app.auth.dependency import analyst_subs
    monkeypatch.delenv("CORE_ANALYST_SUBS", raising=False)
    assert analyst_subs() == set()
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_auth.py -k analyst_subs -v`
Expected: FAIL (`analyst_subs` non défini).

- [ ] **Step 3: Implémenter `analyst_subs` et câbler le bootstrap**

Dans `core/app/auth/dependency.py`, ajouter après `admin_subs()`:

```python
def analyst_subs() -> set[str]:
    """OIDC subs à promouvoir analyste au prochain get_or_create_user
    (source de vérité de CORE_ANALYST_SUBS) — miroir de admin_subs()."""
    raw = os.environ.get("CORE_ANALYST_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}
```

Dans le chemin **mock** de `get_current_user`, ajouter `bootstrap_analyst=True` à l'appel `get_or_create_user(...)` (à côté de `bootstrap_admin=True`).

Dans le chemin **OIDC** (le `return get_or_create_user(...)` final), ajouter :

```python
        bootstrap_analyst=claims["sub"] in analyst_subs(),
```

- [ ] **Step 4: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_auth.py -v`
Expected: PASS (dont les 2 nouveaux ; aucun test existant régressé).

- [ ] **Step 5: Commit**

```bash
git add core/app/auth/dependency.py core/tests/test_auth.py
git commit -m "feat(core): SP-11c — analyst_subs() + bootstrap analyste (OIDC + mock)"
```

---

## Task 5: `GET /me` + `PATCH /users` exposent `isAnalyst`

**Files:**
- Modify: `core/app/auth/routes.py`
- Test: `core/tests/test_me.py` (ajout), `core/tests/test_auth.py` (ajout PATCH)

**Interfaces:**
- Consumes: `set_analyst` (Task 3), `User.is_analyst`.
- Produces: `MeResponse.isAnalyst: bool` ; `UserAdminPatch` accepte `isAdmin: bool | None = None` **et** `isAnalyst: bool | None = None` (chacun appliqué seulement s'il est fourni) ; `_user_json` inclut `isAnalyst` ; audit `user.grant_analyst` / `user.revoke_analyst`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_me.py` un test qui affirme que `GET /me` renvoie `isAnalyst` (suivre le patron du test `isAdmin` déjà présent dans ce fichier — même montage d'app/override d'utilisateur). Exemple minimal :

```python
def test_me_exposes_is_analyst(analyst_env):
    # analyst_env : même fixture que le test isAdmin, mais l'utilisateur courant
    # a is_analyst=True (le construire via get_or_create_user(..., bootstrap_analyst=True)).
    app, client = analyst_env
    body = client.get("/me").json()
    assert body["isAnalyst"] is True
```

Ajouter à `core/tests/test_auth.py` un test PATCH qui promeut un utilisateur analyste et vérifie que `is_analyst` bascule (suivre le patron des tests `patch_user` existants — un admin PATCH un autre user).

```python
def test_patch_user_grants_analyst(admin_client_env):
    app, client, admin, target = admin_client_env  # patron existant du fichier
    resp = client.patch(f"/users/{target.id}", json={"isAnalyst": True})
    assert resp.status_code == 200
    assert resp.json()["isAnalyst"] is True
```

> Si les fixtures nommées ci-dessus n'existent pas telles quelles, réutiliser le montage exact des tests `isAdmin` voisins du même fichier (ne pas inventer une nouvelle infrastructure).

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_me.py tests/test_auth.py -k "analyst" -v`
Expected: FAIL (`isAnalyst` absent de la réponse / du corps accepté).

- [ ] **Step 3: Implémenter**

Dans `core/app/auth/routes.py`:

1. Import : `from app.users.repository import count_admins, list_users, set_admin, set_analyst`.
2. `MeResponse` : ajouter `isAnalyst: bool`. Dans `get_me`, ajouter `isAnalyst=user.is_analyst` au constructeur.
3. `UserAdminPatch` : remplacer par

```python
class UserAdminPatch(BaseModel):
    isAdmin: bool | None = None
    isAnalyst: bool | None = None
```

4. `_user_json` : ajouter `"isAnalyst": user.is_analyst`.
5. Dans `patch_user`, remplacer le corps après le `if target is None: ...` par une application conditionnelle :

```python
    if body.isAdmin is not None:
        if (
            not body.isAdmin
            and target.is_admin
            and count_admins(session, tenant_id=user.tenant_id) == 1
        ):
            raise HTTPException(status_code=409, detail="cannot demote the last admin")
        set_admin(session, tenant_id=user.tenant_id, user_id=user_id, is_admin=body.isAdmin)
        write_audit(
            session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
            action="user.promote" if body.isAdmin else "user.demote",
            object_type="user", object_id=user_id, payload={"isAdmin": body.isAdmin},
        )
    if body.isAnalyst is not None:
        set_analyst(session, tenant_id=user.tenant_id, user_id=user_id, is_analyst=body.isAnalyst)
        write_audit(
            session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
            action="user.grant_analyst" if body.isAnalyst else "user.revoke_analyst",
            object_type="user", object_id=user_id, payload={"isAnalyst": body.isAnalyst},
        )
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    return _user_json(target)
```

- [ ] **Step 4: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_me.py tests/test_auth.py -v`
Expected: PASS (les nouveaux + tous les existants — l'ancien PATCH `{isAdmin: ...}` reste valide car `isAdmin` est maintenant optionnel mais fourni par ces tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/auth/routes.py core/tests/test_me.py core/tests/test_auth.py
git commit -m "feat(core): SP-11c — GET /me + PATCH /users exposent isAnalyst"
```

---

## Task 6: Shell — type `Me.isAnalyst` + régénération OpenAPI

Sans quoi le job CI `api-types-drift` casse (le schéma OpenAPI a changé) et `tsc` diverge du contrat.

**Files:**
- Modify: `shell/src/api/types.ts`, `shell/src/api/itemClient.ts`, `shell/src/api/generated/core-schema.d.ts`, `core/openapi.json`
- Test: `shell/src/api/itemClient.test.ts` (mise à jour)

**Interfaces:**
- Consumes: `MeResponse.isAnalyst` (Task 5).
- Produces: `Me.isAnalyst: boolean` côté shell, mappé par `getMe`.

- [ ] **Step 1: Régénérer le schéma OpenAPI du cœur**

Run (commandes exactes du job `api-types-drift` de `.github/workflows/ci.yml`) :
```bash
cd core && uv run python scripts/export_openapi.py openapi.json
```

Puis régénérer le type TS :
```bash
cd shell && npm run gen:api-types
git diff -- shell/src/api/generated/core-schema.d.ts   # doit montrer l'ajout de isAnalyst
```
Vérifier que `shell/src/api/generated/core-schema.d.ts` contient maintenant `isAnalyst: boolean;` aux deux emplacements `MeResponse` (à côté de `isAdmin`).

- [ ] **Step 2: Mettre à jour le test `getMe`**

Dans `shell/src/api/itemClient.test.ts`, le test `getMe` qui affirme `toEqual({ username, firstName, lastName, isAdmin })` doit inclure `isAnalyst`. Mettre à jour l'assertion et le mock JSON :

```typescript
// mock : ajouter isAnalyst au corps JSON renvoyé
HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false, isAnalyst: false }),
// assertion :
expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false, isAnalyst: false });
```

- [ ] **Step 3: Lancer, vérifier l'échec**

Run: `cd shell && npm run test -- itemClient`
Expected: FAIL (`me` ne contient pas `isAnalyst`).

- [ ] **Step 4: Implémenter côté shell**

1. `shell/src/api/types.ts` : ajouter `isAnalyst: boolean;` à l'interface `Me` (ligne ~29, après `isAdmin`).
2. `shell/src/api/itemClient.ts` `getMe` (~ligne 194) : étendre le type inline et le mapping :

```typescript
      const data = await request<{ username: string; firstName: string; lastName: string; isAdmin: boolean; isAnalyst: boolean }>(
        // ...url inchangée...
      );
      return { username: data.username, firstName: data.firstName, lastName: data.lastName, isAdmin: data.isAdmin, isAnalyst: data.isAnalyst };
```

- [ ] **Step 5: Lancer les tests + tsc**

Run: `cd shell && npm run test -- itemClient && npm run build`
Expected: PASS + build/tsc clean. Si d'autres tests shell construisent un `Me` littéral typé et cassent, y ajouter `isAnalyst: false` (runtime `HttpResponse.json` non typé : pas besoin, sauf assertion d'égalité stricte).

- [ ] **Step 6: Commit**

```bash
git add core/openapi.json shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/generated/core-schema.d.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): SP-11c — Me.isAnalyst + régénération schéma OpenAPI"
```

---

## Task 7: `sql_sandbox` — validation SELECT-only + extraction des références

**Files:**
- Create: `core/app/analytics/sql_sandbox.py`
- Test: `core/tests/test_analytics_sql_sandbox.py`

**Interfaces:**
- Consumes: findings AST du spike (Task 1) — types de nœuds exacts ; `duckdb`.
- Produces: `SqlSandboxError(Exception)` ; `ROW_CAP`/`STATEMENT_TIMEOUT_S`/`MEMORY_LIMIT`/`THREADS` ; `parse_ast(conn, sql) -> dict` ; `validate_select_only(ast) -> None` (lève `SqlSandboxError` sinon) ; `collect_table_refs(ast) -> set[str]`.

> **Note d'implémentation :** remplacer `SELECT_NODE`/`SET_OPERATION_NODE`/`BASE_TABLE`/`table_name` ci-dessous par les chaînes exactes confirmées par le spike (Task 1). Rappel : ces fonctions ne sont PAS la frontière de sécurité (c'est le verrouillage de Task 8) — une extraction imparfaite dégrade au pire en « table introuvable » à l'exécution, jamais en fuite.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import (
    SqlSandboxError, collect_table_refs, parse_ast, validate_select_only,
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_select_only_accepts_select(conn):
    validate_select_only(parse_ast(conn, "SELECT 1"))  # ne lève pas


def test_select_only_rejects_non_select(conn):
    for sql in ["CREATE TABLE x(i int)", "COPY (SELECT 1) TO 'x'", "ATTACH 'y.db'", "PRAGMA version"]:
        with pytest.raises(SqlSandboxError):
            validate_select_only(parse_ast(conn, sql))


def test_select_only_rejects_multiple_statements(conn):
    with pytest.raises(SqlSandboxError):
        validate_select_only(parse_ast(conn, "SELECT 1; SELECT 2"))


def test_parse_ast_rejects_syntax_error(conn):
    with pytest.raises(SqlSandboxError):
        parse_ast(conn, "SELECT FROM WHERE")


def test_collect_table_refs_finds_base_tables(conn):
    refs = collect_table_refs(parse_ast(conn, "SELECT * FROM villes v JOIN routes r ON r.id = v.id"))
    assert {"villes", "routes"} <= refs
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter la validation + l'extraction**

```python
# SPDX-License-Identifier: Apache-2.0
"""Moteur d'isolation du SQL analyste (SP-11c). La frontière de sécurité est
DuckDB (SET enable_external_access=false + lock_configuration=true, cf.
run_analyst_sql), PAS ces fonctions d'AST : parse_ast/validate_select_only/
collect_table_refs servent seulement à rejeter tôt le non-SELECT et à décider
quelles vues matérialiser. Chaînes de nœuds AST confirmées par le spike
scripts/spike_duckdb_sql_sandbox.py (Task 1)."""
import json
import threading

import duckdb

ROW_CAP = 10_000
STATEMENT_TIMEOUT_S = 10.0
MEMORY_LIMIT = "512MB"
THREADS = 2

# Types de nœuds json_serialize_sql (confirmés par le spike Task 1) :
_SELECT_NODE_TYPES = {"SELECT_NODE", "SET_OPERATION_NODE"}
_BASE_TABLE_TYPE = "BASE_TABLE"


class SqlSandboxError(Exception):
    """Erreur SQL analyste destinée à un 400."""


def parse_ast(conn: duckdb.DuckDBPyConnection, sql: str) -> dict:
    try:
        raw = conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
    except duckdb.Exception as exc:
        raise SqlSandboxError(f"invalid SQL: {exc}") from exc
    doc = json.loads(raw)
    if doc.get("error"):
        raise SqlSandboxError(doc.get("error_message") or "invalid SQL")
    return doc


def validate_select_only(ast: dict) -> None:
    statements = ast.get("statements", [])
    if len(statements) != 1:
        raise SqlSandboxError("exactly one SELECT statement is required")
    node = statements[0].get("node", {})
    if node.get("type") not in _SELECT_NODE_TYPES:
        raise SqlSandboxError("only read-only SELECT queries are allowed")


def collect_table_refs(ast: dict) -> set[str]:
    found: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("type") == _BASE_TABLE_TYPE and isinstance(obj.get("table_name"), str):
                found.add(obj["table_name"])
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(ast)
    return found
```

- [ ] **Step 4: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/sql_sandbox.py core/tests/test_analytics_sql_sandbox.py
git commit -m "feat(core): SP-11c — sql_sandbox : validation SELECT-only + extraction des références (AST natif DuckDB)"
```

---

## Task 8: `sql_sandbox` — matérialisation scopée, verrouillage, exécution bornée

**Files:**
- Modify: `core/app/analytics/sql_sandbox.py`
- Test: `core/tests/test_analytics_sql_sandbox.py` (ajouts, fixtures Parquet locales)

**Interfaces:**
- Consumes: `app/analytics/aggregate.py::_dedup_cte`, `::_qi`, `::_has_any_file` ; les constantes/fonctions de Task 7.
- Produces: `run_analyst_sql(conn, *, sql, allowed, base_uri, tenant_id) -> tuple[list[str], list[list], bool]` où `allowed: dict[str, TableInfo]` (collections lisibles → leur `table_info`) et le retour est `(columns, rows, truncated)`. Matérialise seulement les vues référencées ∩ autorisées ; verrouille ; exécute sous timeout + plafond de lignes ; coerce les cellules non-JSON (bytes→hex, datetime→isoformat, Decimal→float).

- [ ] **Step 1: Écrire les tests qui échouent**

Réutiliser le patron de `test_features_aggregate_routes.py` pour écrire des GeoParquet CDC locaux (`gpd.GeoDataFrame(...).to_parquet(...)`), et une connexion DuckDB locale (`duckdb.connect(":memory:")` + `INSTALL spatial; LOAD spatial;`). `base_uri = str(tmp_path)`.

```python
import geopandas as gpd
from shapely.geometry import Point

from app.analytics.sql_sandbox import run_analyst_sql
from app.collections.introspection import ColumnInfo, TableInfo

INFO = TableInfo(table_name="villes", pk_column="id", geometry_column="geometry",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="region", type="string", required=True),
                          ColumnInfo(name="pop", type="integer", required=True)])


def _write(base_dir, rows, *, tenant_id="default", collection_id="villes"):
    part = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    part.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(part / "part-1.parquet")


def _spatial_conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def test_run_reduces_to_current_state(tmp_path):
    _write(tmp_path, [
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)},
        {"id": 1, "region": "Nord", "pop": 99, "_op": "insert", "_lsn": 2, "_ts": 2.0, "geometry": Point(0, 0)},  # version + récente
        {"id": 2, "region": "Sud", "pop": 5, "_op": "delete", "_lsn": 3, "_ts": 3.0, "geometry": Point(1, 1)},  # tombstone
    ])
    conn = _spatial_conn()
    try:
        cols, rows, trunc = run_analyst_sql(
            conn, sql='SELECT region, sum(pop) AS total FROM villes GROUP BY region',
            allowed={"villes": INFO}, base_uri=str(tmp_path), tenant_id="default")
    finally:
        conn.close()
    assert trunc is False
    assert cols == ["region", "total"]
    assert rows == [["Nord", 99]]  # version max(_lsn) gagne, tombstone exclue


def test_isolation_blocks_arbitrary_read_parquet(tmp_path):
    _write(tmp_path, [{"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}])
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):
            run_analyst_sql(conn, sql=f"SELECT * FROM read_parquet('{tmp_path}/**/*.parquet')",
                            allowed={"villes": INFO}, base_uri=str(tmp_path), tenant_id="default")
    finally:
        conn.close()


def test_unauthorized_view_is_not_materialized(tmp_path):
    _write(tmp_path, [{"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}], collection_id="secret")
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):  # "secret" absent de allowed → table introuvable
            run_analyst_sql(conn, sql="SELECT * FROM secret",
                            allowed={"villes": INFO}, base_uri=str(tmp_path), tenant_id="default")
    finally:
        conn.close()


def test_row_cap_truncates(tmp_path):
    _write(tmp_path, [{"id": i, "region": "N", "pop": i, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)} for i in range(1, 12)])
    conn = _spatial_conn()
    try:
        # Forcer un plafond bas via monkeypatch de ROW_CAP serait fragile ; à la place,
        # vérifier la sémantique de troncature avec un cap réduit passé par la constante.
        import app.analytics.sql_sandbox as sandbox
        old = sandbox.ROW_CAP
        sandbox.ROW_CAP = 5
        try:
            cols, rows, trunc = run_analyst_sql(conn, sql="SELECT id FROM villes ORDER BY id",
                                                allowed={"villes": INFO}, base_uri=str(tmp_path), tenant_id="default")
        finally:
            sandbox.ROW_CAP = old
    finally:
        conn.close()
    assert trunc is True
    assert len(rows) == 5


def test_geometry_cell_is_json_safe(tmp_path):
    _write(tmp_path, [{"id": 1, "region": "N", "pop": 1, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(3, 4)}])
    conn = _spatial_conn()
    try:
        cols, rows, _ = run_analyst_sql(conn, sql="SELECT ST_AsText(geometry) AS g FROM villes",
                                        allowed={"villes": INFO}, base_uri=str(tmp_path), tenant_id="default")
    finally:
        conn.close()
    assert rows == [["POINT (3 4)"]]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v`
Expected: FAIL (`run_analyst_sql` non défini).

- [ ] **Step 3: Implémenter**

Ajouter à `core/app/analytics/sql_sandbox.py` (imports en tête : `from datetime import date, datetime` ; `from decimal import Decimal` ; `from app.analytics.aggregate import _dedup_cte, _has_any_file, _qi`) :

```python
def _apply_limits(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    conn.execute(f"SET threads = {THREADS}")


def _materialize(conn, *, name, table_info, base_uri, tenant_id) -> None:
    if not _has_any_file(conn, base_uri, tenant_id, name):
        raise SqlSandboxError(f"collection '{name}' has no data yet")
    cte = _dedup_cte(table_info, base_uri, tenant_id, name)
    conn.execute(f"CREATE TEMP TABLE {_qi(name)} AS {cte} SELECT * FROM live")


def _lock_down(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")


def _coerce(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _execute_bounded(conn, sql):
    timer = threading.Timer(STATEMENT_TIMEOUT_S, conn.interrupt)
    timer.start()
    try:
        cur = conn.execute(sql)
        fetched = cur.fetchmany(ROW_CAP + 1)
        columns = [d[0] for d in cur.description]
    except duckdb.InterruptException as exc:
        raise SqlSandboxError("query exceeded the time limit") from exc
    except duckdb.Exception as exc:
        raise SqlSandboxError(str(exc)) from exc
    finally:
        timer.cancel()
    truncated = len(fetched) > ROW_CAP
    rows = [[_coerce(v) for v in row] for row in fetched[:ROW_CAP]]
    return columns, rows, truncated


def run_analyst_sql(conn, *, sql, allowed, base_uri, tenant_id):
    """Exécute le SQL de l'analyste confiné aux vues autorisées. `allowed` :
    {collection_id: TableInfo}. Retourne (columns, rows, truncated). L'ordre est
    critique : matérialiser (accès externe encore ouvert) PUIS verrouiller PUIS
    exécuter — jamais l'inverse."""
    ast = parse_ast(conn, sql)
    validate_select_only(ast)
    refs = collect_table_refs(ast)
    _apply_limits(conn)
    for name in sorted(refs & set(allowed)):
        _materialize(conn, name=name, table_info=allowed[name], base_uri=base_uri, tenant_id=tenant_id)
    _lock_down(conn)
    return _execute_bounded(conn, sql)
```

> Si le spike (Task 1) a montré que `duckdb.InterruptException` porte un autre nom, ajuster l'`except`. `_execute_bounded` attrape de toute façon `duckdb.Exception` (superclasse) en dernier recours.

- [ ] **Step 4: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v`
Expected: PASS (10 tests au total). Le test d'isolation prouve que `read_parquet` arbitraire lève **après verrouillage** — c'est la frontière DuckDB.

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/sql_sandbox.py core/tests/test_analytics_sql_sandbox.py
git commit -m "feat(core): SP-11c — sql_sandbox : matérialisation scopée + verrouillage DuckDB + exécution bornée"
```

---

## Task 9: Endpoint `POST /analytics/sql` + exemption read-only + audit + métrique

**Files:**
- Modify: `core/app/features/routes.py`, `core/app/main.py`
- Test: `core/tests/test_analytics_sql_routes.py`, `core/tests/test_read_only_mode.py` (ajout)

**Interfaces:**
- Consumes: `run_analyst_sql`/`SqlSandboxError` (Task 8) ; `get_duckdb_connection_factory`/`get_analytics_base_uri`/`get_introspector` (existants) ; `list_visible_collections` ; `write_audit` ; `User.is_analyst`.
- Produces: route `POST /analytics/sql` → `{columns, rows, truncated}` (403 non-analyste, 400 erreur SQL) ; compteur `geostudio.analytics.sql_queries` ; exemption du middleware read-only pour ce chemin.

- [ ] **Step 1: Écrire les tests qui échouent**

`core/tests/test_analytics_sql_routes.py` — réutiliser **verbatim** la fixture `env` / les helpers `_as` / `_register` / `_write_partition` de `test_features_aggregate_routes.py` (copier-coller le montage : engine SQLite, override introspector, fake duckdb factory `spatial`-only, base_uri = `tmp_path`), en promouvant en plus un utilisateur analyste.

```python
def test_non_analyst_gets_403(env):
    app, client, _admin, regular, _tmp, _tid = env
    _as(app, regular)  # regular : ni admin ni analyste
    resp = client.post("/analytics/sql", json={"sql": "SELECT 1"})
    assert resp.status_code == 403


def test_admin_without_analyst_gets_403(env):
    app, client, admin, _r, _tmp, _tid = env
    _as(app, admin)  # admin mais is_analyst=False
    resp = client.post("/analytics/sql", json={"sql": "SELECT 1"})
    assert resp.status_code == 403


def test_analyst_queries_readable_view(env_with_analyst):
    app, client, analyst, tmp_path, tenant_id, col = env_with_analyst  # analyste + collection villes enregistrée+peuplée
    _as(app, analyst)
    resp = client.post("/analytics/sql",
                       json={"sql": f'SELECT region, sum(pop) AS total FROM {col["id"]} GROUP BY region ORDER BY region'})
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["region", "total"]
    assert body["truncated"] is False
    assert body["rows"] == [["Nord", 10], ["Sud", 5]]


def test_analyst_cannot_reach_unauthorized_collection(env_with_analyst_and_private):
    # Une collection privée non partagée à l'analyste n'est pas dans list_visible_collections
    # → non matérialisée → "table introuvable" → 400 (jamais de fuite).
    app, client, analyst, private_col = env_with_analyst_and_private
    _as(app, analyst)
    resp = client.post("/analytics/sql", json={"sql": f'SELECT * FROM {private_col["id"]}'})
    assert resp.status_code == 400


def test_invalid_sql_returns_400(env_with_analyst):
    app, client, analyst, *_ = env_with_analyst
    _as(app, analyst)
    resp = client.post("/analytics/sql", json={"sql": "DROP TABLE villes"})
    assert resp.status_code == 400
```

> Construire l'utilisateur analyste dans la fixture via `get_or_create_user(..., bootstrap_analyst=True)` (ni admin) ; peupler la collection via `_write_partition` (patron déjà présent dans le fichier voisin).

Ajouter à `core/tests/test_read_only_mode.py` :

```python
def test_analytics_sql_is_exempt_from_read_only(monkeypatch):
    # En mode démo lecture seule, POST /analytics/sql ne doit PAS être 403-é par le middleware
    # (c'est une lecture). Suivre le patron du test d'exemption /aggregate déjà présent
    # dans ce fichier : monkeypatch CORE_READ_ONLY_MODE=true, poster, vérifier que le statut
    # n'est pas le 403 « Mode démo » du middleware (403 analyste OK, mais pas ce message).
    ...
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_analytics_sql_routes.py tests/test_read_only_mode.py -v`
Expected: FAIL (route absente → 404 ; exemption absente → 403 middleware).

- [ ] **Step 3: Implémenter la route**

Dans `core/app/features/routes.py` :

Imports (en tête) :
```python
from opentelemetry import metrics
from pydantic import BaseModel

from app.analytics.sql_sandbox import SqlSandboxError, run_analyst_sql
from app.collections.introspection import TableNotFound
from app.collections.repository import list_visible_collections
```

Compteur (près des autres constantes du module) :
```python
_meter = metrics.get_meter(__name__)
_sql_queries_counter = _meter.create_counter(
    "geostudio.analytics.sql_queries", unit="1",
    description="Analyst read-only SQL queries executed via POST /analytics/sql",
)


class SqlQueryBody(BaseModel):
    sql: str
```

Route (à côté de `aggregate_features`) :
```python
@router.post("/analytics/sql")
def analytics_sql(
    body: SqlQueryBody,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
):
    if not user.is_analyst:
        raise HTTPException(status_code=403, detail="analyst role required")
    cols = list_visible_collections(
        session, tenant_id=user.tenant_id, user_id=user.id, is_admin=user.is_admin,
    )
    allowed: dict = {}
    for col in cols:
        try:
            allowed[col.id] = introspect(session, col.table_name)
        except TableNotFound:
            continue
    conn = conn_factory()
    try:
        columns, rows, truncated = run_analyst_sql(
            conn, sql=body.sql, allowed=allowed, base_uri=base_uri, tenant_id=user.tenant_id,
        )
    except SqlSandboxError as exc:
        raise _validation_error([{"field": "sql", "code": "sql_error", "message": str(exc)}])
    finally:
        conn.close()
    _sql_queries_counter.add(1)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="analytics.sql", object_type="analytics", object_id="sql",
        payload={"sql": body.sql[:500]},
    )
    return {"columns": columns, "rows": rows, "truncated": truncated}
```

> `get_current_user` (non-optional) : un analyste est toujours authentifié. `_validation_error` et `write_audit` sont déjà importés/définis dans ce fichier (utilisés par les routes existantes) ; sinon les importer comme `aggregate_features`/les routes voisines le font.

- [ ] **Step 4: Implémenter l'exemption read-only**

Dans `core/app/main.py`, la garde `read_only_guard` : ajouter `/analytics/sql` aux chemins exemptés. Remplacer la condition d'exemption pour inclure le nouveau chemin :

```python
            and request.url.path != "/mcp"
            and request.url.path != "/analytics/sql"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
```

- [ ] **Step 5: Lancer, vérifier PASS**

Run: `cd core && uv run pytest tests/test_analytics_sql_routes.py tests/test_read_only_mode.py -v`
Expected: PASS.

- [ ] **Step 6: Vérifier les frontières d'import + suite complète**

Run: `cd core && uv run lint-imports && uv run pytest`
Expected: `lint-imports` clean (la route vit dans `app.features`, couche déjà autorisée à importer `app.collections`/`app.analytics` ; aucun nouvel import depuis le paquet `app.analytics` vers une couche supérieure). Suite complète verte (tests `postgis` skippés sans DB).

- [ ] **Step 7: Commit**

```bash
git add core/app/features/routes.py core/app/main.py core/tests/test_analytics_sql_routes.py core/tests/test_read_only_mode.py
git commit -m "feat(core): SP-11c — endpoint POST /analytics/sql (403 non-analyste, audit, compteur, exempté du mode démo)"
```

---

## Task 10: Perf empirique, doc, validation finale (clôt SP-11)

**Files:**
- Create: `core/scripts/measure_sql_sandbox.py`
- Modify: `README.md` (section variables d'environnement / rôles)
- Test: exécution réelle contre PostGIS+MinIO + suites complètes

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: preuve empirique (~1 M lignes réparties sur plusieurs fichiers) qu'une requête analyste retourne sous les limites ; documentation de `CORE_ANALYST_SUBS` et du rôle analyste.

- [ ] **Step 1: Script de mesure empirique**

`core/scripts/measure_sql_sandbox.py` — même esprit que `core/scripts/measure_cdc_consumer_throughput.py` / le script perf de SP-11b : générer ~1 M lignes CDC réparties sur plusieurs fichiers Parquet réalistes (un gros backfill + des petits flushes incrémentaux, avec quelques updates/tombstones pour exercer la réduction `max(_lsn)`), écrites sur un MinIO réel sous `tenant_id=default/collection_id=villes/`, puis ouvrir une connexion via `open_connection`, appeler `run_analyst_sql` avec `allowed={"villes": <TableInfo>}` sur une requête d'agrégation (`SELECT region, count(*), avg(pop) FROM villes GROUP BY region`) et imprimer le temps mural. Affirmer `< STATEMENT_TIMEOUT_S` et documenter la valeur observée dans la sortie.

- [ ] **Step 2: Lancer la mesure contre MinIO réel**

Run:
```bash
cd core && S3_ENDPOINT_URL=http://localhost:9000 S3_ACCESS_KEY=minioadmin \
  S3_SECRET_KEY=minioadmin S3_CDC_BUCKET=geostudio-cdc \
  uv run python scripts/measure_sql_sandbox.py
```
Expected: la requête retourne bien en deçà du timeout (documenter la valeur mesurée dans le rapport de tâche, comme SP-11b a documenté ~0,28 s / ~0,13 s).

- [ ] **Step 3: Documenter le rôle analyste dans le README**

Ajouter, dans la section variables d'environnement / rôles du `README.md`, une entrée `CORE_ANALYST_SUBS` (liste de subs OIDC promus analystes au login, miroir de `CORE_ADMIN_SUBS`) et une phrase expliquant que l'analyste peut exécuter du SQL read-only via `POST /analytics/sql` sur les collections qu'il a le droit de lire, et qu'**un admin n'est pas analyste par défaut** (peupler `CORE_ANALYST_SUBS` ou `PATCH /users {isAnalyst:true}` pour l'accorder).

- [ ] **Step 4: Validation finale — suites complètes**

Run:
```bash
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm run test && npm run build
```
Expected: cœur vert (tests `postgis` skippés sans DB ; les lancer réellement contre un PostGIS+pgvector+MinIO jetable au moins une fois — patron des sous-parties précédentes), `lint-imports` clean, shell vert, build/tsc clean. Les 37 specs E2E ne sont pas affectées (aucune UI ajoutée) ; les relancer (`npm run e2e`) pour confirmer l'absence de régression sur le changement de forme de `GET /me`.

- [ ] **Step 5: Commit**

```bash
git add core/scripts/measure_sql_sandbox.py README.md
git commit -m "docs(core): SP-11c — perf empirique SQL analyste + doc CORE_ANALYST_SUBS (clôt SP-11)"
```

---

## Self-Review

**Spec coverage :**
- Rôle analyste (`is_analyst`, `CORE_ANALYST_SUBS`, `PATCH /users`, `GET /me`, admin ≠ analyste) → Tasks 2–6. ✓
- Endpoint `POST /analytics/sql`, 403 non-analyste, exemption démo → Task 9. ✓
- Isolation par vues scopées + verrouillage DuckDB, spike d'ouverture → Tasks 1, 7, 8. ✓
- Vues = collections `can(read)`, réduction état-courant (réutilise SP-11b) → Tasks 8, 9. ✓
- Quotas (timeout, plafond de lignes, mémoire) → Task 8. ✓
- REST-only (pas de MCP) → aucune tâche MCP, conforme. ✓
- Audit + compteur OTel `geostudio.analytics.sql_queries` → Task 9. ✓
- Tests spike / cœur postgis / empirique / non-régression E2E → Tasks 1, 8, 9, 10. ✓
- Clôture de SP-11 → Task 10. ✓

**Placeholder scan :** les seuls points « à confirmer » (types de nœuds AST, nom d'exception d'interruption, fixtures de test nommées) sont explicitement délégués au spike Task 1 et aux fixtures verbatim du fichier voisin — chacun avec la valeur par défaut concrète fournie et la consigne de non-régression. Aucun TODO/TBD sans contenu.

**Type consistency :** `run_analyst_sql(conn, *, sql, allowed, base_uri, tenant_id) -> (columns, rows, truncated)` identique entre Task 8 (définition) et Task 9 (appel) ; `allowed: dict[str, TableInfo]` construit en Task 9 correspond au type attendu par `_materialize`/`_dedup_cte` ; `SqlSandboxError` levée en Tasks 7/8 et attrapée en Task 9 ; `set_analyst`/`bootstrap_analyst` cohérents entre Tasks 3, 4, 5 ; `MeResponse.isAnalyst`/`Me.isAnalyst` cohérents entre Tasks 5 et 6 ; constantes `ROW_CAP`/`STATEMENT_TIMEOUT_S`/`MEMORY_LIMIT`/`THREADS` définies une fois (Task 7) et utilisées (Task 8).
