# Clôture de TOUTES les REV et release v0.2.0 — plan maître

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> Ce plan est un **plan maître** : le lot 0 et les lots 1-2 sont détaillés au pas près ; chaque lot suivant est détaillé par son propre plan daté (`docs/superpowers/plans/2026-10-xx-cloture-lot-N.md`) écrit **après** le triage du lot 0, car l'état réel des 55 REV (piège n°12) peut en avoir déjà fermé.

**Goal:** passer les 39 REV `ouvert` et 16 `partiellement fermé` du backlog à `fermé` (code, décision ou résiduel documenté) puis tagger `v0.2.0`.

**Architecture:** les REV de la campagne multi-angles ont déjà un **test reproducteur `xfail(strict=True)`** (`core/tests/audit/test_audit_lot0..5.py`, `shell/src/audit/audit-lot5.test.tsx`). Fermer une REV = corriger le code, retirer le marqueur `xfail`, vérifier que le test passe. Lots indépendants, 2 en parallèle (worktrees éphémères `sp-cloture-lotN`), revue par tâche + revue finale de branche par lot.

**Tech Stack:** Python/FastAPI/pytest (`core/`), React/Vitest/Playwright (`shell/`), Alembic, docker compose, `gh`.

## Décisions de Tanguy (2026-10-15)

- REV-119 : **spécifier et implémenter** (lot 8).
- REV-284(d)/286(c) : **automatisme de test** à la place des tests manuels (lot 7) ; résiduel « vrai lecteur d'écran / vrai appareil » consigné.
- REV-269 : **appliqué via `gh`**, confirmation demandée avant chaque appel sortant.
- Exécution : **2 lots en parallèle** (1+2, puis 3+4, puis 5, 6, 7, 8).
- Release : **v0.2.0 après TOUS les lots**, aucun tag intermédiaire.
- Vagues ARC/FME : incluses, op à risque **expérimentales** (flags éteints par défaut, lot 9).
- ADR 0013 / 0015 : **tranchés maintenant** (lot 7) — recommandations : 0013 limite assumée documentée (CSP globale), 0015 pas de tombstone sans avis DPO (purge complète seule).

## Global Constraints

- Commits conventional, petits, un sujet ; pied `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Branche `dev` uniquement ; promotion = PR `dev→main`.
- Docs/messages utilisateur en français, code en anglais.
- TDD ; toute route/modèle modifié ⇒ régénérer OpenAPI + types TS (`CLAUDE.md` § Commandes), diff vide attendu seulement si surface derrière flag éteint.
- Toute migration testée **sur base non vide, dans les deux sens** (piège n°8) ; `postgis-test` : `ALTER TABLE` manuel après migration ; 2-3 sessions concurrentes ⇒ rejouer en isolation avant de s'imputer une régression (piège SP-49).
- Un correctif posé sur une surface se **reporte sur ses jumelles** : lister-les avant de clore (piège n°14).
- Les marqueurs `xfail` ne sont retirés que quand le test passe réellement ; vérifier par falsification (le test échoue sans le correctif).
- Fin de chaque lot : `ruff check/format`, `mypy --strict` (modules listés), `lint-imports`, `pytest` complet avec `CORE_TEST_DATABASE_URL` réel, `npm run test/lint/build`, E2E complète si le shell est touché, bilan de fonctionnalités régénéré, backlog (`État` + `count-backlog-etat.sh`) et entrée dans l'archive d'exécution mis à jour **dans le même geste** ; ligne unique dans `CLAUDE.md § Livré`.
- Ne jamais lancer de commandes destructrices (`down -v`, force-push, protection de branche) sans confirmation explicite.

## Carte des lots

| Lot | REV | Parallélisable avec |
|---|---|---|
| 0 Triage | les 55 | — (premier) |
| 1 Secrets/egress/autorisation | 331 332 334 336 337 338 339 340 341 342 360 361 366 329 | 2 |
| 2 Déploiement/exploitation | 343 344 345 346 347 348 354 355 358 281 267 | 1 |
| 3 Import et données | 349 350 351 282 283 280 | 4 |
| 4 Shell UX/a11y | 357 362 363 364 365 367 304 278 284 286(a,d,e) | 3 |
| 5 Pipelines/fédération/alertes | 325 326 327 328 330 275 276 277 | — |
| 6 Rejeu stack réelle | 318 319 321 164 + reliquats | après 1-5 |
| 7 Décisions et automatismes | 284d 286c 269 ADR-0013 ADR-0015 | après 4 |
| 8 REV-119 | 119 | indépendant |
| 9 Marquage expérimental + release | — | dernier |

---

## Lot 0 — Triage (0,5 j)

### Task 0.1: Script de triage mécanique

**Files:**
- Create: `core/scripts/revue/triage_xfail.py`
- Test: `core/tests/test_triage_xfail.py`

**Interfaces:**
- Produces: `python core/scripts/revue/triage_xfail.py` imprime, pour chaque test `xfail(strict=True)` de `core/tests/audit/`, `REV-nnn | nodeid | XPASS|XFAIL` (XPASS = bug déjà corrigé).

- [ ] **Step 1: Test** — `test_triage_xfail.py` : fournir un faux rapport junit XML contenant 1 `xfail` et 1 `XPASS(strict)` ; asserter que `parse_junit(xml)` renvoie `[("test_a","XFAIL"),("test_b","XPASS")]`.
- [ ] **Step 2:** `cd core && uv run pytest tests/test_triage_xfail.py -v` → FAIL (module absent).
- [ ] **Step 3:** implémenter `parse_junit` (stdlib `xml.etree.ElementTree` : un `<failure message="[XPASS(strict)]…">` ⇒ XPASS ; `<skipped type="pytest.xfail">` ⇒ XFAIL) et `main()` qui lance `pytest tests/audit -p no:cacheprovider --junitxml=<tmp>` puis affiche la table, en extrayant `REV-nnn` du `reason=` du marqueur.
- [ ] **Step 4:** relancer le test → PASS.
- [ ] **Step 5:** `git add core/scripts/revue/triage_xfail.py core/tests/test_triage_xfail.py && git commit -m "chore(core): script de triage des reproducteurs xfail de l'audit"`

### Task 0.2: Tableau de triage des 55 REV

**Files:**
- Create: `docs/revue/2026-10-15-triage-cloture-rev.md`

- [ ] **Step 1:** `cd core && CORE_TEST_DATABASE_URL=… PYTHONPATH=. uv run python scripts/revue/triage_xfail.py > /tmp/…/triage.txt` ; `cd shell && npx vitest run src/audit` pour la partie shell.
- [ ] **Step 2:** pour chaque REV **sans** reproducteur (119, 267, 269, 275-278, 280-284, 286, 304, 318, 319, 321, 325-331, 358, 364, 365, 366, 367), lire le code cité en « Preuve » et noter : `déjà corrigé` / `à corriger` / `décision` / `externe`, avec `chemin:ligne` vérifié.
- [ ] **Step 3:** écrire le tableau `REV | lot | statut réel | preuve | action` ; chaque XPASS est marqué « à fermer : retirer xfail ».
- [ ] **Step 4:** `git add docs/revue/2026-10-15-triage-cloture-rev.md && git commit -m "docs(revue): triage des 55 REV avant clôture"`
- [ ] **Step 5:** présenter le tableau à Tanguy ; ajuster les lots 1-9 en conséquence avant de continuer.

---

## Lot 1 — Secrets, egress, autorisation (~8 j)

Branche worktree : `sp-cloture-lot1`. Ledger : `.superpowers/sdd/sp-cloture-lot1-*`.

### Task 1.1: REV-332 — secret S3 du lac illisible depuis SQL Lab (Bloquant)

**Files:**
- Modify: `core/app/analytics/duckdb_conn.py:38-39`, `core/app/analytics/sql_sandbox.py:118-120`
- Test: `core/tests/audit/test_audit_lot2.py::test_s3_secr…` (retirer `xfail`)

- [ ] **Step 1:** lancer le reproducteur en retirant `xfail` : il échoue (`current_setting('s3_secret_access_key')` renvoie la clé).
- [ ] **Step 2:** dans `duckdb_conn.py`, remplacer les `SET s3_access_key_id/s3_secret_access_key` par un `CREATE SECRET` (non lisible via `current_setting`) ; dans `_lock_down`, interdire en plus `duckdb_settings()`/`current_setting` sur les clés `s3_*` et `duckdb_secrets()`.
- [ ] **Step 3:** ajouter un test négatif : `SELECT * FROM duckdb_secrets()` et `SELECT current_setting('s3_secret_access_key')` sont refusés ; un `read_parquet('s3://…')` autorisé continue de fonctionner (test existant du lac).
- [ ] **Step 4:** `uv run pytest tests/audit/test_audit_lot2.py tests/analytics -v` → PASS ; falsification : `git stash` du correctif ⇒ le test échoue.
- [ ] **Step 5:** commit `fix(core): REV-332, le secret S3 du lac n'est plus lisible depuis SQL Lab`.
- [ ] **Step 6:** lister les jumelles : tout autre point qui ouvre une connexion DuckDB avec secrets (`aggregate`, `profile`, pipelines `runtime`, CDC) ; vérifier qu'ils passent par `duckdb_conn.py`.

### Task 1.2: REV-336 + REV-334 — garde commune analytics

**Files:**
- Modify: `core/app/ratelimit/limiter.py:99-123`, `core/app/features/routes.py:362-398` (ou `run_collection_profile`), `core/app/mcp/tools/analytics.py:181-224`
- Test: `core/tests/audit/test_audit_lot0.py::test_analytic_routes_have_a_rate_limit_group` + le test de REV-334 (retirer `xfail`)

- [ ] **Step 1:** retirer les `xfail`, constater l'échec.
- [ ] **Step 2:** `route_group` : ajouter `/aggregate` et `/profile` au groupe `sql`. Mettre `refuse_geo_limited` **une seule fois** dans `run_collection_profile` (ferme REST et MCP).
- [ ] **Step 3:** `uv run pytest tests/audit/test_audit_lot0.py tests/ratelimit tests/features -v` → PASS.
- [ ] **Step 4:** commit `fix(core): REV-334/336, profil et agrégats sous limites géographiques et rate limit`.

### Task 1.3: REV-337 — `writer.collection` `replace` et champs masqués

**Files:** Modify `core/app/pipelines/runtime.py:960-1013` ; Test `test_audit_lot0.py` (test REV-337).

- [ ] **Step 1:** retirer `xfail`, constater l'échec.
- [ ] **Step 2:** avant `delete_all_features` (`:1012`), refuser `replace` si `_masked_fields(...)` est non vide pour l'utilisateur, avec le même message/erreur que la garde géographique (`:1007`).
- [ ] **Step 3:** test PASS ; vérifier aussi les modes `upsert/update/delete` (ils écrivent des colonnes masquées en NULL ?) — si oui, ouvrir la même garde.
- [ ] **Step 4:** commit `fix(core): REV-337, writer.collection replace refuse les champs masqués`.

### Task 1.4: REV-338/339/340/341 — gardes d'egress

**Files:**
- Modify: `core/app/alerts/notify.py:142-144` (SMTP), `core/app/pipelines/connector_runtime.py:563-572` (REST), `:908`, `:920` (blob), `core/app/harvest/egress.py:94-100`, `core/app/secrets/schemas.py:354`
- Test: `core/tests/audit/test_audit_lot1.py` (4 tests)

- [ ] **Step 1:** retirer les 4 `xfail`, constater les échecs.
- [ ] **Step 2 (SMTP):** appeler `assert_egress_allowed(host, port)` (`app/alerts/egress.py`) avant la connexion, épinglage DNS `net_pin`.
- [ ] **Step 3 (REST):** `follow_redirects=False` sur le `RESTClient`, ou re-validation de chaque saut (portée du secret + egress) sans réémettre l'en-tête d'authentification vers un autre hôte.
- [ ] **Step 4 (gzip):** dans la boucle de `harvest/egress.py`, compter les octets **décodés** (`iter_bytes`) et interrompre au plafond.
- [ ] **Step 5 (blob):** valider `accountName` par `^[a-z0-9]{3,24}$` dans `schemas.py` ; imposer `token_uri == "https://oauth2.googleapis.com/token"` (ou allowlist) pour GCS ; appliquer la garde blob d'egress existante à ces deux cas.
- [ ] **Step 6:** `uv run pytest tests/audit/test_audit_lot1.py tests/alerts tests/harvest tests/pipelines tests/secrets -v` → PASS (le test confused-deputy REV-342 reste xfail jusqu'à 1.5).
- [ ] **Step 7:** lister les jumelles (autres clients HTTP : webhooks sortants ADR 0027, `transform.httpCall`, `reader.wfs`, géocodage) et vérifier qu'ils appliquent redirections validées + egress + plafond décodé.
- [ ] **Step 8:** commit par REV (4 commits `fix(core): REV-33x, …`).

### Task 1.5: REV-331 + REV-342 — confused deputy (changement de conception)

**Files:**
- Modify: `core/app/pipelines/config_validation.py` (`_validate_node`), `core/app/alerts/…` (validation d'écriture de config d'alerte)
- Test: `core/tests/audit/test_audit_lot1.py` (REV-342, test placeholder à rendre réel) + nouveau `core/tests/pipelines/test_secret_usage_on_write.py`

- [ ] **Step 1:** écrire le test réel : un éditeur sans droit d'usage sur le secret `S` enregistre une config de pipeline (nœud `reader.connector.rest` ou `transform.httpCall` portant `secretName=S`) ⇒ attendu 403/422 ; idem alerte avec secret SMTP/webhook ; un éditeur autorisé ⇒ 200.
- [ ] **Step 2:** constater l'échec.
- [ ] **Step 3:** à l'écriture (PUT/POST/rollback, MCP `update_config` inclus), appeler `can_use_secret(utilisateur qui enregistre, secretName)` pour chaque nœud/canal portant un secret ; erreur RFC 7807 avec le nom du secret.
- [ ] **Step 4:** tests PASS ; vérifier les chemins jumeaux : import de config, restauration d'historique (`rollback_config`), MCP, copilote.
- [ ] **Step 5:** commit `fix(core): REV-331/342, usage du secret vérifié à l'écriture des configs`.

### Task 1.6: REV-366 — clés d'API : liste/révocation admin

**Files:** Modify `core/app/apikeys/service.py:118-153`, `routes.py:17-25` ; i18n/shell si UI ; OpenAPI + inventaire.

- [ ] **Step 1:** test : un admin (`admin.users.manage`) `GET /v1/admin/api-keys?user=<id>` liste, `DELETE` révoque ; un non-admin ⇒ 403 ; la rétrogradation de rôle révoque les clés devenues dépassantes.
- [ ] **Step 2:** constater l'échec ; **Step 3:** implémenter routes + service ; **Step 4:** PASS ; **Step 5:** OpenAPI + types TS + `inventaire-fonctionnalites.jsonl` + bilan ; **Step 6:** commit `feat(core): REV-366, gestion admin des clés d'API`.

### Task 1.7: REV-360/361 — shell : confirmation RGPD, échec de révocation

**Files:** Modify `shell/src/pages/ComplianceAdminPage.tsx:53-60`, `shell/src/shell/ShareForm.tsx:100-108` ; Test `shell/src/audit/audit-lot5.test.tsx`.

- [ ] **Step 1:** retirer `it.fails`/marqueur des deux tests, constater l'échec.
- [ ] **Step 2:** `ConfirmDialog` (id utilisateur affiché) avant l'anonymisation ; `role="alert"` sur `revokeLink.isError` comme `createLink.isError` (`:175`). Chaînes dans le catalogue i18n par domaine.
- [ ] **Step 3:** `cd shell && npx vitest run src/audit src/pages src/shell` → PASS ; `npm run lint`.
- [ ] **Step 4:** commit `fix(shell): REV-360/361, confirmation d'anonymisation et erreur de révocation de lien`.

### Task 1.8: REV-329 — sidecar desktop : `transform.httpCall`

- [ ] **Step 1:** test : la liste d'op du sidecar (`core/app/pipelines/sidecar/app.py:~38-42`) n'inclut pas `transform.httpCall`.
- [ ] **Step 2:** retirer l'op de la liste (défaut recommandé par la REV tant que le modèle de menace desktop n'existe pas) ; **Step 3:** PASS ; **Step 4:** commit `fix(core): REV-329, httpCall retiré du sidecar desktop`.

### Task 1.9: Clôture du lot 1

- [ ] Régénérer OpenAPI/TS ; `feature_health_cli.py --write` ; mettre à jour l'`État` de chacune des 14 REV (commit qui ferme) + `count-backlog-etat.sh` ; entrée d'archive ; ligne `### Livré`.
- [ ] Suite complète core + shell ; revue finale de branche (agent séparé) ; corriger ; PR `dev` (pas de merge main).

---

## Lot 2 — Déploiement et exploitation (~4 j, en parallèle du lot 1)

Branche `sp-cloture-lot2`. **Migrations** : numéroter après `0066` (vérifier `ls core/alembic/versions | tail`) et rebaser le numéro au merge si le lot 1/autre en crée une.

### Task 2.1: REV-354 + REV-355 — compose prod et `install.sh`

**Files:** Modify `docker-compose.prod.yml:253` (service `worker`), `scripts/install.sh:112-160,509-513` ; Test `core/tests/audit/test_audit_lot4.py` (3 tests) + `core/tests/test_deployability.py`.

- [ ] **Step 1:** retirer les 3 `xfail`, constater l'échec.
- [ ] **Step 2:** `CORE_BASE_URL` sur `worker` en prod ; `set_env_var CORE_EXPORT_ENABLED true` / `CORE_APPEXPORT_ENABLED true` quand le profil est choisi.
- [ ] **Step 3:** vérifier **par valeur** : `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -A3 CORE_BASE_URL` (piège n°2) ; ajouter la règle dans `test_deployability.py`.
- [ ] **Step 4:** PASS ; commit `fix(deploy): REV-354/355, CORE_BASE_URL du worker et flags export du profil`.

### Task 2.2: REV-343 / REV-347 / REV-348 — intégrité base

**Files:** `core/app/configs/repository.py:312` ; `core/app/harvest/models.py:76` + migration ; `core/alembic/versions/0012_pgvector_embeddings.py` + nouvelle migration ; `test_audit_lot2.py`, `test_audit_lot3.py`.

- [ ] **Step 1:** retirer les `xfail`, constater les échecs.
- [ ] **Step 2 (343):** `session.get(Config, config_id, with_for_update=True)`.
- [ ] **Step 3 (347):** migration `ON DELETE SET NULL` sur `harvest_records.collection_id` + modèle ; **tester sur base non vide, upgrade et downgrade**.
- [ ] **Step 4 (348):** migration `DROP INDEX … ; CREATE INDEX … USING hnsw (embedding vector_cosine_ops)` (pas d'entraînement) ; test sur base non vide ; maintenir la liste des index fonctionnels filtrés par le comparateur modèle/Alembic.
- [ ] **Step 5:** PASS (avec `ALTER`/migration appliquée sur `postgis-test`) ; commits séparés.

### Task 2.3: REV-345 / REV-346 — reprises périodiques et défer après commit

- [ ] **Step 1:** retirer `xfail` (`test_terrain3d_has_periodic_reclaim`, `test_tileset3d…`, `test_embedding_defer_happens_after_commit`).
- [ ] **Step 2 (345):** copier le balayage de reprise des jobs appexport/ingestion (SP-49) pour `terrain3d/jobs.py:59` et `tileset3d/jobs.py:54` ; planifier la tâche périodique procrastinate.
- [ ] **Step 3 (346):** `items/repository.py:231` : déférer l'embedding après commit (hook post-commit), + balayage de reprise des items sans embedding.
- [ ] **Step 4:** PASS ; **jumelles (piège n°14)** : lister toutes les tâches procrastinate sans balayage (`grep "\.defer(" core/app`) et traiter ou consigner chacune.
- [ ] **Step 5:** commits.

### Task 2.4: REV-344 — purge de tenant robuste

**Files:** `core/app/compliance/routes.py:105-121`, `jobs.py:30-42`, `purge.py:179` ; `test_audit_lot2.py`.

- [ ] **Step 1:** retirer `xfail` (2 tests), constater l'échec.
- [ ] **Step 2:** état unique de purge par tenant (409 si en cours), ligne de reçu `failed` + message, suppression S3 **après** commit (migration si colonne `status`/`error` à ajouter, testée base non vide).
- [ ] **Step 3:** PASS ; commit `fix(core): REV-344, purge de tenant idempotente avec reçu d'échec`.

### Task 2.5: REV-358 — mode démo et exports

- [ ] **Step 1:** écrire le test manquant : en `CORE_DEMO_MODE`, `POST` d'une route d'export créant un job ⇒ 403/405.
- [ ] **Step 2:** `core/app/main.py:270-278` : n'exempter que les exports synchrones en lecture ; **Step 3:** PASS ; **Step 4:** commit.

### Task 2.6: REV-281 / REV-267 — CI/sauvegarde et perf

- [ ] REV-281 reliquats : (a) rapport de couverture par module, (c) règle d'alerte/sonde externe sur `.last_success`, (d) première exécution du job `stack-smoke` sur une PR, (e) hook `actionlint`, (f) rotation hors-site indépendante de l'envoi — un commit par sous-point, avec test dans `core/tests/test_deployability.py` ou script CI.
- [ ] REV-267 : mesurer le LCP mobile (Lighthouse via chrome-devtools MCP) sur `/public` ; alléger `index.js` selon la mesure ; abaisser `shell/.bundle-size-threshold` au nouveau plancher ; filet canvas. Objectif chiffré **fixé avant** la mesure : LCP < 2,5 s ; sinon fermer avec mesure et résiduel documenté.

### Task 2.7: Clôture du lot 2 — identique à 1.9.

---

## Lots 3 à 9 (détaillés après le triage, un plan par lot)

Chaque lot suit le même gabarit : retirer `xfail` → échec → correctif → PASS → falsification → jumelles → commit ; clôture identique à 1.9.

- **Lot 3 — Import et données** : REV-349 (paramètres positionnels `p0,p1…` dans `ingestion/importer.py:304,316`), REV-350 (`_rename_reserved_property_keys` aussi sur GeoJSON/CSV/GPKG, `parsers.py:464`), REV-351 (`shapely.force_2d` avant WKT, `importer.py:322`), REV-282 (b)(c)(d)(e), REV-283 (a)(b)(c)(d)(e)(f, mesure `EXPLAIN` 10^6), REV-280 (a)(c)(d)(e)(g `SET TIME ZONE 'UTC'`).
- **Lot 4 — Shell UX/a11y** : REV-357 (`float` dans `configs/schemas.py:248-249,273-275`), REV-362 (sélecteur de bookmark obligatoire), REV-363 (Entrée = ajouter un point au centre, `MapMeasureSketchToolbar.tsx:332-338`), REV-364/365/367 (vider chaque liste de Minor point par point, ne fermer qu'une fois vide), REV-304 (`timeRange` sur couches additionnelles), REV-278 (a)-(e), REV-284 (b)(c)(e), REV-286 (a) mode 2 volets `TriptychLayout`, (d) `ResizeObserver`, (e) `touchcancel`.
- **Lot 5 — Pipelines/fédération/alertes** : REV-325 (éditeur JSON avancé `multipartFields`/`paginatorConfig`), 326 (nom d'op dans le message), 327 (refuser `Content-Type` utilisateur en multipart), 328 (monkeypatch/lecture de config), 330 (reprise de pagination + verrou OAuth2), 275 (c) `mark_running` conditionnel, (d) `mem_limit`, (e) jumelles, 276 (b)(c)(d, migration base non vide), 277 (c)(d `notify_status` par canal).
- **Lot 6 — Rejeu stack réelle** : après lots 1-5, `scripts/replay/run.sh` complet y compris `--workers=2` (REV-321) ; trier les `bug()` restants (REV-318/319) : basculer en `test()` ou ouvrir une REV ; contrôler la restauration + reconnexion OIDC (REV-164) — `down -v` seulement avec confirmation explicite.
- **Lot 7 — Décisions et automatismes** :
  - REV-284(d) : test Playwright d'arbre d'accessibilité (`page.accessibility.snapshot`/`getByRole`) sur les 9 pages clés + `axe-core` étendu ; résiduel « vrai lecteur d'écran » consigné.
  - REV-286(c) : projet Playwright `hasTouch`/`isMobile` (émulation d'appareil) avec gestes tactiles sur carte/popup/outil de croquis ; résiduel « appareil réel » consigné.
  - REV-269 : lister avec `gh api` l'état (protection de `main` absente au 2026-10-15), proposer le jeu exact (required checks, reviews) et **demander confirmation avant chaque `gh api -X PUT`** ; vérifier par relecture ; cut de `v0.1.1` non nécessaire (remplacé par v0.2.0), note de migration Keycloak dans le CHANGELOG.
  - ADR 0013 : confirmer la limite assumée (CSP globale), la documenter dans l'ADR + `SECURITY.md`. ADR 0015 : confirmer « pas de tombstone sans avis DPO », mettre le statut de l'ADR à jour.
- **Lot 8 — REV-119** : `superpowers:brainstorming` → spec `docs/superpowers/specs/2026-10-xx-metriques-nommees-dataset-design.md` (partir de `docs/revue/2026-10-11-rev119-constat.md`, Cas 2 : aucune métrique nommée sur le dataset ; A28 = métriques CEL du dataset) → plan → exécution TDD → E2E.
- **Lot 9 — Expérimental + release** :
  - Marquer expérimentales les op à risque (writers externes jamais rejoués, messagerie email/Slack/SNS/Kinesis/RabbitMQ, `mcpCall`, connecteurs cloud) : flag `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED` éteint par défaut, `GET /pipelines/ops` n'expose que les op stables sinon, test de non-exposition, mention `.env.example` + `docker-compose*.yml` (vérif par valeur) + `test_deployability.py`.
  - CHANGELOG : passer `[Unreleased]` en `[0.2.0]`, ajouter les ruptures (`transform.qgis`, statuts `retrying`/`succeeded_with_rejects`, `/v1/`).
  - PR `dev→main` ; CI entièrement verte ; E2E complète 0 failed ; `scripts/replay/run.sh` vert ; `gh` : tag `v0.2.0` + release (confirmation avant `git tag`/push) ; vérifier `check_published_images.py` (9 images multi-arch).

## Self-Review

- Couverture : les 55 REV du backlog figurent dans la carte des lots (REV-164 incluse au lot 6 car citée comme à rejouer) ; chaque décision de Tanguy a un lot.
- Placeholders : les lots 3-9 sont volontairement sous forme de liste à détailler **après** le lot 0 (état réel des REV non encore vérifié) — chacun aura son plan complet avant exécution.
- Hypothèse à vérifier au lot 0 : les noms exacts des tests `xfail` (tronqués ci-dessus) et la numérotation de migration libre.
