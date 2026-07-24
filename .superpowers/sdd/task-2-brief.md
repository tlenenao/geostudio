## Task 2: `service.py` — extension du pipeline de copie partagé

**Files:**
- Modify: `core/app/harvest/service.py`
- Modify: `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes : `HarvestedRecord.copy_filename` (Task 1).
- Produces : `_upsert_copy` transmet `rec.copy_filename or "harvest.geojson"`
  à `run_import(..., filename=...)`, consommé par la Task 3 (`CkanConnector`,
  via le moteur de moissonnage réel).

- [ ] **Step 1: Ajouter les tests (RED)**

Ajouter à `core/tests/test_harvest_service.py`, après l'import existant
`from app.harvest.connectors.base import HarvestedRecord` (ligne 10) :

```python
from app.ingestion.importer import ImportResult
```

Ajouter à la fin du fichier :

```python
def test_upsert_copy_passes_copy_filename_to_run_import(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c1", item_id="i1"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="ckan",
        url="https://data.example.com", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    rec = HarvestedRecord(
        external_id="pkg-1", title="Sentiers", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://data.example.com/dataset/pkg-1",
        items_url="https://data.example.com/dataset/pkg-1/resource/x.gpkg",
        copy_filename="harvest.gpkg",
    )
    connector = _fake_connector([rec], copy_bytes=b"gpkg-bytes")
    service._upsert_copy(
        session, source, rec, existing=None, digest="d1", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.gpkg"


def test_upsert_copy_defaults_filename_when_copy_filename_is_none(session, tenant_and_user, monkeypatch):
    # Régression : STAC/ArcGIS ne renseignent jamais copy_filename (défaut
    # None) — le littéral "harvest.geojson" doit rester inchangé pour eux.
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c2", item_id="i2"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    connector = _fake_connector([RECORD_A], copy_bytes=b"geojson-bytes")
    service._upsert_copy(
        session, source, RECORD_A, existing=None, digest="d2", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.geojson"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "copy_filename" -v`
Expected: `test_upsert_copy_passes_copy_filename_to_run_import` FAIL (le code
actuel appelle toujours `run_import` avec `filename="harvest.geojson"` codé
en dur, jamais `"harvest.gpkg"`) ; `test_upsert_copy_defaults_filename_when_copy_filename_is_none`
PASS déjà (comportement actuel = comportement attendu pour ce cas).

- [ ] **Step 3: Modifier `_upsert_copy`**

Dans `core/app/harvest/service.py`, remplacer (ligne 183-187) :

```python
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename="harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
```

par :

```python
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename=rec.copy_filename or "harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_service.py -v`
Expected: PASS (tous les tests service, y compris les 2 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/service.py core/tests/test_harvest_service.py
git commit -m "feat(core): _upsert_copy respecte HarvestedRecord.copy_filename (SP-12g)"
```

---

