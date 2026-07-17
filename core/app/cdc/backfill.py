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
précision par rapport à ce que ce dernier produit déjà."""
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cdc.parquet_writer import ChangeRow
from app.collections.ddl import quote_ident


def _normalize_record(record: dict) -> dict:
    """Convertit toute valeur `decimal.Decimal` du dict en `float`, générique
    (aucune colonne codée en dur) — toute colonne NUMERIC/DECIMAL de
    n'importe quelle table backfillée peut être concernée, pas seulement
    celle qui a déclenché le rapport initial."""
    return {
        k: float(v) if isinstance(v, Decimal) else v
        for k, v in record.items()
    }


def current_wal_lsn(session: Session) -> int:
    lsn_text = session.execute(text("SELECT pg_current_wal_lsn()")).scalar()
    # pg_current_wal_lsn() renvoie "X/Y" (deux parties hexadécimales) ; les
    # LSN décodées par psycopg2 (msg.data_start) sont des entiers — même
    # espace de valeurs (pg_lsn == uint64 sur 64 bits), conversion nécessaire
    # pour comparer les deux dans la réduction max(_lsn) côté lecteur.
    hi, lo = lsn_text.split("/")
    return (int(hi, 16) << 32) + int(lo, 16)


def backfill_table(
    session: Session, *, table_name: str, pk_column: str, geometry_column: str | None,
    boundary_lsn: int, flush_ts: float,
) -> list:
    """Lit l'état courant de la table et produit des ChangeRow op="insert"
    tagués `boundary_lsn`. La colonne géométrie est lue en texte (format de
    sortie par défaut de Postgres pour le type `geometry` = hex EWKB), même
    représentation que celle produite par wal2json — aucune conversion
    supplémentaire nécessaire côté parquet_writer."""
    t = quote_ident(session, table_name)
    rows = session.execute(text(f'SELECT * FROM public.{t}')).mappings().all()
    out = []
    for r in rows:
        record = _normalize_record(dict(r))
        geom_wkb_hex = record.pop(geometry_column, None) if geometry_column else None
        pk_value = record.get(pk_column)
        out.append(ChangeRow(
            op="insert", lsn=boundary_lsn, ts=flush_ts, pk_column=pk_column,
            pk_value=pk_value, columns=record, geometry_column=geometry_column,
            geometry_wkb_hex=geom_wkb_hex,
        ))
    return out
