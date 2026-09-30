# j13 — Partage et permissions : résumé

## Périmètre couvert

- **Matrice rôle × kind** à la création de config (app, dashboard, site, map, dataset,
  bookmark) pour Créateur / Analyste / Lecteur, et refus de création de groupe et de
  collection vide (Lecteur, Analyste). Conforme à `kind_registry`.
- **Rôles de partage viewer / editor** par groupe : lecture, métadonnées, publication,
  partage, config, suppression, liens. Retrait du partage (404, pas 403, pas de fuite).
- **Publication vs partage « public »** : sémantique vérifiée contre l'API anonyme.
- **Groupes** : création, ajout de membre (créateur seul), cycle de vie (routes absentes),
  groupes inconnus / dupliqués / rôle invalide.
- **Partage d'une carte et de ses données** (collection non partagée).
- **Suppression et références inverses** sur les trois routes de suppression.
- **Administration / modération** des items d'autrui.
- **Liens à échéance** : création (cassée, j13-001), bornes TTL, jeton invalide, droits.
- **UI** : panneau de partage (Créateur, Analyste propriétaire d'un bookmark),
  masquage selon le rôle (viewer, éditeur sans privilège), contrôles de groupe
  proposés à tort, IDOR par URL directe (`/items`, `/apps/:pk/edit`, `/maps`,
  `/datasets/:pk/edit` → messages « introuvable », aucune fuite de titre).

13 findings : 0 S1, 5 S2 (j13-001, 002, 003, 004, 008), 7 S3, 1 S4 —
détail dans `findings.jsonl`. 34 tests Playwright (23 passent, 11 `test.fixme`
rattachés à un finding ; chaque fixme a été falsifié : relancé sans `fixme`, il échoue).

## Déjà connu, non re-signalé (référencé)

- Révocation d'un lien d'un autre item (IDOR `link_id`) : **c01-006 / c08-001**.
- Lien/config racine encore servis après perte de droits du créateur : **c01-005**.
- `GET /items/{id}/sharing` et `GET /groups` lisibles par tout lecteur : **c01-013 / j02-005**
  (REV-009 a tranché pour `GET /groups`).
- `scope` inconnu sans filtre de visibilité : **j02-001**.
- Publier une carte ne publie pas sa collection : **j03-012** (j13-008 en est le pendant
  pour le partage par groupe).
- `/public/configs/by-item` sert tout kind publié : **j10-001**.
- Route `/apps/:pk` hors `ProtectedLayout` (« Accès refusé » au rechargement) : **j02-010**.
- `sensitiveFields` modifiable par un éditeur délégué : **c01-001**.

## Non couvert (et pourquoi)

- **Liens à échéance, chemin nominal** (résolution anonyme, expiration, révocation,
  `/embed/:token`, portée invitée sur collections) : impossible, la création répond 500
  faute de `CORE_SHARE_LINK_TOKEN_SECRET` (j13-001). j13-011/j13-012 restent donc en
  `probable` (lecture de code). Ne pas modifier la stack était une consigne.
- **Isolation multi-tenant** : la stack d'audit n'a qu'un tenant (`default`).
- **Kinds pipeline / alert / report** dans la matrice : ETL et export coupés
  (pipeline/report refusés pour d'autres raisons que le rôle) ; l'alerte n'est utilisée
  que comme référence inverse (j13-003). `tileset3d`/`terrain3d` : capacités éteintes.
- **Partage de collection par l'UI d'administration** (`/admin/collections`) : couvert par
  j08 ; ici seulement par API.
- **Outils MCP de partage** (`set_sharing`) : même service que la route REST
  (`items/service.py`), non rejoués séparément (périmètre j11).
- **Quotas, admin tools, LLM** : désactivés sur la stack.
- **Suppression des personas** : jamais tentée ; groupes et items jetables préfixés
  `aud-j13-*`.

## Méthode

1. Lecture du chemin d'exécution réel : `sharing/authorization.py` (`decide`/`can`),
   `sharing/routes.py`/`repository.py`, `items/routes.py`/`service.py`,
   `configs/routes.py` (gardes `_require_access`, `_require_privilege_for_kind`,
   `_require_no_reverse_references`), `collections/routes.py` (partage de collection),
   `shell/src/shell/ShareForm.tsx`, `ItemActions.tsx`, `ItemDetailPage.tsx`.
2. Sondes API ad hoc (jetons Keycloak `password` des 4 personas) pour confirmer chaque
   hypothèse, puis cristallisation en specs Playwright.
3. Pour chaque défaut : un test `constat …` qui passe (documente le comportement actuel)
   + un `test.fixme("j13-nnn : …")` exprimant l'attendu ; falsification en relançant les
   fixme sans le marqueur (11/11 échouent).

## Commandes lancées

```bash
cd shell
npx eslint e2e/journeys/j13 && npx prettier --check e2e/journeys/j13
npx playwright test -c playwright.journeys.config.ts e2e/journeys/j13
# → 23 passed, 11 skipped (fixme)
docker logs geostudio-core-1 | grep -A20 share_links   # InvalidKeyError: HMAC key must not be empty
docker exec geostudio-core-1 env | grep SHARE          # CORE_SHARE_LINK_TOKEN_SECRET=
cd ../core && PYTHONPATH=. uv run python scripts/audit_findings.py validate \
  ../docs/revue/audit-2026-09-29/j13 --repo-root ..
```

Specs : `shell/e2e/journeys/j13/sharing-api.spec.ts`, `sharing-ui.spec.ts`,
helpers `shell/e2e/journeys/j13/helpers.ts`.
