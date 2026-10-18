# SPDX-License-Identifier: Apache-2.0
"""ARC-13 (critère 3) : import dans une collection existante, lignes hors domaine rejetées
dans le rapport (PostGIS réel)."""

import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.collections.ddl import alter_geometry_column
from app.db import Base, make_session_factory
from app.features.rls import rls_scope
from app.ingestion.importer import run_append, run_import
from app.ingestion.parsers import IngestionParseError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

SEED = b"nom,etat,largeur,lat,lon\nPont,bon,5,48.8,2.3\n"
APPEND = (
    b"nom,etat,largeur,lat,lon,extra\n"
    b"A,bon,3,48.1,2.1,x\n"  # valide
    b"B,ruine,3,48.2,2.2,x\n"  # hors domaine (liste)
    b"C,moyen,99,48.3,2.3,x\n"  # hors domaine (plage)
    b"D,mauvais,10,48.4,2.4,x\n"  # valide
)


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def _seed(Session, tenant, user):
    with Session() as s:
        res = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="seed.csv",
            content=SEED,
            collection_title="Ponts",
            lat_field=None,
            lon_field=None,
        )
        col = collections_repo.get_collection(
            s, tenant_id=tenant.id, collection_id=res.collection_id
        )
        col.field_domains = {
            "etat": {"type": "list", "values": ["bon", "moyen", "mauvais"]},
            "largeur": {"type": "range", "min": 0, "max": 30},
        }
        s.commit()
        return res.collection_id


def test_append_rejects_out_of_domain_rows_in_report(env):
    Session, tenant, user = env
    cid = _seed(Session, tenant, user)
    with Session() as s:
        report = run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="more.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    assert report["inserted"] == 2
    assert report["rejectedCount"] == 2
    assert [r["row"] for r in report["rejected"]] == [2, 3]  # numéro de ligne (1 = 1re donnée)
    assert report["rejected"][0]["errors"][0]["field"] == "etat"
    assert report["rejected"][1]["errors"][0]["code"] == "out_of_domain"
    assert report["ignoredColumns"] == ["extra"]
    with Session() as s:
        names = s.execute(text(f"SELECT nom FROM public.{cid} ORDER BY nom")).scalars().all()
    assert names == ["A", "D", "Pont"]  # aucune rétro-application : "Pont" intact


def test_append_to_unknown_collection_fails(env):
    Session, tenant, user = env
    with Session() as s, pytest.raises(IngestionParseError):
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id="nope",
            filename="x.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )


def test_append_all_rows_visible_through_rls(env):
    Session, tenant, user = env
    cid = _seed(Session, tenant, user)
    with Session() as s:
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="more.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    with Session() as s, rls_scope(s, tenant.id):
        n = s.execute(text(f"SELECT count(*) FROM public.{cid}")).scalar()
    assert n == 3


def test_append_to_collection_stored_in_2154_reprojects(env, pg_engine):
    """AUD-020 : l'ajout sur une collection hors 4326 est accepté et reprojeté."""
    Session, tenant, user = env
    cid = _seed(Session, tenant, user)
    with Session() as s:
        col = collections_repo.get_collection(s, tenant_id=tenant.id, collection_id=cid)
        table = col.table_name
        col.srid = 2154
        s.commit()
    with Session() as s:  # recrée aussi les policies geo_limit_* (geo-limit + 2154)
        alter_geometry_column(s, table, geometry_type="Point", srid=2154)
        s.commit()
    with Session() as s:
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="more.csv",
            content=b"nom,etat,largeur,lat,lon\nA,bon,3,48.1,2.1\n",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    with Session() as s, rls_scope(s, tenant.id):
        x, y = s.execute(
            text(
                f"SELECT ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326)) "
                f"FROM public.{table} WHERE nom = 'A'"
            )
        ).one()
    assert (round(x, 4), round(y, 4)) == (2.1, 48.1)


def test_import_and_append_repair_invalid_polygon(env):
    """AUD-129 : import ET ajout (même _load_rows) réparent un nœud papillon."""
    import json

    Session, tenant, user = env
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]],
    }

    def gj(name):
        return json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"nom": name}, "geometry": bowtie}],
            }
        ).encode()

    with Session() as s:
        res = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="p.geojson",
            content=gj("seed"),
            collection_title="Polys",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        cid = res.collection_id
    with Session() as s:
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="p2.geojson",
            content=gj("more"),
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    with Session() as s, rls_scope(s, tenant.id):
        rows = s.execute(text(f"SELECT ST_IsValid(geom), ST_Area(geom) FROM public.{cid}")).all()
    assert len(rows) == 2
    assert all(v and round(a, 6) == 2.0 for v, a in rows)


def test_append_bowtie_into_polygon_column_is_reported_not_raw_error(env):
    """AUD-129 (reliquat) : un nœud papillon réparé en MultiPolygon, ajouté à une colonne
    Polygon, est rejeté dans le rapport (geometry_mismatch), pas par l'erreur PostGIS brute."""
    import json

    Session, tenant, user = env
    square = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]}

    def gj(*feats):
        return json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"nom": n}, "geometry": g} for n, g in feats
                ],
            }
        ).encode()

    with Session() as s:
        res = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="p.geojson",
            content=gj(("seed", square)),
            collection_title="Polys",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        cid = res.collection_id
    with Session() as s:
        report = run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="p2.geojson",
            content=gj(("ok", square), ("noeud", bowtie)),
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    assert report["inserted"] == 1
    assert report["rejectedCount"] == 1
    assert report["rejected"][0]["row"] == 2
    assert report["rejected"][0]["errors"][0]["code"] == "geometry_mismatch"
