# j07 — Data steward (moissonnage et métadonnées)

## Périmètre couvert
- Sources de moissonnage : création (nominal, validation 422, mode copie 400), droits (403 créateur/analyste/lecteur, 401 anonyme), PATCH, 404, suppression, échecs (garde d'egress, URL invalide), moissonnage réel d'un catalogue STAC public (earth-search), écran `/admin/harvest` (liste, ajout, édition, suppression, accès refusé).
- API STAC native : landing, conformance, collections (pagination), items (limit/offset/bbox/404), search GET/POST (jeton, ids, bbox, datetime), visibilité anonyme/privée.
- Export DCAT-AP : dataset, catalogue, pagination, mapping licence/contact/périodicité/provenance/version/temporel.
- Métadonnées ouvertes par collection : catalogue de métadonnées, round-trip des 10 champs, validation (licence/fréquence/langue/date), effacement, droits, édition UI (Métadonnées ouvertes, Champs sensibles).
- Masquage de champ sensible : OGC items, item unique, STAC items/search, filtre et agrégat (pas d'oracle), validation de la déclaration, cycle déclarer/retirer.
- Collection cassée (table supprimée) : DCAT, STAC (collections/collection/items/search), OGC items, schéma.

## Périmètre NON couvert
- Moissonnage réel des types ArcGIS FS, WMS, WFS, WMTS, CSW, OGC Records, CKAN et du mode `copy` : aucun serveur de test n'est joignable (la garde d'egress bloque les IP internes, `CORE_HARVEST_EGRESS_ALLOWLIST` est vide et la stack ne doit pas être modifiée). Seul STAC (réseau public) a été moissonné.
- Tuiles MVT et export/SQL Lab sous masquage : seuls OGC/STAC/agrégat/filtre ont été vérifiés (SQL Lab renvoie « no data yet » : CDC non compacté).
- Licence/langue au niveau item (`ItemPatch`) : aucun export ne les consomme (déjà connu, audit pré-release).
- Pipelines (`CORE_ETL_ENABLED=false`) et exports (`CORE_EXPORT_ENABLED=false`) : hors stack.
- Écriture REST de features sur collection vide (j02-003) : données insérées en SQL direct pour le cycle de masquage.
- Pagination des listes `/harvest/*` : déjà connue (audit pré-release).

## Méthode
Lecture du code (harvest, stac, dcat, collections, features, ratelimit), exploration par curl/Playwright API sur la stack OIDC, puis specs Playwright. Le moissonnage est exécuté dans le conteneur worker par `run_harvest_task.func` (la file `harvest` n'est consommée par personne, j07-001, et la route `run` répond 500, j07-002). Chaque test `test.fixme` a été réactivé temporairement pour vérifier qu'il échoue. Le limiteur « harvest » (10 écritures/min par jeton) impose un jeton neuf par test.
Nombre de tests : 59 (dépasse le budget indicatif de 30 : quatre familles API/UI distinctes), dont 19 `test.fixme` liés à un finding.

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j07`
- `npx eslint e2e/journeys/j07 && npx prettier --check e2e/journeys/j07`
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j07 --repo-root ..`
- Vérifications SQL/docker : `procrastinate_jobs` (file `harvest`), `harvest_records`, `items`, `list_due_sources` depuis le worker.

## Effets de bord laissés sur la stack
Sources de moissonnage `aud-j07-*`, 9 items `external` issus d'earth-search (orphelins après suppression), collections `aud-j07-*`. Le reset de l'orchestrateur les efface.
