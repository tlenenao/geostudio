# Plan — L8 collecte terrain offline (AUD-070, AUD-071, AUD-004)

> Spec : `docs/superpowers/specs/2026-10-18-l8-collecte-terrain-offline-design.md` (lire §0 et §12 d'abord).
> **Ne pas exécuter sans l'accord explicite de Tanguy ni avant arbitrage de Q1-Q9.**
> Exécution : subagent-driven-development, TDD, une revue par tâche **et** une revue finale de branche.
> Ledgers nommés `.superpowers/sdd/sp-l8-*` (piège n°9). Pas de worktree si une autre session tourne sur l'arbre
> (vérifier `git worktree list`). Commits conventionnels, un sujet, trailer `Co-Authored-By` ; vérifier soi-même
> `git show --stat` après chaque commit de sous-agent.

Conventions de commande (depuis la racine) :
- Cœur : `cd core && uv run pytest <fichier> -q` avec `CORE_TEST_DATABASE_URL` pointant un postgis-test réel
  (sinon les tests `postgis` skippent en silence : vérifier « 0 skipped »).
- Shell : `cd shell && npx vitest run <fichier>` ; E2E : `npx playwright test e2e/<spec>`.
- Régénération API : voir `CLAUDE.md § Commandes` (OpenAPI puis `npm run gen:api-types`).
- Avant toute migration : `cd core && uv run alembic heads` (un seul head), numéroter **0160-0179**.

Définition de « fait » d'une tâche : test écrit d'abord et vu échouer pour la bonne raison, implémentation minimale,
test vert, ruff/mypy/ESLint/Prettier verts sur les fichiers touchés, commit.

## Lot A — Cœur : idempotence, pièces jointes, kit, soumission publique

### T1 — Table `collect_client_ops` + migration 0160
Fichiers : `core/app/collections/` ou nouveau `core/app/collect/{models.py,repository.py}` (un domaine `collect`,
**ajouter au contrat de couches** `lint-imports` entre `features` et `attachments`), `core/alembic/versions/0160_collect_client_ops.py`,
`core/tests/test_collect_client_ops.py`, `core/tests/test_migrations_nonempty.py` (cas 0160).
1. Tests : insertion unique ; doublon `(tenant, collection, actor, kind, client_op_id)` → `IntegrityError` ;
   migration up/down **sur base non vide** ; `purge_tenant` supprime la table (mettre à jour la liste des 27 tables → 28).
2. Modèle + migration (RLS/`tenant_id`, FK cascade) ; comparateur modèle↔Alembic vert.
3. `alembic upgrade head` puis `ALTER TABLE` manuel sur `postgis-test` si nécessaire.
Vérif : `uv run pytest tests/test_collect_client_ops.py tests/test_purge_tenant*.py tests/test_model_migration_parity*.py -q`
`uv run lint-imports`. Commit : `feat(core): table d'idempotence des écritures de collecte`.

### T2 — `Idempotency-Key` sur `POST /items`
Fichiers : `core/app/features/routes.py` (`create_feature`), `core/app/collect/repository.py`, `core/tests/test_features_idempotency.py`.
1. Tests : (a) même clé → 2e appel `200` même `id`, `feature_count` +1 une seule fois, un seul `audit_log`/`EntityHistory` ;
   (b) sans en-tête → inchangé ; (c) clé d'un autre acteur/collection → écriture normale ; (d) **course** : 2 requêtes
   concurrentes (2 sessions) → une seule ligne créée, les deux reçoivent le même fid (mesurer le résultat final, pas la durée — piège n°7) ;
   (e) échec de validation → rien n'est inséré dans `collect_client_ops` (même transaction) ; (f) géo-limite/quota refusent
   comme avant ; (g) `Idempotent-Replay: true` présent au rejeu.
2. Implémenter : insertion de la ligne d'op dans la transaction de l'écriture ; `ON CONFLICT DO NOTHING` + relecture.
3. `payload.clientOpId` dans `write_audit` ; en-tête informatif `X-GS-Offline-Created-At` → `payload.offline`.
Vérif : tests ci-dessus + `tests/test_features*.py`. Commit : `feat(core): Idempotency-Key sur la création de feature`.

### T3 — Pièces jointes : confirm idempotent, unicité `s3_key`, fid vérifié, magic numbers partagés (migration 0161)
Fichiers : `core/app/attachments/{routes.py,repository.py,models.py}`, `core/app/public_submit/service.py`,
nouveau `core/app/upload_sniff.py` (liste blanche partagée, **les deux domaines l'importent** — jumelles piège n°14),
`core/alembic/versions/0161_attachments_unique_s3_key.py`, `core/tests/test_attachments_idempotency.py`, `core/tests/test_upload_sniff.py`.
1. Tests : confirm rejoué (même `Idempotency-Key`) → 200, une seule ligne ; deux confirm de la même clé S3 sans en-tête → 409 ;
   `fid` inexistant → 404 sous `rls_scope` ; `content_type` pris de `head_object` ; magic numbers ogg/mp3/m4a/mp4/webm/wav acceptés,
   exécutable déguisé refusé (415) sur **les deux** routes ; migration : dédoublonnage sur base non vide avec doublons, down OK.
2. Implémenter, migrer, brancher `attachment_fields[].kind` sur les types acceptés (`image|audio|video|file`).
Vérif : `uv run pytest tests/test_attachments*.py tests/test_public_submit*.py tests/test_upload_sniff.py -q`.
Commit : `feat(core): confirm de pièce jointe idempotent, médias audio/vidéo, unicité s3_key`.

### T4 — `required` appliqué côté serveur (règles générées) — socle commun à T6
Fichiers : `core/app/collections/domains.py`, `core/app/features/validation.py` (ou équivalent de `validate_for_write`),
`core/tests/test_required_rules.py`.
1. Lire `with_attribute_rules`/`validate_for_write` ; trancher : règle CEL `<col> != null` vs contrôle natif ; géométrie requise
   par contrôle dédié (`collection.geometry_required`, stocké dans `attribute_rules` ou colonne — si colonne : migration **0163**).
2. Tests : POST sans la propriété requise → 422 champ + message ; PUT idem ; route publique, approbation de soumission et MCP
   `create_feature` passent par la même validation (un test par chemin) ; géométrie requise absente → 422.
Commit : `feat(core): imposer required et géométrie requise à l'écriture`.

### T5 — Kit de collecte (privé et public) + preuve de travail
Fichiers : nouveau `core/app/collect/{routes.py,schemas.py,pow.py}`, `core/app/public_submit/routes.py` (`clientOpId`,
`submission_files`, PoW), `core/app/public_submit/{models.py,service.py}`, `core/alembic/versions/0162_submissions_client_op_files.py`,
`core/app/main.py` (routeur, groupe de rate-limit `collect_sync`), `core/tests/test_collect_kit.py`, `core/tests/test_public_submit_offline.py`, `core/tests/test_pow.py`.
1. Tests kit privé : droit de lecture requis (403 sinon) ; champs masqués/sensibles **absents** (GAP-22, jumelle : comparer à `GET /items`) ;
   `ETag` + `If-None-Match` → 304 ; contient domaines+libellés, règles, `attachment_fields` typés, `geometryType`.
2. Tests kit public : 404/410 comme le POST ; aucun nom de table ni champ sensible ; ne consomme pas de slot ; limite IP.
3. Tests soumission : `clientOpId` rejoué → 202 sans 2e slot ; 5 fichiers max / 10 Mo / 25 Mo total ; compat des anciennes soumissions
   (`attachment` seule) à l'approbation ; migration 0162 base non vide up/down.
4. PoW : défi signé HMAC (60 s), 18 bits, rejeu d'un défi → refus, défi expiré → refus, désactivable par flag de test uniquement.
5. OpenAPI + types TS régénérés (diff non vide attendu).
Vérif : tests + `uv run python scripts/export_openapi.py` (incantation CLAUDE.md) + `uv run lint-imports` + `tests/test_deployability.py`.
Commit : `feat(core): kit de collecte, soumission publique multi-fichiers idempotente, preuve de travail`.

## Lot B — XLSForm fidèle (AUD-070)

### T6 — Libellés de choix, default, calculate, select_multiple
Fichiers : `core/app/xlsform/parser.py`, `core/app/collections/schemas.py` (`FieldDomain.labels`), `core/app/xlsform/routes.py`,
`core/tests/test_xlsform_parser.py` (+ fixtures XLSX dans `core/tests/fixtures/xlsform/`).
1. Tests : `label`/`label::fr`/premier `label::*` ; `required=yes` → règle `constraint` T4 ; `default` → règle `calculation/default` ;
   `calculate` traduisible → `derived`, sinon `not_ported` ; `select_multiple` → `text[]` ; géométrie requise non plus « approximated » ;
   tout ce qui n'est pas porté reste signalé dans le rapport (aucune perte silencieuse) ; `to_cel` : tests de **parité** `today()`,
   `string-length`, `coalesce`, `if` (valeur XPath de référence vs évaluation CEL).
2. Implémenter ; régénérer OpenAPI/TS (`FieldDomain.labels`).
Commit : `feat(core): XLSForm — libellés, required, default, calculate, select_multiple`.

### T7 — `choice_filter` simple (sous réserve Q2)
Fichiers : `parser.py`, `core/app/collections/domains.py`, `core/tests/test_xlsform_choice_filter.py`.
Cascade `list_col=${autre}` : table de correspondance `choices.<colonne_filtre>` → domaines conditionnels ; contrainte serveur CEL ;
formes complexes → `not_ported`. Si Q2 = « not_ported » : tâche réduite à un test qui verrouille le rapport actuel.
Commit : `feat(core): XLSForm — choice_filter simple`.

### T8 — Réimport sur collection existante avec rapport de différences
Fichiers : `core/app/xlsform/routes.py`, `parser.py`, `core/tests/test_xlsform_reimport.py`.
1. Tests : réimport identique → `differences` vide, aucune 2e collection ; colonne ajoutée → `added` ; libellé changé → `changed` ;
   colonne retypée/supprimée → `blocked` (jamais appliquée) ; droit d'écriture sur la collection requis (`can()`).
2. `POST /xlsform/import?collectionId=…` ; App existante non écrasée (rapport seulement), régénérer OpenAPI/TS.
Commit : `feat(core): réimport XLSForm sur collection existante`.

## Lot C — Saisie shell (AUD-071)

### T9 — Géométries ligne/polygone/trace GPS + précision
Fichiers : `shell/src/builder/widgets/form.tsx` (extraire `GeometryInput.tsx` pour ne pas grossir le fichier), `shell/src/map/` (réutilisation
du croquis SP-27/SP-51 : lire `MapMeasureSketchToolbar` avant), `shell/src/builder/widgets/form.geometry.test.tsx`, `shell/e2e/incident-form.spec.ts` (+ cas).
1. Tests Vitest : LineString/Polygon saisis → charge `geometry` correcte (+ promotion Multi, REV-352) ; géométrie requise bloque l'envoi ;
   trace GPS (`watchPosition` simulé) échantillonne ≥ 5 m ; précision > seuil signalée ; colonnes `gps_*` seulement si déclarées.
2. Implémenter ; **chemin de lecture** : relecture d'un enregistrement ligne/polygone en édition (piège n°5).
Commit : `feat(shell): saisie ligne, polygone et trace GPS dans le formulaire`.

### T10 — Champs médias typés
Fichiers : `form.tsx`, `shell/src/api/domains/attachments.ts`, `shell/src/builder/widgets/form.media.test.tsx`.
Tests : `accept`/`capture` selon `kind` ; régression I1/I2 (photo en échec après création : formulaire conservé, bouton « Réessayer » ; PUT
`res.ok` ; Content-Type identique au presign) — falsifier le test I1 en réintroduisant l'ancien `resetTo()`.
Commit : `feat(shell): champs audio, vidéo et fichier typés`.

### T11 — Compression d'image côté client
Fichiers : `shell/src/offline/compressImage.ts` (+test). Canvas, 2048 px côté long, JPEG 0,85 au-delà de 2 Mo, EXIF orientation respectée,
jamais d'agrandissement, repli sur l'original si `createImageBitmap` indisponible. Mesurer le gain sur un échantillon et consigner dans le ledger.
Commit : `feat(shell): compression des photos avant envoi`.

## Lot D — Offline (AUD-004)

### T12 — Page publique `/collect/:token`
Fichiers : `shell/src/pages/CollectPage.tsx`, `shell/src/shell/routes.tsx` (route hors `ProtectedLayout`), `shell/src/shell/RouteTitle.tsx`
(`docTitle.collect`), `shell/src/api/domains/publicSubmit.ts`, solveur PoW `shell/src/offline/pow.ts` (Web Crypto, dans un Worker), i18n,
`shell/src/pages/CollectPage.test.tsx`, `shell/e2e/public-submission.spec.ts` (étendu), `shell/e2e/a11y-audit.spec.ts` (+ page).
Tests : kit chargé ; 404/410 → message ; honeypot ; PoW résolue ; plusieurs fichiers ; `<main>`/`<h1>` ; axe 0 violation ;
QR de partage depuis `SubmissionsPanel`/fiche du jeton.
Commit : `feat(shell): page publique de collecte /collect/:token`.

### T13 — Stockage local IndexedDB
Fichiers : `shell/src/offline/db.ts`, `shell/src/offline/outbox.ts`, `shell/src/offline/db.test.ts` (`fake-indexeddb` importé **dans le fichier**, jamais dans `setup.ts` — piège n°10 ; sous réserve Q7).
Tests : CRUD des 4 stores ; migration de version ; isolation par `ownerKey` (un second propriétaire ne lit rien) ; plafonds (100 saisies, 200 Mo, 5 photos)
→ erreurs typées ; `QuotaExceededError` capturée sans perte ; `Blob` stockés en `Blob` ; purge des kits au logout, file conservée ;
péremption des kits (14 j) et des `sent` (7 j). Falsification : retirer le filtre `ownerKey` → le test d'isolation doit échouer.
Commit : `feat(shell): stockage IndexedDB de la collecte hors-ligne`.

### T14 — Kit en cache et revalidation
Fichiers : `shell/src/offline/kitCache.ts`, `shell/src/api/domains/collectKit.ts` (via `authFetch`/`ItemClient`, règle ESLint `fetch`), tests.
Tests : en ligne → fetch + `If-None-Match` (304 → pas de réécriture) ; hors ligne → kit du cache ; absent hors ligne → message explicite ;
kit > 14 j → avertissement non bloquant pour les saisies en file.
Commit : `feat(shell): cache du kit de collecte`.

### T15 — Moteur de synchronisation
Fichiers : `shell/src/offline/sync.ts`, `shell/src/offline/decision.ts` (table de décision pure), `shell/src/api/domains/features.ts`
(`Idempotency-Key`), `shell/src/offline/sync.test.ts`, `decision.test.ts`.
Tests : chaque ligne de la table §4.3 ; backoff + `Retry-After` ; **reprise après coupure entre la création et la 2e photo** (aucun doublon,
photos déjà confirmées non renvoyées) ; 401 → pause globale + file intacte ; séquentiel (jamais deux envois simultanés pour un `ownerKey`) ;
verrou multi-onglets (`navigator.locks.request("gs-sync")`) ; déclencheurs `online`/`visibilitychange`/manuel ; saisie publique via
`clientOpId`. Falsification : supprimer l'`Idempotency-Key` du mock → le test de rejeu doit échouer.
Commit : `feat(shell): moteur de synchronisation des saisies hors-ligne`.

### T16 — Mise en file depuis `form.tsx` et état de synchro
Fichiers : `form.tsx` (point d'entrée unique `submitOrQueue` ; en ligne = chemin actuel inchangé, hors ligne ou échec réseau = mise en file),
`shell/src/offline/useOutbox.ts`, `shell/src/shell/MyEntriesPanel.tsx` (ou le composant existant de « Mes saisies » — le localiser avant),
`SyncStatusPill.tsx`, `ConnectivityBanner.tsx` (message mode collecte), i18n, tests.
Tests : hors ligne → saisie en file, formulaire vidé **seulement** après écriture IndexedDB réussie ; badges par état ; actions modifier/abandonner
(`ConfirmDialog`)/exporter JSON ; compteur `aria-live` ; `opId` généré à la création du brouillon (pas à l'envoi).
Commit : `feat(shell): mise en file des saisies et écran d'état de synchronisation`.

### T17 — PWA : manifest, service worker, enregistrement
Fichiers : `shell/public/manifest.webmanifest`, icônes, `shell/index.html`, `shell/src/sw/sw.ts` (ou `public/sw.js` généré), plugin Vite
`shell/vite.swPlugin.ts` (injecte `__BUILD_ID__` + liste précache depuis le manifest Vite), `shell/src/offline/registerSw.ts`, `shell/scripts/check-bundle-size.mjs`
(SW hors entrée), `deploy/` nginx/Traefik (`sw.js` en `Cache-Control: no-cache`, `Service-Worker-Allowed`), CSP (`worker-src`, `manifest-src`),
`core/tests/test_deployability.py` (règle sur la CSP/en-têtes), tests Vitest du SW (stratégies avec un faux `caches`).
Tests : `/v1/*`, `/mcp`, `/embed`, requêtes `Authorization` **jamais** mises en cache ; `/assets/*` cache-first ; navigation réseau d'abord + repli ;
`activate` purge les anciens caches ; hash qui change avec le build ; enregistrement uniquement en PROD ; bannière de mise à jour sans `skipWaiting` automatique.
Vérif : `npm run build` + `node scripts/check-bundle-size.mjs …` + `docker compose config` par valeur (piège n°2).
Commit : `feat(shell): PWA installable et service worker de coquille applicative`.

### T18 — Background Sync (bonus) et durcissements
Fichiers : `sw.ts` (événement `sync` → `postMessage` aux clients, aucune logique d'envoi dans le SW), `registerSw.ts`, tests.
Repli complet sans l'API (déjà couvert par T15). Si la valeur est faible, **supprimer la tâche** (YAGNI) et le consigner.
Commit : `feat(shell): déclenchement Background Sync de la file de collecte`.

## Lot E — Qualité et clôture

### T19 — E2E Playwright offline
Fichier : `shell/e2e/collect-offline.spec.ts`, `shell/e2e/support/mocks.ts` (kit, `Idempotency-Key`, S3 mock), `shell/playwright.config.ts` (projet `mobile-touch` pour le scénario tactile ; SW autorisé = `serviceWorkers: "allow"`).
Scénarios : les 6 de la spec §7 (hors ligne/rechargement/retour réseau ; coupure en plein envoi ; 422 → conflit → correction ; `/collect/:token` hors ligne ;
401 → reprise ; deux utilisateurs). Chaque test **falsifié** une fois (injecter le défaut visé). Suite E2E complète verte (piège n°6) ;
`a11y-audit.spec.ts` mis à jour.
Commit : `test(shell): E2E de la collecte hors-ligne`.

### T20 — Sécurité, documentation produit, revue finale
Fichiers : `SECURITY.md` (appareil partagé, IndexedDB non chiffrée, SW), `docs/runbooks/` (page « collecte hors-ligne » : installation PWA, iOS, zone blanche),
aide contextuelle shell, ADR `docs/adr/00NN-collecte-offline.md` (création seule, idempotence, pas de Workbox).
Revue finale de branche : checklist jumelles (attachments↔public_submit, `/collect-kit` privé↔public, masquage GAP-22 sur tous les chemins de lecture du kit,
`purge_tenant`, rate-limit, CSP nginx↔Traefik), puis `uvx pre-commit run --all-files`, suites core+shell complètes, couverture, `lint-imports`, i18n.
Commit : `docs(l8): ADR, runbook et sécurité de la collecte hors-ligne`.

### T21 — Rejeu sur stack réelle et clôture documentaire (à ne faire qu'avec accord)
1. Rejeu : stack compose réelle + Keycloak réel, émulation réseau CDP (offline/3G) : parcours §10.1-3, expiration de jeton en zone blanche,
   iOS Safari si un appareil est disponible ; rapport `docs/revue/2026-10-xx-rapport-rejeu-collecte-offline.md`. Si non exécuté : le consigner comme limite, pas comme succès.
2. Clôture (même geste, jamais différée) : une ligne `### Livré` dans `CLAUDE.md` ; entrée détaillée dans l'archive d'exécution ; état des `GAP`/`REV`/`AUD-004/070/071` ;
   lignes de `docs/revue/inventaire-fonctionnalites.jsonl` (`collect-kit`, `/collect/:token`, `Idempotency-Key`, `xlsform/import?collectionId`) ;
   `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write` ; `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold` ;
   `CHANGELOG.md`.
Commit : `docs: clôture L8 collecte terrain`.

## Dépendances et ordre
T1→T2→T3 ; T4→T6→T7→T8 ; T5 après T1-T3 ; T9-T11 indépendants (T9 après T4 pour la géométrie requise) ; T12 après T5 ;
T13→T14→T15→T16 ; T17 indépendant du reste du lot D (peut courir en parallèle de T13) ; T19 après T12, T16, T17 ; T20→T21 en dernier.
Parallélisme sûr (fichiers disjoints) : {T1-T5} ∥ {T9-T11} ∥ {T17}. Éviter le parallèle sur `form.tsx` (T9, T10, T16) et sur les migrations
(numéroter séquentiellement, un seul head).

## Pièges spécifiques à surveiller
- Piège n°1 : OpenAPI + types TS après T2, T3, T5, T6, T8. n°2 : câblage compose/CSP/nginx par valeur (T17). n°5 : `toFrontLayer`/chemin de lecture des nouveaux champs.
- n°7 : la concurrence d'idempotence se prouve par le résultat final, pas par un chrono. n°8 : migrations base non vide (T1, T3, T5).
- n°10 : stubs jsdom (IndexedDB, `navigator.locks`, `matchMedia`) **locaux au fichier**. n°14 : jumelles `attachments`↔`public_submit`, kit privé↔public.
- Service worker : un test E2E vert avec `serviceWorkers: "block"` ne prouve rien ; vérifier `navigator.serviceWorker.controller` non nul avant de couper le réseau.
