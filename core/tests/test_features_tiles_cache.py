# SPDX-License-Identifier: Apache-2.0
"""P13.06 (c01-007) : une tuile servie à un utilisateur authentifié (colonne
sensible possible) n'est jamais `Cache-Control: public`, et porte `Vary`."""

import os

os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
os.environ.setdefault("CORE_ENV", "development")

from contextlib import contextmanager  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.auth.dependency import get_current_user_optional  # noqa: E402
from app.collections.introspection import ColumnInfo, TableInfo  # noqa: E402
from app.collections.routes import get_introspector  # noqa: E402
from app.features import tiles as tiles_module  # noqa: E402
from app.features.routes import get_masked_for_user, get_rls_scope  # noqa: E402
from app.main import create_app  # noqa: E402


class _RecordingSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return SimpleNamespace(first=lambda: (b"\x1a\x02", 1))


def _tile_client(monkeypatch):
    @contextmanager
    def null_scope(session, tenant_id, *, masked=False):
        yield

    info = TableInfo(
        table_name="employees",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=False),
            ColumnInfo(name="nom", type="string", required=True),
            ColumnInfo(name="salary", type="integer", required=False),
        ],
    )
    col = SimpleNamespace(
        id="employees",
        table_name="employees",
        tenant_id="default",
        is_public=True,
        sensitive_fields=["salary"],
    )
    app = create_app()
    session = _RecordingSession()
    monkeypatch.setattr(tiles_module, "get_collection_for_read", lambda s, u, c, *, guest=None: col)
    monkeypatch.setattr(tiles_module, "quote_ident", lambda s, name: f'"{name}"')
    app.dependency_overrides[db.get_session] = lambda: session
    app.dependency_overrides[get_current_user_optional] = lambda: SimpleNamespace(id="u")
    app.dependency_overrides[get_introspector] = lambda: lambda s, t: info
    app.dependency_overrides[get_rls_scope] = lambda: null_scope
    app.dependency_overrides[get_masked_for_user] = lambda: False  # porte data.view_sensitive
    return TestClient(app), session


_TILE = "/v1/collections/employees/tiles/0/0/0.mvt"
_AUTH = {"Authorization": "Bearer x"}


def test_privileged_tile_of_public_collection_is_private_and_varies(monkeypatch):
    client, session = _tile_client(monkeypatch)
    r = client.get(_TILE, headers=_AUTH)
    assert r.status_code == 200
    assert '"salary"' in session.calls[1][0]  # colonne sensible projetée dans la tuile
    assert r.headers["cache-control"] == "private, max-age=300"
    assert r.headers["vary"] == "Authorization"


def test_tile_etag_revalidates_to_304(monkeypatch):
    # REV-283b : une tuile inchangée se revalide sans renvoyer ses octets.
    client, _session = _tile_client(monkeypatch)
    etag = client.get(_TILE, headers=_AUTH).headers["etag"]
    assert etag.startswith('"') and len(etag) == 34
    for candidate in (etag, f"W/{etag}", f'"autre", {etag}'):
        r = client.get(_TILE, headers={**_AUTH, "If-None-Match": candidate})
        assert r.status_code == 304, candidate
        assert r.content == b""
        assert r.headers["etag"] == etag
        assert r.headers["vary"] == "Authorization"  # conservé (c01-007)


def test_tile_with_stale_etag_is_served_in_full(monkeypatch):
    client, _session = _tile_client(monkeypatch)
    r = client.get(_TILE, headers={**_AUTH, "If-None-Match": '"perime"'})
    assert r.status_code == 200
    assert r.content == b"\x1a\x02"
