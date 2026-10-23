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

    assert {"https://tiles.example.com"} <= allowlist.img_hosts
    assert {"https://tiles.example.com"} <= allowlist.connect_hosts
    assert {"https://dem.example.com"} <= allowlist.img_hosts
    assert {"https://cdn.example.com"} <= allowlist.script_hosts
    # non-régression : un hôte d'extension ne doit jamais apparaître dans
    # img_hosts/connect_hosts, ni un hôte de tuile dans script_hosts.
    assert "https://cdn.example.com" not in allowlist.img_hosts
    assert "https://tiles.example.com" not in allowlist.script_hosts


def test_compute_csp_allowlist_empty_instance_returns_empty_sets(monkeypatch):
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")
    Session = _make_session()
    with Session() as s:
        allowlist = compute_csp_allowlist(s)
    assert allowlist == CspAllowlist()


def test_compute_csp_allowlist_still_separates_script_hosts_from_tile_hosts(monkeypatch):
    """Même intention que test_script_src_never_widened_by_computed_extension_hosts
    (tests/test_security_jobs.py), à un niveau plus bas : si
    compute_csp_allowlist fusionnait un jour script_hosts dans
    img_hosts/connect_hosts (ou l'inverse), ce test le détecterait même si
    render_dynamic_conf n'était pas encore touché. Committé avec le même
    esprit de garde intentionnelle (SP-48/GAP-72 blocage 3, spec §4)."""
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")  # fonds intégrés hors sujet
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.add(
            Extension(
                id="acme.only-script",
                tenant_id=tenant.id,
                owner_id=user.id,
                tag="x",
                label="X",
                module_url="https://script-only.example.com/w.js",
                props=[],
                events=None,
                actions=None,
                default_size={"w": 1, "h": 1},
                permissions={},
            )
        )
        s.commit()
        allowlist = compute_csp_allowlist(s)

    assert allowlist.script_hosts == {"https://script-only.example.com"}
    assert allowlist.img_hosts == set()
    assert allowlist.connect_hosts == set()


def test_compute_csp_allowlist_ignores_disabled_extensions():
    """REV-166 : une extension désactivée ne doit pas élargir script-src."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="c",
            username="carol",
            email=None,
            first_name="",
            last_name="",
        )
        for ext_id, host, enabled in (
            ("acme.on", "https://on.example.com/w.js", True),
            ("acme.off", "https://off.example.com/w.js", False),
        ):
            s.add(
                Extension(
                    id=ext_id,
                    tenant_id=tenant.id,
                    owner_id=user.id,
                    tag="x",
                    label=ext_id,
                    module_url=host,
                    props=[],
                    events=None,
                    actions=None,
                    default_size={"w": 1, "h": 1},
                    permissions={},
                    enabled=enabled,
                )
            )
        s.commit()
        allowlist = compute_csp_allowlist(s)
    assert allowlist.script_hosts == {"https://on.example.com"}


def test_builtin_basemap_hosts_follow_the_external_basemaps_flag(monkeypatch):
    """Revue L6 M8 : les fonds intégrés (IGN, Carto, démo MapLibre) sont autorisés en
    img/connect-src tant que l'instance les propose, retirés en mode souverain."""
    from app.security.service import BUILTIN_BASEMAP_ORIGINS

    Session = _make_session()
    monkeypatch.delenv("CORE_EXTERNAL_BASEMAPS_ENABLED", raising=False)
    with Session() as s:
        allowlist = compute_csp_allowlist(s)
    assert any(h == "https://data.geopf.fr" for h in allowlist.img_hosts)
    assert BUILTIN_BASEMAP_ORIGINS <= allowlist.connect_hosts
    assert not BUILTIN_BASEMAP_ORIGINS & allowlist.script_hosts
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")
    with Session() as s:
        assert not BUILTIN_BASEMAP_ORIGINS & compute_csp_allowlist(s).img_hosts


def test_compute_csp_allowlist_adds_declared_extension_connect_and_img_hosts(monkeypatch):
    """AUD-109 : seules les origines déclarées au manifeste (activé) élargissent
    connect-src/img-src ; l'origine du module reste cantonnée à script-src."""
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="c",
            username="carol",
            email=None,
            first_name="",
            last_name="",
        )
        for name, enabled in (("on", True), ("off", False)):
            s.add(
                Extension(
                    id=f"acme.{name}",
                    tenant_id=tenant.id,
                    owner_id=user.id,
                    tag="x-y",
                    label="X",
                    module_url=f"https://{name}.example.com/w.js",
                    props=[],
                    events=None,
                    actions=None,
                    default_size={"w": 1, "h": 1},
                    permissions={},
                    connect_hosts=[f"https://api-{name}.example.org"],
                    img_hosts=[f"https://img-{name}.example.org"],
                    enabled=enabled,
                )
            )
        s.commit()
        allowlist = compute_csp_allowlist(s)

    assert allowlist.connect_hosts == {"https://api-on.example.org"}
    assert allowlist.img_hosts == {"https://img-on.example.org"}
    assert allowlist.script_hosts == {"https://on.example.com"}
