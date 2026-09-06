# GAP-22 — Sécurité au niveau colonne (masquage de champ sensible) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un nouveau privilège global `data.view_sensitive` protège les
colonnes marquées sensibles sur une `Collection` — masquées à la fois côté
Postgres (rôle `gis_rls_masked`, GRANT/REVOKE par colonne) pour toute lecture
RLS classique, et côté DuckDB (colonnes exclues de la matérialisation) pour
les agrégats structurés et **SQL Lab**, le chemin le plus difficile à
protéger puisqu'il exécute du SQL arbitraire sans jamais passer par Postgres.

**Architecture:** Deux mécanismes de masquage indépendants pour deux familles
de chemins de lecture (spec §2.3) : (A) un second rôle Postgres non-
propriétaire `gis_rls_masked`, choisi par `rls_scope(..., masked=bool)` à la
place de `gis_rls`, jamais granté au niveau table (colonne par colonne
seulement) ; (B)/(C) les fonctions DuckDB de `app/analytics/aggregate.py` et
`app/analytics/sql_sandbox.py` reçoivent un ensemble `masked_fields`/
`masked_fields_by_collection` déjà résolu par l'appelant (ces modules restent
agnostiques du privilège, contrat de couches) et l'utilisent pour exclure les
colonnes sensibles de la validation (agrégats) ou de la matérialisation DuckDB
(SQL Lab).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Postgres/PostGIS,
DuckDB, Pydantic v2, MCP (FastMCP), React/TS (shell), Vitest, pytest
(`@pytest.mark.postgis` contre un vrai conteneur `postgis-test`).

## Global Constraints

- **Spec de référence** : `docs/superpowers/specs/2026-09-06-gap22-securite-colonne-design.md`
  — toute divergence entre cette spec et le code réel constatée en exécutant
  une tâche doit être documentée dans le ledger de la tâche, jamais corrigée
  silencieusement (CLAUDE.md piège n°3).
- **Numéro de migration** : cette spec suppose `0041`, tête constatée `0040`
  au moment de son écriture — **revérifier** `ls core/alembic/versions | sort
  | tail` avant d'écrire le nom de fichier de la Tâche 2 ; ajuster si une
  autre session a poussé une migration entre-temps.
- **`gis_rls_masked` ne reçoit JAMAIS de `GRANT SELECT` au niveau table** —
  uniquement `GRANT SELECT (col1, col2, ...)` par colonne (spec §1.2). Ce
  point conditionne toute la Tâche 3 ; le test de la Tâche 4 doit le
  falsifier avant tout câblage ultérieur.
- **`app.analytics` reste agnostique du privilège** (contrat de couches,
  `pyproject.toml`) : `aggregate.py`/`sql_sandbox.py` ne doivent jamais
  importer `app.roles` ni `Privilege` — ils reçoivent des `frozenset[str]`
  déjà résolus par l'appelant.
- **Aucune granularité par collection/rôle, aucun masquage partiel de
  valeur, aucune UI de simulation** — hors périmètre explicite (spec §4).
  Ne pas les ajouter « pendant qu'on y est ».
- **Toute migration testée upgrade/downgrade/upgrade sur base non vide**
  (CLAUDE.md piège n°8) — au moins une collection déjà enregistrée avec des
  lignes réelles pour la Tâche 2.
- Docs et messages utilisateur en français, code/identifiants en anglais
  (convention du dépôt).
- Commits conventionnels (`feat(core): ...`, `test(core): ...`), un sujet
  par commit, après chaque tâche.
- `PYTHONPATH=.` requis pour toute commande `scripts/*` du cœur ; suite
  `pytest` normale n'en a pas besoin.

---

## Fichiers touchés (vue d'ensemble)

| Fichier | Nature du changement |
|---|---|
| `core/app/roles/privileges.py` | + `Privilege.DATA_VIEW_SENSITIVE`, métadonnée |
| `core/alembic/versions/0041_sensitive_fields.py` | nouvelle migration (colonne + rôle + backfill) |
| `core/app/collections/models.py` | + `Collection.sensitive_fields` |
| `core/app/collections/ddl.py` | + `_all_real_columns`, `sync_masked_role_grants` ; `apply_collection_ddl` les appelle |
| `core/app/collections/schemas.py` | + `CollectionPatch.sensitiveFields` + validateur |
| `core/app/collections/routes.py` | + `_reject_invalid_sensitive_fields`, câblage dans `patch_collection`, `_collection_json` |
| `core/app/features/rls.py` | `rls_scope(..., masked: bool = False)` |
| `core/app/features/routes.py` | `null_rls_scope` compat, `get_masked_for_user`, câblage sur 3 routes de lecture + 2 routes d'agrégat + SQL Lab |
| `core/app/features/tiles.py` | câblage `get_masked_for_user` sur `get_collection_tile` |
| `core/app/mcp/tools/catalog.py` | câblage masqué sur `query_features` |
| `core/app/mcp/tools/analytics.py` | câblage masqué sur `run_analytics_query` |
| `core/app/analytics/aggregate.py` | `_valid_column_names`/`_validate_fields`/`run_collection_aggregate` gagnent `masked_fields` |
| `core/app/analytics/sql_sandbox.py` | `_materialize`/`run_analyst_sql` gagnent `masked_fields`/`masked_fields_by_collection` |
| `shell/src/api/types.ts` | + `sensitiveFields` sur `CollectionRead`/`CollectionUpdate` |
| `shell/src/shell/EditCollectionPanel.tsx` | section « Champs sensibles » |
| `shell/src/api/domains/collectionsAdmin.ts` | relaie `sensitiveFields` |
| `shell/src/i18n/catalog.fr.ts`, `shell/src/i18n/rolePrivilegeCatalog.test.ts` | nouvelle clé i18n + miroir |
| `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` | régénérés (Tâche 16) |

Nouveaux fichiers de test : aucun nouveau fichier de test dédié n'est
strictement nécessaire — chaque tâche étend un fichier de test existant déjà
identifié ci-dessous, sauf mention contraire.

---

### Task 1: Nouveau privilège `DATA_VIEW_SENSITIVE`

**Files:**
- Modify: `core/app/roles/privileges.py`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Modify: `shell/src/i18n/rolePrivilegeCatalog.test.ts`
- Test: `core/tests/test_roles_privileges.py` (si absent, créer — vérifier
  d'abord par `ls core/tests/test_roles_*` s'il existe déjà un fichier de
  test du catalogue de privilèges à étendre plutôt que d'en créer un)
- Test: `shell/src/i18n/rolePrivilegeCatalog.test.ts` (existant, étendu)

**Interfaces:**
- Produces: `Privilege.DATA_VIEW_SENSITIVE: str = "data.view_sensitive"`,
  consommé par toutes les tâches suivantes.

- [ ] **Step 1: Vérifier s'il existe déjà un test de catalogue de privilèges côté cœur**

Run: `ls core/tests | grep -i privilege`

S'il existe un fichier qui teste `ALL_PRIVILEGE_VALUES`/
`BUILT_IN_ROLE_PRIVILEGES`, l'étendre au lieu d'en créer un nouveau (Step 2
ci-dessous suppose son existence — adapter le nom de fichier trouvé).

- [ ] **Step 2: Écrire le test qui échoue**

Dans le fichier trouvé (ou `core/tests/test_roles_privileges.py` si aucun
n'existe) :

```python
from app.roles.privileges import ALL_PRIVILEGE_VALUES, BUILT_IN_ROLE_PRIVILEGES, Privilege


def test_data_view_sensitive_exists_and_joins_admin_only():
    assert Privilege.DATA_VIEW_SENSITIVE == "data.view_sensitive"
    assert Privilege.DATA_VIEW_SENSITIVE.value in ALL_PRIVILEGE_VALUES
    assert Privilege.DATA_VIEW_SENSITIVE.value in BUILT_IN_ROLE_PRIVILEGES["admin"]
    for role in ("creator", "analyst", "reader"):
        assert Privilege.DATA_VIEW_SENSITIVE.value not in BUILT_IN_ROLE_PRIVILEGES[role]
```

- [ ] **Step 2b: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_roles_privileges.py -v` (ou le
fichier trouvé à l'étape 1)
Expected: FAIL — `AttributeError: DATA_VIEW_SENSITIVE`

- [ ] **Step 3: Ajouter le privilège**

Dans `core/app/roles/privileges.py`, ajouter à la fin de l'énumération
(après `COMPLIANCE_MANAGE`) :

```python
class Privilege(StrEnum):
    ...
    COMPLIANCE_MANAGE = "compliance.manage"
    DATA_VIEW_SENSITIVE = "data.view_sensitive"
```

Puis dans `PRIVILEGE_METADATA`, après l'entrée `COMPLIANCE_MANAGE` :

```python
    Privilege.DATA_VIEW_SENSITIVE: ("data", "roles.privilege.dataViewSensitive"),
```

`BUILT_IN_ROLE_PRIVILEGES["admin"]` n'a besoin d'aucune modification (il
utilise déjà `[p for p in ALL_PRIVILEGE_VALUES if p != Privilege.COMPLIANCE_MANAGE.value]`,
qui inclut automatiquement la nouvelle valeur). Les 3 autres rôles
(`creator`/`analyst`/`reader`) restent des listes explicites qui n'incluent
pas la nouvelle valeur — rien à changer.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_roles_privileges.py -v`
Expected: PASS

- [ ] **Step 5: Mettre à jour les miroirs shell**

Dans `shell/src/i18n/catalog.fr.ts`, ajouter (chercher la section des
libellés de privilège existants, ex. `roles.privilege.complianceManage`, et
ajouter à côté) :

```ts
"roles.privilege.dataViewSensitive": "Voir les champs sensibles",
```

Dans `shell/src/i18n/rolePrivilegeCatalog.test.ts`, ajouter à
`CORE_PRIVILEGE_LABEL_KEYS` :

```ts
  "roles.privilege.dataViewSensitive",
```

(à la fin du tableau, après `"roles.privilege.complianceManage"`).

- [ ] **Step 6: Run shell test to verify it passes**

Run: `cd shell && npx vitest run src/i18n/rolePrivilegeCatalog.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/app/roles/privileges.py core/tests/test_roles_privileges.py \
  shell/src/i18n/catalog.fr.ts shell/src/i18n/rolePrivilegeCatalog.test.ts
git commit -m "feat(core): add data.view_sensitive privilege (GAP-22)"
```

---

### Task 2: Migration — `Collection.sensitive_fields` + rôle `gis_rls_masked`

**Files:**
- Modify: `core/app/collections/models.py`
- Create: `core/alembic/versions/0041_sensitive_fields.py` (revérifier le
  numéro, cf. Global Constraints)
- Test: `core/tests/test_migration_0041.py` (nouveau, patron à chercher :
  `ls core/tests | grep -i migration` pour un fichier de test de migration
  existant à imiter précisément — sinon écrire directement contre `alembic`
  en pilotant `op`)

**Interfaces:**
- Produces: colonne `collections.sensitive_fields` (JSON, `[]` par défaut),
  rôle Postgres `gis_rls_masked` (NOLOGIN), consommés par la Tâche 3+.

- [ ] **Step 1: Revérifier la tête de migration**

Run: `cd core && ls alembic/versions | sort | tail -5`
Expected: confirme `0040_share_links.py` comme tête (ou ajuster le numéro de
la Tâche si une autre migration a été poussée entre-temps).

- [ ] **Step 2: Ajouter le champ au modèle**

Dans `core/app/collections/models.py`, juste après `attachment_fields`
(avant le commentaire sur les métadonnées ouvertes) :

```python
    # Noms de colonnes réelles marquées sensibles (GAP-22, masquage par
    # colonne) — jamais pk_column/geometry_column/tenant_id, validé côté
    # route (app/collections/routes.py::_reject_invalid_sensitive_fields).
    sensitive_fields: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False, server_default="[]"
    )
```

- [ ] **Step 3: Écrire la migration**

Créer `core/alembic/versions/0041_sensitive_fields.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Collection.sensitive_fields + rôle gis_rls_masked (GAP-22, masquage de
champ par colonne)

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("sensitive_fields", sa.JSON(), nullable=False, server_default="[]"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS "
            "(SELECT FROM pg_roles WHERE rolname = 'gis_rls_masked') "
            "THEN CREATE ROLE gis_rls_masked NOLOGIN; END IF; END $$;"
        )
        op.execute("GRANT gis_rls_masked TO current_user")
        # Backfill : toute collection déjà enregistrée a sensitive_fields=[]
        # par construction (colonne neuve) — le rôle masqué doit donc voir
        # TOUTES ses colonnes réelles dès l'activation, sinon la première
        # requête sous gis_rls_masked contre une collection préexistante
        # échoue en "permission denied for table" (aucune colonne grantée).
        op.execute(
            """
            DO $$
            DECLARE
                col RECORD;
                colname text;
            BEGIN
                FOR col IN SELECT table_name FROM collections LOOP
                    FOR colname IN
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = col.table_name
                    LOOP
                        EXECUTE format(
                            'GRANT SELECT (%I) ON public.%I TO gis_rls_masked',
                            colname, col.table_name
                        );
                    END LOOP;
                END LOOP;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP OWNED BY gis_rls_masked")
        op.execute("DROP ROLE IF EXISTS gis_rls_masked")
    op.drop_column("collections", "sensitive_fields")
```

- [ ] **Step 4: Test upgrade/downgrade/upgrade sur base non vide**

Écrire `core/tests/test_migration_0041.py` (`@pytest.mark.postgis` — cette
migration ne peut être vérifiée que contre un vrai Postgres, le
`CREATE ROLE`/bloc PL/pgSQL n'a pas d'équivalent SQLite) :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

pytestmark = pytest.mark.postgis


def _alembic_config(pg_engine) -> Config:
    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = pg_engine.connect()
    return cfg


def test_0041_upgrade_downgrade_upgrade_on_non_empty_db(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_0041_probe"))
        conn.execute(text("CREATE TABLE t_0041_probe (id serial PRIMARY KEY, v text)"))
        conn.execute(text("INSERT INTO t_0041_probe (v) VALUES ('x')"))

    cfg = _alembic_config(pg_engine)
    command.downgrade(cfg, "0040")  # base part de 0041 déjà appliquée en CI ; repart à 0040
    command.upgrade(cfg, "0041")
    with pg_engine.connect() as conn:
        cols = (
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'collections'"
                )
            )
            .scalars()
            .all()
        )
        assert "sensitive_fields" in cols
        role = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'gis_rls_masked'")
        ).scalar()
        assert role == 1
    command.downgrade(cfg, "0040")
    with pg_engine.connect() as conn:
        cols = (
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'collections'"
                )
            )
            .scalars()
            .all()
        )
        assert "sensitive_fields" not in cols
        role = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'gis_rls_masked'")
        ).scalar()
        assert role is None
    command.upgrade(cfg, "0041")
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_0041_probe"))
```

**Avant d'écrire ce test**, chercher un fichier de test de migration
existant (`grep -rl "command.downgrade\|command.upgrade" core/tests`) et
calquer EXACTEMENT son patron de fixture `pg_engine`/config alembic — le
code ci-dessus est une hypothèse de forme, à corriger contre le patron réel
trouvé (CLAUDE.md piège n°3, ne pas supposer que ce squelette compile tel
quel).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=<...> uv run pytest tests/test_migration_0041.py -v -m postgis`
Expected: PASS

- [ ] **Step 6: Run `test_model_alembic_parity.py`**

Run: `cd core && uv run pytest tests/test_model_alembic_parity.py -v`
Expected: PASS (la nouvelle colonne modèle/Alembic est en phase)

- [ ] **Step 7: Commit**

```bash
git add core/app/collections/models.py core/alembic/versions/0041_sensitive_fields.py \
  core/tests/test_migration_0041.py
git commit -m "feat(core): add collections.sensitive_fields + gis_rls_masked role (GAP-22)"
```

---

### Task 3: `sync_masked_role_grants` (GRANT/REVOKE par colonne) + câblage dans `apply_collection_ddl`

**Files:**
- Modify: `core/app/collections/ddl.py`
- Test: `core/tests/test_collections_ddl.py`

**Interfaces:**
- Consumes: rôle `gis_rls_masked` (Tâche 2).
- Produces: `sync_masked_role_grants(session: Session, table_name: str,
  sensitive_fields: list[str]) -> None`, consommée par la Tâche 9
  (`patch_collection`) et appelée en interne par `apply_collection_ddl`.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_collections_ddl.py`, réutiliser la fixture `pg_table`
existante (crée `t_rls`) :

```python
from app.collections.ddl import sync_masked_role_grants


def test_apply_collection_ddl_grants_all_columns_to_masked_role_by_default(
    pg_table, pg_session_factory
):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text("ALTER TABLE t_rls ADD COLUMN salary integer"))
        sync_masked_role_grants(session, pg_table, [])  # re-sync après ALTER manuel du test
        session.execute(text("INSERT INTO t_rls (titre, tenant_id, salary) VALUES ('a', 'default', 100)"))
        session.commit()
    with pg_session_factory() as session:
        session.execute(text("SELECT set_config('app.tenant_id', 'default', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls_masked"))
        row = session.execute(text("SELECT titre, salary FROM t_rls")).first()
        assert row == ("a", 100)


def test_sync_masked_role_grants_revokes_sensitive_column(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text("ALTER TABLE t_rls ADD COLUMN salary integer"))
        sync_masked_role_grants(session, pg_table, ["salary"])
        session.execute(text("INSERT INTO t_rls (titre, tenant_id, salary) VALUES ('a', 'default', 100)"))
        session.commit()
    with pg_session_factory() as session:
        session.execute(text("SELECT set_config('app.tenant_id', 'default', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls_masked"))
        # titre reste lisible
        assert session.execute(text("SELECT titre FROM t_rls")).scalar() == "a"
        # salary ne l'est plus
        with pytest.raises(Exception):
            session.execute(text("SELECT salary FROM t_rls")).first()
```

(Le test 1 vérifie que `apply_collection_ddl` grante déjà toutes les
colonnes réelles au rôle masqué par défaut, `sensitive_fields=[]`. Le test 2
falsifie le REVOKE réel.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_collections_ddl.py -v -m postgis -k masked`
Expected: FAIL — `AttributeError: sync_masked_role_grants` ou colonne
`salary` non grantée à `gis_rls_masked`.

- [ ] **Step 3: Implémenter `sync_masked_role_grants` et le câbler**

Dans `core/app/collections/ddl.py`, ajouter après `spatial_index_name` :

```python
def _all_real_columns(session: Session, table_name: str) -> list[str]:
    return list(
        session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table_name},
        ).scalars()
    )


def sync_masked_role_grants(
    session: Session, table_name: str, sensitive_fields: list[str]
) -> None:
    """(Re)calcule en entier les GRANT/REVOKE SELECT par colonne pour
    gis_rls_masked (GAP-22) — jamais un GRANT SELECT au niveau table (un
    REVOKE(colonne) ultérieur serait alors sans effet, cf. spec §1.2).
    Idempotent : recalcule l'état complet à partir de `sensitive_fields`, ne
    diffuse pas un delta contre un état précédent inconnu de l'appelant.
    No-op hors Postgres (appelée depuis patch_collection, qui n'a pas
    l'override de test que register_collection a via get_ddl_applier)."""
    if session.get_bind().dialect.name != "postgresql":
        return
    t = quote_ident(session, table_name)
    all_cols = _all_real_columns(session, table_name)
    sensitive = set(sensitive_fields) & set(all_cols)
    visible = [c for c in all_cols if c not in sensitive]
    if visible:
        cols_sql = ", ".join(quote_ident(session, c) for c in visible)
        session.execute(text(f"GRANT SELECT ({cols_sql}) ON public.{t} TO gis_rls_masked"))
    if sensitive:
        cols_sql = ", ".join(quote_ident(session, c) for c in sorted(sensitive))
        session.execute(text(f"REVOKE SELECT ({cols_sql}) ON public.{t} FROM gis_rls_masked"))
```

Ajouter `"sync_masked_role_grants"` à `__all__`.

Dans `apply_collection_ddl`, juste après la ligne `f"GRANT SELECT, INSERT,
UPDATE, DELETE ON public.{t} TO gis_rls",` de la liste `stmts` (qui est
exécutée dans la boucle `for stmt in stmts: session.execute(text(stmt))`),
ajouter l'appel APRÈS la boucle (car `sync_masked_role_grants` a besoin que
la colonne `tenant_id` existe déjà, ajoutée par le premier `ALTER TABLE` de
`stmts`) :

```python
    for stmt in stmts:
        session.execute(text(stmt))
    sync_masked_role_grants(session, table_name, [])
    # (reste de la fonction inchangé : index spatial, séquence, publication CDC)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_ddl.py -v -m postgis`
Expected: PASS (tous les tests existants + les 2 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/ddl.py core/tests/test_collections_ddl.py
git commit -m "feat(core): sync_masked_role_grants, gis_rls_masked column grants (GAP-22)"
```

---

### Task 4: Falsification directe — REVOKE/GRANT par colonne interagit bien avec la RLS

**Ceci est le test le plus important du plan (spec §6, risque n°1)** :
vérifie l'hypothèse technique centrale — un rôle qui n'a JAMAIS reçu de
GRANT SELECT au niveau table, seulement colonne par colonne, respecte à la
fois la policy RLS (isolation tenant) ET le filtrage par colonne, en même
temps.

**Files:**
- Modify: `core/tests/test_features_rls.py`

**Interfaces:**
- Consumes: `sync_masked_role_grants` (Tâche 3), rôle `gis_rls_masked`
  (Tâche 2).
- Produces: preuve empirique que la Tâche 5 (câblage de `rls_scope`) peut se
  fier au mécanisme.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_features_rls.py`, réutiliser `pg_rls_table` (déjà
défini dans ce fichier) et ajouter une variante à colonnes multiples :

```python
from app.collections.ddl import sync_masked_role_grants


@pytest.fixture()
def pg_rls_table_with_sensitive_column(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope_masked"))
        conn.execute(
            text(
                "CREATE TABLE t_scope_masked "
                "(id serial PRIMARY KEY, v text, salary integer, tenant_id text NOT NULL)"
            )
        )
        conn.execute(text("ALTER TABLE t_scope_masked ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation ON t_scope_masked "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_scope_masked TO gis_rls"))
        conn.execute(
            text(
                "INSERT INTO t_scope_masked (v, salary, tenant_id) VALUES "
                "('mine', 100, 'default'), ('theirs', 200, 'other')"
            )
        )
    with pg_session_factory() as session:
        sync_masked_role_grants(session, "t_scope_masked", ["salary"])
        session.commit()
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope_masked"))


def test_masked_role_filters_column_and_still_respects_tenant_isolation(
    pg_rls_table_with_sensitive_column, pg_session_factory
):
    with pg_session_factory() as session:
        with rls_scope(session, "default", masked=True):
            # Colonne non sensible + isolation tenant : une seule ligne, la mienne.
            rows = session.execute(text("SELECT v FROM t_scope_masked")).scalars().all()
            assert rows == ["mine"]
            # Colonne sensible : refusée, y compris pour ma propre ligne.
            with pytest.raises(Exception):
                session.execute(text("SELECT salary FROM t_scope_masked")).first()
        session.rollback()  # la requête précédente a laissé la transaction en erreur

    with pg_session_factory() as session:
        with rls_scope(session, "default", masked=False):
            # gis_rls (non masqué) voit toujours tout, comme avant ce chantier.
            row = session.execute(
                text("SELECT v, salary FROM t_scope_masked")
            ).first()
            assert row == ("mine", 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_features_rls.py -v -m postgis -k masked`
Expected: FAIL — `TypeError: rls_scope() got an unexpected keyword argument 'masked'`

- [ ] **Step 3: Ne rien implémenter ici — ce test attend `rls_scope(masked=)` de la Tâche 5**

Ce test doit rester rouge à l'issue de cette tâche : elle prouve la sémantique
GRANT/REVOKE de la Tâche 3 (déjà en place), mais dépend de la signature
étendue de `rls_scope` livrée par la Tâche 5. Laisser ce test dans le
fichier, marqué `xfail` temporairement :

```python
@pytest.mark.xfail(reason="rls_scope(masked=) livré par la Tâche 5", strict=True)
def test_masked_role_filters_column_and_still_respects_tenant_isolation(...):
    ...
```

Committer avec ce `xfail` — la Tâche 5 le retirera en faisant passer le test
(règle stricte : si le test passe alors qu'il est marqué `xfail`, la suite
échoue elle-même, donc la Tâche 5 EST FORCÉE de retirer le marqueur en même
temps qu'elle fait passer le test, sans quoi la CI le signale).

- [ ] **Step 4: Commit**

```bash
git add core/tests/test_features_rls.py
git commit -m "test(core): add xfail masked-role/RLS interaction test, pending Task 5 (GAP-22)"
```

---

### Task 5: `rls_scope(masked=)` + `null_rls_scope` compat + dépendance `get_masked_for_user`

**Files:**
- Modify: `core/app/features/rls.py`
- Modify: `core/app/features/routes.py`
- Modify: `core/tests/test_features_rls.py` (retirer le `xfail` de la Tâche 4)

**Interfaces:**
- Consumes: `Privilege.DATA_VIEW_SENSITIVE` (Tâche 1), `has_privilege`
  (`app.roles.guards`, existant).
- Produces: `rls_scope(session, tenant_id, *, masked: bool = False)`,
  `null_rls_scope(session, tenant_id, *, masked: bool = False)`,
  `get_masked_for_user(user=Depends(...), session=Depends(...)) -> bool`
  (dans `app.features.routes`), consommés par les Tâches 6/7/8.

- [ ] **Step 1: Retirer le `xfail` de la Tâche 4 (le test doit d'abord échouer sans le marqueur)**

Dans `core/tests/test_features_rls.py`, retirer le décorateur `@pytest.mark.xfail(...)`
ajouté par la Tâche 4.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_features_rls.py -v -m postgis -k masked_role_filters`
Expected: FAIL — `TypeError: rls_scope() got an unexpected keyword argument 'masked'`

- [ ] **Step 3: Implémenter `rls_scope(masked=)`**

Dans `core/app/features/rls.py` :

```python
@contextmanager
def rls_scope(session: Session, tenant_id: str, *, masked: bool = False):
    role = "gis_rls_masked" if masked else "gis_rls"
    session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
    session.execute(text(f"SET LOCAL ROLE {role}"))
    try:
        yield
    finally:
        try:
            session.execute(text("RESET ROLE"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25P02":
                raise
```

(`role` est interpolé — pas de paramètre lié possible sur `SET LOCAL ROLE`,
même contrainte déjà documentée pour `_quote_literal` dans `ddl.py` — mais
`role` ne vient jamais d'une entrée utilisateur, seulement de la constante
Python choisie ci-dessus : aucune injection possible.)

Mettre à jour le docstring du module pour mentionner le second rôle
(quelques lignes, cohérent avec le style existant).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_features_rls.py -v -m postgis`
Expected: PASS (tous les tests du fichier, y compris les 4 préexistants —
aucune régression, `masked` a un défaut qui préserve leur appel à 2 arguments)

- [ ] **Step 5: Mettre à jour `null_rls_scope` (compat SQLite) et ajouter `get_masked_for_user`**

Dans `core/app/features/routes.py` :

```python
@contextmanager
def null_rls_scope(session, tenant_id, *, masked: bool = False):  # pour SQLite (pas de rôles/GUC)
    yield
```

Puis, juste après `get_rls_scope` :

```python
def get_masked_for_user(
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> bool:
    """Verdict de masquage colonne (GAP-22) pour la requête courante — jamais
    faire confiance à un lecteur anonyme pour du sensible."""
    if user is None:
        return True
    return not has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
```

- [ ] **Step 6: Test unitaire de `get_masked_for_user` (sans FastAPI, appel direct)**

Dans `core/tests/test_features_routes_read.py`, ajouter (réutilise la
fixture `env` existante du fichier) :

```python
from app.features.routes import get_masked_for_user
from app.roles.privileges import Privilege
from app.roles.repository import get_role


def test_get_masked_for_user_true_for_anonymous():
    assert get_masked_for_user(user=None, session=None) is True


def test_get_masked_for_user_reflects_privilege(env):
    _app, _client, admin, regular, _fake_repo = env
    with make_session_factory_from_env(env) as session:  # cf. Step 6b
        # admin porte data.view_sensitive (rôle admin, Tâche 1) -> non masqué
        assert get_masked_for_user(user=admin, session=session) is False
        # regular (aucun rôle sur mesure attribué) -> masqué
        assert get_masked_for_user(user=regular, session=session) is True
```

**`make_session_factory_from_env` n'existe pas** — c'est un espace réservé
qui doit être remplacé, à l'écriture réelle de ce test, par le moyen déjà
utilisé ailleurs dans `test_features_routes_read.py` pour obtenir une
`Session` à partir de la fixture `env` (chercher comment un test voisin de ce
même fichier ouvrit déjà une session directe, ex. via
`db.make_session_factory`/l'engine capturé par la fixture — **vérifier le
fichier réel avant d'écrire ce test**, ne pas deviner une API, CLAUDE.md
piège n°3). Si `env` ne expose pas facilement une session, écrire ce test
dans un fichier séparé avec sa propre fixture SQLite minimale (patron
`test_roles_guards.py` si ce fichier existe — vérifier).

- [ ] **Step 7: Run all tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_rls.py tests/test_features_routes_read.py -v -m postgis`
Run (sans le marqueur `postgis`, pour la partie SQLite) : `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/features/rls.py core/app/features/routes.py \
  core/tests/test_features_rls.py core/tests/test_features_routes_read.py
git commit -m "feat(core): rls_scope(masked=) + get_masked_for_user dependency (GAP-22)"
```

---

### Task 6: Câblage sur les 3 routes de lecture de `features/routes.py`

**Files:**
- Modify: `core/app/features/routes.py`
- Test: `core/tests/test_features_routes_read.py`

**Interfaces:**
- Consumes: `get_masked_for_user` (Tâche 5).
- Produces: `list_features`, `export_collection_items`, `get_single_feature`
  masquent désormais leur rôle Postgres selon le privilège de l'appelant.

- [ ] **Step 1: Écrire le test de câblage qui échoue (spy sur `rls`)**

Dans `core/tests/test_features_routes_read.py`, ajouter une fixture qui
enregistre les arguments avec lesquels `rls` est appelé, pour prouver le
CÂBLAGE (pas la donnée réelle, déjà prouvée par les Tâches 3/4/5) :

```python
def _make_recording_rls_scope():
    calls = []

    @contextmanager
    def recording_rls_scope(session, tenant_id, *, masked=False):
        calls.append(masked)
        yield

    return recording_rls_scope, calls


def test_list_features_masks_when_privilege_absent(env):
    app, client, admin, regular, _fake_repo = env
    recording, calls = _make_recording_rls_scope()
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: recording
    _register(app, client, admin)
    _as(app, regular)  # aucun rôle sur mesure -> pas de data.view_sensitive
    client.get("/v1/collections/incidents/items")
    assert calls == [True]

    calls.clear()
    _as(app, admin)  # bootstrap_admin -> rôle "admin" -> porte data.view_sensitive
    client.get("/v1/collections/incidents/items")
    assert calls == [False]
```

(`contextmanager` est déjà importé en tête de fichier via `from
contextlib import contextmanager` si ce n'est pas déjà le cas — vérifier et
ajouter l'import si absent.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v -k masks_when_privilege`
Expected: FAIL — `assert [] == [True]` (le spy n'est jamais appelé avec un 2e
argument, ou la route ne passe pas encore `masked=`)

- [ ] **Step 3: Câbler `list_features`, `export_collection_items`, `get_single_feature`**

Dans `core/app/features/routes.py`, pour chacune des 3 fonctions, ajouter le
paramètre `masked=Depends(get_masked_for_user)` à la signature et passer
`masked=masked` à l'appel de `rls(...)` :

```python
@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    bbox: str | None = None,
    geom_intersects: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
):
    ...
    with rls(session, col.tenant_id, masked=masked):
        page = repo.select_features(...)
```

Même changement pour `export_collection_items` (ligne ~350-360) et
`get_single_feature` (ligne ~499-510) : ajouter `masked=Depends(get_masked_for_user)`
au paramètre, et `masked=masked` à l'appel `rls(session, col.tenant_id, ...)`.

**Ne PAS toucher** `create_feature`/`put_feature`/`remove_feature` (routes
d'écriture) — elles gardent leur appel `rls(session, col.tenant_id)` sans
`masked=`, défaut `False` préservé.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: PASS

- [ ] **Step 5: Run full existing test files to verify no regression**

Run: `cd core && uv run pytest tests/test_features_routes_read.py tests/test_features_routes_write.py tests/test_features_integration.py -v -m postgis`
Expected: PASS (0 échec — en particulier `test_features_routes_write.py`,
qui ne doit voir aucun changement puisque les routes d'écriture ne sont pas
touchées)

- [ ] **Step 6: Commit**

```bash
git add core/app/features/routes.py core/tests/test_features_routes_read.py
git commit -m "feat(core): mask sensitive columns on the 3 features read routes (GAP-22)"
```

---

### Task 7: Câblage sur `get_collection_tile` (tuiles MVT)

**Files:**
- Modify: `core/app/features/tiles.py`
- Test: `core/tests/test_features_tiles_postgis.py`

**Interfaces:**
- Consumes: `get_masked_for_user` (Tâche 5, importé depuis `app.features.routes`).

- [ ] **Step 1: Écrire le test qui échoue**

Chercher dans `core/tests/test_features_tiles_postgis.py` comment un test
existant décode le contenu MVT (probablement via une librairie de décodage
MVT déjà utilisée dans ce fichier — vérifier avant d'écrire, CLAUDE.md
piège n°3). Ajouter, en réutilisant le même patron de décodage :

```python
def test_tile_omits_sensitive_property_without_privilege(pg_tiles_app):
    # pg_tiles_app : fixture existante du fichier, enregistre une collection
    # réelle avec une géométrie + propriétés. Étendre la collection de test
    # avec une colonne "salary", la marquer sensible via PATCH
    # /collections/{id} {"sensitiveFields": ["salary"]}, puis comparer le
    # contenu MVT décodé pour un utilisateur avec/sans data.view_sensitive.
    ...
```

**Ce test dépend de `PATCH /collections/{id}` acceptant `sensitiveFields`
(Tâche 9)** — si la Tâche 9 n'est pas encore livrée au moment d'exécuter
cette tâche dans l'ordre du plan, marquer temporairement ce test `xfail`
comme la Tâche 4 l'a fait pour `rls_scope(masked=)`, et le retirer dans la
Tâche 9. Sinon (si l'ordre d'exécution réel place la Tâche 9 avant celle-ci
— l'ordre de ce plan les place dans l'ordre inverse volontairement, cf. note
ci-dessous), écrire le test complet directement.

**Note d'ordre** : cette tâche câble le MÉCANISME de masquage sur les
tuiles ; la Tâche 9 câble l'ÉDITION de `sensitiveFields`. Un exécuteur qui
suit ce plan dans l'ordre écrit donc ce test en `xfail` puis le Task 9 le
lève — comme la paire Tâche 4/Tâche 5. Alternative valide : permuter l'ordre
d'exécution des Tâches 7-8 et 9 si l'exécuteur préfère livrer `sensitiveFields`
avant les 3 câblages MCP/tuiles — aucune dépendance technique n'impose
l'ordre inverse, seul le texte de ce plan les a ordonnées ainsi pour garder
tous les câblages Postgres groupés avant les câblages DuckDB.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_features_tiles_postgis.py -v -m postgis -k sensitive_property`
Expected: FAIL (masquage pas encore câblé)

- [ ] **Step 3: Câbler**

Dans `core/app/features/tiles.py`, ajouter l'import :

```python
from app.features.routes import get_masked_for_user, get_rls_scope
```

(remplace l'import existant `from app.features.routes import get_rls_scope`).
Ajouter le paramètre à `get_collection_tile` :

```python
def get_collection_tile(
    collection_id: str,
    z: int,
    x: int,
    y: int,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    ...
    with rls(session, col.tenant_id, masked=masked):
        apply_tile_statement_timeout(session)
        tile = session.execute(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_features_tiles_postgis.py -v -m postgis`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/app/features/tiles.py core/tests/test_features_tiles_postgis.py
git commit -m "feat(core): mask sensitive columns in MVT tiles (GAP-22)"
```

---

### Task 8: Câblage sur le tool MCP `query_features`

**Files:**
- Modify: `core/app/mcp/tools/catalog.py`
- Test: `core/tests/test_mcp_tools_query_features.py`

**Interfaces:**
- Consumes: `has_privilege`/`Privilege` (déjà importés dans ce fichier).

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_mcp_tools_query_features.py`, ajouter (calquer
exactement le patron d'authentification/appel de tool déjà utilisé dans ce
fichier pour les tests existants de `query_features` — vérifier avant
d'écrire) un test qui enregistre une collection avec une colonne
supplémentaire, la marque sensible via une écriture directe en base
(`col.sensitive_fields = ["salary"]; session.commit()` — pas besoin
d'attendre la Tâche 9 ici, on écrit directement le champ du modèle) puis
appelle `sync_masked_role_grants` directement (Tâche 3) pour que le GRANT
Postgres réel soit en place, puis vérifie que `query_features` en tant
qu'utilisateur sans le privilège ne renvoie pas `salary` dans `properties`,
et le renvoie pour un utilisateur qui porte le privilège.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_tools_query_features.py -v -m postgis -k sensitive`
Expected: FAIL

- [ ] **Step 3: Câbler**

Dans `core/app/mcp/tools/catalog.py`, dans `query_features`, remplacer :

```python
            try:
                with rls_scope(session, col.tenant_id):
                    page = select_features(...)
```

par :

```python
            masked = user is None or not has_privilege(
                session, user, Privilege.DATA_VIEW_SENSITIVE.value
            )
            try:
                with rls_scope(session, col.tenant_id, masked=masked):
                    page = select_features(...)
```

(`has_privilege`/`Privilege` déjà importés en tête de ce fichier — vérifier,
sinon ajouter `from app.roles.guards import has_privilege` et `from
app.roles.privileges import Privilege`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_mcp_tools_query_features.py -v -m postgis`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools/catalog.py core/tests/test_mcp_tools_query_features.py
git commit -m "feat(core): mask sensitive columns in query_features MCP tool (GAP-22)"
```

---

### Task 9: `CollectionPatch.sensitiveFields` + validation + câblage `patch_collection`

**Files:**
- Modify: `core/app/collections/schemas.py`
- Modify: `core/app/collections/routes.py`
- Test: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes: `sync_masked_role_grants` (Tâche 3).
- Produces: `sensitiveFields` éditable via `PATCH /collections/{id}`,
  consommé par la Tâche 7 (test précédemment `xfail`) et la Tâche 15 (shell).

- [ ] **Step 1: Écrire les tests qui échouent (validation Pydantic + DB)**

Dans `core/tests/test_collections_routes.py` :

```python
def test_patch_sets_sensitive_fields(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})
    r = client.patch("/v1/collections/incidents", json={"sensitiveFields": ["titre"]})
    assert r.status_code == 200
    assert r.json()["sensitiveFields"] == ["titre"]
    assert client.get("/v1/collections/incidents").json()["sensitiveFields"] == ["titre"]


def test_patch_rejects_unknown_sensitive_field(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})
    r = client.patch("/v1/collections/incidents", json={"sensitiveFields": ["nope"]})
    assert r.status_code == 422


def test_patch_rejects_reserved_column_as_sensitive_field(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/v1/collections", json={"tableName": "incidents"})
    r = client.patch("/v1/collections/incidents", json={"sensitiveFields": ["geom"]})
    assert r.status_code == 422


def test_patch_rejects_duplicate_sensitive_field_names():
    from app.collections.schemas import CollectionPatch

    with pytest.raises(ValueError, match="duplicate"):
        CollectionPatch(sensitiveFields=["titre", "titre"])
```

(`INCIDENTS`/`fake_introspector` du fichier ont `columns=[ColumnInfo(name="titre",
...)]`, `geometry_column="geom"` — donc `"geom"` est bien un nom réservé pour ce
fixture, `"nope"` un nom inconnu, `"titre"` un nom valide. Vérifier ces noms
exacts dans le fichier avant d'écrire ces tests, CLAUDE.md piège n°3.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k sensitive`
Expected: FAIL — `pydantic.errors` sur un champ inconnu `sensitiveFields`, ou
absence de validation 422.

- [ ] **Step 3: Ajouter le champ + validateur Pydantic**

Dans `core/app/collections/schemas.py::CollectionPatch`, ajouter le champ
(après `attachmentFields`) :

```python
    sensitiveFields: list[str] | None = None
```

Et un nouveau validateur, à côté de `_reject_duplicate_attachment_field_keys` :

```python
    @model_validator(mode="after")
    def _reject_duplicate_sensitive_field_names(self) -> "CollectionPatch":
        # GAP-22 : la collision avec une colonne réservée (pk/tenant_id/geometry)
        # ou inexistante nécessite l'introspecteur — vérifiée dans
        # patch_collection (app/collections/routes.py), pas ici.
        if self.sensitiveFields is None:
            return self
        if len(self.sensitiveFields) != len(set(self.sensitiveFields)):
            duplicates = sorted(
                {f for f in self.sensitiveFields if self.sensitiveFields.count(f) > 1}
            )
            raise ValueError(f"duplicate sensitiveFields name(s): {', '.join(duplicates)}")
        return self
```

- [ ] **Step 4: Ajouter la validation DB + câbler `patch_collection`**

Dans `core/app/collections/routes.py`, ajouter l'import
`sync_masked_role_grants` à la ligne existante `from app.collections.ddl
import TenantColumnMismatch` :

```python
from app.collections.ddl import TenantColumnMismatch, sync_masked_role_grants
```

Ajouter, à côté de `_reject_attachment_field_collisions` :

```python
def _reject_invalid_sensitive_fields(
    session: Session,
    col,
    sensitive_fields: list[str],
    introspect: Introspector,
) -> None:
    if not sensitive_fields:
        return
    try:
        info = introspect(session, col.table_name)
    except (TableNotFound, UnsupportedTable):
        return
    valid = {c.name for c in info.columns} - {info.pk_column, "tenant_id", info.geometry_column}
    unknown = sorted(set(sensitive_fields) - valid)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"sensitiveFields must be real, non-reserved column(s): {', '.join(unknown)}",
        )
```

Dans `patch_collection`, après le bloc `if body.attachmentFields is not
None: _reject_attachment_field_collisions(...)`, ajouter :

```python
    if body.sensitiveFields is not None:
        _reject_invalid_sensitive_fields(session, col, body.sensitiveFields, introspect)
```

Après la boucle `for attr, value in (...)` qui affecte les attributs
simples, et après le bloc `if body.attachmentFields is not None: col.attachment_fields = ...`,
ajouter :

```python
    if body.sensitiveFields is not None:
        sync_masked_role_grants(session, col.table_name, body.sensitiveFields)
        col.sensitive_fields = body.sensitiveFields
```

Dans `_collection_json`, ajouter au dict retourné :

```python
        "sensitiveFields": col.sensitive_fields,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: PASS

- [ ] **Step 6: Lever le `xfail` de la Tâche 7 si applicable**

Si la Tâche 7 a été exécutée avant celle-ci et a marqué son test `xfail`
(cf. sa note d'ordre), retirer le marqueur maintenant et vérifier :

Run: `cd core && uv run pytest tests/test_features_tiles_postgis.py -v -m postgis -k sensitive_property`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/app/collections/schemas.py core/app/collections/routes.py \
  core/tests/test_collections_routes.py core/tests/test_features_tiles_postgis.py
git commit -m "feat(core): PATCH /collections/{id} accepts sensitiveFields (GAP-22)"
```

---

### Task 10: Test bout-en-bout Postgres — critère d'acceptation §5.3 de la spec

**Files:**
- Create: `core/tests/test_features_sensitive_fields_integration.py`

**Interfaces:**
- Consumes: tout le chemin (A) livré par les Tâches 1-3, 5, 6, 9.

- [ ] **Step 1: Écrire le test bout-en-bout**

Calquer EXACTEMENT le patron de fixture `pg_app` de
`core/tests/test_features_integration.py` (déjà lu — TestClient réel, vraie
DDL, pas de fake repo/introspecteur) :

```python
# SPDX-License-Identifier: Apache-2.0
"""Bout en bout PostGIS réel : un champ marqué sensible est absent des
réponses pour un utilisateur sans data.view_sensitive, présent pour un
utilisateur qui le porte — critère d'acceptation §5 de la spec GAP-22."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3Client:
    def delete_object(self, *, Bucket, Key):
        pass


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_employees"))
        conn.execute(
            text(
                "CREATE TABLE demo_employees (id serial PRIMARY KEY, "
                "nom text NOT NULL, salary integer, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        # rôle sur mesure SANS data.view_sensitive, avec de quoi lire/gérer
        # des collections (sinon 403 avant même le masquage à tester)
        limited_role = create_role(
            s, tenant_id=tenant.id, name="limited",
            privileges=[Privilege.DATA_VIEW.value, Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        limited = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="l", username="limited",
            email=None, first_name="", last_name="",
        )
        limited.role_id = limited_role.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()
    client = TestClient(app)
    yield client, app, admin, limited
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_employees"))
        conn.execute(
            text(
                "TRUNCATE roles, collection_shares, collections, audit_log, "
                "users, tenants CASCADE"
            )
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_sensitive_field_absent_from_list_and_export_without_privilege(pg_app):
    client, app, admin, limited = pg_app
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "demo_employees"}).status_code == 201
    assert client.patch(
        "/v1/collections/demo_employees", json={"sensitiveFields": ["salary"]}
    ).status_code == 200
    r = client.post(
        "/v1/collections/demo_employees/items",
        json={
            "type": "Feature",
            "properties": {"nom": "Dupont", "salary": 45000},
            "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
        },
    )
    assert r.status_code == 201
    fid = r.json()["id"]

    _as(app, limited)
    listed = client.get("/v1/collections/demo_employees/items").json()
    props = listed["features"][0]["properties"]
    assert "salary" not in props
    assert props["nom"] == "Dupont"

    single = client.get(f"/v1/collections/demo_employees/items/{fid}").json()
    assert "salary" not in single["properties"]

    exported = client.get(
        "/v1/collections/demo_employees/export/items?format=csv"
    ).content.decode()
    assert "salary" not in exported.lower()
    assert "dupont" in exported.lower()

    _as(app, admin)
    listed_admin = client.get("/v1/collections/demo_employees/items").json()
    assert listed_admin["features"][0]["properties"]["salary"] == 45000
```

**Vérifier avant d'écrire** : la signature réelle de `create_role`
(`app/roles/repository.py`) — le squelette ci-dessus est une hypothèse
(nom du paramètre `privileges`, valeur de retour) à corriger contre le code
réel (CLAUDE.md piège n°3). Vérifier aussi que `Role` a bien une table
`roles` avec ce nom exact pour le `TRUNCATE` du teardown.

- [ ] **Step 2: Run test to verify it fails (avant les Tâches 1-9) ou passe (après)**

Ce test devrait déjà **passer** à ce stade du plan puisque les Tâches 1, 2,
3, 5, 6, 9 sont toutes livrées avant celle-ci dans l'ordre de ce plan — son
rôle est de **falsifier l'intégration bout-en-bout**, pas un mécanisme isolé
déjà prouvé par les tâches précédentes. Si ce test échoue ici, c'est le
signal d'un défaut de croisement entre tâches (CLAUDE.md piège n°4) à
corriger avant de continuer.

Run: `cd core && uv run pytest tests/test_features_sensitive_fields_integration.py -v -m postgis`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_features_sensitive_fields_integration.py
git commit -m "test(core): end-to-end proof of column masking on features routes (GAP-22)"
```

---

### Task 11: Masquage DuckDB — agrégats structurés (`app/analytics/aggregate.py`)

**Files:**
- Modify: `core/app/analytics/aggregate.py`
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `_valid_column_names(table_info, masked_fields=frozenset())`,
  `_validate_fields(request, table_info, masked_fields=frozenset())`,
  `run_collection_aggregate(..., masked_fields: frozenset[str] =
  frozenset())` — consommés par la Tâche 12.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_analytics_aggregate.py`, chercher le patron exact des
tests de `run_collection_aggregate`/`UnknownAggregateField` déjà présents
(fixture `TableInfo`, `conn` DuckDB, écriture GeoParquet — probablement très
proche du patron déjà vu dans `test_analytics_sql_sandbox.py::_write`).
Ajouter :

```python
def test_run_collection_aggregate_rejects_masked_field_as_unknown(conn, tmp_path):
    # réutiliser le patron d'écriture GeoParquet + TableInfo déjà présent
    # dans ce fichier, avec une colonne supplémentaire "salary"
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="default",
            collection_id="employees",
            table_info=INFO_WITH_SALARY,
            request=AggregateRequestBody(groupBy="salary", agg="count"),
            masked_fields=frozenset({"salary"}),
        )
    assert exc_info.value.field == "groupBy"


def test_run_collection_aggregate_allows_field_without_masking(conn, tmp_path):
    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="default",
        collection_id="employees",
        table_info=INFO_WITH_SALARY,
        request=AggregateRequestBody(groupBy="salary", agg="count"),
        masked_fields=frozenset(),
    )
    assert category_key == "salary"
```

(`INFO_WITH_SALARY`, la fixture GeoParquet et `conn` sont à définir/réutiliser
en calquant exactement les fixtures déjà présentes dans ce fichier de test —
vérifier leur forme réelle avant d'écrire, CLAUDE.md piège n°3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v -k masked`
Expected: FAIL — `TypeError: run_collection_aggregate() got an unexpected keyword argument 'masked_fields'`

- [ ] **Step 3: Implémenter**

Dans `core/app/analytics/aggregate.py` :

```python
def _valid_column_names(
    table_info: TableInfo, masked_fields: frozenset[str] = frozenset()
) -> set[str]:
    names = {c.name for c in table_info.columns} | {table_info.pk_column}
    if table_info.geometry_column:
        names.add(table_info.geometry_column)
    return names - _EXCLUDED_PROPERTIES - masked_fields
```

`_validate_fields` gagne le même paramètre, relayé à son unique appel de
`_valid_column_names` :

```python
def _validate_fields(
    request: AggregateRequestBody,
    table_info: TableInfo,
    masked_fields: frozenset[str] = frozenset(),
) -> None:
    valid = _valid_column_names(table_info, masked_fields)
    ...  # reste du corps inchangé
```

`run_collection_aggregate` gagne le même paramètre, relayé à son appel de
`_validate_fields` :

```python
def run_collection_aggregate(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    request: AggregateRequestBody,
    masked_fields: frozenset[str] = frozenset(),
) -> tuple[str | list[str], list[dict[str, Any]]]:
    fields = _groupby_fields(request)
    _validate_fields(request, table_info, masked_fields)
    ...  # reste du corps inchangé — vérifier l'endroit exact où
    # _validate_fields est déjà appelée dans le corps réel de la fonction
    # avant d'insérer ce paramètre, ne pas supposer la position exacte
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`
Expected: PASS (tous les tests du fichier, y compris les préexistants — le
défaut de `masked_fields=frozenset()` préserve tout appelant existant)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): aggregate.py accepts masked_fields, rejects them as unknown (GAP-22)"
```

---

### Task 12: Câblage du masquage sur `POST /collections/{id}/aggregate`, `/export`, et `run_analytics_query` (MCP)

**Files:**
- Modify: `core/app/features/routes.py`
- Modify: `core/app/mcp/tools/analytics.py`
- Test: `core/tests/test_features_aggregate_routes.py`
- Test: `core/tests/test_mcp_tools_analytics.py` (chercher le nom exact du
  fichier de test du domaine MCP analytics — `ls core/tests | grep -i
  mcp.*analytic`)

**Interfaces:**
- Consumes: `run_collection_aggregate(..., masked_fields=...)` (Tâche 11).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_features_aggregate_routes.py`, calquer le patron
existant (probablement SQLite + fake introspecteur, comme
`test_features_routes_read.py`) et ajouter un test où l'utilisateur courant
n'a pas `data.view_sensitive`, une collection a `sensitive_fields=["salary"]`
en base, et `POST /collections/{id}/aggregate` avec `groupBy: "salary"`
répond 400/422 (`unknown_field`) plutôt que d'agréger.

Dans le fichier de test MCP analytics trouvé à l'étape précédente, un test
équivalent pour `run_analytics_query`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_aggregate_routes.py -v -k sensitive`
Expected: FAIL (l'agrégat réussit alors qu'il devrait être rejeté)

- [ ] **Step 3: Câbler les 2 routes REST**

Dans `core/app/features/routes.py`, `aggregate_features` et
`export_collection_aggregate` gagnent chacune, avant l'appel à
`run_collection_aggregate` :

```python
    masked_fields = (
        frozenset()
        if user is not None and has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
        else frozenset(col.sensitive_fields)
    )
```

puis `masked_fields=masked_fields` ajouté à l'appel `run_collection_aggregate(...)`.

(`aggregate_features` utilise `get_current_user_optional` — `user` peut être
`None` sur une collection publique, d'où la garde `user is not None`.
`export_collection_aggregate` utilise `get_current_user`, toujours non-None,
mais la même expression reste correcte.)

- [ ] **Step 4: Câbler `run_analytics_query` (MCP)**

Dans `core/app/mcp/tools/analytics.py`, ajouter en tête de fichier :

```python
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
```

Dans `run_analytics_query`, juste avant l'appel à `run_collection_aggregate` :

```python
                masked_fields = (
                    frozenset()
                    if has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
                    else frozenset(col.sensitive_fields)
                )
                try:
                    category_key, rows = run_collection_aggregate(
                        conn,
                        base_uri=features_routes.get_analytics_base_uri(),
                        tenant_id=col.tenant_id,
                        collection_id=col.id,
                        table_info=info,
                        request=query,
                        masked_fields=masked_fields,
                    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_aggregate_routes.py -v`
Run: `cd core && uv run pytest tests/test_mcp_tools_analytics.py -v` (ou le
nom réel du fichier trouvé)
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/app/features/routes.py core/app/mcp/tools/analytics.py \
  core/tests/test_features_aggregate_routes.py core/tests/test_mcp_tools_analytics.py
git commit -m "feat(core): mask sensitive fields on structured aggregate routes + MCP (GAP-22)"
```

---

### Task 13: Masquage DuckDB — SQL Lab (`app/analytics/sql_sandbox.py`), le critère central

**Ceci est le test le plus important côté DuckDB** (spec §5, critère
d'acceptation 6) : prouve qu'un `SELECT` arbitraire ne peut physiquement pas
lire une colonne sensible, pas seulement qu'un champ structuré est rejeté.

**Files:**
- Modify: `core/app/analytics/sql_sandbox.py`
- Test: `core/tests/test_analytics_sql_sandbox.py`

**Interfaces:**
- Produces: `_materialize(..., masked_fields=frozenset())`,
  `run_analyst_sql(..., masked_fields_by_collection: dict[str,
  frozenset[str]] | None = None)` — consommés par la Tâche 14.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_analytics_sql_sandbox.py`, étendre la fixture `INFO`
existante (ou en ajouter une variante) et `_write` pour inclure une colonne
`salary` :

```python
INFO_WITH_SALARY = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
        ColumnInfo(name="salary", type="integer", required=False),
    ],
)


def _write_with_salary(base_dir, *, tenant_id="default", collection_id="villes"):
    part = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-09-06"
    part.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        [
            {
                "id": 1, "region": "Nord", "pop": 10, "salary": 45000,
                "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0),
            }
        ],
        geometry="geometry", crs="EPSG:4326",
    ).to_parquet(part / "part-1.parquet")


def test_sql_lab_select_star_omits_sensitive_column(tmp_path):
    _write_with_salary(tmp_path)
    conn = _spatial_conn()
    try:
        columns, rows, _truncated = run_analyst_sql(
            conn,
            sql="SELECT * FROM villes",
            allowed={"villes": INFO_WITH_SALARY},
            base_uri=str(tmp_path),
            tenant_id="default",
            masked_fields_by_collection={"villes": frozenset({"salary"})},
        )
        assert "salary" not in columns
        assert "region" in columns
    finally:
        conn.close()


def test_sql_lab_explicit_select_of_masked_column_fails(tmp_path):
    _write_with_salary(tmp_path)
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):
            run_analyst_sql(
                conn,
                sql="SELECT salary FROM villes",
                allowed={"villes": INFO_WITH_SALARY},
                base_uri=str(tmp_path),
                tenant_id="default",
                masked_fields_by_collection={"villes": frozenset({"salary"})},
            )
    finally:
        conn.close()


def test_sql_lab_returns_sensitive_column_when_not_masked(tmp_path):
    _write_with_salary(tmp_path)
    conn = _spatial_conn()
    try:
        columns, rows, _truncated = run_analyst_sql(
            conn,
            sql="SELECT salary FROM villes",
            allowed={"villes": INFO_WITH_SALARY},
            base_uri=str(tmp_path),
            tenant_id="default",
            masked_fields_by_collection={},
        )
        assert columns == ["salary"]
        assert rows == [[45000]]
    finally:
        conn.close()


def test_sql_lab_never_exposes_cdc_plumbing_columns(tmp_path):
    _write_with_salary(tmp_path)
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):
            run_analyst_sql(
                conn,
                sql="SELECT _lsn FROM villes",
                allowed={"villes": INFO_WITH_SALARY},
                base_uri=str(tmp_path),
                tenant_id="default",
                masked_fields_by_collection={},
            )
    finally:
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v -k "sensitive or masked or plumbing"`
Expected: FAIL — `TypeError: run_analyst_sql() got an unexpected keyword argument 'masked_fields_by_collection'`

- [ ] **Step 3: Implémenter**

Dans `core/app/analytics/sql_sandbox.py`, ajouter l'import :

```python
from app.analytics.aggregate import _dedup_cte, _has_any_file, _EXCLUDED_PROPERTIES
```

(remplace l'import existant `from app.analytics.aggregate import _dedup_cte, _has_any_file`).

Remplacer `_materialize` :

```python
def _materialize(
    conn: duckdb.DuckDBPyConnection,
    *,
    name: str,
    table_info: TableInfo,
    base_uri: str,
    tenant_id: str,
    masked_fields: frozenset[str] = frozenset(),
) -> None:
    if not _has_any_file(conn, base_uri, tenant_id, name):
        raise SqlSandboxError(f"collection '{name}' has no data yet")
    cte = _dedup_cte(conn, table_info, base_uri, tenant_id, name)
    reserved = {table_info.pk_column} | _EXCLUDED_PROPERTIES | masked_fields
    cols = [table_info.pk_column] + [
        c.name for c in table_info.columns if c.name not in reserved
    ]
    if table_info.geometry_column and table_info.geometry_column not in reserved:
        cols.append(table_info.geometry_column)
    select_list = ", ".join(_qi(c) for c in cols)
    conn.execute(f"CREATE TEMP TABLE {_qi(name)} AS {cte} SELECT {select_list} FROM live")
```

Remplacer la signature et le corps de `run_analyst_sql` :

```python
def run_analyst_sql(
    conn: duckdb.DuckDBPyConnection,
    *,
    sql: str,
    allowed: dict[str, TableInfo],
    base_uri: str,
    tenant_id: str,
    masked_fields_by_collection: dict[str, frozenset[str]] | None = None,
) -> tuple[list[str], list[list[object]], bool]:
    ast = parse_ast(conn, sql)
    validate_select_only(ast)
    refs = collect_table_refs(ast)
    _apply_limits(conn)
    timer = threading.Timer(STATEMENT_TIMEOUT_S, conn.interrupt)
    timer.start()
    masked_by_collection = masked_fields_by_collection or {}
    try:
        for name in sorted(refs & set(allowed)):
            _materialize(
                conn,
                name=name,
                table_info=allowed[name],
                base_uri=base_uri,
                tenant_id=tenant_id,
                masked_fields=masked_by_collection.get(name, frozenset()),
            )
        _lock_down(conn)
        return _execute(conn, sql)
    except duckdb.InterruptException as exc:
        raise SqlSandboxError("query exceeded the time limit") from exc
    except duckdb.Error as exc:
        raise SqlSandboxError(str(exc)) from exc
    finally:
        timer.cancel()
```

(Le docstring existant reste, juste le corps change.)

**Vérifier au passage** que `_EXCLUDED_PROPERTIES` (importé depuis
`aggregate.py`) est bien exporté/importable tel quel (nom privé, préfixé
`_` — Python l'autorise à l'import explicite, mais confirmer qu'aucune règle
`lint-imports`/`ruff` du dépôt n'interdit l'import d'un symbole privé
inter-module ; le dépôt le fait déjà pour `_dedup_cte`/`_has_any_file`,
donc le patron est déjà accepté.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_sql_sandbox.py -v`
Expected: PASS (tous les tests du fichier, y compris les préexistants)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/sql_sandbox.py core/tests/test_analytics_sql_sandbox.py
git commit -m "feat(core): SQL Lab materializes an explicit masked column list (GAP-22)"
```

---

### Task 14: Câblage du masquage sur `POST /analytics/sql` (route SQL Lab)

**Files:**
- Modify: `core/app/features/routes.py`
- Test: `core/tests/test_features_routes_read.py` (ou un fichier dédié —
  chercher `ls core/tests | grep -i "analytics_sql\|sql_lab"` pour un
  fichier de test de route déjà dédié à `POST /analytics/sql`)

**Interfaces:**
- Consumes: `run_analyst_sql(..., masked_fields_by_collection=...)` (Tâche 13).

- [ ] **Step 1: Écrire le test qui échoue**

Dans le fichier de test trouvé à l'étape précédente, ajouter un test qui
enregistre une collection réelle contre un vrai Postgres (patron `pg_app` de
la Tâche 10 — ce test doit être `@pytest.mark.postgis`, la route SQL Lab
utilise `get_duckdb_connection_factory`/`get_analytics_base_uri`, réels au
sens DuckDB mais lit un GeoParquet écrit par le CDC réel — vérifier comment
les tests existants de `POST /analytics/sql` contournent déjà ce besoin,
probablement via un override de `get_duckdb_connection_factory`/
`get_analytics_base_uri` pointant un `tmp_path` avec un fichier GeoParquet
écrit directement par le test, sans dépendre du worker CDC réel — même
patron que `test_analytics_sql_sandbox.py`, à confirmer avant d'écrire),
marque une colonne sensible, puis appelle `POST /analytics/sql {"sql":
"SELECT salary FROM <collection>"}` sans le privilège : 400 (`sql_error`) ;
avec le privilège : 200, `salary` dans les colonnes.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest <fichier trouvé> -v -k sensitive`
Expected: FAIL (SQL Lab renvoie `salary` malgré l'absence de privilège)

- [ ] **Step 3: Câbler**

Dans `core/app/features/routes.py::analytics_sql`, remplacer :

```python
    require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)
    cols = list_visible_collections(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        can_see_all=has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value),
    )
    allowed: dict = {}
    for col in cols:
        try:
            allowed[col.id] = introspect(session, col.table_name)
        except TableNotFound:
            continue
```

par :

```python
    require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)
    sensitive_ok = has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
    cols = list_visible_collections(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        can_see_all=has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value),
    )
    allowed: dict = {}
    masked_fields_by_collection: dict[str, frozenset[str]] = {}
    for col in cols:
        try:
            allowed[col.id] = introspect(session, col.table_name)
        except TableNotFound:
            continue
        masked_fields_by_collection[col.id] = (
            frozenset() if sensitive_ok else frozenset(col.sensitive_fields)
        )
```

Et dans l'appel à `run_analyst_sql(...)` un peu plus bas, ajouter :

```python
        columns, rows, truncated = run_analyst_sql(
            conn,
            sql=body.sql,
            allowed=allowed,
            base_uri=base_uri,
            tenant_id=user.tenant_id,
            masked_fields_by_collection=masked_fields_by_collection,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest <fichier trouvé> -v`
Expected: PASS

- [ ] **Step 5: Run the full SQL Lab test suite for regressions**

Run: `cd core && uv run pytest tests/ -v -k "analytics_sql or sql_lab"`
Expected: PASS, 0 régression

- [ ] **Step 6: Commit**

```bash
git add core/app/features/routes.py <fichier de test trouvé>
git commit -m "feat(core): SQL Lab route masks sensitive fields by collection (GAP-22)"
```

---

### Task 15: Shell — édition de `sensitiveFields` depuis l'écran d'administration de collection

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/shell/EditCollectionPanel.tsx`
- Modify: `shell/src/api/domains/collectionsAdmin.ts`
- Test: `shell/src/shell/EditCollectionPanel.test.tsx` (chercher le nom exact
  du fichier de test existant pour ce composant — `ls shell/src/shell |
  grep -i EditCollectionPanel`)

**Interfaces:**
- Consumes: `sensitiveFields` sur `PATCH /collections/{id}` (Tâche 9),
  `GET /collections/{id}/schema` (existant, inchangé).

- [ ] **Step 1: Régénérer les types TS depuis l'OpenAPI actuel (avant d'ajouter le code shell)**

Run (incantation exacte, cf. CLAUDE.md — nécessite `CORE_SECRETS_MASTER_KEY`
de test) :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Vérifier que `shell/src/api/generated/core-schema.d.ts` porte désormais
`sensitiveFields` sur le schéma de collection (généré, pas manuel — ne pas
éditer ce fichier à la main).

- [ ] **Step 2: Écrire le test shell qui échoue**

Dans le fichier de test d'`EditCollectionPanel` trouvé, calquer le test
existant sur `attachmentFields` (rendu, ajout d'un champ, soumission) pour
`sensitiveFields` — cocher un champ dans la liste, soumettre, vérifier que
`updateCollection`/`patchCollection` (le mock du domaine `collectionsAdmin`)
est appelé avec `sensitiveFields: ["titre"]` inclus dans le corps.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd shell && npx vitest run src/shell/<fichier trouvé>`
Expected: FAIL (aucune UI pour `sensitiveFields`)

- [ ] **Step 4: Ajouter les types**

Dans `shell/src/api/types.ts`, sur les interfaces `CollectionRead`/
`CollectionUpdate` (chercher leur nom exact — probablement nommées
différemment, vérifier avant d'écrire), ajouter à côté d'`attachmentFields` :

```ts
  sensitiveFields: string[];
```

(sur le type de lecture, toujours présent) et

```ts
  sensitiveFields?: string[];
```

(sur le type de mise à jour, optionnel comme `attachmentFields?`).

- [ ] **Step 5: Câbler le domaine `collectionsAdmin`**

Dans `shell/src/api/domains/collectionsAdmin.ts`, la fonction qui construit
le corps de `PATCH /collections/{id}` (chercher son nom exact — probablement
`updateCollection`) doit relayer `sensitiveFields` exactement comme elle
relaie déjà `attachmentFields` — ajouter le champ au corps envoyé si fourni
par l'appelant.

- [ ] **Step 6: Ajouter l'UI dans `EditCollectionPanel.tsx`**

Ajouter un état local `sensitiveFields` (`useState(collection.sensitiveFields ?? [])`),
une section « Champs sensibles » à côté de la section « Pièces jointes »
existante, listant les champs réels de la collection (déjà chargés via
`GET /collections/{id}/schema` pour l'éditeur de pièces jointes existant —
réutiliser cette même donnée de schéma plutôt que refaire un appel), une
case à cocher par champ, et inclure `sensitiveFields` dans l'appel de
sauvegarde existant (là où `attachmentFields`, `licenseUri`, etc. sont déjà
assemblés dans le payload de `PATCH`).

Utiliser une clé i18n nouvelle (ex. `editCollection.sensitiveFieldsTitle`)
ajoutée à `shell/src/i18n/catalog.fr.ts`, respectant la garde `npm run
lint` (`check-i18n-coverage.mjs`) qui interdit toute chaîne française codée
en dur hors `t()` dans ce répertoire.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd shell && npx vitest run src/shell/<fichier trouvé>`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/generated/core-schema.d.ts \
  shell/src/api/domains/collectionsAdmin.ts shell/src/shell/EditCollectionPanel.tsx \
  shell/src/i18n/catalog.fr.ts core/openapi.json <fichier de test trouvé>
git commit -m "feat(shell): edit sensitiveFields from collection admin screen (GAP-22)"
```

---

### Task 16: Vérification finale — portes de qualité, suites complètes, régénération

**Files:** aucun fichier de code — vérification uniquement (les corrections
trouvées, s'il y en a, doivent être commitées séparément avant de clore
cette tâche).

- [ ] **Step 1: Portes de qualité cœur**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

Expected: tous verts. Si `mypy --strict` échoue sur `app/analytics` à cause
des nouveaux paramètres `masked_fields: frozenset[str]`, corriger les
annotations (ne jamais retirer `app/analytics` du périmètre `--strict` pour
contourner).

- [ ] **Step 2: Suite complète cœur**

```bash
cd core && uv run pytest
```

Expected: 0 échec nouveau. Comparer au dernier compte connu documenté dans
`CLAUDE.md` (§Commandes) avant cette branche — tout nouvel échec doit être
diagnostiqué (CLAUDE.md piège n°9 : vérifier qu'aucune session concurrente
ne partage le même conteneur `postgis-test`).

- [ ] **Step 3: Portes de qualité + suite shell**

```bash
cd shell
npm run lint && npm run format:check
npm run test
npm run build
```

Expected: tous verts, couverture ≥ 88 (nettoyer `dist/`/`dist-export/`
avant mesure, piège documenté 4 fois).

- [ ] **Step 4: Pre-commit complet**

```bash
uvx pre-commit run --all-files
```

Expected: 5 hooks verts.

- [ ] **Step 5: Suite E2E**

```bash
cd shell && npm run e2e
```

Expected: aucune régression de compte par rapport au dernier chiffre connu
de `CLAUDE.md` (166 passed / 4 skipped / 0 failed au moment de l'écriture de
cette spec — peut avoir dérivé depuis, comparer au dernier chiffre réel
plutôt qu'à celui-ci).

- [ ] **Step 6: Régénérer le bilan de fonctionnalités si une surface nouvelle a été ajoutée**

Ce plan n'ajoute aucune route REST/outil MCP/route shell nouvelle (seulement
des champs sur des surfaces existantes) — vérifier que
`core/tests/test_feature_inventory.py` reste vert sans ajout à
`docs/revue/inventaire-fonctionnalites.jsonl` :

```bash
cd core && uv run pytest tests/test_feature_inventory.py -v
```

Si ce test échoue (signe qu'une des surfaces touchées est en réalité
comptée comme nouvelle par le détecteur), ajouter la ligne d'inventaire
manquante puis régénérer :

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
```

- [ ] **Step 7: Mettre à jour CLAUDE.md**

Ajouter une ligne dans `### Livré` documentant ce chantier (GAP-22 fermé),
en rappelant explicitement dans le texte les 2 bypass hors périmètre
découverts (spec §1.5 : `pipelines/runtime.py::_read_collection`, `appexport/
freeze.py`/`snapshot.py`) et la limite connue « pas de masquage en écriture »
(spec §4) — ne pas les laisser implicites, CLAUDE.md piège n°12. Mettre à
jour l'état du `GAP-22` dans `docs/revue/2026-09-04-analyse-gaps.md` (ouvert
→ fermé, référence à ce plan).

- [ ] **Step 8: Commit final**

```bash
git add CLAUDE.md docs/revue/2026-09-04-analyse-gaps.md \
  docs/revue/inventaire-fonctionnalites.jsonl docs/revue/bilan-fonctionnalites.html \
  docs/revue/bilan-fonctionnalites.md docs/revue/historique-sante.jsonl
git commit -m "docs: close GAP-22 (column-level sensitive field masking)"
```

---

## Self-Review (effectuée à l'écriture de ce plan)

**Couverture de la spec** : §3.1 (Tâche 1), §3.2 (Tâches 2, 9), §3.3
(Tâches 2, 3, 4), §3.4 (Tâches 5, 6, 7, 8), §3.5 (Tâches 11, 12, 13, 14),
§3.6 (Tâche 15). Chaque critère d'acceptation de la spec §5 est couvert :
1↔Tâche 1, 2↔Tâche 9, 3↔Tâche 10, 4↔Tâche 4, 5↔Tâche 11/12, 6↔Tâche 13,
7↔Tâche 13, 8↔Tâches 6/7/8 (non-régression des appelants existants), 9↔Tâche
2, 10-12↔Tâche 16.

**Espaces réservés** : deux endroits du plan renvoient explicitement à « le
fichier réel, à vérifier avant d'écrire » plutôt qu'à un chemin ou une
signature inventée (Tâche 5 Step 6, Tâche 10 `create_role`/`Role`) — ce
n'est pas un TODO différé mais une consigne explicite de vérification contre
le code réel (CLAUDE.md piège n°3, cohérent avec le reste de ce dépôt qui
préfère ne jamais deviner une signature). Chaque autre étape porte du code
complet.

**Cohérence des types** : `masked_fields`/`masked_fields_by_collection` sont
`frozenset[str]`/`dict[str, frozenset[str]]` de bout en bout entre les
Tâches 11-14 (jamais `list[str]` d'un côté et `set[str]` de l'autre) ;
`rls_scope`/`null_rls_scope`/`get_masked_for_user` utilisent `bool` de bout
en bout entre les Tâches 5-8.
