# j03 — Créateur de carte : résumé

## Périmètre couvert
- Import par API (GeoJSON, CSV lat/lon, XLSX, GPKG EPSG:2154, Shapefile zippé, GeoParquet, KML/KMZ), volumétrie 60 000 points, erreurs (fichier vide, 0 octet, JSON invalide, CRS absent, CSV sans lat/lon, zip illisible), droits (lecteur, autre tenant).
- Tiroir d'import (UI) : validation, erreur, choix des colonnes lat/lon.
- Carte importée : contenu de la config générée, éditeur, liste des champs de symbologie, popup, terrain 3D, historique, rollback, publication/dépublication, lecteur en lecture seule.
- 40 tests : 21 passent (régression), 19 fixme (j03-001 à 016, 021) ; findings 017 à 020 sans test dédié.

## Non couvert
- Rendu canvas MapLibre, mesure/croquis interactifs : style demotiles jamais chargé en Chromium headless (j03-017).
- Tilesets 3D et DEM hébergé : flags désactivés sur la stack.
- Quota de stockage : CORE_QUOTAS_ENABLED=false.
- Envoi navigateur réel vers l'URL présignée : le présigné répond 500 (j03-002) ; envoi simulé par boto3 dans le conteneur MinIO.
- Autres sites `.defer` du cœur, couches deck/tiles3d.

## Méthode
Import de bout en bout impossible (j03-001/002) : un contournement de test (`api.ts`) dépose le fichier via boto3, puis défère la tâche depuis le worker avec `app.open()`, afin d'auditer l'aval. Chaque fixme a été falsifié en retirant le marqueur (échec attendu). Personas OIDC réels (creator, reader, analyst, admin).

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j03` (21 passed, 19 skipped)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j03 --repo-root ..`
