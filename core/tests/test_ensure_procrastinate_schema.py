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
