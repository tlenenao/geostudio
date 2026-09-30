# j11 — Copilote IA et MCP (audit 2026-09-29)

## Périmètre couvert
- MCP `/mcp` sur la stack réelle OIDC : 401 sans jeton / jeton bidon / jeton d'audience REST seule (avec `resource_metadata`), métadonnées `oauth-protected-resource`, découverte Keycloak (S256, DCR), flux authorization_code+PKCE d'un client enregistré dynamiquement (jeton `aud=geostudio-mcp` accepté par `/mcp`, refusé par le REST), `whoami` = `/v1/me` pour les 4 personas, inventaire des 27 outils (ETL éteint : aucun outil pipeline).
- Permissions de l'utilisateur et parité REST↔MCP : `list_items` vs `GET /items`, droits d'écriture (`apps.manage`, `catalog.manage`) lecteur/analyste/créateur, item privé invisible (`get_item`, `get_app_config`, `get_sharing`, `save_app_config`, `set_sharing` → « item not found », y compris admin), masquage du champ sensible dans `query_features`, `explain_dataset`/`run_analytics_query`, `create_dataset`, `create_bookmark`, `create_form_app`, alertes, groupes, `delete_secret`.
- Audit : lignes `agent:*` des écritures MCP vs `user:*` du REST (psql).
- Copilote : capacité éteinte (`copilotEnabled=false`, route 404, panneau absent du builder/SQL Lab), routeur `/copilot/turn` exécuté dans le conteneur cœur via une sonde (bornes d'entrée, liste blanche d'outils, pannes du fournisseur), UI en OIDC réel avec `GET /v1/instance` et `POST /v1/copilot/turn` simulés (payload, jeton d'audience MCP réel, historique localStorage, SQL Lab, lecteur).

## Périmètre NON couvert (et pourquoi)
- Tour de copilote complet avec un vrai LLM : `CORE_LLM_PROVIDER` est vide (stack non modifiable). Le routeur n'est donc pas monté ; seules la sonde et un cœur simulé côté navigateur ont pu être exercés. Le loopback MCP réel du copilote (`McpLoopbackSession`) n'a pas tourné de bout en bout.
- Outils MCP de pipelines (`create_pipeline`, `run_pipeline`, `explain_pipeline`) : `CORE_ETL_ENABLED=false`. Rapports (`explain_report_schedule`) : `CORE_EXPORT_ENABLED=false`. Mode démo lecture seule (`CORE_READ_ONLY_MODE`) : non activable, garde lue dans le code (cf. c01-008).
- `POST /v1/uploads` et l'évaluation d'alerte aboutissent à un 500 (procrastinate `AppNotOpen`, j03-001/j09-001) : les données sont créées par API + SQL (collection vide remplie via psql).
- Requête visuelle : panneau copilote non exercé côté UI (même remontage que j11-007 attendu) ; seules SQL Lab et le builder l'ont été.
- Quotas, outils d'administration (`CORE_QUOTAS_ENABLED`, `CORE_ADMIN_TOOLS_ENABLED`) éteints.

## Méthode
Lecture du code (`core/app/copilot/*`, `core/app/mcp/**`, `shell/src/builder/copilot/*`, `shell/src/auth/RequireAuth.tsx`, `shell/src/lib/copilotHistory.ts`, limiteur, realm Keycloak), sondes Python/curl contre le cœur et Keycloak, puis 24 tests Playwright (`shell/e2e/journeys/j11/`) : API avec jetons Keycloak (client MCP JSON-RPC maison), sonde `docker exec -i geostudio-core-1 python -` (`docs/revue/audit-2026-09-29/j11/probes/copilot_probe.py`), UI OIDC réelle. Résultat : 15 passent (régression), 9 sont `test.fixme` avec l'id du finding, chacun vérifié en échec réel avant d'être marqué. Trouvaille majeure : j11-007 (S1), invisible des E2E historiques car `useMcpToken` renvoie un jeton factice en mode mock (j11-015). j11-008/009/011/012/014/015 viennent de la lecture du code (confiance probable/hypothesis ou preuve command-output), sans test dédié ; j11-009 et j11-013 sont prouvés côté serveur par la sonde.

## Effets de bord laissés sur la stack
Deux clients Keycloak `aud-j11-dcr` / `aud-j11-dcr2` (DCR anonyme, j11-016), quelques collections/apps/alertes `aud-j11-*` et `aud-j11-probe`, une évaluation d'alerte `pending` orpheline (j11-003). Le reset de l'orchestrateur les nettoie.

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j11` (15 passed, 9 skipped)
- `npx eslint e2e/journeys/j11 && npx prettier --check e2e/journeys/j11` (verts)
- sondes : `curl` (`/mcp`, `/.well-known/oauth-protected-resource/mcp`, DCR Keycloak), scripts Python de JSON-RPC MCP, `docker exec -i geostudio-core-1 python -` (sonde copilote), `docker exec geostudio-postgis-1 psql` (audit_log, alert_evaluations, procrastinate_jobs)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j11 --repo-root ..`
