# SP-12c — Moteur de moissonnage + connecteur STAC externe — Progress Ledger

Plan: docs/superpowers/plans/2026-07-19-sp12c-moissonnage-stac.md
Workspace: checkout principal, branche `dev` (pas de worktree — convention
établie depuis SP-6a).
Base globale: dev@8f8119d (SP-12b clos, PR dev→main ouverte).

Note : ce fichier remplace le ledger SP-12b (clos, documenté dans CLAUDE.md).
Contenu précédent préservé dans l'historique git de ce fichier.

## Pré-vol

Scan des 11 tâches : pas de contradiction entre tâches ni avec les contraintes
globales. Interfaces vérifiées contre l'état réel du dépôt et conformes au
plan : `create_item(*, tenant_id, owner_id, resource_type, title, slug=None)`,
`update_item(*, tenant_id, item_id, title, abstract, keywords, is_published,
slug=None)`, `run_import(*, tenant_id, created_by, filename, content,
collection_title, lat_field, lon_field, layer_name=None) -> ImportResult
(.collection_id/.item_id)`, `write_audit(...)`, `ItemRead` camelCase
(resourceType/isPublished/keywords), `is_read_only_mode()`,
`get_current_user_optional`, `request_scoped_session`,
`get_or_create_user(bootstrap_admin=)`, `core_table_names` imports paresseux,
`jobs.import_paths` (ligne 59), pyproject layers (app.public/app.ingestion/
app.dcat) + ignore_imports (…app.db -> app.extensions.models).

Deux items de contexte fin (pas des contradictions, gérés en suivant le plan) :
- Task 5 : `test_jobs.py::test_import_paths_registers_all_domain_tasks` fait des
  assertions par-tâche explicites → l'implémenteur DOIT ajouter
  `assert "app.harvest.jobs.run_harvest_task" in task_names` pour couvrir
  réellement harvest.
- Task 10 : `shell/src/ui/ItemCard.test.tsx` existe déjà (5 tests) →
  l'implémenteur AJOUTE les 2 nouveaux tests, n'écrase pas le fichier.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 8f8119d
- Task 1: complete (commit 8cb616b, review clean — ✅ spec + quality, 0
  Critical/Important). ORM HarvestSource/HarvestRecord + migration 0016 +
  db.core_table_names + import-linter contract (app.harvest). 2/2 tests, full
  suite 608 passed/87 skipped, lint-imports 1 kept/0 broken. Minor non
  bloquant : le test unicité négatif n'est pas dans test_harvest_models.py
  (couvert par le test postgis de Task 3 contre Postgres réel).

Base Task 2: 8cb616b
- Task 2: complete (commits d048dff + f7d1e2e, review clean après fix — ✅
  spec + quality). Connecteur STAC (base.py/stac.py/__init__.py) HTTP-only,
  tolérant/borné. 1 Important trouvé en revue et corrigé (fix f7d1e2e) : la
  tolérance ne couvrait que le fetch HTTP + json() top-level ; un JSON valide
  mais structurellement hostile (top-level non-objet, entrée collections/links
  non-dict, bbox non numérique) crashait fetch() et jetait les records déjà
  collectés — durci avec isinstance(dict) + try/except (AttributeError,
  TypeError, KeyError, ValueError) autour de _collection_to_record, keywords
  non-liste coercé à []. 4 tests de régression hostiles ajoutés. Re-revue :
  Resolved, 0 nouveau Critical/Important. 12/12 tests connecteur, suite 620
  passed/87 skipped. Minors non bloquants : sémantique depth-cap (6 fetches sur
  chaîne unique), timeout redondant client+get, guards isinstance(link,dict)
  sans test dédié (corrects par inspection).

Base Task 3: f7d1e2e
- Task 3: complete (commits 534c3b6 + e81e3d5, review clean après fix — ✅
  spec + quality). repository.py CRUD + list_due_sources +
  mark_missing_as_stale. 1 Critical trouvé en revue et corrigé (fix e81e3d5) :
  list_due_sources comparait un `_now()` aware à un `last_run_at` désérialisé
  naïf (colonne DateTime naïve) → TypeError sur le chemin cold-fetch (session
  fraîche) qu'un vrai scheduler emprunte ; le test initial ne le voyait pas
  (identity map servait le même objet aware). Fix : normalisation aware-UTC de
  last_run_at avant comparaison, `_now()` reste aware (convention dépôt) ; test
  renforcé avec `session.expire_all()` (load-bearing car expire_on_commit=False)
  → RED sur code pré-fix reproduit empiriquement, GREEN après. Re-revue :
  Resolved, 0 nouveau Critical/Important. 7 passed/1 postgis skipped. Minor
  (couvert par le fix) : le test cold-fetch manquait.

Base Task 4: e81e3d5
- Task 4: complete (commits fb84768 + 4c3f50c, review clean après fix — ✅
  spec + quality). service.py moteur : upsert idempotent reference/copy,
  jamais de doublon, is_stale (jamais suppr), audit. Testé contre PostGIS réel
  (6/6, suite 721 avec DB). 1 Important = contradiction plan (contrat "ne lève
  jamais, toute erreur de fetch/IMPORT capturée" vs code exemple qui n'entoure
  que fetch()) → décision utilisateur : PATCH. Fix 4c3f50c : 2e try/except
  autour du loop + mark_missing_as_stale, toute exception loop → last_status=
  "error", jamais de raise (protège le job Task 5 des zombies) ; sur échec
  mid-loop, mark_missing_as_stale ne tourne pas et statut jamais "ok" ;
  progrès partiel (records déjà upsertés) conservé. Test SQLite always-run
  ajouté (copy-mode items_fetcher qui lève). Re-revue : Resolved, 0 nouveau
  Critical/Important. 5 passed/2 postgis skipped. Note : le commit a inclus le
  fichier scratch task-4-report.md (tracké dans ce dépôt, bruit inoffensif).

Base Task 5: 4c3f50c
- Task 5: complete (commit c6899d5, review clean — ✅ spec + quality, 0
  Critical/Important). jobs.py : run_harvest_task + run_harvest_sweep_task
  (cron */15), les DEUX court-circuitent is_read_only_mode() avant toute
  mutation (tests assertent last_status reste None). import_paths += app.harvest.
  jobs. EXTRA contrôleur appliqué : assertion `app.harvest.jobs.run_harvest_task`
  ajoutée à test_jobs.py (couvre réellement l'import_paths, re-run 3/3).
  5 tests harvest_jobs contre PostGIS réel (:5433, InMemoryConnector). Minors
  non bloquants : import `timedelta` inutilisé dans le test ; gap 2-phase-commit
  (crash entre mark_running et harvest → statut coincé "running", hérité du
  brief, à suivre).

Base Task 6: c6899d5
- Task 6: complete (commit 2dbd9be, review clean — ✅ spec + quality, 0
  Critical/Important). schemas.py + routes.py : CRUD admin-only /harvest/sources*
  + /run (deferrer injectable), audit patron app.extensions, cross-tenant 404
  non-fuyant (structurel : get_source tenant-scopé réutilisé partout), copy sur
  connecteur non-supporté → 400 création, type inconnu → 422, read-only via
  middleware existant. /run audite AVANT defer + commit explicite (ferme une
  race). 10 tests (le "11" du plan était une erreur de comptage). L'implémenteur
  a AUSSI monté le routeur dans main.py (2 lignes) pour rendre les tests verts →
  l'étape de montage de Task 7 est déjà faite. 642 passed/95 skipped, lint clean.
  MINORS notés pour la revue finale : (1) HarvestSourcePatch.intervalMinutes
  sans `ge=1` (contrairement à Create) → PATCH intervalMinutes:0 passe et rend
  la source "due" à chaque balayage (bug de planification latent réel, hérité du
  brief, fix trivial) ; (2) pas de test cross-tenant DELETE/run (symétrique par
  construction).

Base Task 7: 2dbd9be
- Task 7: complete (commit 567227b, review clean — ✅ drift-free + cohérent, 0
  Critical/Important). Montage main.py déjà fait par Task 6 (vérifié, pas de
  doublon). Regen openapi.json (3 chemins /harvest, 6 opérations) +
  core-schema.d.ts (généré, cohérent 1:1). Suite cœur 642 passed/95 skipped,
  lint 1 kept/0 broken, build shell vert. Note : export_openapi.py nécessite
  PYTHONPATH=. (pattern connu du dépôt).

Base Task 8: 567227b
- Task 8: complete (commit 2a26888, review clean — ✅ spec + quality, 0
  Critical/Important/Minor). types.ts (ResourceType += external, HarvestSource*),
  itemClient.ts (5 méthodes, listHarvestSources unwrap {sources}→[]), hooks.ts
  (5 hooks, invalidation ["harvest-sources"], enabled respecté). 3 tests ajoutés
  (append, 0 supprimé), 21/21 hooks, suite shell 576/576, build clean.
  getHarvestSource omis à dessein (aucun consommateur ; EditHarvestSourceDialog
  reçoit source en prop).

Base Task 9: 2a26888
- Task 9: complete (commit 8c7d746, review clean — ✅ spec + quality, 0
  Critical/Important). CreateHarvestSourceDialog + EditHarvestSourceDialog +
  HarvestSourcesAdminPage + route /admin/harvest + nav "Moissonnage". Gating
  admin réel (useHarvestSources enabled=isAdmin, ne fetch jamais si non-admin,
  prouvé par flag `called`), readOnly désactive submit (useInstanceInfo), delete
  via ConfirmDialog scopé (within). 3 corrections légitimes du snippet de test
  du plan (within() au lieu de .getByRole sur HTMLElement, typage `created`,
  retrait `exact:true` invalide sur ByRole) — vérifiées non-affaiblissantes.
  3/3 tests page, suite 579, build clean. Minors : readOnly-disable pas testé
  directement, create test n'assert pas `mode` du POST.

Base Task 10: 8c7d746
- Task 10: complete (commit 289b7c0, review clean — ✅ spec + quality, 0
  Critical/Important). ItemCard.tsx : RESOURCE_TYPE_LABELS {external:"Externe"}
  + fallback. 2 tests ajoutés (append), 5 existants préservés (0 suppression),
  7/7. Changement minimal, aucun fichier parasite.

Base Task 11: 289b7c0
- Task 11: complete (commits 125e243 + 772f66c, review clean après fix — ✅
  spec + quality). E2E harvest-stac.spec.ts (admin → source STAC → run → item
  externe + badge → re-run sans doublon). Validation empirique : 44/44 E2E,
  cœur 642 passed/95 skipped (SQLite), 95 postgis passed contre Postgres réel
  (contrainte unique harvest + jobs), migration 0016 s'applique proprement
  0001→0016, lint 1 kept/0 broken. 1 finding test-honnêteté (CONFIRMED) : le
  toHaveCount(1) de re-moissonnage était tautologique (mock à objet unique
  réassigné) → fix 772f66c : magasin Map keyé par id externe, upsert, /items
  renvoie les valeurs → l'assertion a un vrai mode d'échec ; commentaire vers
  la preuve authoritative cœur. Vérifié directement (petit diff, re-review
  agent interrompu par limite). Note : l'invariant réel sans-doublon est prouvé
  côté cœur (test_harvest_repository unique + test_harvest_service re-harvest).

## Roll-up Minors (pour la revue finale de branche)
- Task 2 : sémantique depth-cap (6 fetches sur chaîne unique) ; timeout
  redondant client+get ; guards isinstance(link,dict) sans test dédié.
- Task 5 : import `timedelta` inutilisé dans test_harvest_jobs.py ; gap
  2-phase-commit (crash entre mark_running et harvest → statut coincé
  "running", hérité du brief).
- Task 6 (NOTABLE) : HarvestSourcePatch.intervalMinutes sans `ge=1` (Create l'a)
  → PATCH intervalMinutes:0/négatif passe ; 0 rend la source "due" à chaque
  balayage (bug planification latent réel, fix trivial). Pas de test cross-tenant
  DELETE/run (symétrique par construction).
- Task 9 : readOnly-disable des dialogues pas testé directement ; create test
  n'assert pas `mode` du POST.
- Général : fichiers scratch .superpowers/sdd/*-report.md parfois inclus dans
  des commits (task-4-report.md dans 4c3f50c) — bruit inoffensif, dir en partie
  gitignore.

## Revue finale de branche (opus, base 8f8119d) — Ready to merge: With fixes
- Les 9 propriétés de sécurité/intégrité TIENNENT bout-en-bout (idempotence,
  isolation tenant 404 non-fuyant, admin-only+audit, read-only sur les DEUX
  jobs, tolérance/bornes connecteur, harvest_source ne lève jamais,
  import_paths, lint-imports, items externes jamais ré-exportés par STAC/DCAT —
  pas de blanchiment de catalogue). 0 Critical, 0 Important.
- Fix gating #1 + robustesse #2 appliqués en 1 commit (08650ef, re-revue
  Resolved) : HarvestSourcePatch.intervalMinutes `ge=1` (PATCH intervalMinutes:0
  → 422, openapi regénéré) ; session.rollback() + refetch avant statut d'erreur
  dans le loop except → harvest_source ne lève JAMAIS même sur IntegrityError
  empoisonnant la transaction (test postgis réel reproduit une vraie
  IntegrityError, no-raise + statut "error"). 644 passed/96 skipped (no DB),
  740 passed contre Postgres réel, lint 1 kept/0 broken, build shell clean.
  Changement de sémantique assumé : progrès partiel désormais ANNULÉ par le
  rollback (sans dommage — upsert idempotent, réconcilié au run suivant).
- Minor doc restant corrigé (commit 1d9dfcf) : commentaire service.py:70 mis à
  jour (progrès partiel annulé, pas conservé).
- Suivis post-merge (non bloquants, documentés) : cap global de documents
  fetchés dans StacConnector ; sweep qui saute les sources "running" ; masquage
  des boutons d'écriture de la page harvest en mode démo (aligné sur le pattern
  SP-9 déjà accepté).

## SP-12c COMPLET — 11 tâches + revue finale + fixes. HEAD=1d9dfcf. Reste: finishing.

---

# SP-12d — Connecteur ArcGIS FS + durcissement egress SSRF
Plan: docs/superpowers/plans/2026-07-22-sp12d-connecteur-arcgis-egress.md
Branch: dev. Base (merge-base main): df33995. Start HEAD: f87f3a8.
Pre-flight: clean. Fixtures verified — test_harvest_routes uses `env` fixture
(app,client,Session,admin,regular) + `_as(app,user)`, NOT `client_admin`.
test_harvest_service has session/tenant_and_user fixtures (lines 30/40).
pyproj>=3.6 present. openapi script = core/scripts/export_openapi.py.
types.ts:264 HarvestSourceType="stac". Shell dialogs + admin page exist.

## Tasks
- [x] Task 1: egress.py — complete (f87f3a8..ebdcb62, review clean)
- [x] Task 2: seam+STAC+egress — complete (ebdcb62..da3f377, review clean, no issues)
- [x] Task 3: ArcgisConnector.fetch — complete (da3f377..769dfb6, review clean; brief test coords fixed 489353->647850, stale comment corrected)
- [x] Task 4: ArcGIS copy pagination — complete (817a63e..54e492c, review clean, no issues)
- [x] Task 5: schema arcgis + regen — complete (54e492c..6afeccb, review clean, drift isolated)
- [x] Task 6: skip running + reclaim — complete (6afeccb..5a08d86, review clean)
- [x] Task 7: postgis integration — complete (5a08d86..7db4b07, review clean; 4 passed real Postgres; brief copy test wiring bug fixed — mock http_get injected copy-test-only; +feature_count==3 assertion)
- [x] Task 8: shell type selector — complete (7db4b07..18a5ebb, review clean, no issues)
- [x] Task 9: shell demo masking — complete (18a5ebb..c8de045, review clean, no issues)
- [x] Task 10: E2E harvest-arcgis — complete (c8de045..e73118e, review clean; 45/45 E2E first-try)

## SP-12d roll-up Minors
- Task 1: RFC6598 CGNAT 100.64.0.0/10 not blocked (outside brief's 6-category list; note for worker network reachability).
- Task 6: two new running-source tests don't expire_all() → naive-updated_at branch untested (inherited from brief; behavior proven via aware path, identical to covered last_run_at). Low risk.

## SP-12d — All 10 tasks complete, reviews clean. Final verification:
- Core SQLite 678 passed/100 skipped; postgis 100 passed; lint-imports 1 kept/0 broken.
- Shell 583 Vitest; 45/45 E2E; build clean. No OpenAPI drift.
## Final whole-branch review (opus, f87f3a8..e73118e) — Ready to merge: YES
- 7 end-to-end properties traced adversarially and HOLD (egress guard in path of both
  connectors+copy for IP-literal & DNS; harvest_source never raises on any branch incl
  poisoning IntegrityError; anti-dup constraint intact; reprojection can't leak; no new
  authz; reference items never re-exported by STAC/DCAT). Task 3/7 deviations confirmed sound.
- IMPORTANT #1 (fixing pre-merge): ArcGIS copy fetch_copy_geojson caps features (200000) but
  not pages → hostile 1-feature/page + exceededTransferLimit=true forces up to 200k sequential
  GETs (bounded but long worker stall). Fix: add page cap, break with warning.
- Minors (accepted / logged follow-ups): CGNAT 100.64/10 not blocked; Task6 tz-naive branch
  structural-only; per-page guarded client churn (v0 ok); allowlist case-sensitive (fails
  closed); Edit dialog has no type selector — CORRECT (HarvestSourcePatch has no type field,
  type immutable post-create by design).

## Final-review fix applied (1aa4ed7): ArcGIS copy page cap _MAX_COPY_PAGES=1000.
Page-cap test passes; truncates-at-max-features still hits feature cap (400<1000).
Connector suite 13/13, lint clean. IMPORTANT #1 RESOLVED. Branch complete: HEAD=1aa4ed7.

## SP-12d CLOS. HEAD=629d5aa. Pushed origin/dev. CLAUDE.md updated (629d5aa).
## PR #44 dev→main ouverte (https://github.com/tlenenao/geostudio/pull/44).

---

# SP-12e — Connecteurs GetCapabilities (WMS/WFS/WMTS) + affichage raster
Plan: docs/superpowers/plans/2026-07-23-sp12e-connecteurs-getcapabilities-raster.md
Branch: dev (checkout principal, pas de worktree — convention dépôt).
Base (merge-base main): df33995. Start HEAD: 118c1f4 (après commit séparé du
refacto CLAUDE.md, décidé par l'utilisateur).

## Pré-vol
Scan des 10 tâches : pas de contradiction entre tâches ni avec les contraintes
globales. Duplication ~12 lignes de cycle de vie client (fetch/_fetch try/finally)
entre wms/wfs/wmts — délibérée (3 connecteurs séparés, parsing distinct),
idiomatique, non bloquante. Décision utilisateur pré-exécution : le refacto
CLAUDE.md non commité (~1400 lignes, hors SP-12e) a été commité séparément
(118c1f4) pour que Task 10 parte d'un arbre propre.

## Tasks
Base Task 1: 118c1f4
- Task 1: complete (commit c76f238, review clean — ✅ spec + quality, 0
  findings). ows.py (parse défensif defusedxml + helpers namespace-agnostiques +
  bornes) + HarvestedRecord.raster_tiles_url (dernier champ, défaut None) +
  defusedxml>=0.7. 7/7 ows, 28/28 non-régression STAC/ArcGIS, lint 1 kept/0
  broken. Reviewer note : call sites existants (arcgis:80, stac:139) en kwargs →
  ordre de champ non-critique de toute façon.

Base Task 2: c76f238
- Task 2: complete (commits c87908a + fix 5a69de5, review clean après fix — ✅
  spec + quality). WmsConnector (couche nommée → record raster GetMap 3857) +
  registre. Déviation ASSUMÉE et validée : CRS inheritance en OVERRIDE (couche
  avec propre <CRS> l'emporte, sinon hérite) au lieu de l'UNION du code verbatim
  du brief — car le code UNION du brief CONTREDIT son propre test
  test_layer_without_web_mercator_is_reference_only (nomerc own 4326 sous racine
  3857 : union le promeut raster à tort). Override fait passer les 3 tests et
  colle à la dégradation gracieuse. 1 Important trouvé en revue (reproduit live)
  et corrigé (fix 5a69de5) : keyword extraction `k.text.strip()` non gardé →
  `<Keyword/>` vide (text None) levait AttributeError HORS du connecteur, viole
  "ne lève jamais" ; gardé `if k.text and k.text.strip()` (aligné sur WFS) +
  test de non-régression `test_empty_keyword_does_not_raise`. 7/7 WMS, 28
  non-régression, lint clean.

Base Task 3: 5a69de5
- Task 3: complete (commit 41fb3e5, review clean — ✅ spec + quality, 0
  Critical/Important). WfsConnector (FeatureType → record vecteur
  supports_copy=True + copie GeoJSON paginée startIndex/count, bornée
  _MAX_COPY_PAGES/_MAX_COPY_FEATURES/_COPY_PAGE_SIZE, tolérante) + registre
  (stac/arcgis/wms/wfs préservés). 3 risques nommés tracés OK : pagination
  bornée (double borne pages+features, pas de boucle infinie), _ft_bbox/
  _ft_keywords ne lèvent pas sur XML vide/hostile (gardes + except), registre
  complet. 6/6 WFS, 22 non-régression, lint clean. Minor cosmétique (verbatim du
  brief) : off-by-one borne de pages (au plus _MAX_COPY_PAGES-1 GET, plus strict
  que le nom du constant, sans impact — passe le test).

Base Task 4: 41fb3e5
- Task 4: complete (commit 5803aaf, review clean — ✅ spec + quality, 0
  Critical/Important). WmtsConnector (Layer → record raster {z}/{y}/{x},
  ResourceURL RESTful sinon KVP GetTile) + registre (5 connecteurs préservés).
  4 risques nommés tracés OK, dont le strip KVP vérifié EMPIRIQUEMENT par le
  reviewer (bytes.replace substring match retire bien <ResourceURL>, le test KVP
  exerce le bon chemin) ; dégradation intéger-TileMatrix correcte (mercator AND
  all-int), no-raise sur XML hostile, registre complet. 6/6 WMTS, 54 suite
  connecteurs, lint clean. Minor (couverture) : pas de fixture "mercator +
  TileMatrix non entier" ; garde correcte par inspection.

Base Task 5: 5803aaf
- Task 5: complete (commit 5d2cbd4, review clean — ✅ spec + quality, 0
  findings). Literal type élargi à stac/arcgis/wms/wfs/wmts ; regen openapi.json
  (drift borné à l'enum HarvestSourceCreate.type, +4 lignes) + core-schema.d.ts
  (miroir 1 ligne) + types.ts HarvestSourceType 5 valeurs. Gating copie 400
  wms/wmts vient du _check_copy_support préexistant (aucune route ajoutée).
  2 corrections contrôleur appliquées (brief assumait un client_admin
  inexistant) : 3 nouveaux tests réécrits sur env/_as réel ; test existant
  test_create_unknown_type_is_rejected wms→csw (garde reject préservée, plus
  wms qui est désormais valide). RED confirmé (6 fail/3 pass) → GREEN (9/9),
  suite core -k not postgis 709 passed, build shell clean.

Base Task 6: 5d2cbd4
- Task 6: complete (commit 0678ce2, review clean — ✅ spec + quality, 0
  Critical/Important). Migration 0017 (external_url/tiles_url/layer_kind,
  réversible, 0016→0017) + colonnes modèle alignées + create_record 3 kwargs +
  _layer_kind (raster avant feature) + les 2 branches de _upsert_reference
  (create ET refresh) + _upsert_copy (tiles_url=None). Migration vérifiée
  upgrade→downgrade→upgrade contre PostGIS réel (0001→0017). RED→GREEN, suite
  710 passed. Minor : test lit via identity map sans expire (convention du
  fichier ; existence colonnes prouvée par le cycle migration réel).

Base Task 7: 0678ce2
- Task 7: complete (commit aa93429, review clean — ✅ spec + quality, 0
  Critical/Important). GET /harvest/layers (auth non-admin) : SQL filter
  tenant + tiles_url IS NOT NULL (+ q ILIKE) PUIS can(read) par ligne. Design
  2-portes GENUINEMENT testé : item caché (owner=regular, tiles_url non-null,
  non publié) passe le filtre SQL, exclu SEULEMENT par can(read) ; record
  feature (tiles_url NULL) exclu par le SQL. Reviewer a tracé can() → exclusion
  correcte. Isolation tenant doublement appliquée (list_layer_records +
  get_access_facts). RED→GREEN, 19 non-régression, lint clean. Minor (hérité du
  brief) : get_access_facts par ligne sans pagination — OK au volume actuel.

Base Task 8: aa93429
- Task 8: complete (commit f282014, review clean — ✅ spec + quality, 0
  findings). CreateHarvestSourceDialog : 5 options Type + gating copie
  (COPY_TYPES=[stac,arcgis,wfs], option Copie disabled sinon, switch vers
  wms/wmts remet mode=reference). Test de reset GENUINEMENT exercé
  (copy→switch wms→submit→assert body mode:reference). Cohérence
  COPY_TYPES/onChange vérifiée. Adapté au harnais réel (Harness local + server
  MSW, pas de renderWithProviders). RED→GREEN 3/3, build clean.

Base Task 9: f282014
- Task 9: complete (commit b1a8caa, review clean — ✅ spec + quality, 0
  findings). LayerSource élargi (service:"external", kind:"raster", additif) +
  toMapLayer branche raster (réutilise la variante MapLayer raster existante,
  AUCUNE nouvelle primitive carto) + fetchExternalRasterSources 3ᵉ promesse du
  Promise.allSettled (panne raster tolérée, throw seulement si tout échoue,
  throw sur !res.ok) + route mock E2E harvest/layers* défaut inerte {layers:[]}.
  Test raster Vitest assert kind/visible/tilesUrl exact (placeholder inclus).
  7/7 LayerPicker, 586 Vitest, 45/45 E2E, build clean.

Base Task 10: b1a8caa
- Task 10: complete (commit 5cfe75d, review clean — ✅ spec + quality, 0
  findings). E2E harvest-wms.spec.ts (admin → source WMS → moissonnage mock →
  item raster externe + badge Externe → carte → LayerPicker → ajout couche →
  assertion "Retirer USA States (WMS distant)" visible = MapLayer raster ajouté
  au config). Preuve GENUINE (pas tautologique, tracée : run→rasterLayers→
  /harvest/layers override→fetchExternalRasterSources→LayerPicker→onAdd→
  LayersPanel). Route override Playwright LIFO correcte. CLAUDE.md Fait a→e +
  À venir f→g (pas de mangling). Passé verbatim 1er run, 46/46 E2E, 586 Vitest,
  build clean, aucun changement produit.

## SP-12e — 10/10 tâches complètes, toutes revues clean.
## Fix de vérification finale (commit c9f0911) : DÉRIVE OpenAPI détectée —
GET /harvest/layers (Task 7) ajouté APRÈS la régénération de Task 5 →
openapi.json + core-schema.d.ts régénérés (le job CI api-types-drift aurait
échoué sinon). Aucune dérive résiduelle après régénération.

## Vérification finale de branche (HEAD=c9f0911)
- Core SQLite : 714 passed / 100 skipped. lint-imports 1 kept / 0 broken.
- Core PostGIS RÉEL (postgis-test:5433/gis_test) : 100 passed. ATTENTION infra :
  le gis_test persistant avait un harvest_records périmé (create_all n'ALTER pas
  une table existante → colonnes 0017 absentes) ; 8 échecs d'abord, corrigés en
  appliquant les 3 ADD COLUMN nullable de 0017 au gis_test (non destructif).
  Suivi : la base de test partagée ne migre pas — toute future migration heurtera
  ce mur, à traiter (drop harvest_records avant create_all, ou upgrade head).
- OpenAPI : aucune dérive résiduelle (regénéré + commité).
- Shell : Vitest 586 passed (87 fichiers) ; E2E 46 passed ; build clean.

## Vérification finale — done.

## Revue finale de branche (opus, 118c1f4..c9f0911) — Ready to merge: YES
Les 8 propriétés bout-en-bout TIENNENT (tracées adversarialement) : XML sûr
(defusedxml, aucun connecteur ne lève, engine never-raise ceinture+bretelles) ;
garde egress sur le chemin par défaut des 3 connecteurs + copie WFS via http_get
gardé ; séparation raster/vecteur + _layer_kind cohérent colonnes ; dégradation
gracieuse WMS/WMTS ; /harvest/layers 2 portes (SQL + can(read)) ; bornes dures ;
blast radius borné (drift = enum type + /harvest/layers) ; frontière carte
réutilise MapView raster. 0 Critical, 0 Important.

### Minor #1 (SUBSTANTIEL, DÉCISION UTILISATEUR) — WMS CRS inheritance en
replace-semantics (wms.py, `crs = own_crs if own_crs else inherited_crs`) au lieu
de l'UNION du plan. Par OGC 06-042 §7.2.4.6.7, <CRS>/<SRS> est ADDITIF (héritage
cumulatif) → replace donne un faux-négatif (couche mercator-capable qui redéclare
sa liste sans 3857, comptant sur l'héritage, devient reference-only à tort). Non
bloquant : serveurs réels (GeoServer/MapServer) re-listent tout le set → les 2
sémantiques coïncident en pratique ; échec = dégradation gracieuse, jamais crash.
Le reviewer note que le fixture test_layer_without_web_mercator_is_reference_only
encode l'attente non-spec (nomerc own 4326 sous racine 3857 : en union il
hériterait 3857 et serait addable). NB : c'est la déviation déjà adjugée en Task 2.
→ DÉCISION UTILISATEUR : corriger maintenant (union + réécrire le fixture).
FIX APPLIQUÉ (commit d8c11e0) : wms.py `crs = inherited_crs | _layer_crs(layer)`
(OGC-conforme) ; WMS_130 amputé de nomerc (states prouve désormais l'héritage
3857 par UNION) ; nouveau fixture WMS_NO_MERCATOR (racine+enfant 4326 seulement)
pour test_layer_without_web_mercator_is_reference_only (reference-only genuine
sous union). 7/7 WMS, lint 1 kept/0 broken. HEAD=d8c11e0.

## SP-12e CLOS. HEAD=d8c11e0. Poussé origin/dev (629d5aa..d8c11e0).
## PR #45 dev→main ouverte (https://github.com/tlenenao/geostudio/pull/45).
## Vérif finale post-fix : cœur 714 passed/100 skipped (SQLite) + 100 postgis
## réel, lint 1 kept/0 broken, aucun drift OpenAPI, shell 586 Vitest + 46/46 E2E
## + build clean. Note : PR #44 (SP-12c/d) déjà MERGÉE dans main (ae778ac).

### Minors non bloquants (suivis) :
- WFS copy : early-exit `len<page_size: break` du plan retiré → 1 requête vide
  en trop par harvest (borné, tests verts) ; + off-by-one page bound (999).
- ows.py : _MAX_DOCUMENTS + descendants() définis/testés mais non consommés
  (réservés au futur connecteur CSW SP-12f).
- /harvest/layers : N+1 get_access_facts par ligne (OK volume actuel, TODO batch).
- Infra test : gis_test PostGIS persistant ne migre pas (create_all n'ALTER pas
  une table existante) — colonnes 0017 ajoutées à la main ; mordra la prochaine
  migration sur harvest_records.
## Roll-up Minors (revue finale de branche)
- Task 3 : off-by-one cosmétique borne de pages WFS (au plus _MAX_COPY_PAGES-1).
- Task 4 : pas de fixture "mercator + TileMatrix non entier" (garde correcte par inspection).
- Task 6 : test service lit via identity map sans expire (convention fichier ;
  persistance prouvée par le cycle migration réel).
- Task 7 : GET /harvest/layers fait get_access_facts par ligne sans pagination
  (hérité du brief, OK au volume actuel).

---

# SP-12f — Connecteurs CSW 2.0.2 et OGC API - Records
Plan: docs/superpowers/plans/2026-07-24-sp12f-connecteurs-csw-ogc-records.md
Branch: dev (checkout principal, pas de worktree — convention dépôt).
Start HEAD: bfd5e87.

## Pré-vol
Scan des 5 tâches : pas de contradiction entre tâches ni avec les contraintes
globales. Task 1 (CswConnector) réutilise ows.py de SP-12e (parse_capabilities,
local, children, child, child_text, descendants, _WORLD_BBOX) — déjà présents
et déjà testés non-consommés (note SP-12e : "réservés au futur connecteur CSW
SP-12f"). Task 2 (OgcRecordsConnector) suit le style JSON tolérant de stac.py,
autonome (pas de dépendance à ows.py). Task 3 câble le registre + Literal
schemas.py — cohérent avec l'existant (5 connecteurs déjà enregistrés).
Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks
Base Task 1: bfd5e87
- Task 1: complete (commit a877a38, review clean — ✅ spec + quality, 0
  Critical/Important). csw.py (CswConnector GET-KVP paginé, ISO19139 avec
  repli DC décidé une fois sur la 1ère page) + registre non touché (Task 3).
  Transcription vérifiée octet-pour-octet contre le brief. 13/13 tests
  connecteur, 121 suite harvest, aucune régression. Minor cosmétique : séparateur
  `?`/`&` de _page_url double `?&` si base_url admin finit déjà par `?` nu (rare,
  inoffensif pour la plupart des serveurs CSW).

Base Task 2: a877a38
- Task 2: complete (commit f484526, review clean — ✅ spec + quality, 0
  Critical/Important). ogc_records.py (chemins fixes /collections +
  /collections/{id}/items, pagination via links[rel=next], bornée). Déviation
  ASSUMÉE et validée : le code du brief calculait external_url de repli avec
  page_url (variable de boucle, réassignée à chaque page) au lieu de l'URL
  initiale de la collection — contredisait le propre test du brief (rec-2,
  page 2, attend l'URL page 1 sans offset). Fix implémenteur : fallback_url
  capturé une fois par collection, threadé séparément de page_url. Revue :
  CONFIRMÉ par traçage manuel des deux chemins, risque nul (champ
  metadata-only, aucun aval copie/carte/RLS) — accepté sans escalade
  utilisateur (contrairement au cas CRS WMS SP-12e, ici pas d'enjeu spatial).
  9/9 tests connecteur, 130 suite harvest, aucune régression.

Base Task 3: f484526
- Task 3: complete (commit 14bb95a, review clean — ✅ spec + quality, 0
  findings). Registre (__init__.py, csw+ogc-records ajoutés à _REGISTRY,
  clés cohérentes avec .type des 7 connecteurs) + Literal schemas.py +
  tests get_connector/routes/service. Correction contrôleur légitime :
  test_create_unknown_type_is_rejected passe de type="csw" (devenu valide)
  à "geonode-legacy". routes.py NON touché (confirmé) — _check_copy_support
  préexistant gère déjà le 400 copie pour supports_copy=False. openapi.json
  diff minimal (2 valeurs d'enum). RED→GREEN, suite core complète 743
  passed/100 skipped, aucune régression.

Base Task 4: 14bb95a
- Task 4: complete (commit c4ea800, review clean — ✅ spec + quality, 0
  Critical/Important). core-schema.d.ts régénéré + HarvestSourceType +=
  csw/ogc-records + 2 options dialogue + 2 tests. COPY_TYPES (stac/arcgis/wfs)
  inchangé, csw/ogc-records en dehors → Copie disabled + reset mode=reference
  au switch (même pattern que wms/wmts). EXTRA mineure divulguée et vérifiée
  sûre : dédup d'un tableau dupliqué onChange vers la constante COPY_TYPES
  (identique élément-par-élément, même fichier/bloc, pas de restructuration
  non-divulguée). 5/5 tests dialogue, 588/588 suite shell, build clean.

Base Task 5: c4ea800
- Task 5: complete (commit 0bd620d, review clean — ✅ spec + quality, 0
  Critical/Important). harvest-csw.spec.ts + harvest-ogc-records.spec.ts
  (admin → source → moissonnage mock → item externe cherchable, preuves
  genuines : POST body, run→runCount, recherche avec waitForRequest réel,
  aucun câblage carte car métadonnées pures). CLAUDE.md (Fait a→f, À venir g
  seul) + feuille de route (§Connecteurs, table A22, note d'amendement)
  cohérents. EXTRA divulguée et vérifiée conforme au brief : paragraphe
  §Connecteurs de la feuille de route était déjà périmé (héritage SP-12e,
  "les quatre") — corrigé avec le texte de remplacement DÉJÀ prescrit par le
  brief lui-même (pas un jugement de l'implémenteur). 48/48 E2E, aucune
  régression.

## Roll-up Minors (pour la revue finale de branche)
- Task 1 : séparateur `?`/`&` de _page_url double si base_url admin finit par
  `?` nu (rare, inoffensif).
- Task 2 : fallback external_url pointe l'URL initiale de collection plutôt
  que la page où le record a été trouvé (metadata-only, aucun aval fonctionnel).
- Task 5 : d'autres mentions périmées du nombre de connecteurs subsistent hors
  du périmètre exact du brief — feuille de route lignes ~1326 ("4 retenus"),
  ~1345 (M9 "4 connecteurs"), ~1180 (SP-16 "4-5 connecteurs") ; CLAUDE.md:58
  section "Décisions figées" liste encore la chaîne sans OGC API - Records.
  Non bloquant, suivi doc à faire (éventuellement lors de la revue finale ou
  d'une session dédiée).

## Vérification finale
- Core : suite complète 743 passed/100 skipped (à Task 3, HEAD 14bb95a ;
  aucun fichier core touché depuis par Tasks 4-5). Shell : 588/588 Vitest +
  build clean (à Task 4, HEAD c4ea800 ; aucun fichier shell src touché depuis
  par Task 5). E2E : 48/48 (à Task 5, HEAD 0bd620d = HEAD final). Aucune
  dérive openapi/core-schema résiduelle (confirmée en revue finale).

## Revue finale de branche (opus, bfd5e87..0bd620d) — Ready to merge: YES
8 propriétés bout-en-bout tracées adversarialement et TIENNENT : ne-lève-jamais
(defusedxml + JSON tolérant, y compris chemins de repli ISO→DC et fan-out
collections/pages) ; garde egress structurellement incontournable (client
construit uniquement via build_guarded_client, EgressBlockedError PAS avalé,
propage à l'engine) ; items_url/raster_tiles_url toujours None aux 3 sites de
construction ; supports_copy=False cohérent sur 4 couches (schema/registre/
_check_copy_support sur create ET patch/shell) — aucune fuite mode=copy même
via PATCH ; bornes = arrêts durs qui composent (cap global vérifié en tête de
boucle collection ET dans _collect_collection, pas un slice a posteriori) ;
blast radius nul (additif pur, 0 migration) ; aucun blanchiment de catalogue
(STAC/DCAT non touchés, resourceType=external inchangé) ; artefacts générés
(openapi.json/core-schema.d.ts/types.ts) cohérents, dérive bornée à l'enum
attendu. 0 Critical, 0 Important. Les 2 déviations de tâche (URL de repli OGC
Records ; dédup COPY_TYPES shell) confirmées saines au niveau branche entière.
Minors non bloquants : feuille de route ligne ~1345 (M9 "4 connecteurs",
périmé avant même SP-12f) ; CLAUDE.md:58 ne nomme pas ogc-records explicitement
(défendable, "protocole successeur" de CSW) ; keywords JSON non coercés en str
dans ogc_records.py (pattern hérité identique de stac.py, déjà approuvé,
non-régression — durcissement partagé futur à envisager).

## SP-12f COMPLET — 5 tâches + revue finale, toutes clean. HEAD=0bd620d.
Reste : finishing (merge/PR).

