# SPDX-License-Identifier: Apache-2.0
"""FIX final SP-L0 : reader.collection(2154) → writer.collection(2154) conserve les géométries
(le flux garde le SRID natif ; le writer reprojette en 4326 avant `_geometry_sql`)."""

import dataclasses

import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.configs.schemas import PipelinePayload
from app.db import Base, make_session_factory
from app.items import repository as items_repo  # noqa: F401
from app.pipelines import runtime
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_pipeline_runtime import (
    TABLE_INFO,
    _no_masking_by_default,  # noqa: F401
    _row,
)

X, Y = 700000.0, 6600000.0


def _payload(mode: str):
    w = {"collectionId": "villes_l93", "mode": mode}
    if mode == "upsert":
        w["keyColumns"] = ["region"]
    return PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.collection",
                    "params": {"collectionId": "villes"},
                },
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": w},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )


def _write(tmp_path, tenant_id, pop):
    import geopandas as gpd

    rows = [_row(1, "R", pop, x=X, y=Y)]
    d = tmp_path / f"tenant_id={tenant_id}" / "collection_id=villes" / "dt=2026-08-05"
    d.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:2154").to_parquet(d / "part-1.parquet")


@pytest.mark.postgis
def test_2154_to_2154_append_then_upsert_preserves_geometry(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )  # fmt: skip
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, geometry_column, is_public, editable, "
                "created_at, updated_at) VALUES ('villes_l93', :t, :o, 'villes_l93', "
                "'V', '', 'id', 'geometry', false, true, now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE villes_l93 (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "region VARCHAR, pop INTEGER, geometry geometry(Point, 2154))"
            )
        )
        apply_collection_ddl(s, "villes_l93")
        s.commit()
        monkeypatch.setattr(
            runtime,
            "_table_info_for_collection",
            lambda session, cid: dataclasses.replace(TABLE_INFO, table_name=cid, srid=2154),
        )
        monkeypatch.setattr(
            runtime,
            "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )
        try:
            for mode, pop in (("append", 1), ("upsert", 2)):
                _write(tmp_path, tenant.id, pop)
                runtime.run_pipeline(
                    s,
                    payload=_payload(mode),
                    tenant_id=tenant.id,
                    user=user,
                    endpoint_url="http://localhost:9000",
                    access_key="x",
                    secret_key="y",
                    base_uri=str(tmp_path),
                )
                s.commit()
                row = s.execute(
                    text("SELECT pop, ST_X(geometry), ST_Y(geometry) FROM villes_l93")
                ).all()
                assert len(row) == 1
                assert row[0][0] == pop
                assert (round(row[0][1], 1), round(row[0][2], 1)) == (X, Y)
        finally:
            s.rollback()
            s.execute(
                text(
                    "DROP TABLE villes_l93; TRUNCATE items, configs, config_revisions, "
                    "collections, audit_log, users, tenants CASCADE"
                )
            )
            s.commit()
