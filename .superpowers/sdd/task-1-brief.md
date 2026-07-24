## Task 1: `HarvestedRecord` gagne `copy_filename`

**Files:**
- Modify: `core/app/harvest/connectors/base.py`
- Create: `core/tests/test_harvest_base.py`

**Interfaces:**
- Produces : `HarvestedRecord.copy_filename: str | None = None` (nouveau
  champ, dernier de la dataclass), consommé par la Task 2 (`service.py`) et
  la Task 3 (`CkanConnector`). Pour les 6 connecteurs existants (STAC,
  ArcGIS, WMS, WFS, WMTS, CSW, OGC API - Records — 7 en tout), ce champ n'est
  jamais renseigné explicitement → défaut `None`, comportement inchangé.

- [ ] **Step 1: Écrire le fichier de tests (RED)**

Créer `core/tests/test_harvest_base.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.base import HarvestedRecord


def test_copy_filename_defaults_to_none():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url=None,
    )
    assert rec.copy_filename is None


def test_copy_filename_can_be_set():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url="https://x/data.gpkg",
        copy_filename="harvest.gpkg",
    )
    assert rec.copy_filename == "harvest.gpkg"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_base.py -v`
Expected: FAIL avec `TypeError: HarvestedRecord.__init__() got an unexpected
keyword argument 'copy_filename'`

- [ ] **Step 3: Ajouter le champ**

Modifier `core/app/harvest/connectors/base.py` (remplacer les lignes 9-18) :

```python
@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None
    raster_tiles_url: str | None = None
    copy_filename: str | None = None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_base.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lancer la suite harvest complète (non-régression)**

Run: `cd core && uv run pytest tests/ -k harvest -v`
Expected: PASS (tous les tests des 7 connecteurs existants, inchangés — le
nouveau champ a un défaut).

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/base.py core/tests/test_harvest_base.py
git commit -m "feat(core): HarvestedRecord.copy_filename (SP-12g)"
```

---

