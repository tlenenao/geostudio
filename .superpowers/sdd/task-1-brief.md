### Task 1: `check_export_guard` becomes mode-aware

**Files:**
- Modify: `core/app/appexport/guard.py`
- Modify: `core/tests/test_appexport_guard.py`

**Interfaces:**
- Consumes: unchanged (`app.collections.repository`, `app.configs.schemas.BuilderConfig`).
- Produces: `check_export_guard(session, *, tenant_id: str, config: BuilderConfig, mode: str) -> ExportGuardResult` — `mode` is now a **required** keyword-only parameter (was absent before). For `mode="connected"`: `statistics`-type sources are checked against the same `is_public` gate as `features` (not rejected outright), and the widget-type allowlist is skipped entirely. `mode="static"` behavior is byte-for-byte unchanged from SP-18a.

- [ ] **Step 1: Update every existing test call site to pass `mode="static"`, write the failing new-mode tests**

Replace the full contents of `core/tests/test_appexport_guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.guard import check_export_guard
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _app_config(*, data_sources, widget_types=("text",)) -> BuilderConfig:
    items = [
        LayoutItem(id=f"w{i}", widget=t, x=0, y=i, w=4, h=2)
        for i, t in enumerate(widget_types)
    ]
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(type="grid", items=items))],
    )


def _public_collection(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type="point", srid=4326,
    )
    s.commit()
    return tenant.id, col


def _private_collection(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
        title="X", description="", is_public=False,
        pk_column="id", geometry_column=None, geometry_type="point", srid=4326,
    )
    s.commit()
    return tenant.id, col


def test_no_data_sources_and_only_builtin_widgets_is_allowed():
    Session = _session()
    with Session() as s:
        result = check_export_guard(s, tenant_id="t1", config=_app_config(data_sources=[]), mode="static")
    assert result.allowed is True
    assert result.reasons == []


def test_static_source_needs_no_check():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="static", service="core", layer="", query={"records": []}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_non_public_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_public_collection_is_allowed():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_missing_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer="ghost", query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant.id, config=config, mode="static")
    assert result.allowed is False
    assert any("introuvable" in r for r in result.reasons)


def test_statistics_source_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer="x", query={}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("agrégat" in r for r in result.reasons)


def test_unsupported_widget_type_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


def test_unsupported_widget_in_top_level_layout_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = BuilderConfig(
            kind="app",
            dataSources=[],
            layout=Layout(type="grid", items=[
                LayoutItem(id="w0", widget="acme-widget", x=0, y=0, w=4, h=2),
            ]),
            pages=[],
        )
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


# --- Connecté (SP-18b) : mêmes cas, comportement différent sur deux axes ---


def test_statistics_source_on_public_collection_is_allowed_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is False


def test_third_party_widget_is_allowed_in_connected_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="connected")
    assert result.allowed is True
    assert result.reasons == []
```

- [ ] **Step 2: Run to verify the connected-mode tests fail**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: the four `*_connected_mode` tests FAIL with `TypeError:
check_export_guard() missing 1 required keyword-only argument: 'mode'` (the
other tests, which now also pass `mode="static"`, fail the same way).

- [ ] **Step 3: Update `guard.py`**

Replace the full contents of `core/app/appexport/guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a/b) : refuse tout export dont une DataSource
référence une collection non publique. Le mode Statique (SP-18a) refuse en
plus les sources "statistics" (rien à figer côté serveur) et tout widget
hors de l'allowlist builtin (rien n'est bundlé au runtime, un widget tiers
serait introuvable). Le mode Connecté (SP-18b) n'a besoin d'aucune des deux
restrictions : "statistics" appelle /collections/{id}/aggregate en direct
au runtime (déjà anonyme-capable côté serveur pour une collection publique,
cf. app/features/routes.py's get_current_user_optional), et un widget tiers
charge son JS depuis son URL d'origine exactement comme dans le shell
normal — rien n'est bundlé, donc rien à interdire."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
# Uniquement pertinent en mode Statique (mode="static") — cf. docstring.
_SUPPORTED_WIDGET_TYPES = frozenset({
    "text", "image", "button", "table", "list", "map", "indicator", "chart",
    "pivot", "nav", "form", "hero", "richSection", "gallery", "datasetCard",
    "dateRangeFilter", "selectFilter", "sliderFilter", "tabs", "modal",
    "drawer", "filter",
})


@dataclass
class ExportGuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _collect_widget_types(config: BuilderConfig) -> set[str]:
    types: set[str] = set()
    # A config always has at least one page. If `pages` is empty (legacy /
    # implicit single-page shape, cf. shell/src/builder/pages.ts:6-7,23),
    # the widgets actually live in the top-level `layout` — scan both so a
    # single-page app (the common case) doesn't sail through unchecked.
    if config.layout is not None:
        for item in config.layout.items:
            types.add(item.widget)
    for page in config.pages:
        for item in page.layout.items:
            types.add(item.widget)
    return types


def check_export_guard(
    session: Session, *, tenant_id: str, config: BuilderConfig, mode: str,
) -> ExportGuardResult:
    reasons: list[str] = []

    for source in config.dataSources:
        if source.type == "static":
            continue
        if source.type == "statistics" and mode == "static":
            reasons.append(
                f"source '{source.id}' : l'export statique ne supporte pas encore "
                "les sources de type agrégat (statistics)"
            )
            continue
        if source.type not in ("features", "statistics"):
            reasons.append(f"source '{source.id}' : type '{source.type}' non supporté")
            continue
        # "features" (les deux modes) et "statistics" en mode connecté :
        # même garde is_public — le mode connecté appelle
        # /collections/{id}/aggregate en direct au runtime au lieu de figer
        # un résultat côté serveur.
        collection_id = source.layer
        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
        if col is None:
            reasons.append(f"source '{source.id}' : collection '{collection_id}' introuvable")
            continue
        facts = collections_repo.get_access_facts(col)
        if not facts.is_public:
            reasons.append(
                f"source '{source.id}' : collection '{collection_id}' n'est pas partagée publiquement"
            )

    if mode == "static":
        unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
        for widget_type in sorted(unsupported):
            reasons.append(
                f"widget '{widget_type}' non supporté par l'export statique "
                "(extension tierce, non prise en charge)"
            )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/guard.py core/tests/test_appexport_guard.py
git commit -m "feat(core): export guard becomes mode-aware — connected lifts statistics/widget restrictions (SP-18b)"
```

---

