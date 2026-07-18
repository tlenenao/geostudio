# SPDX-License-Identifier: Apache-2.0
"""Consommateur du flux de réplication logique (SP-11a) : décode les messages
wal2json et pilote le feedback (confirmed_flush_lsn), borné par
CdcBufferManager.safe_ack_lsn côté appelant — jamais après un simple insert,
seulement après un flush GeoParquet réussi (app.cdc.main, Task 9).

Boucle manuelle (read_message + select), pas consume_stream() : il faut
pouvoir déclencher un flush sur seuil de TEMPS même en l'absence de nouveau
message, ce que consume_stream() (bloquant, un seul callback par message
reçu) ne permet pas.

Contrat psycopg2 validé empiriquement par le spike
(core/scripts/spike_cdc_replication.py, Task 1) — DEUX déviations du contrat
présumé, documentées en détail dans le rapport de spike (Task 1, section
« Déviation 1 »), reprises ici :

1. La LSN à passer à `cur.send_feedback(flush_lsn=...)` doit être
   `cur.wal_end` — une propriété du CURSEUR, lue après avoir lu tous les
   messages disponibles — et PAS `msg.data_start`/`msg.wal_end` (attributs du
   MESSAGE, identiques entre eux, qui pointent le DÉBUT de l'enregistrement
   WAL). Confirmer un flush à la position `data_start` ne fait PAS avancer
   `confirmed_flush_lsn` côté serveur (vérifié empiriquement contre
   `pg_replication_slots` par le spike) : le message serait rejoué au drain
   suivant même après un `send_feedback` "réussi" (pas d'exception levée,
   mais aucun effet). `cur.wal_end` pointe réellement au-delà du dernier
   message lu et fait avancer la position de façon vérifiable.
2. Reconnecter immédiatement sur le même slot juste après avoir fermé la
   connexion de réplication précédente peut lever
   `psycopg2.errors.ObjectInUse` ("replication slot ... is active for PID
   ...") — la fermeture du socket côté client ne garantit pas que le
   walsender serveur a déjà relâché le slot au moment où le
   `start_replication` suivant est tenté. Retry borné (10 tentatives, 0.3s de
   backoff), avec réouverture complète de la connexion à chaque tentative.

DÉVIATION SUPPLÉMENTAIRE trouvée pendant Task 7, pas anticipée par le spike
(dont le script draine toujours une fenêtre de plusieurs secondes avant de
lire `cur.wal_end`, masquant ce cas) : lire `cur.wal_end` IMMÉDIATEMENT après
le `read_message()` qui vient de retourner un message peut donner une valeur
encore égale à `data_start` de CE message (wal2json ne fait pas avancer
`walEnd` au sein d'un même paquet XLogData) — auquel cas `send_feedback` de
cette valeur précise n'avance PAS `confirmed_flush_lsn`, exactement le même
symptôme que la déviation 1 ci-dessus, vérifié empiriquement (reproduit et
confirmé sur ~10 essais indépendants, toujours 0 avancement à délai nul).
Un court settle (poll `select()` + un `read_message()` supplémentaire,
`_SETTLE_S = 0.1s`) après réception d'un message, AVANT de lire `cur.wal_end`
pour le tagger, laisse le temps au trafic keepalive du walsender déjà en vol
d'être absorbé et pousse `cur.wal_end` à une valeur qui avance réellement
`confirmed_flush_lsn` — vérifié fiable sur 5 essais indépendants avec un
délai aussi court que 50ms (`_SETTLE_S` prend une marge à 100ms). Compromis
assumé : ce settle ajoute ~100ms de latence par message reçu (acceptable
pour ce produit, pas un système haute fréquence) ; un message supplémentaire
capté pendant ce settle est traité lui aussi, jamais perdu.

INVARIANT INTER-MESSAGES (important pour Task 8, backfill/dedup — pas
encore écrite) : quand le settle capte un message "extra" (une deuxième
transaction, potentiellement indépendante, arrivée dans la fenêtre de
~100ms), `msg` ET `extra` sont tous deux tagués avec la MÊME valeur de
`lsn` (`cur.wal_end`, lue une seule fois — cf. `stream_changes` ci-dessous).
Deux transactions réellement différentes peuvent donc porter un
`ChangeRow.lsn` identique. L'ORDRE D'AJOUT est préservé (`msg` est toujours
traité/bufferisé avant `extra` — cf. `on_message(msg...)` puis
`on_message(extra...)` dans `stream_changes`) : c'est cet ordre, PAS la
valeur numérique de `_lsn`, qui fait foi pour départager deux lignes de
même LSN. Toute logique future de dédoublonnage/backfill qui réduit par
`(pk, max(_lsn))` DOIT traiter les ex-aequo comme "dernier écrit gagne par
ordre d'ajout" et non prendre un maximum arbitraire — une réduction naïve
façon `groupby(pk)['_lsn'].idxmax()` résout les ex-aequo à la PREMIÈRE
occurrence rencontrée, ce qui garderait silencieusement une ligne PÉRIMÉE
au lieu de la plus récente pour deux modifications rapprochées du même
enregistrement tombées dans la même fenêtre de settle.

DÉBIT MESURÉ (review Task 7, Finding 2 — l'estimation a priori de
"10-20 messages/s" au design n'avait jamais été mesurée réellement ; mesure
empirique faite après coup avec `core/scripts/measure_cdc_consumer_throughput.py`,
contre un PostGIS jetable réel, rafales de N INSERT individuels — 1 commit
chacun, simulant N écritures OGC API Features séparées) : le débit réel est
NETTEMENT PLUS ÉLEVÉ que l'estimation a priori, parce que celle-ci supposait
un settle plein (~100ms) payé pour CHAQUE message, alors qu'en pratique
`select.select(..., _SETTLE_S)` retourne dès que le socket a déjà des
octets en attente (ce qui est le cas en continu pendant une rafale déjà
écrite) — le coût du settle n'est réellement payé en entier que lorsque le
flux redevient calme entre deux messages. Mesuré : rafale de 100 messages
(5 runs indépendants) → 61 à 70 messages/s (médiane ~65/s, ~1.4-1.6s de lag
total pour consommer toute la rafale) ; rafale de 300 messages → ~210
messages/s (le coût du settle s'amortit encore mieux sur une rafale plus
large et continue). Aucune perte de données observée sur aucun run (contenu
intégral vérifié). Verdict : ces chiffres sont ACCEPTABLES pour la portée
affichée de ce produit (pas un système haute fréquence — cf. arbitrages
CLAUDE.md) ; un burst de 100 écritures individuelles absorbé en ~1.5s est
largement sous tout seuil de rafale réaliste pour ce produit. Mitigation
déjà en place si le débit réel devait un jour dépasser ce qui est mesuré
ici : `geostudio.cdc.lag_seconds` (Task 3, déjà mergée) rend le retard
observable en production — un consommateur qui prend du retard le fait
VISIBLEMENT (gauge qui grimpe), pas silencieusement, et ne perd aucune
donnée dans l'intervalle (le slot de réplication retient tout jusqu'à
l'ack, le buffer en mémoire n'est jamais vidé avant un flush réussi)."""
import json
import select
import time

import psycopg2
import psycopg2.errors
import psycopg2.extras
from dataclasses import dataclass

from app.cdc.parquet_writer import ChangeRow

SLOT_NAME = "geostudio_cdc_slot"
OUTPUT_PLUGIN = "wal2json"

_RECONNECT_ATTEMPTS = 10
_RECONNECT_BACKOFF_S = 0.3
_SETTLE_S = 0.1


def ensure_replication_slot(raw_dsn: str) -> None:
    """Idempotent. Retry avec backoff sur ObjectInUse (cf. docstring module,
    déviation 2) : peut se produire si un process précédent vient de libérer
    ce même slot (redémarrage rapproché du worker)."""
    for attempt in range(_RECONNECT_ATTEMPTS):
        conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
        cur = conn.cursor()
        try:
            cur.create_replication_slot(SLOT_NAME, output_plugin=OUTPUT_PLUGIN)
            return
        except psycopg2.errors.DuplicateObject:
            return
        except psycopg2.errors.ObjectInUse:
            if attempt == _RECONNECT_ATTEMPTS - 1:
                raise
            time.sleep(_RECONNECT_BACKOFF_S)
        finally:
            cur.close()
            conn.close()


@dataclass
class DecodedChange:
    table_name: str
    row: ChangeRow


def decode_wal2json_message(
    payload: str, *, lsn: int, collection_meta: dict,
) -> list:
    """collection_meta : {table_name: (pk_column, geometry_column)} — résolu
    par app.cdc.main depuis app.collections.models.Collection. Une table
    publiée mais absente de collection_meta (désenregistrée entre-temps, ou
    jamais backfillée par ce process) est ignorée — app.cdc.main la recharge
    et backfille au premier changement vu (Task 8/9)."""
    data = json.loads(payload)
    out = []
    for change in data.get("change", []):
        table_name = change["table"]
        meta = collection_meta.get(table_name)
        if meta is None:
            continue
        pk_column, geometry_column = meta
        kind = change["kind"]
        if kind == "delete":
            keynames = change.get("oldkeys", {}).get("keynames", [])
            keyvalues = change.get("oldkeys", {}).get("keyvalues", [])
            oldkeys = dict(zip(keynames, keyvalues))
            pk_value = oldkeys.get(pk_column)
            row = ChangeRow(
                op="delete", lsn=lsn, ts=0.0, pk_column=pk_column, pk_value=pk_value,
                columns={pk_column: pk_value}, geometry_column=geometry_column,
                geometry_wkb_hex=None,
            )
        else:
            record = dict(zip(change.get("columnnames", []), change.get("columnvalues", [])))
            geom_hex = record.pop(geometry_column, None) if geometry_column else None
            row = ChangeRow(
                op=kind, lsn=lsn, ts=0.0, pk_column=pk_column,
                pk_value=record.get(pk_column), columns=record,
                geometry_column=geometry_column, geometry_wkb_hex=geom_hex,
            )
        out.append(DecodedChange(table_name=table_name, row=row))
    return out


def _start_replication_with_retry(raw_dsn: str):
    """Connexion + start_replication avec retry sur ObjectInUse (cf. docstring
    module, déviation 2). Réouvre la connexion en entier à chaque tentative —
    une connexion ayant essuyé un ObjectInUse peut être dans un état
    invalide, pas seulement retenter start_replication dessus."""
    conn = None
    cur = None
    for attempt in range(_RECONNECT_ATTEMPTS):
        conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
        cur = conn.cursor()
        try:
            cur.start_replication(
                slot_name=SLOT_NAME,
                options={"pretty-print": "0", "include-pk": "1"},
            )
            return conn, cur
        except psycopg2.errors.ObjectInUse:
            cur.close()
            conn.close()
            if attempt == _RECONNECT_ATTEMPTS - 1:
                raise
            time.sleep(_RECONNECT_BACKOFF_S)
    raise AssertionError("unreachable")  # pragma: no cover


def stream_changes(
    raw_dsn: str, *, on_message, is_flush_due, do_flush,
    should_stop=lambda: False, poll_timeout_s: float = 1.0,
) -> None:
    """Boucle jusqu'à should_stop() (par défaut : jamais — le process
    cdc-worker tourne indéfiniment). `on_message(payload, lsn)` décode et
    bufferise ; `is_flush_due()`/`do_flush()` sont rappelés à CHAQUE
    itération, message reçu ou non — c'est ce qui permet le flush par âge
    (30s) sur un flux calme. `do_flush()` retourne la LSN à confirmer (ou
    None si rien à confirmer).

    `lsn` passé à `on_message` est `cur.wal_end` (propriété du CURSEUR), lue
    APRÈS un court settle suivant la réception d'un message — PAS
    `msg.data_start`/`msg.wal_end` (attributs du message), et PAS non plus
    `cur.wal_end` lu au tout premier instant (cf. docstring module,
    déviation supplémentaire). C'est cette valeur qui, propagée jusqu'à
    ChangeRow.lsn puis CdcBufferManager.safe_ack_lsn(), est envoyée à
    `send_feedback` plus bas — toute la chaîne doit rester dans l'espace
    d'adresses LSN que le serveur reconnaît réellement pour ce mécanisme."""
    conn, cur = _start_replication_with_retry(raw_dsn)
    try:
        while not should_stop():
            msg = cur.read_message()
            if msg:
                # Settle avant de figer la LSN de ce message (cf. docstring
                # module) : sans ce délai, cur.wal_end peut encore valoir
                # data_start du message qu'on vient de lire, et le
                # send_feedback ultérieur basé dessus n'avancerait pas
                # confirmed_flush_lsn. Un message supplémentaire capté
                # pendant le settle est traité aussi, jamais perdu.
                select.select([conn], [], [], _SETTLE_S)
                extra = cur.read_message()
                lsn = cur.wal_end
                on_message(msg.payload, lsn)
                if extra:
                    on_message(extra.payload, lsn)
            if is_flush_due():
                ack_lsn = do_flush()
                if ack_lsn is not None:
                    cur.send_feedback(flush_lsn=ack_lsn, reply=True, force=True)
            if not msg:
                select.select([conn], [], [], poll_timeout_s)
    finally:
        cur.close()
        conn.close()
