# SPDX-License-Identifier: Apache-2.0
"""Point d'entrée process du worker CDC (SP-11a) — service `cdc-worker` du
compose, jamais démarré via create_app()/app.main : observability.setup()
est donc appelé ici au niveau module, même patron et même raison que
app/jobs.py (SP-10a) — quel que soit le process qui importe ce module EST le
point d'entrée du worker."""
import os
import threading
import time
import uuid

from sqlalchemy import select

from app import observability

observability.setup()

from app.cdc import backfill, consumer, storage  # noqa: E402  (après setup(), même patron que app.jobs)
from app.cdc.buffer import CdcBufferManager
from app.cdc.parquet_writer import write_geoparquet
from app.collections.models import Collection
from app.db import make_engine, make_session_factory


class _WorkerState:
    """État en mémoire du process — un seul cdc-worker à la fois, pas de
    partage entre threads/process. last_seen_lsn : LSN du dernier message
    reçu du flux (toutes tables confondues), utilisé pour borner le feedback
    via CdcBufferManager.safe_ack_lsn même quand aucun flush n'a eu lieu à
    cette itération. last_flush_ts : collection_id -> epoch du dernier flush
    GeoParquet réussi, source de la gauge geostudio.cdc.lag_seconds."""

    def __init__(self) -> None:
        self.last_seen_lsn = 0
        self.last_flush_ts: dict = {}
        # Garde last_flush_ts : lu depuis le thread background OTel
        # (PeriodicExportingMetricReader appelle get_lag_seconds() sur son
        # propre thread) pendant que le thread worker principal écrit dedans
        # (_flush_table) — sans ce verrou, une mutation concurrente pendant
        # l'itération de get_lag_seconds() peut lever `RuntimeError:
        # dictionary changed size during iteration`, non rattrapée par OTel,
        # ce qui tue silencieusement le thread d'export et désactive la
        # gauge geostudio.cdc.lag_seconds pour le reste du process.
        # last_seen_lsn n'a pas besoin du même verrou : jamais lu par le
        # callback de la gauge, seulement écrit/lu par le thread du flux CDC.
        self._lock = threading.Lock()

    def get_lag_seconds(self) -> dict:
        now = time.time()
        with self._lock:
            return {cid: now - ts for cid, ts in self.last_flush_ts.items()}

    def record_flush(self, collection_id, ts: float) -> None:
        with self._lock:
            self.last_flush_ts[collection_id] = ts


def build_s3_key(*, tenant_id: str, collection_id: str, dt: str) -> str:
    return f"cdc/tenant_id={tenant_id}/collection_id={collection_id}/dt={dt}/part-{uuid.uuid4().hex}.parquet"


def _load_collection_meta(session) -> dict:
    """table_name -> (collection_id, tenant_id, geometry_column, srid, pk_column)."""
    return {
        c.table_name: (c.id, c.tenant_id, c.geometry_column, c.srid, c.pk_column)
        for c in session.scalars(select(Collection)).all()
    }


def _write_and_upload(rows, *, srid: int, local_path: str, s3_client, bucket: str, key: str) -> None:
    """Écrit le GeoParquet local puis l'uploade, en garantissant que le
    fichier temporaire est toujours supprimé (succès ou échec) — extrait de
    _flush_table pour rester testable indépendamment de run() (qui exige
    DB/S3 réels). Une exception de write_geoparquet/upload_parquet_file
    (panne MinIO/réseau transitoire, géométrie malformée, pression disque)
    continue de se propager telle quelle après nettoyage : le crash-and-
    restart du worker (`restart: unless-stopped`) reste le comportement de
    récupération voulu, seul le leak de fichier est fermé ici."""
    try:
        write_geoparquet(rows, srid=srid, path=local_path)
        storage.upload_parquet_file(s3_client, bucket=bucket, key=key, local_path=local_path)
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


def run() -> None:
    raw_dsn = os.environ["CDC_DATABASE_URL"]
    engine = make_engine(raw_dsn.replace("postgresql://", "postgresql+psycopg://"))
    session_factory = make_session_factory(engine)
    s3_bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    s3_client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(s3_client, s3_bucket)

    state = _WorkerState()
    observability.register_cdc_lag_gauge(state.get_lag_seconds)

    consumer.ensure_replication_slot(raw_dsn)

    buffer = CdcBufferManager()
    with session_factory() as session:
        collection_meta = _load_collection_meta(session)
        boundary_lsn = backfill.current_wal_lsn(session)
        for table_name, (_cid, _tid, geometry_column, _srid, pk_column) in collection_meta.items():
            rows = backfill.backfill_table(
                session, table_name=table_name, pk_column=pk_column,
                geometry_column=geometry_column, boundary_lsn=boundary_lsn, flush_ts=time.time(),
            )
            for row in rows:
                buffer.add(table_name, row)

    def _flush_table(table_name: str) -> None:
        collection_id, tenant_id, _geometry_column, srid, _pk_column = collection_meta[table_name]
        rows = buffer.drain(table_name, flush_ts=time.time())
        if not rows:
            return
        dt = time.strftime("%Y-%m-%d", time.gmtime())
        key = build_s3_key(tenant_id=tenant_id, collection_id=collection_id, dt=dt)
        local_path = f"/tmp/cdc-{uuid.uuid4().hex}.parquet"
        _write_and_upload(
            rows, srid=srid or 4326, local_path=local_path,
            s3_client=s3_client, bucket=s3_bucket, key=key,
        )
        state.record_flush(collection_id, time.time())

    def _do_flush():
        for table_name in buffer.tables_due_for_flush():
            _flush_table(table_name)
        return buffer.safe_ack_lsn(last_seen_lsn=state.last_seen_lsn)

    def _on_message(payload: str, lsn: int) -> None:
        state.last_seen_lsn = lsn
        meta_by_table = {t: (pk, geom) for t, (_cid, _tid, geom, _srid, pk) in collection_meta.items()}
        for decoded in consumer.decode_wal2json_message(payload, lsn=lsn, collection_meta=meta_by_table):
            buffer.add(decoded.table_name, decoded.row)

        # Table publiée mais inconnue de collection_meta : collection créée
        # après le dernier chargement — backfill paresseux au premier
        # changement vu (Task 8 §Décision de conception), avant de traiter
        # le message lui-même sur la prochaine itération.
        import json
        unknown_tables = {
            change["table"] for change in json.loads(payload).get("change", [])
            if change["table"] not in collection_meta
        }
        for table_name in unknown_tables:
            with session_factory() as session:
                fresh = session.scalar(select(Collection).where(Collection.table_name == table_name))
            if fresh is None:
                continue
            collection_meta[table_name] = (fresh.id, fresh.tenant_id, fresh.geometry_column, fresh.srid, fresh.pk_column)
            with session_factory() as session:
                backfill_rows = backfill.backfill_table(
                    session, table_name=table_name, pk_column=fresh.pk_column,
                    geometry_column=fresh.geometry_column, boundary_lsn=lsn - 1, flush_ts=time.time(),
                )
            for row in backfill_rows:
                buffer.add(table_name, row)

    consumer.stream_changes(
        raw_dsn, on_message=_on_message,
        is_flush_due=lambda: bool(buffer.tables_due_for_flush()),
        do_flush=_do_flush,
    )


if __name__ == "__main__":
    run()
