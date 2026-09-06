# SPDX-License-Identifier: Apache-2.0
"""Backfill initial par collection (SP-11a §Flux de données/Backfill initial).

Décision de conception (ce plan, au-delà du texte de la spec) : pas
d'EXPORT_SNAPSHOT. On lit pg_current_wal_lsn() juste avant de démarrer
START_REPLICATION, puis on SELECT * chaque collection déjà enregistrée,
taguée avec cette LSN comme borne. C'est safe parce que le slot capture déjà,
depuis sa création (ou son dernier confirmed_flush_lsn sur une reprise), tout
changement WAL — un changement qui arrive entre la lecture de la LSN-frontière
et le SELECT * sera de toute façon redélivré par le flux live avec sa vraie
LSN (plus grande), qui l'emporte dans la réduction (pk, max(_lsn)) côté
lecteur : au pire quelques doublons inoffensifs, jamais de perte ni de
fantôme. Pour une collection enregistrée APRÈS que le slot existe déjà, le
même mécanisme s'applique au premier changement vu pour une table inconnue
(app.cdc.main, Task 9) — pas de notification poussée depuis apply_collection_ddl.

Normalisation Decimal→float (correctif post-Task 11, cf. task-11-report.md
§Critère 3) : `SELECT *` en SQL brut renvoie les colonnes NUMERIC/DECIMAL
comme `decimal.Decimal` via SQLAlchemy/psycopg, alors que
`consumer.decode_wal2json_message` décode le même type de colonne depuis le
JSON wal2json en `float` Python (JSON n'a pas de type décimal). Les deux
chemins alimentent le même buffer/flush (CdcBufferManager, app.cdc.main) ;
un lot qui mélange une ligne de backfill (Decimal) et une ligne rejouée du
flux live (float) pour la MÊME colonne NUMERIC fait échouer
`pa.Table.from_pandas` (appelé par `GeoDataFrame.to_parquet`) avec
`ArrowTypeError`, de façon déterministe et permanente (le worker refait le
même backfill et rejoue les mêmes messages non ackés à chaque redémarrage).
`_normalize_record` convertit tout `Decimal` en `float` ici, pour aligner
le backfill sur le type déjà produit par le chemin live — pas une perte de
précision par rapport à ce que ce dernier produit déjà.

Normalisation DATE/TIMESTAMP/UUID→str (extension post-Task 11, même classe
de bug, cf. task-11-fix-report.md) : `SELECT *` brut renvoie aussi
`datetime.date`/`datetime.datetime` (colonnes DATE/TIMESTAMP/TIMESTAMPTZ)
et `uuid.UUID` (colonnes UUID) comme objets Python typés, alors que
wal2json n'a aucun type JSON natif pour ceux-ci et les émet comme chaînes
dans le payload JSON — `json.loads` produit donc des `str` côté
`decode_wal2json_message`. Même risque de mélange de types dans un même lot
de flush que pour NUMERIC. Vérifié empiriquement (contre un PostGIS+
wal2json réel, colonnes DATE/TIMESTAMP/TIMESTAMPTZ/UUID, script one-off non
commité) que le format de chaîne émis par wal2json pour DATE et UUID
coïncide exactement avec `date.isoformat()`/`str(uuid.UUID)`, mais PAS pour
TIMESTAMP/TIMESTAMPTZ : `datetime.isoformat()` sépare date et heure par
"T" et affiche toujours les minutes d'offset UTC (ex. `+00:00`), alors que
wal2json (qui reprend la représentation texte native de Postgres) sépare
par un espace et omet les minutes/secondes d'offset quand elles sont
nulles (ex. `+00`, `+05:30` mais jamais `+00:00`) — confirmé pour plusieurs
offsets (`+00`, `+05`, `+05:30`, `-05:30`) via `SET timezone` + lecture
`::text` côté serveur. `_pg_timestamp_str` reproduit ce format Postgres
plutôt que `.isoformat()` brut pour les valeurs `datetime.datetime`."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cdc.parquet_writer import ChangeRow
from app.sql_ident import quote_ident


def _pg_timestamp_str(dt: datetime) -> str:
    """Reproduit le format texte natif de Postgres pour TIMESTAMP/
    TIMESTAMPTZ (celui que wal2json émet dans son payload JSON), PAS
    `datetime.isoformat()` : séparateur espace (pas "T"), microsecondes
    omises si nulles et sinon rendues SANS les zéros de fin (Postgres émet
    `.5` pour 500000µs, `.12` pour 120000µs, `.123456` seulement quand les 6
    chiffres sont significatifs — contrairement à `isoformat()`, qui pad
    toujours sur 6 chiffres), offset UTC omettant les minutes/secondes
    quand elles sont nulles (`+00`, `+05`, `+05:30` — jamais `+00:00`,
    contrairement à isoformat)."""
    s = dt.strftime("%Y-%m-%d %H:%M:%S")
    if dt.microsecond:
        s += f".{dt.microsecond:06d}".rstrip("0")
    if dt.tzinfo is not None:
        offset = dt.utcoffset()
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hh, rem = divmod(total_seconds, 3600)
        mm, ss = divmod(rem, 60)
        s += f"{sign}{hh:02d}"
        if mm or ss:
            s += f":{mm:02d}"
            if ss:
                s += f":{ss:02d}"
    return s


def _normalize_value(v):
    """Convertit une valeur issue d'un `SELECT *` brut vers la même
    représentation que produirait `decode_wal2json_message` (JSON n'a pas de
    type décimal/date/UUID natif) pour le même type de colonne — générique,
    aucun nom de colonne codé en dur. `datetime.datetime` est une
    sous-classe de `datetime.date` : l'ordre des `isinstance` compte."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return _pg_timestamp_str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def _normalize_record(record: dict) -> dict:
    """Convertit toute valeur `decimal.Decimal`/`datetime.date`/
    `datetime.datetime`/`uuid.UUID` du dict vers la représentation déjà
    produite par le chemin live (`decode_wal2json_message`), générique
    (aucune colonne codée en dur) — toute colonne NUMERIC/DATE/TIMESTAMP/
    UUID de n'importe quelle table backfillée peut être concernée."""
    return {k: _normalize_value(v) for k, v in record.items()}


def current_wal_lsn(session: Session) -> int:
    lsn_text = session.execute(text("SELECT pg_current_wal_lsn()")).scalar()
    # pg_current_wal_lsn() renvoie "X/Y" (deux parties hexadécimales) ; les
    # LSN décodées par psycopg2 (msg.data_start) sont des entiers — même
    # espace de valeurs (pg_lsn == uint64 sur 64 bits), conversion nécessaire
    # pour comparer les deux dans la réduction max(_lsn) côté lecteur.
    hi, lo = lsn_text.split("/")
    return (int(hi, 16) << 32) + int(lo, 16)


def backfill_table(
    session: Session,
    *,
    table_name: str,
    pk_column: str,
    geometry_column: str | None,
    boundary_lsn: int,
    flush_ts: float,
) -> list:
    """Lit l'état courant de la table et produit des ChangeRow op="insert"
    tagués `boundary_lsn`. La colonne géométrie est lue en texte (format de
    sortie par défaut de Postgres pour le type `geometry` = hex EWKB), même
    représentation que celle produite par wal2json — aucune conversion
    supplémentaire nécessaire côté parquet_writer."""
    t = quote_ident(session, table_name)
    rows = session.execute(text(f"SELECT * FROM public.{t}")).mappings().all()
    out = []
    for r in rows:
        record = _normalize_record(dict(r))
        geom_wkb_hex = record.pop(geometry_column, None) if geometry_column else None
        pk_value = record.get(pk_column)
        out.append(
            ChangeRow(
                op="insert",
                lsn=boundary_lsn,
                ts=flush_ts,
                pk_column=pk_column,
                pk_value=pk_value,
                columns=record,
                geometry_column=geometry_column,
                geometry_wkb_hex=geom_wkb_hex,
            )
        )
    return out
