# j08b — Admin de tenant, passe « flags allumés » (2026-09-30)

## Périmètre couvert

- **Blocage par quota** (jamais testable en première passe) : sur un second processus cœur (`audit-core-quota`, :8201, même image/base/S3/réseau, limites basses) lancé puis supprimé par les specs — la stack n'est pas modifiée. Quotas d'items (409 RFC 7807, même règle admin/créateur, lecture intacte, 8 créations concurrentes pour 1 place : 1 seule acceptée), de collections (`/collections/empty` bloqué, `POST /collections` non bloqué : j08b-001), de stockage (refus 409 à l'import, double comptage j08b-003, objet orphelin j08b-002). Affichage shell contre ce cœur (réécriture `:8200 -> :8201` par `page.route`) : page Infrastructure, refus à la création d'une App.
- **Confirmation/réfutation de la première passe** : j08-015 confirmé (j08b-002, aggravé par j08b-003) ; j08-016 confirmé (j08b-011, aucune règle de cycle de vie, aucune suppression) ; j08-017 levé (quotas testés) mais le périmètre réel du quota est plus étroit que supposé (j08b-001, -010, -012).
- **Anti-lockout du dernier administrateur** : impossible d'isoler un dernier titulaire dans le tenant `default` sans toucher aux personas ; simulé dans un tenant jetable créé par `lockout_sim.py` avec les services réels (`anonymize_user`, `count_users_with_privileges`) : contournement par compte anonymisé (j08b-004). Rétrogradation de soi avec autre titulaire présent : couvert en exploration (200), retiré du lot pour le budget de 25 tests.
- **Outils d'administration** (`CORE_ADMIN_TOOLS_ENABLED=true`) : lancement (200 admin, 403 lecteur/créateur/analyste, 401 anonyme, 422 outil inconnu), cookie (HttpOnly/Secure/SameSite=Strict/Path=/admin/30 min), jeton d'un autre outil ou falsifié (401), forwardAuth Traefik (403 sans cookie, 200 avec pour Martin/Grafana), révocation immédiate après retrait du privilège, page Infrastructure (3 boutons, popup, alerte d'échec). Défauts : Titiler 500 (j08b-005), redirection de dev vers un 404 (j08b-006), lien MinIO (j08b-009).

## Périmètre NON couvert

- **Purge de tenant** : jamais déclenchée (consigne). **Personas `audit-*`** : ni anonymisés ni rétrogradés ; comptes jetables `aud-j08b-*`.
- Quota de stockage via attachments, tileset3d, terrain3d : lus dans le code (même schéma de double comptage, j08b-003) mais non exécutés (présignés en 500 et jobs `AppNotOpen` connus).
- Bypass par `writer.dataset` (pipelines) et job tileset3d : lecture de code seule ; seul `run_import` est exécuté (au niveau fonction, les routes n'atteignent pas le job : `AppNotOpen`).
- Observabilité/Grafana `:3011` : simple vérification de la passerelle (200), pas de contenu.
- Concurrence du quota d'items : une sonde (8 créations parallèles) sans dépassement ; pas de preuve d'absence de course.
- Accès direct non authentifié à Martin (:3010) et Titiler (:8000) sur le compose de dev : conscient (`docker-compose.prod.yml` remet `ports: !reset []`), non signalé.

## Méthode

Lecture du code (quotas, compliance, roles, auth, admin_tools, shell Infrastructure), sondes `curl` sur la stack OIDC, puis 25 tests Playwright (API et UI) ; chaque `test.fixme` a été rejoué sans `fixme` pour confirmer qu'il échoue pour la raison du finding, puis restauré. Le cœur de quota est démarré/arrêté par `helpers.ts` (`startQuotaCore`/`stopQuotaCore`) ; les objets S3 déposés par les tests sont supprimés en `afterAll`.

## Résultats

- 14 tests passent (régression), 11 `test.fixme` (j08b-001 à -011 ; j08b-012 est un constat de lecture de code sans test).
- 12 findings : S2 x4 (001, 003, 004, 010), S3 x7 (002, 005, 006, 008, 009, 011, 012), S4 x1 (007).

## Commandes lancées

```bash
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j08b
cd shell && npx eslint e2e/journeys/j08b && npx prettier --check e2e/journeys/j08b
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j08b --repo-root ..
```

Effets de bord laissés (reset par l'orchestrateur) : comptes Keycloak `aud-j08b-*`, rôles `aud-j08b-*-tools`, tenants jetables `audj08bs*`/`audj08bn*` (utilisateurs/rôles), ~2 collections `aud_j08b_*` enregistrées/créées, collection + item `aud-j08b-imp-*` (import_sim), tables `audj08b_reg_*`, configs `aud-j08b-*` remplissant le quota, lignes `audit_log`. Aucun conteneur auxiliaire ne reste (`audit-core-quota` supprimé).
