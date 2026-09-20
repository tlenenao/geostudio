# SPDX-License-Identifier: Apache-2.0
"""Tuiles MVT sur PostGIS réel (spec SP-24 §6, preuves 2 et 3). Le point de
ces tests : prouver que l'isolation tenant vient de la RLS (rôle gis_rls +
GUC app.tenant_id), pas d'un filtre applicatif — donc aucune substitution du
scope RLS ni du repository ici, contrairement aux tests SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

TILE_PATH = "/v1/collections/demo_incidents/tiles/0/0/0.mvt"


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text(
                "CREATE TABLE demo_incidents (id serial PRIMARY KEY, "
                "titre text NOT NULL, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    client.post("/v1/collections", json={"tableName": "demo_incidents"})
    yield client, app, Session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _insert(client, titre: str, lon: float = 2.35, lat: float = 48.85):
    r = client.post(
        "/v1/collections/demo_incidents/items",
        json={
            "type": "Feature",
            "properties": {"titre": titre},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        },
    )
    assert r.status_code == 201, r.text


def test_an_empty_tile_is_a_204(pg_app):
    client, _, _ = pg_app
    r = client.get(TILE_PATH)
    assert r.status_code == 204
    assert r.content == b""


def test_a_tile_carries_the_properties_but_never_tenant_id(pg_app):
    client, _, _ = pg_app
    _insert(client, "Fuite avenue de la Gare")
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    # Les noms de colonnes apparaissent en clair dans les clés du MVT (protobuf
    # non compressé) : une assertion sur les octets suffit et évite d'ajouter
    # un décodeur MVT aux dépendances de test.
    assert b"titre" in r.content
    assert b"Fuite avenue de la Gare" in r.content
    assert b"tenant_id" not in r.content


def test_a_public_collection_is_readable_anonymously(pg_app):
    client, app, _ = pg_app
    _insert(client, "Publique")
    client.patch("/v1/collections/demo_incidents", json={"isPublic": True})
    app.dependency_overrides[get_current_user_optional] = lambda: None
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=300"


def test_a_private_collection_tile_is_never_cached_publicly(pg_app):
    client, _, _ = pg_app
    _insert(client, "Privée")
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, max-age=300"


def test_a_private_collection_is_a_404_anonymously(pg_app):
    client, app, _ = pg_app
    _insert(client, "Privée")
    app.dependency_overrides[get_current_user_optional] = lambda: None
    r = client.get(TILE_PATH)
    assert r.status_code == 404
    # Pas d'assertion supplémentaire sur r.content ici : un 404 FastAPI est un
    # corps JSON `{"detail": "collection not found"}` qui ne peut structurellement
    # jamais contenir le titre de la donnée, que l'autorisation ait ou non
    # fonctionné correctement — vérifier son absence n'apporterait aucune preuve.


def test_rows_of_another_tenant_never_reach_the_tile(pg_app):
    """Preuve de RLS, pas preuve de WHERE : la ligne du tenant "autre" est
    insérée directement en base (donc invisible d'aucun filtre applicatif de
    la route), et ne doit pas sortir dans la tuile du tenant "default"."""
    client, _, Session = pg_app
    _insert(client, "Chez nous")
    with Session() as s:
        s.execute(
            text(
                "INSERT INTO demo_incidents (titre, geom, tenant_id) VALUES "
                "('Chez le voisin', ST_SetSRID(ST_MakePoint(2.35, 48.85), 4326), 'autre')"
            )
        )
        s.commit()
    # Preuve que la ligne du voisin existe réellement en base, hors RLS
    # (connexion superutilisateur de test, aucun SET ROLE ici) — sinon
    # l'assertion finale passerait aussi bien si l'INSERT avait
    # silencieusement échoué.
    with Session() as s:
        neighbour_count = s.execute(
            text("SELECT count(*) FROM demo_incidents WHERE titre = 'Chez le voisin'")
        ).scalar()
    assert neighbour_count == 1
    content = client.get(TILE_PATH).content
    assert b"Chez nous" in content
    assert b"Chez le voisin" not in content


def test_a_dense_tile_is_truncated_to_the_feature_cap(pg_app, monkeypatch):
    """I3 de la revue finale SP-24 : le plafond est un vrai LIMIT exécuté par
    Postgres, pas seulement une chaîne présente dans le SQL. Plafond abaissé
    à 2 pour ne pas avoir à insérer 5000 lignes."""
    from app.features import tiles as tiles_module

    client, _, _ = pg_app
    monkeypatch.setattr(tiles_module, "MAX_TILE_FEATURES", 2)
    for titre in ("Alpha", "Bravo", "Charlie"):
        _insert(client, titre)
    r = client.get(TILE_PATH)
    assert r.status_code == 200
    # Lesquelles sortent n'est pas déterministe (aucun ORDER BY, et il n'en
    # faut pas : trier coûterait exactement ce que le plafond évite) — leur
    # NOMBRE l'est.
    assert sum(1 for t in (b"Alpha", b"Bravo", b"Charlie") if t in r.content) == 2


def test_a_tile_request_sets_a_transaction_local_statement_timeout(pg_app):
    """La borne de durée est réellement en vigueur côté serveur pendant la
    requête, et ne survit pas à la transaction (sinon elle fuirait sur la
    connexion suivante à travers PgBouncer)."""
    from sqlalchemy import text as sa_text

    from app.features import tiles as tiles_module

    client, _, Session = pg_app
    _insert(client, "Bornée")
    seen: list[str] = []
    original = tiles_module.apply_tile_statement_timeout

    def spy(session):
        original(session)
        seen.append(session.execute(sa_text("SHOW statement_timeout")).scalar())

    tiles_module.apply_tile_statement_timeout = spy
    try:
        assert client.get(TILE_PATH).status_code == 200
    finally:
        tiles_module.apply_tile_statement_timeout = original
    assert seen == ["10s"]
    with Session() as s:
        assert s.execute(sa_text("SHOW statement_timeout")).scalar() != "10s"


def test_tile_omits_sensitive_property_without_privilege(pg_engine):
    """GAP-22 Task 7 : la propriété marquée sensible ne doit jamais fuiter
    dans le contenu MVT décodé (ici : jamais apparaître comme clé de
    propriété dans le protobuf brut, même patron que
    `test_a_tile_carries_the_properties_but_never_tenant_id` ci-dessus) pour
    un utilisateur sans `data.view_sensitive`, et rester visible pour un
    utilisateur qui le porte.

    Passe par le vrai chemin utilisateur `PATCH /collections/{id}
    {"sensitiveFields": [...]}` (Task 9), pas une écriture directe du
    modèle — miroir de
    `test_features_integration.py::
    test_list_features_masks_sensitive_column_under_real_grant_revoke`
    (Task 6/8), adapté à la route de tuiles MVT."""
    from app.collections import repository as collections_repo
    from app.collections.ddl import apply_collection_ddl

    Base.metadata.create_all(pg_engine)
    # Nom de table sans "salary" comme sous-chaîne : le nom de la couche MVT
    # (issu du nom de table) apparaît lui aussi en clair dans le protobuf, une
    # collision aurait rendu `b"salary" not in content` vraie pour la mauvaise
    # raison (trouvé en exécutant : le premier nom de table choisi,
    # "demo_incidents_salary_tile", faisait échouer l'assertion positive
    # elle-même, indépendamment du masquage).
    table = "demo_incidents_sensitive_tile"
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        conn.execute(
            text(
                f"CREATE TABLE {table} (id serial PRIMARY KEY, "
                "titre text NOT NULL, salary integer, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-salary-tile-gap22",
            username="admin-salary-tile-gap22",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        # Rôle par défaut "creator" : ne porte pas data.view_sensitive
        # (BUILT_IN_ROLE_PRIVILEGES, app/roles/privileges.py) -> masked=True
        # pour cet utilisateur via get_masked_for_user.
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="regular-salary-tile-gap22",
            username="regular-salary-tile-gap22",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        apply_collection_ddl(s, table)
        collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=admin.id,
            table_name=table,
            title="Incidents salaire (tuile)",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        s.execute(
            text(
                f"INSERT INTO {table} (tenant_id, titre, salary, geom) VALUES "
                "(:tid, 'Nid de poule', 5000, ST_SetSRID(ST_MakePoint(2.35, 48.85), 4326))"
            ),
            {"tid": tenant.id},
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    tile_path = f"/v1/collections/{table}/tiles/0/0/0.mvt"
    try:
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_current_user_optional] = lambda: admin
        patch_r = client.patch(f"/v1/collections/{table}", json={"sensitiveFields": ["salary"]})
        assert patch_r.status_code == 200, patch_r.text

        app.dependency_overrides[get_current_user] = lambda: regular
        app.dependency_overrides[get_current_user_optional] = lambda: regular
        r_regular = client.get(tile_path)
        assert r_regular.status_code == 200, r_regular.text
        assert b"titre" in r_regular.content
        assert b"salary" not in r_regular.content

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_current_user_optional] = lambda: admin
        r_admin = client.get(tile_path)
        assert r_admin.status_code == 200, r_admin.text
        assert b"salary" in r_admin.content
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.execute(
                text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
            )


def test_a_list_property_appears_as_json_in_the_tile(pg_engine):
    """REV-191 §D : ST_AsMVT n'accepte que des propriétés scalaires ; une
    colonne list (text[] introspecté) doit sortir en JSON, pas en array brut
    que ST_AsMVT ne sait pas sérialiser. Table dédiée plutôt que `pg_app`
    (fixe sur `demo_incidents`, sans colonne array) — même patron que
    `test_tile_omits_sensitive_property_without_privilege` ci-dessus."""
    table = "demo_incidents_tags_tile"
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        conn.execute(
            text(
                f"CREATE TABLE {table} (id serial PRIMARY KEY, titre text NOT NULL, "
                "tags text[], geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-tags-tile",
            username="admin-tags-tile",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    try:
        create_r = client.post("/v1/collections", json={"tableName": table})
        assert create_r.status_code == 201, create_r.text
        item_r = client.post(
            f"/v1/collections/{table}/items",
            json={
                "type": "Feature",
                "properties": {"titre": "x", "tags": ["urgent", "voirie"]},
                "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
            },
        )
        assert item_r.status_code == 201, item_r.text
        r = client.get(f"/v1/collections/{table}/tiles/0/0/0.mvt")
        assert r.status_code == 200
        # to_jsonb(...)::text met un espace après la virgule (confirmé
        # empiriquement contre le Postgres réel du conteneur de test — ne pas
        # supposer un format compact).
        assert b'["urgent", "voirie"]' in r.content
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.execute(
                text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
            )


def test_serving_a_tile_writes_no_audit_row(pg_app):
    """Décision de spec §3.1 : une vue de carte produit des centaines de
    tuiles, les auditer noierait la table."""
    client, _, Session = pg_app
    _insert(client, "Auditee a l'ecriture seulement")
    with Session() as s:
        before = s.execute(text("SELECT count(*) FROM audit_log")).scalar()
    r = client.get(TILE_PATH)
    # Preuve qu'il s'agit bien d'une tuile servie avec succès, pas d'un 404/500
    # qui n'écrirait pas non plus dans audit_log pour une raison sans rapport :
    # sinon l'assertion finale prouverait "tenter quoi que ce soit sur cette
    # route n'écrit pas d'audit", pas "servir une tuile n'écrit pas d'audit".
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    assert b"Auditee a l'ecriture seulement" in r.content
    with Session() as s:
        assert s.execute(text("SELECT count(*) FROM audit_log")).scalar() == before
