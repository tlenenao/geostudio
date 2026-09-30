# j05 — Analyste : résumé

## Périmètre couvert
- SQL Lab API (`POST /v1/analytics/sql`) : requêtes valides, jointures/sous-requêtes, droits (403/401), sandbox (DML, fichiers, S3, ATTACH, multi-statements refusés), timeout 10 s, plafond 10 000 lignes, limiteur 429, champ masqué.
- Agrégats (`POST /v1/collections/{id}/aggregate`) : mesures, stats, grains temporels, histogramme, validations, filtres.
- Exports API (CSV/XLSX/GeoJSON/GPKG, agrégat exporté), formats, MIME, erreurs, droits.
- SQL Lab UI : navigation, exécution, historique, erreur DuckDB, accès Lecteur refusé, complétion.
- Assistant de requête visuelle (UI) : remplissage, bouton Créer désactivé, message ETL, réinitialisation au changement de base.

## Périmètre NON couvert
- Exécution de la requête visuelle : flag ETL désactivé sur cette stack (`/v1/pipelines/*` en 404).
- Copilote / génération en langage naturel : copilote désactivé, pas de fournisseur LLM.
- Export asynchrone `/v1/export` : flag export désactivé.
- Plafond d'export items (413 au-delà de 10 000 entités) et contenu du GPKG au-delà de l'en-tête.
- Widgets graphique/AppRenderer avec contexte global temps×emprise, contexte d'emprise carte (couverts seulement par lecture de code : j05-024).

## Méthode
Données créées par API, boto3 (dépôt MinIO puis tâche différée depuis le worker, contournement de j03-001/002) et INSERT psql pour les tables typées (POST /items cassé, j02-003). Comportements caractérisés par curl/Playwright, puis 35 tests Playwright (17 verts, 18 `test.fixme` falsifiés en les réactivant : 18 échecs). Findings code-read marqués probable/hypothesis.

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j05`
- `cd shell && npx eslint e2e/journeys/j05 && npx prettier --check e2e/journeys/j05`
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j05 --repo-root ..`
