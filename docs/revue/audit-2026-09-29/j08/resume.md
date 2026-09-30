# j08 — Admin de tenant (audit 2026-09-29)

## Périmètre couvert

- Utilisateurs : liste, recherche, pagination (API + UI, 60 comptes générés), changement de rôle par ligne (effet immédiat sur `/me`, audit `user.role_change`), erreurs 400/404.
- Rôles : catalogue des 20 privilèges (le refus d'un privilège inconnu a été vérifié par sonde curl), cycle de vie complet (API + UI), immuabilité des 4 prédéfinis, blocage de suppression (409), effet immédiat d'un privilège ajouté/retiré, validation (noms, privilèges), élévation par `admin.roles.manage`.
- Conformité RGPD : anonymisation (autre compte, `me`, 404/409/403, trace d'audit, lignes écrasées en base), reconnexion après anonymisation, page `/admin/compliance` (titulaire d'un rôle sur mesure), garde-fous de la purge **sans jamais la déclencher** (403, 400 slug erroné, 403 inter-tenant, 422, aucun `tenant.purge_requested` en base).
- Usage (`/tasks`, `/usage/*`) : droits `tasks.view` / `tasks.view_all`, filtre `actorId`, agrégats, paramètres invalides, état vide analyste.
- Quotas : `GET /admin/usage` (comptages, stockage S3 mesuré au octet, limites nulles), compte des utilisateurs anonymisés.
- SettingsNav : liens visibles pour Administrateur (7) et Lecteur (1), pages refusées avec message ; page Infrastructure (usage « sans limite »).
- Extensions : liste, bascule d'activation persistée, validation API.

## Périmètre NON couvert

- **Blocage par quota** (items, collections, stockage) : `CORE_QUOTAS_ENABLED=false` et aucune limite `CORE_QUOTA_MAX_*` sur la stack ; la stack ne doit pas être modifiée. Couvert par lecture de code uniquement (j08-015/016/017).
- **Purge de tenant** : jamais déclenchée (consigne).
- **Anonymisation des 4 personas `audit-*`** : évitée (destructif) ; tous les comptes anonymisés/rôle-modifiés sont des comptes Keycloak jetables `aud-j08-*`. Le garde anti-lockout d'anonymisation et de changement de rôle du dernier titulaire n'est pas exécuté (`mockuser` détient aussi `admin.users.manage`, donc jamais « dernier » sans détruire un persona).
- **Outils d'infrastructure** (Martin/Titiler/Grafana) : `CORE_ADMIN_TOOLS_ENABLED=false`, seul l'état « non activé » est vérifié.
- **Import de fichier** : `POST /v1/uploads` → 500 (j03-001/002), jamais utilisé ; l'usage S3 est mesuré via un dépôt direct boto3 (`putUpload` de j03).
- Collections admin et moissonnage : traités par j07.

## Méthode

Lecture du code des routes/services (roles, compliance, usage, quotas, extensions, auth) et des pages shell (SettingsNav, Users/Roles/Compliance/Usage/Extensions/Infrastructure), sondes `curl` sur la stack OIDC, puis 35 tests (22 API, 13 UI) sur stack réelle avec comptes Keycloak jetables (`kcadm` dans le conteneur, mot de passe lu dans `.env`). Les 11 tests `test.fixme` ont été rejoués une fois avec `fixme` retiré pour confirmer qu'ils échouent bien pour la raison du finding, puis le fichier a été restauré.

## Résultats

- 24 tests passent (régression), 11 sont `test.fixme` (j08-001, 002, 003, 004, 005, 006, 007, 009, 011, 012, 013).
- 18 findings : voir `findings.jsonl`.

## Commandes lancées

```bash
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j08
cd shell && npx eslint e2e/journeys/j08 && npx prettier --check e2e/journeys/j08
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j08 --repo-root ..
```

Effets de bord laissés (reset par l'orchestrateur) : comptes `aud-j08-*` (Keycloak + `users`), 60 lignes `aud-j08-*-bulk-*`, rôles sur mesure `aud-j08-*` dont des doublons/vides créés par la sonde j08-005, extensions `aud-j08-ext*` (désactivées, dont une `javascript:`), lignes `audit_log` factices, un objet S3 de 8 Ko.
