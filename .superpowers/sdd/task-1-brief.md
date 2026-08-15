### Task 1: `check_export_guard` gains `mode="standalone"`

**Files:**
- Modify: `core/app/appexport/guard.py`
- Modify: `core/tests/test_appexport_guard.py`

**Interfaces:**
- Consumes: unchanged (`app.collections.repository`, `app.configs.schemas.BuilderConfig`).
- Produces: `check_export_guard(session, *, tenant_id, config, mode)` — `mode="standalone"` behaves like `mode="connected"` for the `is_public` check on `features`/`statistics` sources (statistics fully supported), but like `mode="static"` for the widget-type allowlist (builtin-only, no third-party widgets).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_appexport_guard.py` (every existing test/helper stays as-is above this):

```python


# --- Autoporté (SP-18c) : leniency d'is_public de "connected", allowlist de widgets de "static" ---


def test_statistics_source_on_public_collection_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False


def test_unsupported_widget_type_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


def test_builtin_widgets_only_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "table", "map"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is True
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: the five new `*_standalone_mode` tests FAIL — `mode="standalone"`
currently falls through `check_export_guard`'s `if mode == "static":` branch
as false (so the widget allowlist is never applied, `test_unsupported_widget_type_is_blocked_in_standalone_mode`
fails) and the `statistics` early-rejection is also skipped as false-for-static
only (so those pass by accident already) — actually verify empirically, the
important one to see fail is the widget-allowlist test.

- [ ] **Step 3: Update `guard.py`**

Replace the full contents of `core/app/appexport/guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a/b/c) : refuse tout export dont une DataSource
référence une collection non publique. Le mode Statique (SP-18a) refuse en
plus les sources "statistics" (rien à figer côté serveur) et tout widget
hors de l'allowlist builtin (rien n'est bundlé au runtime, un widget tiers
serait introuvable). Le mode Connecté (SP-18b) n'a besoin d'aucune des deux
restrictions : "statistics" appelle /collections/{id}/aggregate en direct
au runtime (déjà anonyme-capable côté serveur pour une collection publique,
cf. app/features/routes.py's get_current_user_optional), et un widget tiers
charge son JS depuis son URL d'origine exactement comme dans le shell
normal — rien n'est bundlé, donc rien à interdire. Le mode Autoporté
(SP-18c) combine les deux axes indépendamment : is_public lenient comme
Connecté ("statistics" pleinement supporté, figé dans l'instantané et
interrogé via /aggregate par le mini-serveur), MAIS allowlist de widgets
stricte comme Statique (rien n'est bundlé ici non plus — décision prise en
session 2026-08-15, cf. design SP-18c §3.3 : aucune tentative de bundling
offline de widgets tiers)."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
# Pertinent pour mode="static" ET mode="standalone" — cf. docstring.
_SUPPORTED_WIDGET_TYPES = frozenset({
    "text", "image", "button", "table", "list", "map", "indicator", "chart",
    "pivot", "nav", "form", "hero", "richSection", "gallery", "datasetCard",
    "dateRangeFilter", "selectFilter", "sliderFilter", "tabs", "modal",
    "drawer", "filter",
})

_STRICT_WIDGET_MODES = frozenset({"static", "standalone"})


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
        # "features" (tous modes) et "statistics" en mode connecté/autoporté :
        # même garde is_public — connecté appelle /collections/{id}/aggregate
        # en direct au runtime, autoporté le fige dans l'instantané et le
        # sert depuis le mini-serveur ; aucun des deux n'a besoin de figer
        # un résultat au moment de l'export lui-même.
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

    if mode in _STRICT_WIDGET_MODES:
        unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
        for widget_type in sorted(unsupported):
            reasons.append(
                f"widget '{widget_type}' non supporté par ce mode d'export "
                "(extension tierce, non prise en charge)"
            )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/guard.py core/tests/test_appexport_guard.py
git commit -m "feat(core): export guard gains mode=standalone — connected leniency, static widget allowlist (SP-18c)"
```

---

