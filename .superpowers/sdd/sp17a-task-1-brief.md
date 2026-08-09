### Task 1: `PrintLayout` — schéma cœur + régénération OpenAPI/TS

**Files:**
- Modify: `core/app/configs/schemas.py:313-334`
- Test: `core/tests/test_configs_schemas.py` (créer si absent, sinon ajouter)

**Interfaces:**
- Produces: `PrintLayout` (Pydantic, `core/app/configs/schemas.py`) — `pageSize: Literal["a4","a3"]="a4"`, `orientation: Literal["portrait","landscape"]="portrait"`, `title: str|None=None`, `showLegend: bool=True`, `showScaleBar: bool=True`, `showNorthArrow: bool=False`, `cartouche: str|None=None`. Champ `BuilderConfig.printLayout: PrintLayout | None = None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_configs_schemas.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig, PrintLayout


def test_print_layout_defaults():
    layout = PrintLayout()
    assert layout.pageSize == "a4"
    assert layout.orientation == "portrait"
    assert layout.showLegend is True
    assert layout.showScaleBar is True
    assert layout.showNorthArrow is False
    assert layout.title is None
    assert layout.cartouche is None


def test_print_layout_rejects_invalid_page_size():
    with pytest.raises(ValidationError):
        PrintLayout(pageSize="letter")


def test_builder_config_print_layout_optional_and_absent_by_default():
    config = BuilderConfig(
        kind="map",
        map={"basemap": {"style": "https://example.test/style.json"}, "view": {"center": [0.0, 0.0], "zoom": 3.0}},
    )
    assert config.printLayout is None


def test_builder_config_accepts_print_layout_on_map_kind():
    config = BuilderConfig(
        kind="map",
        map={"basemap": {"style": "https://example.test/style.json"}, "view": {"center": [0.0, 0.0], "zoom": 3.0}},
        printLayout={"pageSize": "a3", "orientation": "landscape", "title": "Carte des incidents"},
    )
    assert config.printLayout is not None
    assert config.printLayout.pageSize == "a3"
    assert config.printLayout.title == "Carte des incidents"


def test_builder_config_accepts_print_layout_on_app_kind():
    config = BuilderConfig(kind="app", layout={"type": "grid", "items": []}, printLayout={"cartouche": "GeoStudio"})
    assert config.printLayout is not None
    assert config.printLayout.cartouche == "GeoStudio"
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_configs_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'PrintLayout'`

- [ ] **Step 3: Implémenter**

Dans `core/app/configs/schemas.py`, insérer entre la fin de `AlertRulePayload` (ligne 313, juste après le `return self` du `_require_single_scalar_query`) et `class BuilderConfig(BaseModel):` (ligne 316) :

```python
class PrintLayout(BaseModel):
    pageSize: Literal["a4", "a3"] = "a4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    title: str | None = None
    showLegend: bool = True
    showScaleBar: bool = True
    showNorthArrow: bool = False
    cartouche: str | None = None
```

Puis, dans `class BuilderConfig`, ajouter le champ juste après `alert: AlertRulePayload | None = None` (ligne 334) :

```python
    printLayout: PrintLayout | None = None
```

Aucun changement à `_require_kind_payload` : `printLayout` est optionnel pour tous les kinds, sans validation croisée.

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_configs_schemas.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Régénérer l'OpenAPI + les types TS, vérifier l'absence de dérive**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Run: `cd core && git diff --stat openapi.json` puis `cd ../shell && git diff --stat src/api/generated/core-schema.d.ts`
Expected: les deux fichiers montrent un diff non vide contenant `PrintLayout`/`printLayout` (nouveau schéma ajouté) — pas d'erreur de génération.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_configs_schemas.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): SP-17a — schéma PrintLayout sur BuilderConfig"
```

---

