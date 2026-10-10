# SPDX-License-Identifier: Apache-2.0
"""Chemins de lecture hors RLS qui REFUSENT sur une collection limitée (REV-121,
spec §3) + garde AST : aucun `rls_scope(` de app/ sans `geo_limits=` (pièges
n°11/14 — un nouveau chemin de lecture ne peut pas oublier la limite)."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.appexport.freeze import freeze_config
from app.appexport.snapshot import write_snapshot
from app.mcp.tools.identity import McpToolError, refuse_geo_limited
from app.pipelines.runtime import PipelineRuntimeError, _require_readable_collection_id
from app.sharing import geo_limits as gl
from tests.test_geo_limits_core import SQUARE, _put, env  # noqa: F401  (fixture)


def test_pipeline_reader_refuses_a_limited_collection(env):  # noqa: F811
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    with pytest.raises(PipelineRuntimeError, match="geo-limited"):
        _require_readable_collection_id(
            s, tenant_id=tenant.id, user=alice, collection_id="parcelles"
        )
    # non limité (bob, autre cible) ou autre collection : lecture normale
    assert (
        _require_readable_collection_id(s, tenant_id=tenant.id, user=bob, collection_id="parcelles")
        == "parcelles"
    )
    assert (
        _require_readable_collection_id(s, tenant_id=tenant.id, user=alice, collection_id="routes")
        == "routes"
    )


def test_mcp_refuses_a_limited_collection(env):  # noqa: F811
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    with pytest.raises(McpToolError) as exc:
        refuse_geo_limited(s, alice, "parcelles", path="aggregates")
    assert exc.value.status == 403
    refuse_geo_limited(s, alice, "routes", path="aggregates")
    refuse_geo_limited(s, bob, "parcelles", path="aggregates")


def _config(collection_id: str):
    # seuls dataSources[].type/layer sont lus avant le refus
    src = SimpleNamespace(id="ds", type="features", service="core", layer=collection_id)
    return SimpleNamespace(dataSources=[src])


def test_app_export_refuses_any_limited_collection(env, tmp_path):  # noqa: F811
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "role", alice.role_id, SQUARE)
    cfg = _config("parcelles")
    with pytest.raises(gl.GeoLimitRefused):
        freeze_config(s, tenant_id=tenant.id, config=cfg)
    with pytest.raises(gl.GeoLimitRefused):
        write_snapshot(s, tenant_id=tenant.id, config=cfg, snapshot_dir=str(tmp_path))


def test_alert_evaluation_refuses_a_limited_owner(env):  # noqa: F811
    from app.alerts import jobs

    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    assert "parcelles" in gl.resolve_geo_limits(s, tenant_id=tenant.id, user_id=alice.id)
    # la garde est posée avant toute lecture du lac (cf. _measure_value)
    src = Path(jobs.__file__).read_text()
    assert src.index("resolve_geo_limits(session") < src.index("run_collection_aggregate(\n")


APP_DIR = Path(__file__).resolve().parent.parent / "app"
# Le DI `get_rls_scope` lie `geo_limits` par functools.partial ; `rls.py` définit la fonction.
# freeze/snapshot refusent en amont toute collection portant une limite (test ci-dessus).
_ALLOWED_WITHOUT_KEYWORD = {"features/rls.py", "appexport/freeze.py", "appexport/snapshot.py"}


def test_only_known_modules_switch_to_the_rls_role():
    """Un `SET LOCAL ROLE gis_rls` hors rls_scope ne poserait pas app.geo_limits
    (= non limité). Seuls rls.py et le fournisseur d'emprise (qui la pose à la main)."""
    allowed = {"features/rls.py", "collections/routes.py"}
    found = {
        p.relative_to(APP_DIR).as_posix()
        for p in APP_DIR.rglob("*.py")
        if "SET LOCAL ROLE" in p.read_text() and p.name != "ddl.py"
    }
    assert found <= allowed, found - allowed


def test_every_rls_scope_call_carries_geo_limits():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        rel = path.relative_to(APP_DIR).as_posix()
        if rel in _ALLOWED_WITHOUT_KEYWORD:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "rls_scope":
                if not any(k.arg == "geo_limits" for k in node.keywords):
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], f"rls_scope() sans geo_limits= : {offenders}"
