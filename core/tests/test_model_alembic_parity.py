# SPDX-License-Identifier: Apache-2.0
"""Compare le schéma réel produit par `alembic upgrade head` au schéma déclaré
par les modèles SQLAlchemy (Base.metadata) — filet transverse de SP-43 Étape 0.
Sans lui, un `server_default=` ajouté en migration mais oublié sur le
`mapped_column` correspondant (ou l'inverse) est invisible : la suite pytest
construit son schéma via `Base.metadata.create_all()` (jamais via Alembic),
donc un défaut qui n'existe qu'en production migrée ne peut jamais être vu
par aucun autre test du dépôt (cf. F-tests-01, sp42-findings.jsonl).

Patron de fixture identique à test_metadata_migration_alembic.py /
test_attachments_migration_alembic.py : base jetable Postgres créée et
détruite par ce test, jamais le schéma partagé postgis-test. `Config()`
volontairement SANS fichier ini (cf. ces deux tests) : `Config("alembic.ini")`
désactiverait silencieusement des loggers d'autres modules du cœur via
`fileConfig(disable_existing_loggers=True)`.

Deux pièges vérifiés en écrivant ce test (ni l'un ni l'autre n'était dans le
brief initial — le texte littéral d'un plan est régulièrement faux sur les
interfaces tierces, cf. piège n°3 CLAUDE.md) :

1. `core/alembic/env.py` ignore `cfg.set_main_option("sqlalchemy.url", ...)`
   — il lit toujours `os.environ["DATABASE_URL"]` sans condition (ligne
   `config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])`).
   Il faut donc positionner la variable d'environnement `DATABASE_URL`, pas
   seulement l'option de Config, sous peine de migrer silencieusement la
   mauvaise base (ou de lever un `KeyError`).
2. `from app.db import Base` seul ne suffit PAS à peupler `Base.metadata` :
   les 22 modules `models.py` du dépôt ne s'enregistrent qu'à l'import, et
   rien n'importe le module `app.attachments.models` (ni
   `app.pipelines.models`, etc.) tant qu'on ne le fait pas explicitement —
   `core/alembic/env.py` lui-même n'en importe qu'une poignée (suffisant
   pour `upgrade head`, qui rejoue des migrations écrites à la main, mais
   pas pour un `compare_metadata()` qui a besoin du jeu complet). Sans ce
   peuplement, `compare_metadata()` échoue même en `NoReferencedTableError`
   (clé étrangère vers une table absente du metadata) avant de produire un
   diff exploitable. Solution : appeler `app.db.core_table_names()`, la
   fonction qui importe déjà les 22 modules pour ce même besoin ailleurs
   dans le cœur (`init_db`, denylist du registre de collections) — source
   unique, pas de liste dupliquée à tenir à jour ici.

Un troisième piège, trouvé par la revue de cette même tâche (Important #1) :
`compare_metadata()` enveloppe TOUJOURS les diffs de niveau colonne
(`modify_type`/`modify_nullable`/`modify_default`/`modify_comment`, produits
par `AlterColumnOp.to_diff_tuple()`, cf. `alembic/operations/ops.py`) dans
une **sous-liste**, même pour un seul changement sur une seule colonne —
`[('modify_type', ...)]`, jamais `('modify_type', ...)` nu. Seuls les ops de
niveau table (`add_table`/`remove_table`/`add_column`/`add_constraint`/
`remove_index`/...) reviennent en tuples nus au premier niveau. Un filtre
qui teste `d[0] == "modify_type"` sans aplatir d'abord ne peut donc jamais
s'activer : `d[0]` est alors le tuple imbriqué lui-même, jamais la chaîne.
`_flatten_diff()` ci-dessous aplatit avant tout filtrage ; falsifié par
`test_filter_real_diff_absorbs_a_nested_geometry_modify_type` plus bas."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command
from app.collections.routes import POSTGIS_SYSTEM_TABLES
from app.db import Base, core_table_names  # chemin confirmé par grep (Step 1) : core/app/db.py

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"sp43_migration_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    throwaway_url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", base_url)
    throwaway_engine = sa.create_engine(throwaway_url, isolation_level="AUTOCOMMIT")
    with throwaway_engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    throwaway_engine.dispose()
    try:
        yield throwaway_url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def _alembic_config(db_url: str) -> Config:
    # Config() SANS chemin de fichier ini : cf. test_attachments_migration_alembic.py
    # / test_metadata_migration_alembic.py (SP-40/SP-41) pour l'explication complète.
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_model_metadata_matches_migrated_schema(throwaway_database_url):
    cfg = _alembic_config(throwaway_database_url)
    # core/alembic/env.py lit inconditionnellement DATABASE_URL (pas l'option
    # de Config) : la positionner est nécessaire, pas seulement cosmétique.
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

    # Peuple Base.metadata avec les 22 modules models.py du dépôt — sans quoi
    # compare_metadata() lève NoReferencedTableError sur la première clé
    # étrangère vers une table dont le module n'a jamais été importé.
    core_table_names()

    engine = sa.create_engine(throwaway_database_url)
    with engine.connect() as conn:
        # compare_server_default=False est le défaut d'Alembic (comparer les
        # défauts serveur entre dialectes est jugé peu fiable en général) —
        # sans ce override, exactement les divergences que ce filet doit
        # attraper (server_default= oublié côté modèle) restent invisibles.
        ctx = MigrationContext.configure(conn, opts={"compare_server_default": True})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()

    real_diff = _filter_real_diff(diff)
    assert real_diff == [], (
        "Schéma migré (Alembic head) et Base.metadata divergent : "
        f"{real_diff}\nCorriger le server_default= manquant côté modèle "
        "OU la migration manquante côté Alembic — ne jamais supprimer ce "
        "test pour faire passer un diff réel."
    )


def _flatten_diff(diff_list: list) -> list:
    """`compare_metadata()` renvoie une liste où chaque élément est SOIT un
    tuple nu (ops de niveau table : add_table/remove_table/add_column/
    add_constraint/remove_index/...), SOIT une sous-liste d'un ou plusieurs
    tuples imbriqués (ops de niveau colonne : `AlterColumnOp.to_diff_tuple()`
    empile modify_type/modify_nullable/modify_default/modify_comment pour
    UNE colonne dans une seule sous-liste, même s'il n'y en a qu'un — cf.
    `alembic/operations/ops.py`). Aplatir ici avant tout filtrage : sans ça,
    `d[0] == "modify_type"` compare une chaîne à un tuple imbriqué et n'est
    jamais vrai (Important #1, revue Tâche 1 SP-43)."""
    flat: list = []
    for item in diff_list:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def _filter_real_diff(diff: list) -> list:
    """Aplatit puis retire le bruit structurel qui n'est jamais un vrai écart
    de schéma imputable à nos modèles : types géométrie/pgvector (leur
    représentation SQLAlchemy générique diffère toujours du type natif
    Postgres) et tables système PostGIS (créées par `CREATE EXTENSION`,
    jamais déclarées par nos modèles)."""
    flat_diff = _flatten_diff(diff)
    ignored_kinds = {"geometry", "vector"}

    def _is_postgis_system_table(item: object) -> bool:
        return getattr(item, "name", None) in POSTGIS_SYSTEM_TABLES

    return [
        d
        for d in flat_diff
        if not (
            d[0] == "modify_type"
            and (
                getattr(d[6], "__visit_name__", "") in ignored_kinds
                or getattr(d[5], "__visit_name__", "") in ignored_kinds
            )
        )
        # spatial_ref_sys (etc.) : table système PostGIS, cf.
        # app.collections.routes.POSTGIS_SYSTEM_TABLES — sera toujours "en
        # trop" pour compare_metadata, indépendamment de tout défaut de nos
        # modèles ; ne pas la laisser polluer le signal de la Tâche 5.
        and not (d[0] == "remove_table" and _is_postgis_system_table(d[1]))
    ]


class _FakeVisitedType:
    """Imite un type SQLAlchemy dont `__visit_name__` identifie une colonne
    géométrie/pgvector (les vrais `Geometry`/`Vector` portent cet attribut) —
    fabriqué à la main pour ne pas dépendre de geoalchemy2/pgvector dans ce
    test de filtrage isolé."""

    def __init__(self, visit_name: str) -> None:
        self.__visit_name__ = visit_name


def test_filter_real_diff_absorbs_a_nested_geometry_modify_type() -> None:
    """Falsification de la correction de l'Important #1 (revue Tâche 1
    SP-43) : reproduit la forme RÉELLE d'un item modify_type retourné par
    compare_metadata() — une sous-liste contenant un seul tuple, jamais un
    tuple nu — pour une colonne dont le type divergent est reconnu comme
    geometry/vector. AVANT la correction (filtre non aplati, testant
    `d[0] == "modify_type"` directement sur l'élément de la liste externe),
    cet item glissait tel quel dans real_diff car `d[0]` valait alors le
    tuple imbriqué, jamais la chaîne "modify_type" : la condition était
    donc toujours fausse et le filtre ne s'activait jamais. APRÈS
    (`_filter_real_diff`, qui aplatit d'abord via `_flatten_diff`), l'item
    est bien absorbé."""
    fake_diff_item = [
        (
            "modify_type",
            None,
            "some_table",
            "geom",
            {
                "existing_nullable": False,
                "existing_server_default": None,
                "existing_comment": None,
            },
            _FakeVisitedType("VARCHAR"),
            _FakeVisitedType("geometry"),
        )
    ]
    fake_diff = [fake_diff_item]

    # Preuve du défaut AVANT correction : la version naïve (celle du commit
    # initial de cette tâche, non aplatie) ne filtre RIEN — elle compare la
    # sous-liste elle-même à la chaîne "modify_type", toujours faux.
    naive_filtered = [
        d
        for d in fake_diff
        if not (
            d[0] == "modify_type"
            and (
                getattr(d[6], "__visit_name__", "") in {"geometry", "vector"}
                if len(d) > 6
                else False
            )
        )
    ]
    assert naive_filtered == fake_diff, (
        "cette assertion documente le bug corrigé : la version naïve "
        "(non aplatie) ne filtre jamais un modify_type imbriqué, puisque "
        "d[0] y est une sous-liste et non la chaîne 'modify_type'"
    )

    # La fonction réelle du fichier (corrigée, aplatit avant de filtrer)
    # absorbe bien l'item fabriqué.
    assert _filter_real_diff(fake_diff) == []
