# SPDX-License-Identifier: Apache-2.0
"""compute_csp_allowlist (SP-48/GAP-72) — pure SQLite, même patron que
test_alert_sweep.py/test_pipeline_sweep.py : aucune fonctionnalité
spécifique à PostGIS n'est exercée ici (les MapConfig de test n'ont aucune
couche `vector`/`feature` à collectionId, donc `recompute_item_bbox`
(appelé en interne par `create_config`) ne touche jamais de table dynamique
de collection ni de géométrie — vérifié contre `app/configs/bbox.py` avant
d'écrire ce test, piège CLAUDE.md n°3). Pas de marqueur `postgis` : évite
une dépendance inutile au conteneur `postgis-test` partagé, dont plusieurs
sessions concurrentes se disputaient l'accès au moment de l'exécution de ce
plan (piège CLAUDE.md n°9)."""

from app.configs.repository import create_config
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapTerrain, MapView
from app.db import init_db, make_engine, make_session_factory
from app.extensions.models import Extension
from app.harvest.models import HarvestSource
from app.items import repository as items_repo
from app.security.service import CspAllowlist, compute_csp_allowlist
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_compute_csp_allowlist_aggregates_the_three_sources():
    Session = _make_session()
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
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        s.add(
            HarvestSource(
                id="src-1",
                tenant_id=tenant.id,
                owner_id=user.id,
                type="wms",
                url="https://tiles.example.com/wms",
            )
        )
        s.add(
            Extension(
                id="acme.gauge",
                tenant_id=tenant.id,
                owner_id=user.id,
                tag="gauge",
                label="Gauge",
                module_url="https://cdn.example.com/gauge.js",
                props=[],
                events=None,
                actions=None,
                default_size={"w": 4, "h": 4},
                permissions={},
            )
        )
        create_config(
            s,
            BuilderConfig(
                kind="map",
                map=MapConfig(
                    basemap=BaseMap(style="x"),
                    view=MapView(center=[0, 0], zoom=1),
                    terrain=MapTerrain(tilesUrl="https://dem.example.com/tiles.png"),
                    layers=[],
                ),
            ),
            item.id,
            tenant_id=tenant.id,
        )
        s.commit()

        allowlist = compute_csp_allowlist(s)

    assert "https://tiles.example.com" in allowlist.img_hosts
    assert "https://tiles.example.com" in allowlist.connect_hosts
    assert "https://dem.example.com" in allowlist.img_hosts
    assert "https://cdn.example.com" in allowlist.script_hosts
    # non-régression : un hôte d'extension ne doit jamais apparaître dans
    # img_hosts/connect_hosts, ni un hôte de tuile dans script_hosts.
    assert "https://cdn.example.com" not in allowlist.img_hosts
    assert "https://tiles.example.com" not in allowlist.script_hosts


def test_compute_csp_allowlist_empty_instance_returns_empty_sets():
    Session = _make_session()
    with Session() as s:
        allowlist = compute_csp_allowlist(s)
    assert allowlist == CspAllowlist()
