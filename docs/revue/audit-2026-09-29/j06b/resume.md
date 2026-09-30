# j06b — Data engineer (pipelines), passe « flags allumés »

## Périmètre couvert
- API pipelines avec `CORE_ETL_ENABLED=true` (`/v1/pipelines/*` monté, catalogue à 57 op) : enregistrement, validation (op inconnue, params, cron), prochaine exécution, aperçu (avec/sans graphe en corps, erreurs, pagination), historique des runs, droits (collection privée, pipeline d'autrui, lecteur).
- Exécution réelle par le worker : reader.collection -> filter -> derive -> writer.export CSV, schéma qui change (colonne supprimée + notification), erreurs lisibles (secret absent, SSRF 169.254.169.254, reader.file flag éteint).
- Webhook entrant (cycle de vie du jeton, 401/404, révocation, limiteur), planification cron (balayage `*/5` : politique activée, coupée, annuelle).
- Builder : palette + recherche, glisser-déposer, connexion, annuler/rétablir, zone annotée, enregistrement/réouverture, aperçu tabulaire, jeton webhook.
- Confirmation/réfutation de j06-004 (DSN sans garde d'egress : confirmé par exécution, j06b-010) et j06-015 (double run : confirmé, j06b-006).

## Périmètre NON couvert
- `reader.file`/`writer.file` : `CORE_PIPELINE_FILE_IO_ENABLED` n'est pas câblé dans docker-compose (seul l'échec flag éteint est testé).
- Connecteurs Snowflake, BigQuery, MSSQL, Oracle, blob : aucun service externe disponible.
- Plafonds et délais des connecteurs, outil MCP run_pipeline, copilote LLM (éteint), profil observability.
- Export/appexport/3D/quotas : hors périmètre pipelines.
- Exécution d'un run réussi avec secret de connecteur : impossible tant que j06b-005 n'est pas corrigé.

## Méthode
Specs API (`apiFor` de j03) et UI sous `shell/e2e/journeys/j06b/` (25 tests : 16 passent, fixme pour les findings). Contournement d'AppNotOpen : le run est déféré depuis le conteneur worker (`run_pipeline_task.defer`). Jeu de données sans géométrie créé via `/collections/empty` et insertion SQL. Chaque `test.fixme` a été rejoué en `test()` et échoue pour la raison du finding. Lecture du code pour les localisations.

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06b` (le test de balayage dure jusqu'à ~6 min)
- `npx eslint e2e/journeys/j06b && npx prettier --check e2e/journeys/j06b`
- requêtes `psql` dans le conteneur postgis (`pipeline_runs`), `boto3` dans le conteneur core (bucket des exports)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j06b --repo-root ..`
