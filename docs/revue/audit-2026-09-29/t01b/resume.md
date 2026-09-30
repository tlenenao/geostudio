# t01b — Accessibilité, passe « flags allumés » : résumé

## Périmètre couvert
Stack OIDC avec ETL, export, appexport, admin tools, quotas (limites larges) et tileset3d allumés, LLM éteint, profil observability absent.
- Pipelines : éditeur DAG `/pipelines/:id/edit` (palette de 57 opérations, canevas React Flow, nœuds, arêtes, contrôles) : axe clair (nœud sélectionné), clavier (connexion, focus, arêtes, ordre de tabulation), cibles, noms, contraste en sombre.
- Rapports / alertes : `/reports`, `/reports/new`, `/reports/:id/edit`, éditeur de règles d'alerte (`/datasets/:id/edit`) : axe clair, erreurs de planification cron, « Automatisation » n'est plus un `<span aria-disabled>` (réfute j06-010, test qui passe).
- Administration : `/admin/compliance` (compte jetable avec `compliance.manage`, purge jamais cliquée), `/admin/infrastructure` (outils admin allumés, usage de quota), `/tasks` (usage plateforme, tri au clavier, `aria-sort`).
- Export d'app : panneau `AppExportPanel` dans `/apps/:id/edit` (déclencheur, choix de mode, focus, alerte d'échec).
- Tileset 3D : tiroir « Nouveau tileset 3D » (piège du focus, Échap, rendu du focus, axe clair et sombre, envoi simulé par interception réseau).
- Confirmé en exploration (non re-signalé, cause t01-005) : en sombre, `/reports/new`, `/reports/:id/edit`, l'éditeur d'alerte de `/datasets/:id/edit` et le panneau Historique des éditeurs ont du texte noir sur #0a1316 (1,11:1).
- Exploré sans finding nouveau : `/admin/users|roles|collections|harvest|extensions`, `/settings`, `/analytics/sql`, `/datasets/visual-query/new` en clair et sombre (seules `region`/`landmark-one-main`/`page-has-heading-one`, déjà t01-001/003, et color-contrast de t01-005).

## Périmètre NON couvert
- Blocage de quota en interface : les limites du shell (100000/10000) sont inatteignables sans modifier la stack ; aucun écran de dépassement n'a été rendu (j08b a couvert l'API sur un second cœur).
- Envoi réel d'un tileset (multipart cassé, j10b-012) et exécution réelle d'un run de pipeline / export d'app (AppNotOpen sur `.defer()`) : états « en cours » et « terminé » vus seulement via interception ou erreur.
- Grafana / profil observability (port 3001 refusé par WSL2) ; copilote LLM (éteint) ; lecteur d'écran réel ; zoom 200-400 %.
- Éditeur de carte avec terrain 3D / tileset hébergé rendu (worker MapLibre octet-stream, j12-001).
- Connexion de nœuds à la souris (drag entre poignées) : non revérifiée, seul le parcours « ↝ puis clic » existant a été comparé au clavier.
- Tests exploratoires retirés pour tenir le budget de 25 tests (aucun finding dessus) : raccourci « / », ajout d'étape par Entrée, suppression de nœud au clavier, lecteur sur `/pipelines/new`, canal e-mail, alerte vide, lecteur sur rapport privé, liens `/settings`, pages `/admin/*` restantes, formulaire tileset désactivé, envoi tileset en cours.

## Méthode
1. Balayage axe (clair + sombre, admin/creator) de ~20 routes via un spec exploratoire jetable, agrégation par règle.
2. Sondes clavier ad hoc sur le canevas (Tab, Entrée, Suppr, `focus()`), lecture du code pour situer les causes (PipelineCanvas, PipelinePalette, AppExportPanel, Tileset3DUploadButton, ComplianceAdminPage, AdminInfrastructurePage).
3. Chaque bug confirmé figé dans un `test.fixme` (`t01b-NNN`) ; rejoué avec `T01B_VERIFY=1` : 15 échecs attendus, chacun sur l'assertion visée. Les 9 autres tests passent (régression).
4. Un compte Keycloak jetable + un rôle jetable (`compliance.manage`) sont créés pour l'écran de conformité (comme j08) ; la stack n'est pas modifiée.

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t01b` : 9 passed, 15 skipped (fixme)
- `cd shell && T01B_VERIFY=1 npx playwright test -c playwright.journeys.config.ts e2e/journeys/t01b` : 9 passed, 15 failed (attendu)
- `cd shell && npx eslint e2e/journeys/t01b && npx prettier --check e2e/journeys/t01b`
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t01b --repo-root ..`

## Points positifs vérifiés
Tiroir tileset : focus piégé, Échap, focus rendu, axe propre en clair et en sombre. Conformité : axe propre clair/sombre, erreur d'anonymisation en `role=alert`, purge verrouillée. Usage `/tasks` : tri d'en-tête au clavier avec `aria-sort`. Pipelines : axe propre en clair, Échap annule la connexion amorcée, suppression de nœud par bouton au clavier, raccourci « / ». Panneau d'export : axe propre et alerte « Échec de l'export. » annoncée.
