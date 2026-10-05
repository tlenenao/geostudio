# SPDX-License-Identifier: Apache-2.0
"""Snapshot « état courant » du lac GeoParquet CDC (REV-280a).

`…/collection_id=C/snapshot/snap-<cut_ts_ms>-<max_lsn>.parquet` contient, pour
chaque PK, sa dernière version parmi les lignes du lac dont `_ts <= cut_ts`.
Les TOMBSTONES (`_op = 'delete'`) sont CONSERVÉES : un backfill tardif porte
une `_lsn` plus basse que les lignes vives (cf. app.cdc.backfill), et sans la
tombstone une ligne supprimée ressusciterait à la lecture « snapshot + delta ».
Le snapshot garde toutes les colonnes du lac, masquées ou non, exactement comme
les partitions brutes : le masquage GAP-22 et la RLS s'appliquent à la lecture,
après `_dedup_cte`, jamais ici.

Le lecteur lit `snapshot ∪ {lignes brutes avec _ts > cut_ts}` ; la découpe se
fait sur `_ts` (horloge du flush), jamais sur la LSN. Un fichier brut dont les
lignes ont `_ts <= cut_ts` mais qui arrive APRÈS l'écriture du snapshot est
perdu pour lui — d'où la marge `grace_s` (cut = maintenant − grace).

Publication : une écriture S3 (COPY → upload multipart) n'est visible qu'une
fois complète ; en local, écriture sous `.tmp` puis `os.replace`."""

import logging
import os
import re
from collections.abc import Callable

import duckdb

from app.sql_ident import quote_ident_duckdb as _qi

logger = logging.getLogger(__name__)
_SNAP_RE = re.compile(r"snap-(\d+)-(\d+)\.parquet$")
_HIVE_COLS = "tenant_id, collection_id, dt"


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def snapshot_dir(base_uri: str, tenant_id: str, collection_id: str) -> str:
    return f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/snapshot"


def raw_glob(base_uri: str, tenant_id: str, collection_id: str) -> str:
    return f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"


def list_snapshots(
    conn: duckdb.DuckDBPyConnection, base_uri: str, tenant_id: str, collection_id: str
) -> list[tuple[str, int, int]]:
    """(uri, cut_ts_ms, max_lsn), du plus récent au plus ancien."""
    glob = f"{snapshot_dir(base_uri, tenant_id, collection_id)}/snap-*.parquet"
    found = []
    for (uri,) in conn.execute(f"SELECT file FROM glob({_lit(glob)})").fetchall():
        m = _SNAP_RE.search(uri)
        if m:
            found.append((uri, int(m.group(1)), int(m.group(2))))
    return sorted(found, key=lambda s: s[1], reverse=True)


def _readable(conn: duckdb.DuckDBPyConnection, uri: str) -> bool:
    """Pied de page Parquet lisible ? Sinon le snapshot n'est jamais « le dernier »."""
    try:
        conn.execute(f"SELECT count(*) FROM parquet_metadata({_lit(uri)})").fetchone()
        return True
    except duckdb.Error:
        return False


def latest_snapshot(
    conn: duckdb.DuckDBPyConnection, base_uri: str, tenant_id: str, collection_id: str
) -> tuple[str, int] | None:
    """Dernier snapshot lisible ; None (=> lecture brute, M7) si aucun ou si le
    listage échoue. # ponytail: valide le pied de page seulement, pas le corps."""
    try:
        for uri, cut, _ in list_snapshots(conn, base_uri, tenant_id, collection_id):
            if _readable(conn, uri):
                return uri, cut
            logger.warning("snapshot du lac illisible ignoré: %s", uri)
    except duckdb.Error:
        logger.warning("listage des snapshots du lac impossible, lecture brute", exc_info=True)
    return None


def cut_seconds(cut_ts_ms: int) -> float:
    """Seuil `_ts` partagé par l'écriture et la lecture (même flottant des deux
    côtés : la partition snapshot/delta est exacte)."""
    return cut_ts_ms / 1000.0


def write_snapshot(
    conn: duckdb.DuckDBPyConnection,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    pk_column: str,
    *,
    now_ms: int,
    grace_s: int = 300,
    cleanup: Callable[[str], None] | None = None,
) -> str | None:
    """Écrit un nouveau snapshot = précédent ∪ delta, réduit à la dernière
    version par PK. None si rien de neuf (ou lac vide)."""
    cut_ms = now_ms - grace_s * 1000
    prev = []
    for snap in list_snapshots(conn, base_uri, tenant_id, collection_id):
        if _readable(conn, snap[0]):
            prev.append(snap)
        else:  # fichier partiel d'un cycle interrompu : on repart d'un prev sain
            logger.warning("snapshot du lac illisible supprimé: %s", snap[0])
            _drop(snap[0], cleanup)
    prev_cut_ms = prev[0][1] if prev else None
    if prev_cut_ms is not None and prev_cut_ms >= cut_ms:
        return None
    lower = f"AND _ts > {cut_seconds(prev_cut_ms)!r}" if prev_cut_ms is not None else ""
    glob = raw_glob(base_uri, tenant_id, collection_id)
    # hive_partitioning=true seulement pour exclure les colonnes de partition :
    # le snapshot ne les stocke pas (elles viennent du chemin à la lecture).
    delta = (
        f"SELECT * EXCLUDE ({_HIVE_COLS}) FROM read_parquet({_lit(glob)}, "
        f"hive_partitioning=true, union_by_name=true) "
        f"WHERE _ts <= {cut_seconds(cut_ms)!r} {lower}"
    )
    try:
        n, delta_lsn = conn.execute(f"SELECT count(*), max(_lsn) FROM ({delta})").fetchone()  # type: ignore[misc]
    except duckdb.IOException:  # aucun fichier brut : lac vide
        return None
    if not n:
        return None
    src = delta
    max_lsn = int(delta_lsn)
    if prev:
        src = (
            f"SELECT * FROM read_parquet({_lit(prev[0][0])}, hive_partitioning=false) "
            f"UNION ALL BY NAME {delta}"
        )
        max_lsn = max(max_lsn, prev[0][2])
    cols = [c[0] for c in conn.execute(f"SELECT * FROM ({src}) LIMIT 0").description]
    order = "_lsn DESC, COALESCE(_seq, -1) DESC" if "_seq" in cols else "_lsn DESC"
    reduced = (
        f"SELECT * FROM ({src}) QUALIFY row_number() OVER "
        f"(PARTITION BY {_qi(pk_column)} ORDER BY {order}) = 1"
    )
    uri = f"{snapshot_dir(base_uri, tenant_id, collection_id)}/snap-{cut_ms}-{max_lsn}.parquet"
    local = "://" not in uri
    target = uri + ".tmp" if local else uri
    if local:
        os.makedirs(os.path.dirname(uri), exist_ok=True)
    try:
        conn.execute(f"COPY ({reduced}) TO {_lit(target)} (FORMAT PARQUET)")
        if not _readable(conn, target):
            raise OSError(f"snapshot illisible après écriture: {target}")
        if local:
            os.replace(target, uri)
    except BaseException:
        _drop(target, cleanup)  # best-effort : jamais de fichier partiel publié
        raise
    return uri


def _drop(uri: str, cleanup: Callable[[str], None] | None) -> None:
    try:
        if "://" not in uri:
            os.remove(uri)
        elif cleanup:
            cleanup(uri)
    except Exception:
        logger.warning("suppression du snapshot %s impossible", uri, exc_info=True)
