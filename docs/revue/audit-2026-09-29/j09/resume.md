# j09 — Ops / instance (audit 2026-09-29)

## Périmètre couvert
- Notifications in-app : API (liste, compteur, lecture unitaire/globale, préférence all/failures_only/none, droits inter-utilisateurs, pagination invalide) et cloche du shell (badge, rendu texte brut, « tout marquer lu », plafond de 20).
- Alertes (AlertRule) : création via /configs, validation (expression, canaux, gabarit, cron), droits lecteur/analyste, évaluation par le worker (firing, non-renotification sans transition, garde d'egress du webhook, audit `alert.notify`), historique, éditeur UI (bouton « Exécuter maintenant », libellé d'état), dataset vide.
- Jobs / journal des tâches : `/v1/usage/tasks` (matrice de droits, visibilité des actions d'alerte), pagination.
- Troncature des tuiles MVT (`X-Tile-Truncated`, plafond 5000).
- État d'instance : `/v1/instance`, `/health`, page `/admin/infrastructure` (passerelle éteinte).
- Passerelle `/admin-tools/*` : comportement « éteinte » (404 fermé) et lecture du code des jetons/cookie/verify.
- Rapports planifiés : refus 403 de création quand l'export est désactivé.

## Périmètre NON couvert (et pourquoi)
- Passerelle `/admin/martin|titiler|grafana` en fonctionnement : `CORE_ADMIN_TOOLS_ENABLED=false` sur la stack, non modifiable (j09-016). Jeton de lancement, cookie `gs_admin_session`, forwardAuth Traefik et révocation de privilège lus dans le code seulement.
- Grafana / profil observability : non démarré.
- Livraison réelle d'un webhook/email : la garde d'egress bloque toute cible locale et aucun SMTP n'existe ; seul le chemin d'échec est prouvé.
- Rapports planifiés en exécution (PDF, `/reports/{id}/runs` avec des runs) : `CORE_EXPORT_ENABLED=false`, worker export absent.
- Reprise (reclaim) des évaluations pending après 60 min et balayage cron périodique : non attendus dans le temps imparti (logique lue, évaluations déclenchées à la main via un process qui ouvre l'App procrastinate).
- Notifications d'import/pipeline/export/appexport produites par de vrais jobs : import impossible (j03-001/002), ETL et export désactivés ; lignes insérées en SQL pour tester l'API et la cloche.
- Quotas (`CORE_QUOTAS_ENABLED=false`).

## Méthode
Lecture du code (alerts, notifications, usage, admin_tools, instance, jobs, tiles, NotificationBell, AlertRuleEditor, AdminInfrastructurePage), sondes curl sur l'API, puis 25 tests Playwright (`shell/e2e/journeys/j09/`) : API réelle avec jetons Keycloak (personas), UI réelle via OIDC, données créées par API + `psql` (collections vides + INSERT, notifications), évaluations d'alerte déférées depuis un process cœur qui ouvre l'App procrastinate (la route REST échoue, j09-001). Le lakehouse CDC met environ 1 à 2 min à refléter des lignes insérées en SQL (le seed attend l'agrégat).
Résultat : 12 tests passent (régression), 13 sont `test.fixme` avec l'id du finding (12 findings vérifiés + 1 cas sans test : j09-005 côté /usage prouvé par curl).
Les findings j09-014/015/016 sont issus de la lecture du code (015 vérifié par grep, 014 et 016 « probable »).

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09` (12 passed, 13 skipped)
- `npx eslint e2e/journeys/j09 && npx prettier --check e2e/journeys/j09` (verts)
- sondes : `curl` sur `/v1/instance`, `/health`, `/v1/notifications?page=0`, `/v1/usage/tasks?page=0`, `/v1/admin-tools/*`, `/v1/alerts/{id}/evaluate`, tuiles `/v1/collections/{id}/tiles/0/0/0.mvt`
- `docker exec … python` (déféré d'évaluation), `psql` (audit_log, alert_evaluations, notifications)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j09 --repo-root ..`
