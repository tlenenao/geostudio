## Task 3: Registre, schémas, routes et openapi.json

**Files:**
- Modify: `core/app/harvest/connectors/__init__.py`
- Modify: `core/app/harvest/schemas.py`
- Modify: `core/tests/test_harvest_csw_connector.py` (ajout `test_get_connector_returns_csw`)
- Modify: `core/tests/test_harvest_ogc_records_connector.py` (ajout `test_get_connector_returns_ogc_records`)
- Modify: `core/tests/test_harvest_routes.py`
- Modify: `core/tests/test_harvest_service.py`
- Modify: `core/openapi.json` (régénéré)

**Interfaces:**
- Consumes : `CswConnector` (Task 1), `OgcRecordsConnector` (Task 2).
- Produces : `get_connector("csw")` / `get_connector("ogc-records")`
  fonctionnels ; `HarvestSourceCreate.type` accepte `"csw"`/`"ogc-records"` ;
  `openapi.json` à jour, consommé par la Task 4 (régénération `core-schema.d.ts`).

- [ ] **Step 1: Étendre les tests des connecteurs avec `get_connector` (RED)**

Ajouter à la fin de `core/tests/test_harvest_csw_connector.py` :

```python
def test_get_connector_returns_csw():
    from app.harvest.connectors import get_connector

    c = get_connector("csw")
    assert c.type == "csw"
    assert c.supports_copy is False
```

Ajouter à la fin de `core/tests/test_harvest_ogc_records_connector.py` :

```python
def test_get_connector_returns_ogc_records():
    from app.harvest.connectors import get_connector

    c = get_connector("ogc-records")
    assert c.type == "ogc-records"
    assert c.supports_copy is False
```

- [ ] **Step 2: Réécrire les tests de routes autour du nouveau Literal (RED)**

Dans `core/tests/test_harvest_routes.py`, remplacer le test qui utilisait
`"csw"` comme exemple de type inconnu (il devient un type valide) par un type
toujours inexistant, et ajouter la couverture des deux nouveaux types :

```python
def test_create_unknown_type_is_rejected(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": "geonode-legacy", "url": "https://x", "mode": "reference",
    })
    assert resp.status_code == 422


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_create_metadata_source_is_accepted(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": type_, "url": "https://catalog.example.com/x", "mode": "reference",
    })
    assert resp.status_code == 201
    assert resp.json()["type"] == type_


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_copy_mode_rejected_for_metadata_connectors(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": type_, "url": "https://catalog.example.com/x", "mode": "copy",
    })
    assert resp.status_code == 400
```

- [ ] **Step 3: Ajouter le test service de confirmation NULL (RED)**

Ajouter à `core/tests/test_harvest_service.py`, après `RASTER_REC` (ligne 33) :

```python
METADATA_ONLY_REC = HarvestedRecord(
    external_id="csw#iso-1", title="Batiments", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0],
    external_url="https://geonetwork.example.com/csw?request=GetRecordById&id=iso-1",
    items_url=None,
)
```

Puis ajouter, après `test_reference_persists_tiles_url_and_layer_kind` :

```python
def test_reference_metadata_only_record_has_null_tiles_and_layer_kind(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([METADATA_ONLY_REC]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="csw",
        url="https://geonetwork.example.com/csw", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="csw#iso-1")
    assert rec.tiles_url is None
    assert rec.layer_kind is None
```

- [ ] **Step 4: Lancer les trois fichiers de tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v`
Expected: FAIL — `get_connector("csw")`/`get_connector("ogc-records")` lèvent
`ValueError` ; les créations de source `csw`/`ogc-records` renvoient 422 au
lieu de 201/400.

- [ ] **Step 5: Enregistrer les deux connecteurs**

Modifier `core/app/harvest/connectors/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.csw import CswConnector
from app.harvest.connectors.ogc_records import OgcRecordsConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wfs import WfsConnector
from app.harvest.connectors.wms import WmsConnector
from app.harvest.connectors.wmts import WmtsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
    "wfs": WfsConnector(),
    "wmts": WmtsConnector(),
    "csw": CswConnector(),
    "ogc-records": OgcRecordsConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 6: Étendre le schéma Pydantic**

Modifier `core/app/harvest/schemas.py` ligne 8 :

```python
class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts", "csw", "ogc-records"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)
```

- [ ] **Step 7: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v`
Expected: PASS

- [ ] **Step 8: Lancer la suite harvest complète**

Run: `cd core && uv run pytest tests/ -k harvest -v`
Expected: PASS (tous les tests harvest, y compris ceux inchangés des Tasks 1-2)

- [ ] **Step 9: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: le fichier `core/openapi.json` est réécrit — `git diff core/openapi.json`
montre `"csw"` et `"ogc-records"` ajoutés à l'énumération du type de
`HarvestSourceCreate`.

- [ ] **Step 10: Commit**

```bash
git add core/app/harvest/connectors/__init__.py core/app/harvest/schemas.py \
  core/tests/test_harvest_csw_connector.py core/tests/test_harvest_ogc_records_connector.py \
  core/tests/test_harvest_routes.py core/tests/test_harvest_service.py core/openapi.json
git commit -m "feat(core): enregistre les connecteurs csw/ogc-records (SP-12f)"
```

---

