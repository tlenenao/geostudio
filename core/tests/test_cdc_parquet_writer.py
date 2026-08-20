# SPDX-License-Identifier: Apache-2.0
import json
from datetime import UTC, datetime
from decimal import Decimal

import geopandas as gpd
import pandas as pd
import shapely.wkb
from shapely.geometry import Point

from app.cdc.backfill import _normalize_record
from app.cdc.consumer import decode_wal2json_message
from app.cdc.parquet_writer import ChangeRow, build_geodataframe, write_geoparquet


def _hex(geom) -> str:
    return shapely.wkb.dumps(geom, hex=True)


def test_build_geodataframe_insert_and_update():
    rows = [
        ChangeRow(
            op="insert",
            lsn=100,
            ts=1721212121.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1, "titre": "a"},
            geometry_column="geom",
            geometry_wkb_hex=_hex(Point(2.3, 48.8)),
        ),
        ChangeRow(
            op="update",
            lsn=105,
            ts=1721212125.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1, "titre": "b"},
            geometry_column="geom",
            geometry_wkb_hex=_hex(Point(2.4, 48.9)),
        ),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert list(gdf["_op"]) == ["insert", "update"]
    assert list(gdf["_lsn"]) == [100, 105]
    assert list(gdf["_ts"]) == [1721212121.0, 1721212125.0]
    assert list(gdf["titre"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.iloc[1].equals(Point(2.4, 48.9))


def test_build_geodataframe_delete_is_tombstone_only():
    rows = [
        ChangeRow(
            op="insert",
            lsn=1,
            ts=1.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1, "titre": "a"},
            geometry_column="geom",
            geometry_wkb_hex=_hex(Point(0, 0)),
        ),
        ChangeRow(
            op="delete",
            lsn=2,
            ts=2.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1},
            geometry_column="geom",
            geometry_wkb_hex=None,
        ),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert gdf["_op"].iloc[1] == "delete"
    assert pd.isna(gdf["titre"].iloc[1])  # tombstone : pas de colonnes métier hors PK
    assert gdf.geometry.iloc[1] is None


def test_write_geoparquet_mixed_backfill_and_live_numeric_batch_does_not_crash(tmp_path):
    """Régression Critère 3 (task-11-report.md) : reproduit le crash exact
    observé après un redémarrage de cdc-worker — le même cycle de flush
    combine une ligne issue du backfill (relit l'état courant de la table,
    NUMERIC -> Decimal via SQLAlchemy/psycopg) et une ligne rejouée du flux
    live non acké (NUMERIC -> float via decode_wal2json_message, JSON n'a
    pas de type décimal), pour la MÊME colonne "score" d'une table
    "points_interet". Avant le correctif, pa.Table.from_pandas (appelé par
    GeoDataFrame.to_parquet) levait ArrowTypeError sur ce mélange de types
    au sein d'une même colonne object. Le chemin de backfill est simulé ici
    via _normalize_record (la même fonction que backfill_table appelle en
    interne) plutôt que via une vraie connexion Postgres — ce test n'est pas
    postgis-marked, il vérifie uniquement l'accord de types entre les deux
    producteurs de ChangeRow.columns, pas la lecture SQL elle-même (déjà
    couverte par test_cdc_backfill.py)."""
    # Chemin backfill : SELECT * brut renvoie un Decimal pour une colonne
    # NUMERIC ; backfill_table le normalise en float via _normalize_record
    # avant de construire le ChangeRow (cf. app/cdc/backfill.py).
    backfill_record = _normalize_record({"id": 1, "score": Decimal("1.5")})
    assert isinstance(backfill_record["score"], float)  # précondition du test
    backfill_row = ChangeRow(
        op="insert",
        lsn=100,
        ts=1.0,
        pk_column="id",
        pk_value=1,
        columns=backfill_record,
        geometry_column=None,
        geometry_wkb_hex=None,
    )

    # Chemin live : payload wal2json réel décodé, NUMERIC non quoté -> float
    # (json.loads), pour la même colonne "score" de la même table.
    payload = json.dumps(
        {
            "change": [
                {
                    "table": "points_interet",
                    "kind": "update",
                    "columnnames": ["id", "score"],
                    "columnvalues": [1, 2.7],
                }
            ],
        }
    )
    decoded = decode_wal2json_message(
        payload,
        lsn=200,
        collection_meta={"points_interet": ("id", None)},
    )
    live_row = decoded[0].row
    assert isinstance(live_row.columns["score"], float)  # précondition du test

    # Les deux lignes dans le MÊME batch de flush, comme dans
    # CdcBufferManager après un redémarrage du worker (backfill + rejeu des
    # messages non ackés dans le même cycle) : ne doit PAS lever
    # pyarrow.lib.ArrowTypeError.
    path = str(tmp_path / "mixed_numeric.parquet")
    write_geoparquet([backfill_row, live_row], srid=4326, path=path)

    gdf = gpd.read_parquet(path)
    assert list(gdf["score"]) == [1.5, 2.7]


def test_write_geoparquet_mixed_backfill_and_live_timestamptz_batch_does_not_crash(tmp_path):
    """Extension Critère 3 (même classe de bug, task-11-fix-report.md) :
    mélange backfill (datetime.datetime -> str via _normalize_record) et
    live (wal2json -> str via json.loads) pour la MÊME colonne TIMESTAMPTZ
    "vu_le" de la table "points_interet", dans le même lot de flush. Le
    payload wal2json ci-dessous utilise le format texte natif de Postgres
    vérifié empiriquement (espace, pas "T" ; offset "+00", pas "+00:00") —
    si _normalize_record produisait encore `.isoformat()` brut, les deux
    chaînes ("2026-03-05T14:30:00+00:00" vs "2026-03-05 14:30:00+00")
    resteraient homogènes en type (str/str, donc pas d'ArrowTypeError) mais
    incohérentes en valeur ; ce test vérifie donc le CONTENU, pas seulement
    l'absence de crash."""
    backfill_record = _normalize_record(
        {
            "id": 1,
            "vu_le": datetime(2026, 3, 5, 14, 30, 0, tzinfo=UTC),
        }
    )
    assert isinstance(backfill_record["vu_le"], str)  # précondition du test
    assert backfill_record["vu_le"] == "2026-03-05 14:30:00+00"
    backfill_row = ChangeRow(
        op="insert",
        lsn=100,
        ts=1.0,
        pk_column="id",
        pk_value=1,
        columns=backfill_record,
        geometry_column=None,
        geometry_wkb_hex=None,
    )

    # Chemin live : payload wal2json réel décodé — même format texte natif
    # Postgres (vérifié empiriquement contre wal2json réel, cf. docstring
    # de app/cdc/backfill.py), pour la même colonne "vu_le".
    payload = json.dumps(
        {
            "change": [
                {
                    "table": "points_interet",
                    "kind": "update",
                    "columnnames": ["id", "vu_le"],
                    "columnvalues": [1, "2026-03-05 15:00:00+00"],
                }
            ],
        }
    )
    decoded = decode_wal2json_message(
        payload,
        lsn=200,
        collection_meta={"points_interet": ("id", None)},
    )
    live_row = decoded[0].row
    assert isinstance(live_row.columns["vu_le"], str)  # précondition du test

    path = str(tmp_path / "mixed_timestamptz.parquet")
    write_geoparquet([backfill_row, live_row], srid=4326, path=path)

    gdf = gpd.read_parquet(path)
    assert list(gdf["vu_le"]) == ["2026-03-05 14:30:00+00", "2026-03-05 15:00:00+00"]


def test_write_geoparquet_roundtrip_preserves_crs_and_columns(tmp_path):
    rows = [
        ChangeRow(
            op="insert",
            lsn=1,
            ts=1.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1, "titre": "a"},
            geometry_column="geom",
            geometry_wkb_hex=_hex(Point(0, 0)),
        )
    ]
    path = str(tmp_path / "part.parquet")
    write_geoparquet(rows, srid=2154, path=path)
    gdf = gpd.read_parquet(path)
    assert gdf.crs.to_epsg() == 2154
    assert len(gdf) == 1
    assert gdf["_op"].iloc[0] == "insert"
