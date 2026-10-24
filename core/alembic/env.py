import os
import sys
import time
from logging.config import fileConfig
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Add parent directory to sys.path so 'app' module can be imported when alembic is invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audit import models as audit_models  # noqa: F401
from app.configs import (
    models as configs_models,  # noqa: F401 — registers Config/ConfigRevision on Base.metadata
)
from app.db import Base
from app.items import models as items_models  # noqa: F401
from app.migration_guard import refuse_destructive_downgrade
from app.sharing import models as sharing_models  # noqa: F401
from app.tenants import models as tenants_models  # noqa: F401
from app.users import models as users_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url", os.environ.get("CORE_MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]
)
target_metadata = Base.metadata
# Clé arbitraire stable du verrou de migration (ASCII « GEOSTUDI »).
MIGRATION_LOCK_KEY = 0x47454F5354554449


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _guard_destructive_downgrade(connection) -> None:
    """AUD-192 : refuse, avant toute étape, un downgrade qui détruirait des lignes."""
    script = ScriptDirectory.from_config(config)
    current = context.get_context().get_current_heads()
    if not current:
        return
    target = context.get_revision_argument() or "base"
    try:  # résolution d'alembic (`-1`, `base`, id) ; une montée de version n'a rien à descendre
        steps = script._downgrade_revs(target, tuple(current))
    except Exception:
        return
    downgraded = {step.revision.revision for step in steps}
    if downgraded:
        refuse_destructive_downgrade(connection, downgraded)
        connection.rollback()  # fin de la transaction de lecture, alembic ouvre la sienne


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # ARC-32 : N réplicas `core` lancent `alembic upgrade head` au démarrage. Verrou consultatif de
    # SESSION sur une connexion AUTOCOMMIT dédiée : ni un verrou de transaction (il disparaît au
    # commit des `autocommit_block` des migrations 0045/0049), ni une transaction ouverte (elle
    # bloquerait leur CREATE INDEX CONCURRENTLY, qui attend tous les virtualxid) ne conviennent.
    # Les suivants attendent, puis voient « déjà à jour ».
    # ATTENTION : un verrou de session exige une connexion DIRECTE à Postgres (pas PgBouncer en mode
    # transaction) -> CORE_MIGRATION_DATABASE_URL (compose/Helm) ; sans elle, best effort.
    with connectable.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
        locked = lock_conn.dialect.name == "postgresql"
        if locked:
            # Sondage `pg_try_advisory_lock`, jamais `pg_advisory_lock` bloquant : un suiveur
            # bloqué DANS une requête garderait un virtualxid que le CREATE INDEX CONCURRENTLY du
            # leader attend -> interblocage invisible de Postgres. Entre deux sondes : inactif.
            while not lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY}
            ).scalar():
                time.sleep(0.5)
        try:
            with connectable.connect() as connection:
                if connection.dialect.name == "postgresql":
                    # AUD-188 : une migration n'attend pas indéfiniment un verrou (elle bloquerait
                    # lectures/écritures derrière elle) ni ne tourne sans borne. Ajustables.
                    for guc, var, default in (
                        ("lock_timeout", "CORE_MIGRATION_LOCK_TIMEOUT", "30s"),
                        ("statement_timeout", "CORE_MIGRATION_STATEMENT_TIMEOUT", "30min"),
                    ):
                        connection.exec_driver_sql(f"SET {guc} = '{os.environ.get(var, default)}'")
                    connection.commit()
                context.configure(connection=connection, target_metadata=target_metadata)
                _guard_destructive_downgrade(connection)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            if locked:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
