# SPDX-License-Identifier: Apache-2.0
"""Helpers purs du service de tuiles MVT (spec SP-24 §3.1). Aucun accès base :
on teste la validation des coordonnées, la liste des colonnes de propriétés et
la forme du SQL produit — le SQL réel est exercé par
test_features_tiles_postgis.py."""

import pytest

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.tiles import (
    MAX_TILE_FEATURES,
    TILE_STATEMENT_TIMEOUT_MS,
    InvalidTileCoords,
    build_mvt_sql,
    mvt_feature_id_column,
    mvt_property_columns,
    validate_tile_coords,
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _info(pk_type: str = "integer", **kwargs) -> TableInfo:
    defaults = dict(
        table_name="demo_incidents",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type=pk_type, required=False),
            ColumnInfo(name="titre", type="string", required=True),
            ColumnInfo(name="tenant_id", type="string", required=True),
        ],
    )
    defaults.update(kwargs)
    return TableInfo(**defaults)


@pytest.mark.parametrize("coords", [(0, 0, 0), (1, 1, 1), (24, 0, 0), (2, 3, 3)])
def test_valid_coords_are_accepted(coords):
    assert validate_tile_coords(*coords) is None


@pytest.mark.parametrize(
    "coords",
    [(-1, 0, 0), (25, 0, 0), (0, 1, 0), (0, 0, 1), (1, 2, 0), (1, 0, 2), (2, -1, 0)],
)
def test_out_of_range_coords_are_rejected(coords):
    with pytest.raises(InvalidTileCoords):
        validate_tile_coords(*coords)


def test_tenant_id_never_becomes_a_tile_property():
    assert mvt_property_columns(_info()) == ["id", "titre"]


def test_integer_primary_key_becomes_the_mvt_feature_id():
    assert mvt_feature_id_column(_info(pk_type="integer")) == "id"


def test_non_integer_primary_key_yields_no_feature_id():
    # PostGIS ignore un feature_id non entier ; on préfère ne rien passer
    # plutôt que dépendre de sa clémence. Le shell retombe alors sur la
    # propriété de PK (cf. Task 10).
    assert mvt_feature_id_column(_info(pk_type="string")) is None


def test_sql_filters_on_the_untransformed_geometry_column():
    sql = build_mvt_sql(_quote, _info())
    # Le && porte sur t."geom" brut, jamais sur ST_Transform(t."geom", …) :
    # sinon l'index GiST de la Task 4 ne sert à rien (spec §3.2).
    assert 't."geom" && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)' in sql
    assert 'ST_Transform(t."geom", 3857) &&' not in sql


def test_sql_quotes_every_identifier_and_carries_the_columns():
    sql = build_mvt_sql(_quote, _info())
    assert 'public."demo_incidents"' in sql
    assert 't."titre" AS "titre"' in sql
    assert '"tenant_id"' not in sql
    assert "ST_AsMVT(" in sql
    assert "ST_AsMVTGeom(" in sql


def test_sql_drops_rows_whose_tile_geometry_is_null():
    assert "IS NOT NULL" in build_mvt_sql(_quote, _info())


def test_sql_caps_the_number_of_features_read_per_tile():
    # I3 de la revue finale SP-24 : sans plafond, un seul GET sur une
    # collection dense agrège toute la table en une tuile en mémoire, par un
    # appelant potentiellement anonyme et sans trace d'audit.
    sql = build_mvt_sql(_quote, _info())
    # DANS la sous-requête : c'est le nombre de lignes lues qu'on borne, pas
    # la sortie de l'agrégat (toujours une ligne).
    assert sql.index("LIMIT :max_features") < sql.index(") AS tile")


def test_the_tile_route_is_mounted_unconditionally():
    from app.main import create_app

    # FastAPI >=0.130 n'expose plus les routes incluses comme des APIRoute
    # aplaties dans app.routes (nouvelle classe interne _IncludedRouter, sans
    # attribut .path) : le schéma OpenAPI généré reste la façon stable et
    # publique de vérifier qu'un chemin est monté, indépendamment de la
    # représentation interne du routage.
    paths = set(create_app().openapi()["paths"])
    assert "/v1/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt" in paths


def _client(monkeypatch, info: TableInfo | None = None, collection=None):
    """App réelle, session et collection substituées : ces cas-là échouent
    AVANT tout SQL, donc aucune base n'est nécessaire."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import db
    from app.auth.dependency import get_current_user_optional
    from app.collections.introspection import TableNotFound
    from app.collections.routes import get_introspector
    from app.features import tiles as tiles_module
    from app.main import create_app

    app = create_app()
    col = collection or SimpleNamespace(
        id="demo_incidents", table_name="demo_incidents", tenant_id="default", is_public=True
    )
    monkeypatch.setattr(tiles_module, "get_readable_collection", lambda s, u, c: col)
    app.dependency_overrides[db.get_session] = lambda: None
    app.dependency_overrides[get_current_user_optional] = lambda: None
    app.dependency_overrides[get_introspector] = lambda: (
        lambda s, t: info if info is not None else (_ for _ in ()).throw(TableNotFound(t))
    )
    return TestClient(app)


def test_zoom_out_of_range_is_a_400(monkeypatch):
    r = _client(monkeypatch, _info()).get("/v1/collections/demo_incidents/tiles/99/0/0.mvt")
    assert r.status_code == 400
    assert "z must be within" in r.json()["detail"]


def test_x_out_of_range_for_the_zoom_is_a_400(monkeypatch):
    r = _client(monkeypatch, _info()).get("/v1/collections/demo_incidents/tiles/1/9/0.mvt")
    assert r.status_code == 400


def test_collection_without_geometry_is_a_400(monkeypatch):
    info = _info(geometry_column=None, geometry_type=None, srid=None)
    r = _client(monkeypatch, info).get("/v1/collections/demo_incidents/tiles/0/0/0.mvt")
    assert r.status_code == 400
    assert "geometry" in r.json()["detail"]


def test_unknown_table_is_a_404(monkeypatch):
    r = _client(monkeypatch, None).get("/v1/collections/demo_incidents/tiles/0/0/0.mvt")
    assert r.status_code == 404


class _RecordingSession:
    """Session enregistreuse : la route va jusqu'au bout de son chemin
    nominal sans base, ce qui laisse observer les DEUX instructions qu'elle
    émet (le garde de durée, puis la requête de tuile) et leurs paramètres."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []

    def execute(self, statement, params=None):
        from types import SimpleNamespace

        self.calls.append((str(statement), params))
        return SimpleNamespace(scalar=lambda: b"\x1a\x02")


def _recording_client(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import db
    from app.auth.dependency import get_current_user_optional
    from app.collections.routes import get_introspector
    from app.features import tiles as tiles_module
    from app.features.routes import get_rls_scope
    from app.main import create_app

    @contextmanager
    def null_scope(session, tenant_id):
        yield

    app = create_app()
    session = _RecordingSession()
    col = SimpleNamespace(
        id="demo_incidents", table_name="demo_incidents", tenant_id="default", is_public=True
    )
    monkeypatch.setattr(tiles_module, "get_readable_collection", lambda s, u, c: col)
    monkeypatch.setattr(tiles_module, "quote_ident", lambda s, name: f'"{name}"')
    app.dependency_overrides[db.get_session] = lambda: session
    app.dependency_overrides[get_current_user_optional] = lambda: None
    app.dependency_overrides[get_introspector] = lambda: lambda s, t: _info()
    app.dependency_overrides[get_rls_scope] = lambda: null_scope
    return TestClient(app), session


def test_the_tile_query_runs_under_a_statement_timeout(monkeypatch):
    client, session = _recording_client(monkeypatch)
    assert client.get("/v1/collections/demo_incidents/tiles/0/0/0.mvt").status_code == 200
    timeout_sql, timeout_params = session.calls[0]
    # Posé AVANT la requête de tuile, et transaction-local (set_config(...,
    # true)) : rien ne fuit sur la connexion suivante à travers PgBouncer.
    assert "set_config('statement_timeout'" in timeout_sql
    assert timeout_params == {"ms": str(TILE_STATEMENT_TIMEOUT_MS)}
    assert "ST_AsMVT(" in session.calls[1][0]


def test_the_tile_query_binds_the_feature_cap(monkeypatch):
    client, session = _recording_client(monkeypatch)
    assert client.get("/v1/collections/demo_incidents/tiles/0/0/0.mvt").status_code == 200
    tile_sql, tile_params = session.calls[1]
    assert "LIMIT :max_features" in tile_sql
    assert tile_params["max_features"] == MAX_TILE_FEATURES
