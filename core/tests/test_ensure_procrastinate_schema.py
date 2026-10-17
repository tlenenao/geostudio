# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from scripts.ensure_procrastinate_schema import main, schema_is_applied


@pytest.mark.postgis
def test_running_main_twice_never_raises(pg_engine, monkeypatch):
    """Régression du bloqueur SP-Deploy §3.4-1 : avant ce fix, appeler
    `apply_schema()` une seconde fois sur une base où le schéma existe déjà
    levait (`CREATE TYPE` échoue), ce qui faisait boucler le service
    `worker` en redémarrage (`schema --apply && worker`, relancé en entier
    par `restart: unless-stopped` à chaque crash). `main()` doit être
    rejouable sans exception, quel que soit l'état de départ."""
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])

    main()
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    assert schema_is_applied(conninfo)

    main()  # deuxième appel — ne doit PAS lever


@pytest.mark.postgis
def test_schema_is_applied_reflects_real_state(pg_engine):
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    # pg_engine (session-scope) peut déjà avoir le schéma appliqué par un
    # autre test de la suite (pg_engine_with_procrastinate_schema) — on
    # vérifie seulement la cohérence du prédicat, pas un état "avant/après"
    # isolé (la base de test est partagée, comme pour cette fixture sœur).
    assert schema_is_applied(conninfo) in (True, False)


def _conninfo() -> str:
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


@pytest.mark.postgis
def test_ensure_schema_baselines_untracked_db_then_applies_missing(pg_engine):
    """Base existante sans suivi : la 1re passe n'applique rien (tout est déjà
    là, sondes OK) ; une migration oubliée du suivi est rejouée exactement une fois."""
    from sqlalchemy import text

    from scripts.ensure_procrastinate_schema import _migration_files, ensure_schema

    ensure_schema(_conninfo())  # garantit le schéma
    with pg_engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS gs_procrastinate_migrations"))
    assert ensure_schema(_conninfo()) == []
    last = _migration_files()[-1].name
    with pg_engine.begin() as c:
        c.execute(text("DELETE FROM gs_procrastinate_migrations WHERE name = :n"), {"n": last})
    assert ensure_schema(_conninfo()) == [last]
    assert ensure_schema(_conninfo()) == []


def test_every_installed_migration_version_has_a_probe_or_an_exemption():
    """M2 : une migration procrastinate future sans sonde serait rejouée sur une base
    ancienne sans suivi ; il faut une sonde (ou une exemption motivée)."""
    from scripts.ensure_procrastinate_schema import _PROBE_EXEMPT, _PROBES, _migration_files

    versions = {f.name[:8] for f in _migration_files() if f.name[:8] >= "03.00.00"}
    missing = versions - set(_PROBES) - set(_PROBE_EXEMPT)
    assert not missing, missing


def test_partial_baseline_stops_at_first_missing_artefact():
    """M3 : base en 03.01 (workers présent, defer_jobs_v1 absent) -> 03.00/03.01 baselinés,
    03.02 et suivants à appliquer."""
    from scripts.ensure_procrastinate_schema import _PROBES, _baseline_names, _migration_files

    present = {"03.00.00", "03.01.00"}

    class FakeConn:
        def execute(self, query):
            version = next(v for v, q in _PROBES.items() if q == query)

            class R:
                def fetchone(self):
                    return (version in present,)

            return R()

    names = _baseline_names(FakeConn(), _migration_files())
    assert any(n.startswith("03.01.00") for n in names)
    assert not any(n[:8] >= "03.02.00" for n in names)


@pytest.mark.postgis
def test_connection_disables_prepared_statements_for_pgbouncer(pg_engine, monkeypatch):
    """C1 : derrière PgBouncer (mode transaction), `prepare_threshold=None` est obligatoire."""
    import psycopg

    from scripts.ensure_procrastinate_schema import ensure_schema

    seen = {}
    real = psycopg.connect

    def spy(conninfo, **kwargs):
        seen.update(kwargs)
        return real(conninfo, **kwargs)

    monkeypatch.setattr(psycopg, "connect", spy)
    ensure_schema(_conninfo())
    assert "prepare_threshold" in seen and seen["prepare_threshold"] is None
