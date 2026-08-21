# SPDX-License-Identifier: Apache-2.0
"""Spike SP-11a : CDC via réplication logique PostgreSQL + wal2json.

Vérifie, DANS L'ORDRE, contre un PostGIS jetable réel (wal_level=logical,
extension wal2json installée — cf. deploy/postgis/Dockerfile) :
1. création idempotente d'un slot de réplication logique avec le plugin
   wal2json ;
2. insert/update/delete sur une table avec colonne géométrie, décodés
   correctement depuis le flux wal2json ;
3. ALTER PUBLICATION ... ADD TABLE dynamique alors que le slot existe déjà
   (la nouvelle table doit apparaître dans le flux sans recréer le slot) ;
4. un cycle crash-simulé/redémarrage : un message consommé mais jamais
   confirmé (send_feedback) doit être rejoué à l'identique après
   reconnexion sur le même slot (at-least-once, jamais de perte).

Si un de ces points échoue durement, le plan s'arrête avant d'investir dans
le worker complet (spec SP-11a §Risques) — documenter l'échec et retourner
en brainstorm/spec plutôt que de continuer sur les tasks suivantes.

Usage :
  SPIKE_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@127.0.0.1:5432/gis \
    uv run python -m scripts.spike_cdc_replication
Connexion DIRECTE à postgis (pas pgbouncer:6432) — le protocole de
réplication logique n'est pas supporté en pool "transaction".
Sort avec le code 0 (PASS) ou 1 (FAIL, échecs listés).
"""

import json
import os
import select
import sys
import time

import psycopg2
import psycopg2.errors
import psycopg2.extras
from sqlalchemy import create_engine, text

SLOT_NAME = "spike_cdc_slot"
PUBLICATION_NAME = "spike_cdc_pub"


def _setup_tables(dsn: str) -> None:
    engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    with engine.begin() as c:
        c.execute(text(f"DROP PUBLICATION IF EXISTS {PUBLICATION_NAME}"))
        c.execute(text("DROP TABLE IF EXISTS spike_cdc_t1, spike_cdc_t2"))
        c.execute(
            text(
                "CREATE TABLE spike_cdc_t1 (id serial PRIMARY KEY, v text, "
                "geom geometry(Point, 4326))"
            )
        )
        c.execute(text("CREATE TABLE spike_cdc_t2 (id serial PRIMARY KEY, v text)"))
        c.execute(text(f"CREATE PUBLICATION {PUBLICATION_NAME} FOR TABLE spike_cdc_t1"))
    engine.dispose()


def _ensure_slot(raw_dsn: str) -> None:
    conn = psycopg2.connect(
        raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection
    )
    cur = conn.cursor()
    try:
        cur.create_replication_slot(SLOT_NAME, output_plugin="wal2json")
    except psycopg2.errors.DuplicateObject:
        pass
    cur.close()
    conn.close()


def _drain_messages(raw_dsn: str, *, ack: bool, timeout_s: float = 5.0) -> list[dict]:
    """Consomme le flux pendant `timeout_s`. N'accuse réception (send_feedback)
    qu'à la fin, et seulement si `ack=True` — reproduit le contrat "flush S3
    réussi -> feedback" du worker réel : tant que `ack=False`, un redémarrage
    doit tout rejouer.

    DÉVIATION vs le contrat présumé par le plan : la LSN à envoyer à
    `send_feedback` doit être `cur.wal_end` (propriété du CURSEUR, lue une
    fois après la boucle de lecture) — PAS `msg.data_start` ni `msg.wal_end`
    (attribut par message). Empiriquement, `msg.wal_end` est identique à
    `msg.data_start` pour un message XLogData (les deux pointent le DÉBUT de
    l'enregistrement WAL) ; confirmer un flush à cette position ne retire pas
    le message côté serveur, qui est rejoué au prochain drain même après un
    `ack=True` "réussi". Seule `cur.wal_end`, mise à jour par le curseur au
    fil de la lecture du flux, pointe au-delà du dernier message consommé et
    fait réellement avancer `confirmed_flush_lsn` du slot (vérifié contre
    `pg_replication_slots`).

    DEUXIÈME DÉVIATION : reconnecter immédiatement sur le même slot juste
    après avoir fermé la connexion de réplication précédente peut lever
    `psycopg2.errors.ObjectInUse` ("replication slot ... is active for PID
    ...") — la fermeture du socket côté client (`conn.close()`) ne garantit
    pas que le walsender serveur a déjà relâché le slot au moment où le
    `start_replication` suivant est tenté. Retry court avec backoff, borné,
    plutôt qu'un simple `raise` — pertinent pour Task 7, dont le worker réel
    ne reconnecte qu'après un redémarrage (même risque de course)."""
    conn = None
    cur = None
    for attempt in range(10):
        conn = psycopg2.connect(
            raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection
        )
        cur = conn.cursor()
        try:
            cur.start_replication(slot_name=SLOT_NAME, options={"pretty-print": "0"})
            break
        except psycopg2.errors.ObjectInUse:
            cur.close()
            conn.close()
            if attempt == 9:
                raise
            time.sleep(0.3)
    messages: list[dict] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        msg = cur.read_message()
        if msg:
            messages.append(json.loads(msg.payload))
            continue
        select.select([conn], [], [], 0.5)
    if ack:
        cur.send_feedback(flush_lsn=cur.wal_end, reply=True, force=True)
    cur.close()
    conn.close()
    return messages


def main() -> int:
    dsn = os.environ["SPIKE_DATABASE_URL"]
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    _setup_tables(dsn)

    # 1. Création idempotente du slot.
    _ensure_slot(dsn)
    _ensure_slot(dsn)  # ne doit pas lever la deuxième fois
    check("slot créé de façon idempotente", True)

    # 2. insert/update/delete décodés, géométrie présente.
    engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO spike_cdc_t1 (v, geom) VALUES "
                "('a', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
            )
        )
        c.execute(text("UPDATE spike_cdc_t1 SET v = 'b' WHERE v = 'a'"))
        c.execute(text("DELETE FROM spike_cdc_t1 WHERE v = 'b'"))
    msgs = _drain_messages(dsn, ack=False)
    changes = [ch for m in msgs for ch in m.get("change", [])]
    kinds = [ch["kind"] for ch in changes]
    check("insert/update/delete tous décodés", kinds == ["insert", "update", "delete"])
    insert_change = changes[0]
    geom_idx = insert_change["columnnames"].index("geom")
    geom_value = insert_change["columnvalues"][geom_idx]
    check("colonne géométrie présente et non vide", bool(geom_value))
    delete_change = changes[2]
    check("delete n'expose que la clé (oldkeys)", "oldkeys" in delete_change)

    # 3. ALTER PUBLICATION ADD TABLE dynamique, slot déjà existant.
    with engine.begin() as c:
        c.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} ADD TABLE spike_cdc_t2"))
        c.execute(text("INSERT INTO spike_cdc_t2 (v) VALUES ('new-table')"))
    msgs2 = _drain_messages(dsn, ack=True, timeout_s=5.0)
    changes2 = [ch for m in msgs2 for ch in m.get("change", [])]
    check(
        "table ajoutée après coup apparaît dans le flux sans recréer le slot",
        any(ch["table"] == "spike_cdc_t2" for ch in changes2),
    )

    # 4. Crash simulé : message consommé sans ack, doit être rejoué.
    with engine.begin() as c:
        c.execute(text("INSERT INTO spike_cdc_t1 (v, geom) VALUES ('crash-test', NULL)"))
    first_drain = _drain_messages(dsn, ack=False, timeout_s=3.0)
    first_changes = [ch for m in first_drain for ch in m.get("change", [])]
    check("message crash-test bien reçu avant le crash simulé", len(first_changes) == 1)
    second_drain = _drain_messages(
        dsn, ack=False, timeout_s=3.0
    )  # "redémarrage" : nouvelle connexion, même slot
    second_changes = [ch for m in second_drain for ch in m.get("change", [])]
    check(
        "message non-acké rejoué à l'identique après reconnexion",
        second_changes == first_changes,
    )
    _drain_messages(dsn, ack=True, timeout_s=3.0)  # ack final, nettoyage
    third_drain = _drain_messages(dsn, ack=False, timeout_s=2.0)
    third_changes = [ch for m in third_drain for ch in m.get("change", [])]
    # NB : third_drain lui-même peut contenir un message wal2json avec un
    # "change" vide (transaction concurrente ailleurs dans le cluster, sans
    # rapport avec spike_cdc_t1/t2) — comme les autres checks, on compare la
    # liste de changements APLATIE, pas la liste brute des messages.
    check("plus rien à rejouer une fois acké", third_changes == [])

    with engine.begin() as c:
        c.execute(text(f"DROP PUBLICATION IF EXISTS {PUBLICATION_NAME}"))
        c.execute(text("DROP TABLE IF EXISTS spike_cdc_t1, spike_cdc_t2"))
    conn = psycopg2.connect(dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    try:
        cur.drop_replication_slot(SLOT_NAME)
    except Exception:
        pass
    cur.close()
    conn.close()
    engine.dispose()

    print("\nRésultat spike :", "PASS" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
