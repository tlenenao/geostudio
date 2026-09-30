# j05b — Analyste, passe « flags allumés »

## Périmètre couvert
- Requête visuelle exécutée pour de bon (ETL allumé) via l'UI : filtre (numérique, date, « contient »), jointure interne/gauche, résumé avec les 9 fonctions de métrique, relance idempotente (mode replace), réouverture « Modifier la requête » (round-trip filtre/résumé/centile), schéma de sortie, lecture du dataset de sortie par l'agrégat et SQL Lab après réplication CDC. Les sorties sont vérifiées en SQL direct.
- Droits : Analyste et Lecteur sur l'API pipelines, Analyste sur l'assistant.
- Exports avec flags allumés : plafond 10 000 entités (10 000 passent, 10 001 -> 413, un filtre ramène sous le plafond), contenu réel du GPKG (SQLite, gpkg_contents, 60 lignes, en-tête de géométrie), GeoJSON, tâche `POST /v1/export` (422/404/droits, 500 AppNotOpen, exécution déférée à la main, échec du rendu), lecture d'un job par un tiers.
- Contexte analytique global : plage temporelle ISO et date seule restituées depuis `?ctx=` sur une app réelle (dataset avec timeField), `?ctx=` illisible.
- Diagnostics hors spec : Playwright dans le conteneur export-worker (cœur injoignable), RestartCount et journaux d'export-worker.

## Périmètre NON couvert
- Rendu PNG/PDF abouti : impossible sans modifier la stack (VITE_CORE_URL=localhost:8200 injoignable depuis export-worker, j05b-006).
- Copilote / génération de requête en langage naturel : LLM éteint par consigne.
- Contexte d'emprise (extent) et cross-filter inter-datasets : non rejoués (seul le temps l'est).
- Quotas de tenant : hors périmètre analyste et non simulables sans toucher la stack.
- Healthcheck export-worker, secret du worker, reader.file : connus, non re-signalés.

## Méthode
25 tests Playwright sous `shell/e2e/journeys/j05b/` (18 passent, 7 `test.fixme` ré-activés un par un : tous échouent pour la raison du finding). Les tests de sortie de requête visuelle contournent j02-003 par un `ALTER TABLE … SET DEFAULT 'default'` sur la table de sortie (documenté dans `helpers.ts::submitWizard`) et j06b-001 en déférant le run depuis le worker. Première passe re-confirmée : j05-024 verified (j05b-007), j05-023 nuancé (l'enrobage % existe ; casse et jokers non, j05b-003), aucune régression sur les valeurs des métriques (somme, moyenne, médiane, centile, écart-type, distinct, NULL correctement groupé).

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j05b`
- `cd shell && npx eslint e2e/journeys/j05b && npx prettier --check e2e/journeys/j05b`
- `docker inspect geostudio-export-worker-1 --format '{{.RestartCount}}'`, `docker logs geostudio-export-worker-1`, script Playwright dans le conteneur (diag de rendu)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j05b --repo-root ..`
