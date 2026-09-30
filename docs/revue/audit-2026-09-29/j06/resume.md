# j06 — Data engineer (pipelines) : résumé

## Contexte déterminant
La stack d'audit tourne avec `CORE_ETL_ENABLED=false` (`/v1/instance` → `etlEnabled:false`).
Conséquence : `/v1/pipelines/*` n'est pas monté (404), `POST /v1/configs` kind=pipeline
renvoie 403, aucun pipeline ne peut être créé ni exécuté. Le périmètre a donc été
couvert par (a) le coffre de secrets (routes inconditionnelles), (b) le comportement
« ETL coupé » du cœur et du shell, (c) des sondes de fonctions pures dans le conteneur
cœur (validation de graphe, garde d'egress), (d) lecture de code pour le reste.

## Couvert
- Coffre de secrets : création/liste/suppression, absence de fuite, chiffrement au repos, audit, doublons, kinds, droits par persona, 401.
- Comportement ETL coupé : API (404 routes, 403 config, ordre des gardes), shell (domaine verrouillé, /pipelines/new, /pipelines/:pk/edit inconnu, wizard requête visuelle, dialogue « Nouveau », palette ⌘K, lecteur).
- Validation de graphe à l'enregistrement (cycle, degré entrant, reader/writer requis, cas non couverts).
- Garde d'egress SSRF (13 cibles bloquées dont IPv4-mappé, décimal, hexa ; 2 trous trouvés).
- Lecture de code : service/routes/jobs pipeline, webhook entrant, balayage cron, runtime DuckDB, connecteurs.

## NON couvert (et pourquoi)
- Builder interactif : palette (57 op), connexion de nœuds, undo/redo, zones annotées, aperçu tabulaire, détail de run, éditeur cron, jeton webhook : ETL désactivé sur la stack (routes non montées, éditeur remplacé par un message) ; non modifié par consigne. Voir j06-001.
- Exécution, planification cron réelle, déclenchement webhook, erreurs de run (secret absent, schéma qui change) : idem, worker `etl` non actif.
- Connecteurs REST/Postgres/Snowflake/BigQuery/MSSQL/Oracle/blob : aucun compte/service externe ; leur garde et leurs plafonds ont seulement été lus (j06-004, j06-014).
- reader.file / writer.file (`CORE_PIPELINE_FILE_IO_ENABLED`) : flag éteint.
- Import de fichier (j03-001/002) : non nécessaire à ce périmètre.
- Copilote, export : flags éteints, hors périmètre j06.
- Dépendance de deep-link : `page.goto` perd la destination après reconnexion OIDC (j02-004, connu) ; les specs naviguent par `history.pushState` (helper `spaGoto`).

## Méthode
Specs Playwright sur stack réelle (personas OIDC, API via jetons Keycloak, `psql`/`docker exec` pour les vérifications de base et de conteneur). Chaque `test.fixme` a été rejoué non-skippé pour confirmer qu'il échoue pour la raison annoncée avant d'être conservé. 57 tests dans `shell/e2e/journeys/j06` (43 passent, 14 `fixme` : le cas egress est paramétré, d'où un léger dépassement du budget de 40).

## Findings (15)
S2 : j06-001 (test-gap ETL), 002 (topologie de graphe), 004 (DSN sans garde d'egress + Créateur), 014 (plafonds/timeouts) ; S3 : 003, 005, 006, 010, 012, 013, 015 ; S4 : 007, 008, 009, 011.

## Commandes
```
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06
npx eslint e2e/journeys/j06 && npx prettier --check e2e/journeys/j06
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j06 --repo-root ..
```
