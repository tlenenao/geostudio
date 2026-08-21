# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité du worker CDC (SP-21, chantier 1.6).

Un `docker healthcheck` qui ne vérifie que la présence du process ne détecte
pas le cas que I5 nomme explicitement — « un worker vivant mais bloqué ».
Pour le CDC, il existe un signal serveur direct et fiable :
`pg_replication_slots.active`, à true seulement tant qu'un consommateur tient
le slot. C'est ce que teste cette sonde."""

from scripts.healthcheck_cdc import SLOT_NAME, slot_is_active


class _FakeConnection:
    """Assez de `psycopg` pour cette sonde : `execute(...).fetchone()`."""

    def __init__(self, row):
        self._row = row
        self.executed: list[tuple] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self._row


def test_slot_is_active_when_a_consumer_holds_it():
    conn = _FakeConnection((True,))
    assert slot_is_active(conn, SLOT_NAME) is True
    sql, params = conn.executed[0]
    assert "pg_replication_slots" in sql
    assert params == (SLOT_NAME,)  # jamais interpolé dans le SQL


def test_slot_is_inactive_when_nobody_consumes_it():
    """Le cas qui compte : le slot existe (donc le WAL s'accumule) mais
    personne ne le draine — process vivant, réplication morte."""
    assert slot_is_active(_FakeConnection((False,)), SLOT_NAME) is False


def test_missing_slot_is_not_healthy():
    """Slot absent : le worker n'a pas encore fini son `ensure_replication_slot`,
    ou il a échoué. Dans les deux cas, pas sain."""
    assert slot_is_active(_FakeConnection(None), SLOT_NAME) is False


# `test_slot_name_matches_the_consumer` (revue finale SP-21, item 7) a été
# supprimé : `scripts/healthcheck_cdc.py` fait `from app.cdc.consumer import
# SLOT_NAME` (ligne 17) — il n'existe qu'un seul site de définition, et ce
# test relisait cette même valeur par la même chaîne d'import pour
# l'affirmer égale à elle-même. Aucune divergence n'est possible tant que ce
# site d'import reste le seul ; le garde-fou réel est cet import lui-même,
# pas un test qui ne peut structurellement jamais échouer.


def test_main_returns_non_zero_without_a_dsn(monkeypatch):
    from scripts.healthcheck_cdc import main

    monkeypatch.delenv("CDC_DATABASE_URL", raising=False)
    assert main() == 1
