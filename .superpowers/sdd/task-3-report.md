# Task 3 report — Registre, schémas, routes et openapi.json (SP-12f)

## Implémenté

1. Ajouté `test_get_connector_returns_csw` (fin de
   `core/tests/test_harvest_csw_connector.py`) et
   `test_get_connector_returns_ogc_records` (fin de
   `core/tests/test_harvest_ogc_records_connector.py`).
2. Réécrit `test_create_unknown_type_is_rejected` dans
   `core/tests/test_harvest_routes.py` : le type inconnu utilisé est
   désormais `"geonode-legacy"` (au lieu de `"csw"`, qui devient un type
   valide). Ajouté `test_create_metadata_source_is_accepted` (paramétré
   `csw`/`ogc-records`, attend 201) et
   `test_copy_mode_rejected_for_metadata_connectors` (même paramétrage,
   attend 400 en mode `copy`).
3. Ajouté la fixture `METADATA_ONLY_REC` et le test
   `test_reference_metadata_only_record_has_null_tiles_and_layer_kind` dans
   `core/tests/test_harvest_service.py`, juste après `RASTER_REC` /
   `test_reference_persists_tiles_url_and_layer_kind`.
4. Enregistré les deux connecteurs dans
   `core/app/harvest/connectors/__init__.py` (`_REGISTRY["csw"]` →
   `CswConnector()`, `_REGISTRY["ogc-records"]` → `OgcRecordsConnector()`,
   imports ajoutés en tête de fichier).
5. Étendu le `Literal` de `HarvestSourceCreate.type` dans
   `core/app/harvest/schemas.py` avec `"csw"` et `"ogc-records"`.
6. Régénéré `core/openapi.json`.
7. `core/app/harvest/routes.py` n'a **pas** été touché (confirmé par
   `git status` avant commit) : le mécanisme `_check_copy_support` existant,
   basé sur `connector.supports_copy`, gère déjà le rejet en 400 pour les
   nouveaux connecteurs sans modification.

## Évidence TDD

### RED (avant enregistrement des connecteurs / extension du schéma)

Commande :
```
uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v
```

Résultat : `6 failed, 50 passed, 3 skipped`.

Échecs :
- `test_harvest_csw_connector.py::test_get_connector_returns_csw` —
  `get_connector("csw")` lève `ValueError: unknown harvest connector type: 'csw'`.
- `test_harvest_ogc_records_connector.py::test_get_connector_returns_ogc_records` —
  même `ValueError` pour `"ogc-records"`.
- `test_harvest_routes.py::test_create_metadata_source_is_accepted[csw]` et
  `[ogc-records]` — `assert 422 == 201` (Pydantic rejette le type, absent du
  `Literal`).
- `test_harvest_routes.py::test_copy_mode_rejected_for_metadata_connectors[csw]`
  et `[ogc-records]` — `assert 422 == 400` (même cause : rejet Pydantic avant
  même d'atteindre `_check_copy_support`).

Remarque : `test_reference_metadata_only_record_has_null_tiles_and_layer_kind`
(service) n'était **pas** dans les 6 échecs — il passait déjà en RED, car ce
test monkeypatch `service.get_connector` directement
(`monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([...]))`),
contournant le registre `_REGISTRY`. Ce test vérifie la persistance NULL de
`tiles_url`/`layer_kind` pour un enregistrement purement métadonnées, pas le
câblage du registre — comportement attendu et cohérent avec le brief.
Vérifié isolément :
```
uv run pytest tests/test_harvest_service.py -k metadata_only -v
→ 1 passed
```

### GREEN (après Steps 5-6)

Commande :
```
uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v
```
Résultat : `56 passed, 3 skipped` (les 3 skips sont les tests `copy_mode`
PostGIS/intégrité déjà marqués `skip` avant cette tâche, sans lien).

## Suite harvest complète

```
uv run pytest tests/ -k harvest -v
→ 137 passed, 13 skipped, 693 deselected
```

## Suite complète du cœur

```
cd core && uv run pytest
→ 743 passed, 100 skipped
```
Aucune régression.

## Diff `openapi.json`

```diff
@@ -813,7 +813,9 @@
               "arcgis",
               "wms",
               "wfs",
-              "wmts"
+              "wmts",
+              "csw",
+              "ogc-records"
             ],
             "title": "Type",
             "type": "string"
```
Diff minimal, exactement l'ajout attendu sur l'énumération
`HarvestSourceCreate.type` — aucune autre dérive.

## Fichiers modifiés

- `core/app/harvest/connectors/__init__.py` — enregistrement `CswConnector`
  et `OgcRecordsConnector` dans `_REGISTRY`.
- `core/app/harvest/schemas.py` — `Literal` de `HarvestSourceCreate.type`
  étendu à `"csw"`, `"ogc-records"`.
- `core/tests/test_harvest_csw_connector.py` — `test_get_connector_returns_csw`.
- `core/tests/test_harvest_ogc_records_connector.py` —
  `test_get_connector_returns_ogc_records`.
- `core/tests/test_harvest_routes.py` — type inconnu remplacé
  (`geonode-legacy`), + 2 tests paramétrés (acceptation 201, rejet copie 400).
- `core/tests/test_harvest_service.py` — `METADATA_ONLY_REC` +
  `test_reference_metadata_only_record_has_null_tiles_and_layer_kind`.
- `core/openapi.json` — régénéré.

Commit : `14bb95a` — `feat(core): enregistre les connecteurs csw/ogc-records (SP-12f)`
(7 fichiers, +66/-3).

## Auto-revue

- `get_connector("csw")` / `get_connector("ogc-records")` fonctionnent
  bout-en-bout via la route HTTP réelle (`POST /harvest/sources`), pas
  seulement au niveau unitaire : `test_create_metadata_source_is_accepted`
  passe par `client.post(...)` → FastAPI → Pydantic → `_check_copy_support`
  → `harvest_repo.create_source`, et retourne bien 201 avec
  `resp.json()["type"] == type_`.
- Le mode `copy` est bien rejeté en 400 pour les deux nouveaux types via le
  mécanisme `_check_copy_support` existant (aucune modification de
  `routes.py`) : `connector.supports_copy` vaut `False` pour
  `CswConnector`/`OgcRecordsConnector` (déjà posé dans les Tasks 1-2), donc
  `_check_copy_support` lève l'erreur 400 sans changement de code de route.
- `core/app/harvest/routes.py` n'apparaît pas dans `git status` avant le
  commit — confirmé non touché.
- Diff `openapi.json` vérifié minimal (voir ci-dessus).

## Écarts par rapport au brief

Aucun écart de fond. Les fixtures (`env`, `_as`) et le contenu réel des
fichiers de test correspondaient exactement à ce que le brief et la
description de tâche annonçaient (pas de fixture `client_admin`, confirmé).
Seule note : la fixture `METADATA_ONLY_REC`/le test de service associé
n'étaient pas RED au sens du registre (ils passaient déjà avant l'Step 5,
car le test monkeypatch `get_connector` directement) — comportement attendu,
documenté ci-dessus, sans impact sur la validité de la couverture ajoutée.
