# SP-18b — Export d'apps : mode Connecté Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author export a published app/dashboard as a static bundle
that keeps calling the **origin GeoStudio core** live, in read-only anonymous
mode, for its already-publicly-shared data sources — SP-18's second export
mode, reusing SP-18a's guard/job/route/panel mechanism almost unchanged.

**Architecture:** `app.appexport.guard.check_export_guard` gains a required
`mode` parameter: for `mode="connected"` it lifts the `statistics`
DataSource-type rejection (`/collections/{id}/aggregate` is already
anonymous-capable for public collections) and drops the widget-type
allowlist entirely (nothing is bundled — third-party SP-8 widgets keep
loading their JS from their own origin exactly as in the normal shell).
`build_app_export_task` skips `freeze_config` for `mode="connected"` (data
stays live) and instead embeds a small `geostudio-connection.json`
(`{"coreUrl": ...}`, sourced from the already-existing `CORE_BASE_URL` env
var) into the zip alongside the **unfrozen** config. The existing prebuilt
runtime (`shell/src/staticExport/entry.tsx`, one Vite entry, one Docker
image) becomes mode-aware at load: it always fetches
`geostudio-app-config.json`, then optionally fetches
`geostudio-connection.json` — present means Connecté (`createItemClient` from
`shell/src/api/itemClient.ts`, the same factory the normal running shell
uses, constructed with the embedded `coreUrl` and a `getToken` that always
returns `undefined`), absent means Statique (`createStaticItemClient`,
unchanged). A new narrow, capability-gated CORS middleware in
`core/app/main.py` allows cross-origin browser access (wildcard origin, no
credentials ever involved) to exactly the read-only endpoints an exported
bundle needs.

**Tech Stack:** FastAPI/SQLAlchemy/procrastinate (core, existing patterns),
Vite/React/TypeScript (shell, existing patterns) — no new dependencies.

## Global Constraints

- Capability gate is the **existing** `CORE_APPEXPORT_ENABLED` (no new flag):
  `_SUPPORTED_MODES` in `core/app/appexport/routes.py` simply widens from
  `{"static"}` to `{"static", "connected"}`.
- **`coreUrl` embedded in a Connecté bundle is `CORE_BASE_URL`** — already
  present in every deployment (`core/app/mcp/server.py:12`'s docstring: "the
  cœur's own externally-reachable URL"), already used for the exact same
  "externally reachable URL others should call" purpose by the MCP resource
  identifier. No new env var. Default `http://localhost:8200` is an
  operator footgun for a *real* deployment (an operator who never set
  `CORE_BASE_URL` gets a bundle that only works against localhost) but this
  is a pre-existing property of `CORE_BASE_URL` shared with the MCP server,
  not something SP-18b introduces or should special-case.
- **Load-bearing gotcha, discovered during research — must not regress:**
  `shell/src/auth/useAuth.ts`'s `enableMockAuth()` makes `getAccessToken()`
  return the literal string `"mock-token"`. The export entry must keep
  calling `enableMockAuth()` (both modes need it — `AppRenderer` calls
  `useAuth()` via `ActionConditionBridge`, which throws without it, no
  `<AuthProvider>` ancestor exists in either export mode). But the
  `getToken` passed into `createItemClient` for Connecté **must be a
  hardcoded `() => undefined`, never wired through `useAuth().getAccessToken`
  or `buildExportAwareToken`** — the real `createItemClient` attaches
  `Authorization: Bearer ${token}` whenever `getToken()` returns a truthy
  value, and the core's `get_current_user_optional` (used by every
  anonymous-capable endpoint) treats *any present* `Authorization` header as
  "must be a valid token or 401" — it does **not** fall back to anonymous on
  an invalid token. Sending `"mock-token"` would 401 every single read a
  Connecté bundle makes.
- **Reused from SP-18a, still true, explains a design simplification here
  too:** a persisted `BuilderConfig`'s `DataSource.layer` is always the
  literal collection id already (`datasetId` isn't a real schema field —
  pydantic's `extra="ignore"` silently drops it on every round-trip through
  the server). So `check_export_guard` and the job never need
  dataset-item resolution, and the CORS allowlist never needs to cover
  `/datasets/{id}/arcgis/...` — a persisted config's DataSource always
  resolves through `/collections/{id}/...` regardless of mode.
- New CORS middleware in `core/app/main.py`: `allow_origins` is a wildcard
  (`*`) — safe here specifically because no credentials/cookies ever cross
  this boundary (every request is Bearer-header-or-nothing, never
  cookie-based) — but the **path allowlist is narrow**: only
  `GET /collections`, `GET /collections/{id}`, `GET /collections/{id}/schema`,
  `GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`,
  `POST /collections/{id}/aggregate`, `GET /extensions` — exactly the
  anonymous-capable endpoints (`get_current_user_optional`-gated) a Connecté
  bundle's `ItemClient` calls. Never the whole API. Read (and enabled) once
  at `create_app()` time, same evaluation-timing convention as the existing
  `if is_appexport_enabled(): app.include_router(...)` — not re-checked
  per-request.
- **SQL Lab (`/analytics/sql`) stays out of scope for Connecté v1** — it
  requires `get_current_user` (real auth) **and** `user.is_analyst`
  (`core/app/collections/routes.py:313,318`), there is no anonymous path for
  it today, and no `sqlLab` widget type exists yet in the shell's widget
  registry. Not built here; a future SQL-Lab-backed widget would just get a
  real 401 from the live endpoint at runtime (never a data leak, since the
  server-side auth check is untouched by this plan) — no guard-side special
  case is needed to keep this safe.
- `check_export_guard`'s new `mode: str` parameter is **required, no
  default** — every existing call site must be updated explicitly (the sole
  production caller is `build_app_export_task`; several test files call it
  directly and need `mode="static"` added to preserve their existing
  assertions unchanged).
- Every code step in this plan follows TDD (failing test → minimal
  implementation → passing test → commit), per this repo's CLAUDE.md.

---

## File structure

**Core (`core/`)**
- Modify `core/app/appexport/guard.py`, `core/tests/test_appexport_guard.py`
- Modify `core/app/appexport/bundler.py`, `core/tests/test_appexport_bundler.py`
- Modify `core/app/appexport/jobs.py`, `core/tests/test_appexport_jobs.py`
- Modify `core/app/appexport/routes.py`, `core/tests/test_appexport_routes.py`
- Modify `core/app/main.py`
- Create `core/tests/test_appexport_cors.py`

**Shell (`shell/`)**
- Modify `shell/src/api/types.ts`
- Modify `shell/src/staticExport/entry.tsx`
- Modify `shell/src/builder/appexport/AppExportPanel.tsx`,
  `shell/src/builder/appexport/AppExportPanel.test.tsx`
- Create `shell/e2e/connected-export.spec.ts`

---

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

### Task 2: `build_bundle_zip` gains an optional `connection` payload

**Files:**
- Modify: `core/app/appexport/bundler.py`
- Modify: `core/tests/test_appexport_bundler.py`

**Interfaces:**
- Consumes: unchanged.
- Produces: `build_bundle_zip(config: BuilderConfig, *, runtime_dir: str, connection: dict | None = None) -> bytes`. When `connection` is provided, the zip additionally contains `geostudio-connection.json` (plain `json.dumps(connection)`) at the zip root. Default `None` preserves SP-18a's exact existing behavior byte-for-byte (no such file, existing tests untouched).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_bundler.py` (existing two tests stay exactly as-is above this):

```python


def test_bundle_includes_connection_json_when_provided(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")

    zip_bytes = build_bundle_zip(
        _config(), runtime_dir=str(runtime_dir), connection={"coreUrl": "https://core.example.org"},
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "geostudio-connection.json" in zf.namelist()
        payload = zf.read("geostudio-connection.json").decode("utf-8")
        assert '"coreUrl"' in payload and "https://core.example.org" in payload


def test_bundle_omits_connection_json_by_default(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")

    zip_bytes = build_bundle_zip(_config(), runtime_dir=str(runtime_dir))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "geostudio-connection.json" not in zf.namelist()
```

- [ ] **Step 2: Run to verify the new test fails**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: `test_bundle_includes_connection_json_when_provided` FAILS with
`TypeError: build_bundle_zip() got an unexpected keyword argument
'connection'`. `test_bundle_omits_connection_json_by_default` passes already
(current behavior already omits the file — kept as an explicit regression
guard for this task, not a new failure).

- [ ] **Step 3: Update `bundler.py`**

Replace the full contents of `core/app/appexport/bundler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Assemble le zip d'export : runtime prébâti (jamais reconstruit par ce
job) + config sérialisée en JSON, lue au runtime par
shell/src/staticExport/entry.tsx via un fetch relatif — aucune invocation
Node/Vite ici.

Mode Statique (SP-18a) : `connection=None`, le fichier geostudio-app-
config.json contient la config déjà gelée (freeze_config) par l'appelant.
Mode Connecté (SP-18b) : `connection={"coreUrl": ...}`, la config passée
n'est PAS gelée (elle garde ses DataSources "features"/"statistics"
d'origine) — un second fichier geostudio-connection.json embarque l'URL du
cœur d'origine ; sa présence/absence dans le zip est le seul signal dont
entry.tsx a besoin pour choisir createItemClient (réseau réel) vs
createStaticItemClient (aucun réseau)."""
import io
import json
import os
import zipfile

from app.configs.schemas import BuilderConfig


def build_bundle_zip(
    config: BuilderConfig, *, runtime_dir: str, connection: dict | None = None,
) -> bytes:
    entry_path = os.path.join(runtime_dir, "index.export.html")
    if not os.path.isfile(entry_path):
        raise FileNotFoundError(f"export runtime not found at {entry_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(entry_path, "rb") as f:
            zf.writestr("index.html", f.read())
        assets_dir = os.path.join(runtime_dir, "assets")
        if os.path.isdir(assets_dir):
            for name in os.listdir(assets_dir):
                with open(os.path.join(assets_dir, name), "rb") as f:
                    zf.writestr(f"assets/{name}", f.read())
        zf.writestr("geostudio-app-config.json", config.model_dump_json(by_alias=True))
        if connection is not None:
            zf.writestr("geostudio-connection.json", json.dumps(connection))
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/bundler.py core/tests/test_appexport_bundler.py
git commit -m "feat(core): bundler embeds an optional geostudio-connection.json (SP-18b)"
```

---

### Task 3: `build_app_export_task` branches on `mode`

**Files:**
- Modify: `core/app/appexport/jobs.py`
- Modify: `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes: `check_export_guard(..., mode=...)` (Task 1), `build_bundle_zip(..., connection=...)` (Task 2).
- Produces: unchanged public signature `build_app_export_task(job_id: str, tenant_id: str) -> None`. For `mode="connected"`: skips `freeze_config`, reads `CORE_BASE_URL` (default `http://localhost:8200`, same default used elsewhere in this codebase for the same variable) and passes it as `connection={"coreUrl": ...}` to the bundler.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_appexport_jobs.py` (existing three tests and
`_setup`/`_fake_s3` stay as-is; add a `mode` parameter to `_setup` with
default `"static"` so existing calls — which pass none — keep testing
static mode unchanged):

Modify `_setup`'s signature and the `create_job` call inside it:

```python
def _setup(monkeypatch, tmp_path, *, with_private_source=False, mode="static"):
```

```python
        job = appexport_repo.create_job(s, tenant_id=tenant.id, item_id=item.id, user_id=owner.id, mode=mode)
```

(only those two lines change in `_setup`; everything else in the function body is untouched)

Then append these new tests at the end of the file:

```python


def test_connected_job_skips_freezing_and_embeds_core_base_url(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, mode="connected")
    monkeypatch.setenv("CORE_BASE_URL", "https://core.example.org")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)

    captured: dict = {}
    real_build_bundle_zip = __import__("app.appexport.jobs", fromlist=["build_bundle_zip"]).build_bundle_zip

    def spy_build_bundle_zip(config, **kwargs):
        captured["connection"] = kwargs.get("connection")
        captured["config"] = config
        return real_build_bundle_zip(config, **kwargs)

    monkeypatch.setattr("app.appexport.jobs.build_bundle_zip", spy_build_bundle_zip)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)

    build_app_export_task(job_id=job_id, tenant_id=tenant_id)

    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "done"
    assert captured["connection"] == {"coreUrl": "https://core.example.org"}


def test_connected_job_with_private_source_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, with_private_source=True, mode="connected")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "publique" in job.error
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: `test_connected_job_skips_freezing_and_embeds_core_base_url` FAILS
(`check_export_guard() missing 1 required keyword-only argument: 'mode'` —
`jobs.py` doesn't pass `mode` yet). `test_connected_job_with_private_source_marks_error`
fails the same way. The three pre-existing tests (now implicitly
`mode="static"` via `_setup`'s default) also fail for the same reason since
`jobs.py`'s call to `check_export_guard` has no `mode=` kwarg at all yet.

- [ ] **Step 3: Update `jobs.py`**

Replace the full contents of `core/app/appexport/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-18a/b) : guard → (statique : gèle les
DataSources ; connecté : garde la config telle quelle + embarque l'URL du
cœur) → assemble le zip → upload S3. Tourne sur le worker partagé (queue
`appexport`, pas de Chromium/Node ici). Toute erreur marque le job "error",
jamais un job bloqué en "running" (même critère que
app.export.jobs/app.pipelines.jobs)."""
import logging
import os

from app.appexport import repository as appexport_repo
from app.appexport.bundler import build_bundle_zip
from app.appexport.freeze import freeze_config
from app.appexport.guard import check_export_guard
from app.auth.dependency import is_appexport_enabled
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _prepare_bundle_inputs(
    session, *, tenant_id: str, mode: str, config: BuilderConfig,
) -> tuple[BuilderConfig, dict | None]:
    if mode == "connected":
        core_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
        return config, {"coreUrl": core_url}
    return freeze_config(session, tenant_id=tenant_id, config=config), None


@app.task(queue="appexport")
def build_app_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_appexport_enabled():
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error="app export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        appexport_repo.mark_running(session, job_id=job_id)
        item_id = job.item_id
        mode = job.mode

    try:
        with request_scoped_session(session_factory) as session:
            config_read = configs_repo.get_config_by_item(session, item_id)
            if config_read is None:
                raise ValueError(f"app export item '{item_id}' not found")
            guard_result = check_export_guard(session, tenant_id=tenant_id, config=config_read.config, mode=mode)
            if not guard_result.allowed:
                raise ValueError("; ".join(guard_result.reasons))
            bundle_config, connection = _prepare_bundle_inputs(
                session, tenant_id=tenant_id, mode=mode, config=config_read.config,
            )

        runtime_dir = os.environ["APPEXPORT_RUNTIME_DIR"]
        zip_bytes = build_bundle_zip(bundle_config, runtime_dir=runtime_dir, connection=connection)

        result_key = f"appexports/{job_id}.zip"
        bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        s3_client = s3_client_from_env()
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(Bucket=bucket, Key=result_key, Body=zip_bytes, ContentType="application/zip")

        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("app export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/jobs.py core/tests/test_appexport_jobs.py
git commit -m "feat(core): app export job branches on mode — connected skips freezing (SP-18b)"
```

---

### Task 4: widen `_SUPPORTED_MODES` on the routes

**Files:**
- Modify: `core/app/appexport/routes.py`
- Modify: `core/tests/test_appexport_routes.py`

**Interfaces:**
- Produces: `POST /app-exports` now accepts `mode: "static" | "connected"` (was `"static"` only).

- [ ] **Step 1: Update the existing invalid-mode test, write the new accepted-mode test**

In `core/tests/test_appexport_routes.py`, replace
`test_post_app_export_rejects_invalid_mode` (the comment and the mode value
both change — `"connected"` is no longer invalid):

```python
def test_post_app_export_rejects_invalid_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "bogus"})
    assert response.status_code == 422
```

Then append a new test at the end of the file:

```python


def test_post_app_export_accepts_connected_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "connected"})
    assert response.status_code == 202
    assert len(calls) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: `test_post_app_export_rejects_invalid_mode` still PASSES (`"bogus"`
was already rejected by the old `_SUPPORTED_MODES = {"static"}`).
`test_post_app_export_accepts_connected_mode` FAILS with `422` instead of
`202` (`"connected"` not yet in `_SUPPORTED_MODES`).

- [ ] **Step 3: Widen `_SUPPORTED_MODES` in `routes.py`**

In `core/app/appexport/routes.py`, change:

```python
_SUPPORTED_MODES = {"static"}  # "connected"/"standalone" arrivent en SP-18b/c
```

to:

```python
_SUPPORTED_MODES = {"static", "connected"}  # "standalone" arrive en SP-18c
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/routes.py core/tests/test_appexport_routes.py
git commit -m "feat(core): POST /app-exports accepts mode=connected (SP-18b)"
```

---

### Task 5: narrow, capability-gated CORS middleware

**Files:**
- Modify: `core/app/main.py`
- Create: `core/tests/test_appexport_cors.py`

**Interfaces:**
- Produces: when `CORE_APPEXPORT_ENABLED=true`, `OPTIONS`/`GET`/`POST` on a
  fixed allowlist of already-anonymous-capable read paths (`/collections`,
  `/collections/{id}`, `/collections/{id}/schema`, `/collections/{id}/items`,
  `/collections/{id}/items/{fid}`, `/collections/{id}/aggregate`,
  `/extensions`) get `Access-Control-Allow-Origin: *` on the response (and a
  204 with the matching preflight headers for `OPTIONS`). Every other path,
  and every path when the flag is off, is untouched.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_appexport_cors.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def test_cors_header_present_on_matched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/collections")
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_header_absent_when_disabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    client = TestClient(create_app())
    response = client.get("/collections")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_responds_on_matched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.options("/collections/col1/aggregate")
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "content-type" in response.headers.get("access-control-allow-headers", "").lower()


def test_cors_header_absent_on_unmatched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_cors.py -v`
Expected: FAIL — `test_cors_header_present_on_matched_path_when_enabled` and
`test_cors_preflight_responds_on_matched_path_when_enabled` fail (no header
present / 405 instead of 204); the other two pass already (nothing to
regress).

- [ ] **Step 3: Add the middleware in `main.py`**

In `core/app/main.py`, change the import line:

```python
from fastapi.responses import JSONResponse
```

to:

```python
from fastapi.responses import JSONResponse, Response
```

Then, directly below the existing `_EXPORT_PATH_RE` definition, add:

```python
# CORS narrow allowlist (SP-18b) : uniquement les endpoints déjà
# anonymes-capables (get_current_user_optional) qu'un bundle d'export
# Connecté appelle en direct depuis un domaine tiers arbitraire — jamais
# toute l'API. Wildcard origin sûr ici précisément parce qu'aucune
# credential/cookie ne traverse cette frontière (Bearer-ou-rien).
_APPEXPORT_CORS_PATH_RE = re.compile(
    r"^/collections(/[^/]+)?$"
    r"|^/collections/[^/]+/schema$"
    r"|^/collections/[^/]+/items(/[^/]+)?$"
    r"|^/collections/[^/]+/aggregate$"
    r"|^/extensions$"
)
```

Then, inside `create_app()`, directly after the existing `read_only_guard`
middleware function definition (right before `def get_session() ->
Iterator[Session]:`), add:

```python
    if is_appexport_enabled():
        @app.middleware("http")
        async def appexport_cors(request: Request, call_next):
            if not _APPEXPORT_CORS_PATH_RE.match(request.url.path):
                return await call_next(request)
            if request.method == "OPTIONS":
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                    },
                )
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
```

(evaluated once at `create_app()` time, same timing convention as the
existing `if is_appexport_enabled(): app.include_router(appexport_routes.router)`
a few lines below it — not re-checked per request.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_cors.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full core suite to confirm nothing broke**

Run: `cd core && uv run pytest -q`
Expected: PASS (no regressions — the middleware only touches responses on
the narrow matched-path allowlist).

- [ ] **Step 6: Commit**

```bash
git add core/app/main.py core/tests/test_appexport_cors.py
git commit -m "feat(core): narrow CORS allowlist for connected app exports (SP-18b)"
```

---

### Task 6: widen `AppExportMode` on the shell

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `AppExportMode = "static" | "connected"` (was `"static"` only).

- [ ] **Step 1: Widen the type**

In `shell/src/api/types.ts`, change:

```ts
export type AppExportMode = "static";
```

to:

```ts
export type AppExportMode = "static" | "connected";
```

- [ ] **Step 2: Run the type checker**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS (widening a union type is never a breaking change for
existing callers that only ever passed `"static"`).

- [ ] **Step 3: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): AppExportMode gains \"connected\" (SP-18b)"
```

---

### Task 7: export entry becomes mode-aware at load

**Files:**
- Modify: `shell/src/staticExport/entry.tsx`

**Interfaces:**
- Consumes: `createItemClient` (`shell/src/api/itemClient.ts`, unchanged —
  already accepts `{coreUrl, getToken}` as plain params, no rewrite needed),
  `createStaticItemClient` (unchanged, Task 6's `AppExportMode` type is not
  referenced here — this file branches on the *presence* of
  `geostudio-connection.json`, not on a mode string).
- Produces: same bootstrap behavior for Statique as before; for Connecté
  (when `geostudio-connection.json` is present in the served bundle),
  constructs a live, anonymous `ItemClient` pointed at the embedded
  `coreUrl`.

- [ ] **Step 1: Update `entry.tsx`**

Replace the full contents of `shell/src/staticExport/entry.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du bundle d'export (SP-18a Statique + SP-18b
// Connecté) : un seul runtime prébâti pour les deux modes, mode détecté au
// chargement par la présence de geostudio-connection.json (core/app/
// appexport/bundler.py). Jamais de redirection OIDC ici — enableMockAuth()
// avant le premier rendu, dans les deux modes : AppRenderer appelle
// useAuth() (via ActionConditionBridge) et ce hook lit `mockMode` avant de
// toucher react-oidc-context, qui lèverait sinon faute d'<AuthProvider>
// ancêtre — INDÉPENDANT du getToken passé à createItemClient ci-dessous.
//
// Piège découvert en conception SP-18b, à ne pas réintroduire :
// enableMockAuth() fait retourner "mock-token" à useAuth().getAccessToken —
// si ce token était câblé dans createItemClient's getToken, chaque requête
// anonyme casserait (get_current_user_optional traite tout Authorization
// présent comme "doit être valide", jamais de repli anonyme sur un token
// invalide). Le getToken du mode Connecté est donc un () => undefined
// codé en dur, jamais relié à useAuth().
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { enableMockAuth } from "../auth/useAuth";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig, ItemClient } from "../api/types";
import "../index.css";

enableMockAuth();
registerBuiltinWidgets();
// DataContext (builder/DataContext.tsx) appelle useQueries (@tanstack/react-query),
// tout comme App.tsx en mode normal — sans ce provider, tout widget de données
// (table/list/chart/…) fait planter React avec "No QueryClient set" avant même
// le premier rendu, indépendamment du choix de widget.
const queryClient = new QueryClient();

async function loadConnection(): Promise<{ coreUrl: string } | null> {
  const response = await fetch("./geostudio-connection.json");
  if (!response.ok) return null;
  return (await response.json()) as { coreUrl: string };
}

function buildClient(config: AppConfig, connection: { coreUrl: string } | null): ItemClient {
  if (connection) {
    return createItemClient({ coreUrl: connection.coreUrl, getToken: () => undefined });
  }
  return createStaticItemClient(config);
}

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("export entry: #root introuvable");
  const response = await fetch("./geostudio-app-config.json");
  if (!response.ok) throw new Error("export entry: geostudio-app-config.json introuvable");
  const config = (await response.json()) as AppConfig;
  const connection = await loadConnection();
  const client = buildClient(config, connection);
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <div className="h-screen w-screen">
            {/* No `pageId`/`onNavigate` here: leaving `pageId` undefined lets
                AppRenderer's own internal state drive navigation (nav
                widgets, tabs, story mode) — a fixed `pageId` prop pins the
                active page forever since it always wins over internal state
                (SP-18a review, C3). */}
            <AppRenderer config={config} mode="runtime" />
          </div>
        </ItemClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  if (root) root.textContent = `Erreur de chargement : ${(err as Error).message}`;
});
```

- [ ] **Step 2: Build the export runtime and typecheck**

Run: `cd shell && npm run build:export-runtime`
Expected: PASS (builds `dist-export/`, no TS errors — `createItemClient`'s
`{coreUrl, getToken}` shape and `ItemClient` are both already exported from
`../api/itemClient` and `../api/types` respectively).

- [ ] **Step 3: Commit**

```bash
git add shell/src/staticExport/entry.tsx
git commit -m "feat(shell): export runtime detects Connecté mode via geostudio-connection.json (SP-18b)"
```

---

### Task 8: second "Connecté" button + fix the write-warning mode bug

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.tsx`
- Modify: `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Interfaces:**
- Produces: same public component signature. Internally, `showWriteWarning:
  boolean` is replaced by `pendingWarningMode: AppExportMode | null` — this
  also fixes a latent bug in the SP-18a code: the "Exporter quand même"
  confirm button always called `runExport("static")` regardless of which
  mode's button had triggered the warning; with only one mode that bug was
  invisible, but it would silently export Static instead of Connecté the
  moment a second button existed.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/appexport/AppExportPanel.test.tsx` (the
existing two tests stay as-is, but the second one's `getByRole("button", {
name: /statique/i })` click now also has a sibling "Connecté" button to
disambiguate from — no change needed there since `/statique/i` still
matches only one button):

```tsx


  it("triggers a connected export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected");
  });

  it("confirms the write warning with the mode that actually triggered it", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config(true)} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /quand même/i }));
    await waitFor(() => expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected"));
  });
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: both new tests FAIL — no "Connecté" button exists yet
(`getByRole("button", { name: /connect/i })` throws), and the confirm
button always sends `"static"`.

- [ ] **Step 3: Update `AppExportPanel.tsx`**

In `shell/src/builder/appexport/AppExportPanel.tsx`, replace the
`showWriteWarning` state declaration:

```tsx
  const [showWriteWarning, setShowWriteWarning] = useState(false);
```

with:

```tsx
  const [pendingWarningMode, setPendingWarningMode] = useState<AppExportMode | null>(null);
```

Replace `runExport`'s first line:

```tsx
  async function runExport(mode: AppExportMode) {
    setShowWriteWarning(false);
```

with:

```tsx
  async function runExport(mode: AppExportMode) {
    setPendingWarningMode(null);
```

Replace `onChooseMode`:

```tsx
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) => WRITE_CAPABLE_WIDGET_TYPES.has(t));
    if (hasWriteWidget) {
      setDialogOpen(false);
      setShowWriteWarning(true);
      return;
    }
    void runExport(mode);
  }
```

with:

```tsx
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) => WRITE_CAPABLE_WIDGET_TYPES.has(t));
    if (hasWriteWidget) {
      setDialogOpen(false);
      setPendingWarningMode(mode);
      return;
    }
    void runExport(mode);
  }
```

Replace the dialog's button row:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
        </div>
```

with:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
            Connecté
          </Button>
        </div>
```

Replace the warning block:

```tsx
      {showWriteWarning && (
        <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
          <p>
            Cette app contient un widget Formulaire — toute écriture sera
            désactivée dans l&apos;export statique faute de backend.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => runExport("static")}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowWriteWarning(false)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
```

with:

```tsx
      {pendingWarningMode && (
        <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
          <p>
            Cette app contient un widget Formulaire — toute écriture sera
            désactivée dans l&apos;export faute de session authentifiée.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => runExport(pendingWarningMode)}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPendingWarningMode(null)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/appexport/AppExportPanel.test.tsx
git commit -m "feat(shell): AppExportPanel gains a Connecté button, fixes write-warning mode bug (SP-18b)"
```

---

### Task 9: real cross-origin E2E test

**Files:**
- Create: `shell/e2e/connected-export.spec.ts`

**Interfaces:**
- Consumes: `dist-export/` (built by Task 7's `npm run build:export-runtime`, same artifact both modes now share).

- [ ] **Step 1: Write the test**

Create `shell/e2e/connected-export.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Preuve en conditions réelles (pas assérée) que le mode Connecté (SP-18b)
// fait un vrai fetch cross-origin dans Chromium depuis l'origine du bundle
// exporté vers une origine "cœur" distincte, et que ce fetch part sans
// aucun header Authorization — même esprit que static-export.spec.ts (SP-18a)
// prouvant le mode Statique sans aucun backend : ici on prouve le mode
// Connecté avec un vrai backend, sur un vrai domaine tiers, sans identifiant
// embarqué. La fausse "core" ci-dessous répond avec Access-Control-Allow-
// Origin: * — c'est le comportement que core/app/main.py's CORS middleware
// (Task 5) doit fournir en vrai ; ce test ne remplace pas test_appexport_cors.py,
// il prouve le côté client du contrat.
import { test, expect } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { readFile, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST_EXPORT = fileURLToPath(new URL("../dist-export", import.meta.url));

const CONNECTED_CONFIG = {
  kind: "app", theme: {}, navigationMode: "tabs", variables: [], messages: [],
  dataSources: [
    { id: "s1", type: "features", service: "core", layer: "col1", query: {} },
  ],
  pages: [{
    id: "p1", name: "P1", onEnter: [],
    layout: { type: "grid", breakpoints: {}, items: [{ id: "w1", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s1" } }] },
  }],
};

async function skipIfNoBuild() {
  await access(path.join(DIST_EXPORT, "index.export.html")).catch(() => {
    test.skip(true, "dist-export/index.export.html absent — lancer `npm run build:export-runtime` avant ce test");
  });
}

async function startFakeCore(): Promise<{ server: Server; url: string; sawAuthHeader: () => boolean }> {
  let sawAuthHeader = false;
  const server = createServer((req, res) => {
    if (req.headers.authorization) sawAuthHeader = true;
    res.setHeader("Access-Control-Allow-Origin", "*");
    if (req.url === "/collections/col1/items") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({
        type: "FeatureCollection",
        features: [{ id: 1, type: "Feature", properties: { name: "Alpha" }, geometry: null }],
      }));
      return;
    }
    res.statusCode = 404;
    res.end("not found");
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return { server, url: `http://127.0.0.1:${port}`, sawAuthHeader: () => sawAuthHeader };
}

test("connected export bundle renders live data from a real cross-origin core, with no auth header", async ({ page }) => {
  await skipIfNoBuild();

  const fakeCore = await startFakeCore();
  const connection = { coreUrl: fakeCore.url };

  const server = createServer(async (req, res) => {
    const reqUrl = req.url ?? "/";
    if (reqUrl === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(CONNECTED_CONFIG));
      return;
    }
    if (reqUrl === "/geostudio-connection.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(connection));
      return;
    }
    const filePath = reqUrl === "/" ? "/index.export.html" : reqUrl;
    try {
      const body = await readFile(path.join(DIST_EXPORT, filePath.replace(/^\//, "")));
      const contentType = filePath.endsWith(".js") ? "application/javascript" : filePath.endsWith(".css") ? "text/css" : "text/html";
      res.setHeader("Content-Type", contentType);
      res.end(body);
    } catch {
      res.statusCode = 404;
      res.end("not found");
    }
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  const url = `http://127.0.0.1:${port}`;

  try {
    await page.goto(url);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
    expect(fakeCore.sawAuthHeader()).toBe(false);
  } finally {
    server.close();
    fakeCore.server.close();
  }
});
```

- [ ] **Step 2: Build the export runtime, then run the test**

Run: `cd shell && npm run build:export-runtime && npx playwright test e2e/connected-export.spec.ts`
Expected: PASS. If it fails with a CORS console error visible via
`page.on("console", ...)`, the most likely cause is `_fetchGeoJsonFeatures`
(itemClient.ts) sending a header the fake core's `Access-Control-Allow-Origin: *`
response doesn't cover for a non-simple request — verify `getToken: () =>
undefined` really produces an empty `headers: {}` object on that call path
(Task 7's `buildClient` wiring), not a `{}`-shaped-but-truthy value.

- [ ] **Step 3: Commit**

```bash
git add shell/e2e/connected-export.spec.ts
git commit -m "test(e2e): connected export bundle renders live cross-origin data with no auth header (SP-18b)"
```

---

## Self-review notes

- **Spec coverage:** umbrella spec §2.1 (Connecté restricted to public
  sources, no embedded credential) → Task 1 (guard) + Task 7 (hardcoded
  `getToken`). §3 mechanism (guard before every export, same job/route
  shape) → Tasks 1–4 reuse SP-18a's shape verbatim, only widening it. §5.2
  validation ("données affichées à jour côté cœur", "item non partagé
  bloque l'export") → Task 9 (live E2E) + Task 1's
  `test_features_source_on_non_public_collection_is_still_blocked_in_connected_mode`.
  §6 open question ("format exact de l'artefact Connecté") → resolved:
  same zip mechanism as Static, `geostudio-connection.json`'s
  presence/absence is the mode signal.
- **Placeholder scan:** none found — every step has real, complete code.
- **Type consistency:** `check_export_guard(..., mode: str)` used
  identically in Task 1 (definition) and Task 3 (`jobs.py` call site,
  `mode=mode` from `job.mode`). `build_bundle_zip(..., connection: dict |
  None)` used identically in Task 2 (definition) and Task 3
  (`_prepare_bundle_inputs`'s return value). `AppExportMode` used
  identically across Task 6 (type widened), Task 7 (not referenced —
  intentional, entry.tsx branches on file presence not a mode string), Task
  8 (`pendingWarningMode: AppExportMode | null`).
