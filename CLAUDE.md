# CLAUDE.md — guide de travail GeoStudio

Ce dépôt est développé **exclusivement par Claude** (sessions successives), piloté
par Tanguy. Ce fichier est le point d'entrée de chaque session : il dit où est la
vérité, ce qui est décidé, et comment on travaille ici.

## Ce qu'est ce projet

GeoStudio : plateforme d'applications géospatiales open-source (Apache-2.0).
Produit = le shell React (catalogue, éditeur de cartes, **builder no-code
config-driven**) + un cœur Python qui remplace progressivement GeoNode.
Fork de `gis-project` créé le 2026-07-05 pour exécuter l'« option C »
(refonte par étranglement) ; l'historique git (198 commits SP-0x) est conservé.

## Documents de référence (ordre d'autorité)

1. **`docs/vision/2026-07-04-feuille-de-route-geostudio.md`** — LA référence :
   phasage SP-1→SP-15, périmètre exact du remplacement de GeoNode (= l'interface
   `ItemClient`), modèle de données du cœur v0, **30 arbitrages tranchés (§8)**,
   jalons M1–M12. Un arbitrage ne se rediscute pas en session ; s'il doit changer,
   on met à jour ce document explicitement.
2. `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` — pourquoi
   l'option C, décisions produit (§9).
3. `docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md` — vision
   long terme.
4. `docs/vision/2026-07-09-brainstorm-geostudio-analytics-platform.md` — vision
   analytics/BI/decision support (validée, déclinée en SP-14/SP-15 et A28–A30) :
   benchmark, architecture Datasets→Widgets, personas.
5. `docs/superpowers/specs/` + `plans/` — chaque SP a sa spec puis son plan datés.
6. `docs/archive/` — générations dépassées ; ne pas s'en inspirer sans lire la
   note d'archive.

## Décisions figées (ne pas re-débattre)

- Produit **open-source public**, licence **Apache-2.0**, nom **GeoStudio**.
- Cœur **Python/FastAPI** = `core/` (monolithe modulaire) ; **`tenant_id` et
  `audit_log` sur toute table/écriture dès la première migration** Alembic.
- Autorisation : tables maison, **une seule porte `can(user, action, object)`**.
- Groupes de partage gérés par le cœur (pas par Keycloak). Identité : OIDC
  délégué à Keycloak, jamais de mots de passe dans le cœur.
- API d'écriture des données : **OGC API Features dans le cœur** (sous-ensemble
  utile d'abord) ; RLS PostGIS sur les données métier à partir de SP-3.
- Jobs : **procrastinate** (file Postgres, pas de broker). Fichiers : S3 présigné.
- Expressions no-code : **CEL** (spike cel-js avant SP-5, repli JSONLogic).
- Formulaires : générés depuis le schéma des collections + overrides.
- SDK public : **Web Components (Lit) + pont React interne** — pas d'ouverture
  aux tiers avant ça ; le registre React actuel reste interne.
- Client TS du shell : types générés depuis l'OpenAPI du cœur.
- MCP : module du cœur, même process, permissions de l'utilisateur, audité.
- GeoNode/Superset/Redis : **sortis (jalon M1, 2026-07-09)** — retirés du
  compose et du code ; tout code de contenu passe par le cœur.
- Post-v0.1 (SP-10→15 ; A27 amendé : OTel puis Lakehouse, ordre SP-12→15
  ensuite à arbitrer avant leur lancement) : observabilité **OTel + profil
  `grafana/otel-lgtm`** ; lakehouse **CDC par réplication logique (worker
  maison) → GeoParquet plat** (Iceberg différé), **DuckDB côté serveur** (API
  structurée pour les widgets, SQL read-only réservé aux analystes) ; **STAC
  natif dans le cœur** + export DCAT-AP + moissonnage par référencement
  (connecteurs : STAC → **ArcGIS FS** → GetCapabilities → CSW → CKAN) ; 3D
  **deck.gl Tile3DLayer + terrain raster-dem**, impression **Playwright en
  worker**.
- Analytics (brainstorm 2026-07-09 validé) : **datasets = objets de plateforme**
  (nouveau type d'item, pipeline déclaratif + métriques CEL, A28) — SP-14
  Analytics UX (requête visuelle, contexte global temps×emprise — emprise
  opt-in par dataset, A29 —, cross-filter, SQL Lab) et SP-15 alertes & rapports
  planifiés (exports secs CSV/XLSX, A30) ; bindings CEL généralisés + variables
  typées entrent au périmètre SP-5.

## Règles d'architecture non négociables

1. **`ItemClient` (`shell/src/api/itemClient.ts`) est le sas** : le shell ne parle
   jamais à un backend de catalogue autrement qu'à travers cette interface.
2. **Tout objet de plateforme est un document déclaratif schématisé** (AppConfig,
   MapConfig, bientôt collections/formulaires) — c'est ce qui rend le MCP et la
   génération IA possibles. Pas de logique cachée hors config.
3. Apps et dashboards = **un seul runtime** `AppRenderer(config, mode)` avec modes
   edit/preview/runtime. Pas de deuxième moteur.
4. Frontières de modules du cœur outillées (lint d'imports) dès SP-1a.

## Comment on travaille

- **Workflow superpowers** : brainstorm → spec (`docs/superpowers/specs/`) → plan
  (`docs/superpowers/plans/`) → exécution TDD → E2E → review. Fichiers datés
  `YYYY-MM-DD-spX…`.
- **TDD systématique** ; chaque feature visible a sa spec E2E Playwright. Les
  13 specs E2E existantes sont le filet de la migration : elles restent vertes.
- Commits **conventional** (`feat(shell): …`, `fix(core): …`), petits, un sujet.
- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Branche de travail : `dev` ; `main` reçoit les états stables (merge).

## Commandes

```bash
# shell
cd shell && npm ci
npm run test         # Vitest (61 fichiers, 398 tests)
npm run e2e          # Playwright (18 specs, VITE_AUTH_MODE=mock)
npm run build        # tsc --noEmit + vite build

# cœur
cd core && uv sync
uv run pytest        # 340 tests (302 exécutés + 38 marqués postgis, nécessitent docker)

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 9 services
                      # (postgis, pgbouncer, minio, martin, titiler,
                      # core, keycloak, shell, traefik)
```

## État au 2026-07-13 (mise à jour à chaque jalon)

- **Fait** : tout SP-0 (shell : catalogue, partage/publication, éditeur de carte,
  builder complet — pages, variables, thèmes, templates, breakpoints, SDK
  embryonnaire ; core : configs versionnées + rollback). Renommage
  `builder-service/`→`core/` (A14). **Tout SP-1 (a→d)** : socle du cœur (auth
  JWT OIDC + mode mock, `tenants/users/audit_log`, lint de frontières, `GET
  /me`), module `items`, partage/publication (`can()`, groupes, items publics
  anonymes), bascule complète du shell sur le cœur (`CoreItemClient`, plus
  aucun appel GeoNode), réalm Keycloak réel câblé et validé end-to-end. **Jalon
  M1 (GeoNode-free) atteint** : GeoNode/Superset/Redis retirés du compose et du
  code. **Tout SP-2 (a+b)** : serveur MCP v0 — `/mcp` authentifié OAuth
  2.1+PKCE (Keycloak Authorization Server, DCR, audience `geostudio-mcp`), puis
  les 7 outils métier (`list_items`, `get_item`, `get_app_config`,
  `save_app_config`, `create_item`, `get_sharing`, `set_sharing`, mêmes
  fonctions de repository et même porte `can()` que l'API REST,
  `actor_kind=agent` dans `audit_log`) + schéma JSON `AppConfig` publié
  (ressource MCP et endpoint HTTP). **Jalon M2 (AI-operable) atteint** : un
  agent MCP peut créer un dashboard valide qui s'ouvre dans le builder du shell.
- **SP-3a livré** (2026-07-10) : registre de collections (enregistrement
  admin, garde-fous, introspection vivante `GET /collections/{id}/schema`,
  partage groupes×rôles, accès anonyme aux collections publiques), rôle admin
  (`users.is_admin`, bootstrap `CORE_ADMIN_SUBS`, `GET/PATCH /users`), RLS
  générée par collection (rôle `gis_rls`, policy `tenant_isolation`), seed
  démo (`core/scripts/seed_demo.py`), infra de test PostGIS (marqueur
  `postgis`).
- **SP-3b livré** (2026-07-11) : OGC API Features Part 1+4 dans le cœur
  (landing, conformance, items GeoJSON — bbox, filtres, pagination avec
  liens —, POST/PUT/DELETE validés par schéma, audités), chaque requête
  métier sous `rls_scope` (rôle `gis_rls` + GUC tenant, validé à travers
  PgBouncer par `scripts/spike_pgbouncer_rls.py`).
- **SP-3c livré** (2026-07-11) : le shell lit ses couches "feature" (sélecteur
  de couches carte, sources de données du builder) directement depuis le
  cœur (`GET /collections`, `GET/POST/PUT/DELETE /collections/{id}/items`) ;
  `pg_featureserv` retiré du compose (10→9 services) et de toute la doc ;
  les 13 specs E2E restent vertes sur des mocks re-câblés. **SP-3 est clos.**
- **SP-4 livré et clos** (2026-07-11, sous-phases a+b+c) : formulaires dans le
  builder — nouveau widget Formulaire (schéma introspecté, overrides label/
  ordre/masquage/validation, écriture `feature.create`/`update`/`delete`,
  champ géométrie point, SP-4a), édition depuis la sélection carte/table
  (`itemSelected` émis par Carte et Table au clic, action `loadRecord` du
  Formulaire, mode édition avec bouton Annuler, préservation des champs/
  géométrie masqués à la modification, SP-4b), puis intégration (SP-4c) :
  `canWrite` par utilisateur exposé par le cœur sur les collections (miroir
  exact du prédicat serveur `_get_writable`), le Formulaire masque ses
  boutons d'écriture en fail-open quand `canWrite=false` (la frontière de
  sécurité reste le 403 serveur, inchangé), gabarit de galerie « Application
  de saisie » (Formulaire+Carte+Table pré-câblés sur une même source), spec
  E2E complète « déclarer un incident » + spec viewer-sans-boutons/403-forcé.
  **14 specs E2E vertes** (13 + `incident-form.spec.ts`).
- **SP-5a livré** (2026-07-11) : spike + moteur d'expressions CEL — spike
  `cel-js` validé (7/7, vocabulaire `vars`/`record`/`user`, gate A8 franchi),
  `shell/src/builder/expr.ts` (`evaluateExpression`/`validateExpression`,
  jamais throw), `visibleWhen` sur tout `WidgetItem` (masque un widget en
  preview/runtime, jamais en edit, `WidgetHost` câble `useAuth()` →
  `WidgetContext.user`), colonne calculée sur le widget Table (rétrocompatible
  avec les colonnes `string`), validation à l'édition (`getConfigExpressionErrors`,
  bouton **Enregistrer** désactivé si une expression est invalide), spec E2E
  `expressions.spec.ts`. **15 specs E2E vertes** (14 + `expressions.spec.ts`,
  20/20 tests). Revue finale de branche : aucun Critical/Important non résolu ;
  dette a11y notée hors périmètre (aria-label pré-existant sur le champ
  colonnes texte du Table, antérieur à SP-5a).
- **SP-5b livré** (2026-07-11) : actions composées avec condition —
  `ActionMessage.when` (CEL optionnel), `ActionBus.emit` ne déclenche la
  cible d'un message que si sa condition s'évalue à vrai contre
  `{ record: payload de l'émetteur, vars, user }` (message sans condition :
  comportement inchangé) ; `AppRenderer` alimente le bus en variables/
  utilisateur courants (`ActionConditionBridge`, même patron que
  `VariableBusBridge`) ; `ActionsPanel` gagne une condition éditable par
  action avec validation inline, `getConfigExpressionErrors` la valide
  aussi. **Fix cœur au passage** : `LayoutItem.visibleWhen`/`Message.when`
  ajoutés à `core/app/configs/schemas.py` — corrige un bug latent de SP-5a
  (`visibleWhen` était silencieusement supprimé à chaque enregistrement
  réel, le round-trip Pydantic `model_validate`/`model_dump` ignorant tout
  champ non déclaré ; non détecté par les E2E de SP-5a qui mockent le
  réseau). **16 specs E2E vertes** (15 + `action-conditions.spec.ts`).
  Revue finale de branche : aucun Critical/Important ; 1 Minor corrigé sur
  le champ (garde `typeof` sur une condition d'action non-string dans
  `getConfigExpressionErrors`, parité avec le garde équivalent de SP-5a sur
  les colonnes calculées). Prochain chantier : **SP-5c** (bindings CEL
  généralisés + variables typées — re-cadrage par son propre brainstorm
  avant plan, cf. spec SP-5
  `docs/superpowers/specs/2026-07-11-sp5-expressions-actions-composees-design.md`
  §1).
- **SP-5c livré et clos** (2026-07-12) : toute prop de tout widget accepte
  `{ $expr: "…" }`, résolu récursivement dans `WidgetHost` avant passage au
  composant, dans les 3 modes edit/preview/runtime (`resolveExprBindings`,
  reconnu seulement si l'objet a exactement une clé `$expr` string — pas de
  collision avec les colonnes calculées `{ label, expr }`) ; `Variable`
  gagne un type (`string|number|bool|date|record|list`, défaut `"string"`,
  rétrocompatible) qui pilote son éditeur dans `VariablesPanel` et la
  coercion appliquée par `Variable.set` (`VariableBusBridge` :
  extraction-par-clé + coercion pour string/number/bool/date en dégradation
  silencieuse, payload entier de l'émetteur pour record/list) ;
  `{{var:nom}}` reste le même mécanisme, rendu tolérant aux types non-string
  (`String(...)` scalaires, `JSON.stringify(...)` record/list). Cœur :
  `Variable.type`/`initialValue` élargis (Pydantic) pour persister sans
  rejet. Exécuté en subagent-driven-development (6 tâches, revue par tâche
  + revue finale de branche modèle opus, aucun Critical/Important). **17
  specs E2E vertes** (16 + `expr-bindings.spec.ts`, Table.itemSelected →
  variable record → `$expr` sur une prop non-Texte). PR #23 (dev→main)
  ouverte, CI verte après correction d'un drift attendu (`core-schema.d.ts`
  régénéré depuis l'OpenAPI, `Variable.type`/`initialValue` manquants) —
  fusion à la main. **SP-5 est clos.**
- **SP-6a livré** (2026-07-12) : infra jobs (`procrastinate`, file Postgres,
  service `worker` séparé dans le compose) + ingestion GeoJSON/CSV — un
  utilisateur authentifié (pas de restriction admin) uploade un fichier via
  URL S3 présignée (le cœur ne voit jamais les octets, arbitrage A6), le
  worker parse en pur Python (`shapely`, zéro GDAL — réservé à SP-6b),
  fail-fast strict (`IngestionParseError`, jamais d'exception brute qui
  fuite — 7 chemins de fuite fermés en revue : type de géométrie inconnu,
  encodage non-UTF8, `features`/`properties` malformés, champ CSV
  surdimensionné), crée une table PostGIS + l'enregistre comme collection
  (mêmes fonctions internes qu'un admin enregistrant à la main,
  `app.collections`/`app.configs`/`app.items`) + un item carte, sans
  intervention manuelle. Shell : bouton « Importer un fichier »
  (présignation → upload → poll du job → redirection carte, détection
  auto des colonnes lat/lon CSV avec repli manuel). Exécuté en
  subagent-driven-development (6 tâches, revue par tâche + revue finale de
  branche modèle opus). La revue finale a trouvé et fait corriger 3 défauts
  d'intégration invisibles à l'échelle d'une tâche : lignes importées
  héritant `tenant_id='default'` au lieu du tenant réel de l'uploader
  (invisible sous RLS pour tout tenant non-"default"), aucune trace d'audit
  pour la collection/l'item créés par le worker, clé d'upload S3 non
  vérifiée par préfixe tenant (risque confused-deputy) — plus un bug de
  test préexistant et sans rapport découvert en validant les tests
  `postgis` pour de vrai contre un conteneur PostGIS jetable plutôt que de
  se fier au skip local (`str(engine.url)` masque le mot de passe).
  **302 tests cœur** (272+30 skipped avant → 302 passed/38 skipped, tests
  postgis exécutés réellement en local pour la validation, skippés par
  défaut sans `CORE_TEST_DATABASE_URL`), **398 tests shell**, **18 specs
  E2E vertes** (17 + `ingestion.spec.ts`). Poussé sur `dev`. **SP-6a est
  clos.**
- **SP-6b livré et clos** (2026-07-12) : ingestion GeoPackage/Shapefile
  zippé — deux nouveaux parseurs (`parse_gpkg`, `parse_shapefile_zip`, via
  `pyogrio`, wheels manylinux, aucun paquet système), CRS source reprojeté
  automatiquement en WGS84 (`pyproj`, tout CRS résolu) avec fail-fast sur
  CRS absent/non reconnu/non transformable ; `ingestion_jobs.layer_name`
  (nullable) + `POST /uploads/inspect` (liste les couches d'un fichier
  juste après l'upload S3, avant la création du job) ; côté shell,
  sélection de couche **forcée** dès qu'il y en a plus d'une (jamais
  d'auto-sélection de la première) — un import mono-couche saute
  directement à l'exécution du job. Critère **M4** de la feuille de route
  (GPKG 50 000 entités → carte en <5 min) validé empiriquement : **~1,7-1,8s
  mesurés contre un PostGIS jetable réel**, ~170x sous le budget de 300s
  (insertion PostGIS non batchée, arbitrage YAGNI confirmé par benchmark).
  Exécuté en subagent-driven-development (7 tâches, revue par tâche + revue
  finale de branche modèle opus). Un défaut Important trouvé et corrigé en
  cours de route (Task 2) : `_crs_transform` ne capturait que l'échec de
  `pyproj.CRS.from_user_input`, laissant fuiter un `ProjError` brut de
  `Transformer.from_crs` sur un CRS résolu mais sans chemin de
  transformation vers WGS84 (`CRSError` est une sous-classe de `ProjError`,
  except élargi). Revue finale : aucun Critical/Important — `layer_name`
  tracé bout-en-bout sans perte sur les 7 tâches, garde tenant de
  `/uploads/inspect` identique à celle de `/uploads` (SP-6a), fermeture des
  fichiers temporaires vérifiée sur tous les chemins d'erreur des
  parseurs, `pyogrio`/`pyproj` synchronisés `pyproject.toml`+`Dockerfile`+
  `uv.lock`. 4 Minor notés, non bloquants : pas de limite de
  taille/décompression sur l'upload gpkg/zip (risque zip-bomb sur le
  worker partagé, suivi recommandé), `numpy` importé directement sans
  entrée `pyproject.toml` dédiée (transitif via `pyogrio`, choix assumé),
  commentaire « confused deputy » absent sur la garde tenant d'
  `inspect_upload`, cas 0-couche non testé côté shell (dormant —
  `list_layers` lève avant de pouvoir retourner `[]`). **Défaut
  pré-existant et sans rapport découvert au passage** (hors scope, non
  aggravé par cette branche) : `core/app/configs/models.py` (ORM `Config`)
  ne déclare pas `tenant_id`, alors que la migration `0002_tenants.py`
  l'ajoute en `NOT NULL` via DDL brut — invisible aux tests postgis du
  dépôt (tous construisent leur schéma via `Base.metadata.create_all`,
  jamais un vrai `alembic upgrade head`) ; un déploiement réel migré via
  Alembic puis écrivant `configs` via l'ORM lèverait une `IntegrityError`.
  À traiter séparément (**résolu 2026-07-13**, cf. entrée SP-7 plus bas).
  **326 tests cœur passed/43 skipped** (sans DB ;
  369 passed avec `CORE_TEST_DATABASE_URL` contre un PostGIS jetable),
  **400 tests shell**, **19 specs E2E vertes** (18 + `ingestion-gpkg.
  spec.ts`). Poussé sur `dev`.
- **SP-6c livré et clos** (2026-07-12) : nombre d'entités par collection
  (`feature_count`) — calculé à l'ingestion (`run_import`) et à
  l'enregistrement admin (`COUNT(*)` réel), maintenu atomiquement (`UPDATE
  ... feature_count = feature_count ± 1`, même transaction, jamais de cycle
  lire-Python-puis-réécrire) à chaque `create_feature`/`remove_feature` OGC
  API Features, exposé par l'API collections et affiché en badge dans
  `LayerPicker`. Migration 0011 avec backfill `COUNT(*)` sur les collections
  déjà enregistrées. Revue finale : aucun Critical/Important, 3 Minor non
  bloquants. **331 tests cœur passed/44 skipped** (375 avec PostGIS réel),
  **402 tests shell**. Poussé sur `dev`.
- **SP-7 livré et clos** (2026-07-13) : recherche sémantique + MCP v1 —
  pgvector (colonne `embedding vector(1536)` directe sur `items`/
  `collections`, image Postgres custom `deploy/postgis/Dockerfile` car
  `postgis/postgis` ne bundle pas pgvector), fournisseur d'embeddings
  enfichable (`FakeProvider` déterministe par défaut, `OpenAICompatibleProvider`
  en option, `CORE_EMBEDDING_PROVIDER`), recherche hybride trigram+vecteur
  combinée par Reciprocal Rank Fusion (permissions filtrées **avant** tout
  scoring, vérifié par des tests adversariaux sur items et collections) dans
  `list_items`/`list_visible_collections` (Postgres-only ; SQLite garde
  l'`ILIKE` actuel inchangé), `LayerPicker` gagne une recherche de
  collections, 3 outils MCP v1 (`search_catalog`, `query_features`,
  `create_form_app` — génère Carte+Table+Formulaire depuis le schéma d'une
  collection, Formulaire conditionné à `canWrite`, mapping schéma→champs
  dupliqué côté Python en écho documenté à `fieldsFromSchema` TS, même
  arbitrage que CEL/A8). Exécuté en subagent-driven-development (12 tâches,
  revue par tâche + revue finale de branche modèle opus). Plusieurs défauts
  réels trouvés **dans le plan lui-même** (pas dans le code produit) et
  corrigés en cours de route, chacun documenté et re-vérifié : `hybrid_search_ids`
  sans seuil de qualité sur la branche vecteur (RRF laissait un item
  sémantiquement opposé battre un item proche par double-comptage) ; jobs
  d'embedding cassant 75+ tests préexistants (`app.jobs.app`, l'App
  procrastinate partagée, n'est jamais `.open()`-ée par le process FastAPI —
  fixé en fail-open, `ProcrastinateException` narrow, pas `Exception` nu) ;
  plusieurs tests `postgis` du plan qui n'exerçaient jamais vraiment
  Postgres (`@pytest.mark.postgis` seul ne route pas vers Postgres dans ce
  dépôt, seule la fixture `pg_engine` le fait) ; un pattern glob Playwright
  (`**/collections`) qui ne matche pas une URL avec query string. **Revue
  finale de branche : 1 Critical trouvé et corrigé** — `app/jobs.py` n'avait
  pas `import_paths`, donc le worker réel (`docker-compose.yml`) n'important
  que `app.jobs`, n'enregistrait **aucune** tâche de domaine (régression de
  l'ingestion SP-6a en plus des nouveaux jobs d'embedding jamais exécutés) ;
  fixé avec `import_paths=[...]` + test de régression en sous-process dédié
  (un test in-process aurait été un faux positif). **Défaut pré-existant
  sévère découvert au passage, hors périmètre SP-7, non corrigé** :
  procrastinate 3.9.0 (version installée) rejette `SyncPsycopgConnector`
  comme non-async pour sa CLI — `procrastinate --app app.jobs.app worker`
  (la commande exacte de `docker-compose.yml`) ne démarre pas du tout,
  indépendamment du fix `import_paths` ; choix de connecteur datant de SP-6a,
  signifie qu'en l'état le service `worker` ne peut pas démarrer en
  déploiement réel (ingestion **et** embeddings non fonctionnels via
  `docker compose up`) ; à traiter dans une session dédiée (changer de
  connecteur = changement de comportement à revoir séparément, pas un simple
  fix). **359 tests cœur passed/62 skipped** (sans DB ; tous les tests
  `postgis` exécutés réellement contre un Postgres+pgvector réel à chaque
  tâche), **404 tests shell**, **20 specs E2E vertes** (19 +
  `layer-picker-search.spec.ts`). Poussé sur `dev`.
- **Résolu (2026-07-13, hors SP, /systematic-debugging)** : connecteur
  procrastinate non-async — `app.jobs.app` utilise désormais
  `PsycopgConnector` (async, satisfait le CLI ; sert toujours `.defer(...)`
  en synchrone via son `get_sync_connector()` interne) au lieu de
  `SyncPsycopgConnector`. Deuxième bug compound trouvé en reproduisant la
  vraie commande de `docker-compose.yml` dans l'image core réelle : le
  script `procrastinate` du PATH ne met jamais le cwd (`/app`) sur
  `sys.path`, donc `--app app.jobs.app` échouait à l'import même une fois
  le connecteur corrigé — `docker-compose.yml` invoque maintenant `python -m
  procrastinate` (comme `-c`/`-m`, qui ajoutent le cwd). Vérifié en
  construisant l'image `core/Dockerfile` réelle et en lançant `schema
  --apply` puis `worker` contre un Postgres vivant : le worker démarre et
  reste up. Même session : correction du même défaut d'IntégrityError
  latent que celui du SP-6b (voir plus haut), et de l'échec CI de PR #26
  (image Postgres CI sans pgvector — `.github/workflows/ci.yml` construit
  maintenant l'image `deploy/postgis/Dockerfile`, celle-là même déjà
  utilisée par `docker-compose.yml`) ; au passage, dérive silencieuse
  découverte sur `core/openapi.json`/`shell/.../core-schema.d.ts`
  (paramètre `q` de `GET /collections` manquant, non détectée avant faute
  du job `api-types-drift` bloqué en amont par l'échec pgvector) —
  régénérés. `core/app/configs/models.py` (`Config`/`ConfigRevision`)
  déclare maintenant `tenant_id` (mirroir du pattern `app.items`),
  `create_config`/`update_config`/`rollback_config` prennent un
  `tenant_id` obligatoire, tous les appelants mis à jour (routes, outils
  MCP, importeur d'ingestion).
- **SP-8a livré** (2026-07-13) : contrat de widget Web Component + pont
  `WidgetHost` — un widget peut être écrit en Web Component standard (custom
  element + manifeste JSON typé `WcWidgetManifest`) plutôt qu'en React et se
  comporte comme un widget interne (palette, panneau de props, thème,
  events, actions composées) sans toucher au renderer ni à la palette :
  `registerWcWidget` construit un `WidgetDefinition` standard depuis le
  manifeste et l'enregistre via `registerWidget` inchangé (`registry.ts`,
  `WidgetHost.tsx`, `PropsPanel.tsx`, `ActionsPanel.tsx`, `WidgetPalette.tsx`
  non modifiés — vérifié par diff), `WcHost` monte le custom element et lui
  assigne `props`/`data`/`user`/`navigate` comme propriétés DOM (jamais
  d'attributs sérialisés), relaie ses `CustomEvent` vers l'`ActionBus` et
  invoque ses méthodes publiques pour les actions du bus, panneau de props
  généré depuis le manifeste (aucun code React à la main), thème hérité
  nativement via les `--gs-*` déjà posées par `AppRenderer` (rien à
  construire dans le pont). `Compteur` porté en Lit (`gs-counter`,
  `example.counter-wc`) comme widget de référence, à côté du `Compteur`
  React existant (les deux coexistent). Exécuté en TDD (executing-plans, pas
  de subagents dans cette session). Deux défauts trouvés et corrigés
  **dans le plan** (pas dans le code produit) pendant l'implémentation :
  les tests d'édition de props numériques (Task 1 + Task 4) éditaient un
  champ number sans jamais faire suivre `onChange` vers `props` du
  composant testé, ce qui déclenche le reset de valeur contrôlée de React
  (un clear()+type() donne un résultat concaténé au lieu de remplacé) —
  fixé en enveloppant le panneau testé dans un composant avec state, comme
  le fait le vrai `PropsPanel` du builder ; l'E2E cliquait dans le widget
  WC alors qu'il était encore en mode édition, où l'intérieur d'un widget
  est couvert par l'overlay de sélection du canvas (même contrainte que
  `theme.spec.ts`/`widget-sdk.spec.ts`) — réaligné pour vérifier le rendu
  vivant (incréments, couleur du thème) en runtime après Enregistrer.
  **Défaut d'environnement sans rapport découvert au passage** : les
  décorateurs `lit/decorators.js` (`@customElement`/`@property`/`@state`)
  lèvent `Unsupported decorator location: field` avec le tsconfig de ce
  projet (`useDefineForClassFields: true`, pas d'`experimentalDecorators` →
  esbuild émet des décorateurs TC39 standards que Lit 3 ne supporte pas
  encore pleinement) ; `GsCounter` écrit avec l'API Lit sans décorateurs
  (`static properties`) plutôt que de changer le tsconfig global — à garder
  en tête pour tout futur widget WC en Lit. **421 tests shell** (404 avant
  + 17 : 13 sur `shell/src/builder/wc/`, 4 sur `counterWidgetWc.test.tsx`),
  **28 specs E2E vertes** (20 + 7 ajoutées depuis SP-7 +
  `wc-widget-bridge.spec.ts`). PR #27 (sp8a-wc-widget-bridge→dev) **fusionnée**.
- **SP-8b livré** (2026-07-13) : registre d'extensions + chargement dynamique
  de modules ES — un widget Web Component écrit et hébergé **hors du repo
  shell** (manifeste JSON + module ES servis par une URL) devient disponible
  dans le builder après enregistrement/activation par un admin, **sans
  redéploiement du shell**, et sa désactivation ne casse pas les apps qui
  l'utilisaient. Cœur : table `app.extensions` (clé composite `id`+`tenant_id`
  — deux tenants peuvent enregistrer le même type, pas de ressource physique
  à découpler contrairement à `Collection`), écritures admin-only auditées
  (`extension.create`/`update`), `GET /extensions` anonyme+scopé tenant
  (défaut tenant si anonyme, même convention que `app.collections`). Shell :
  `useActiveExtensions` (react-query, dégradation silencieuse à `[]`) récupère
  la liste au bootstrap de `AppBuilderPage`/`AppRuntimePage` (fail-open : un
  `/extensions` en échec ne bloque pas la page), `registerExtensionWidget`
  enregistre chaque manifeste dans le registre de widgets existant
  (`registerWidget` inchangé) via un `Component` qui importe paresseusement
  et mémoïse le module (`ensureModuleLoaded`, un rejet est aussi mis en
  cache — pas de retentative avant reload) et délègue au `WcHost` de SP-8a
  (inchangé, réutilisé par composition), avec placeholder pendant le
  chargement (« Chargement… ») ou en échec (« Extension indisponible » /
  « Widget inconnu » si désactivée). `wc/manifest.ts` étendu (rétrocompatible)
  avec un type de prop `dataSource` (rendu via `DataSourceSelect`, filtré par
  `permissions.collections` — filtre d'autorat côté panneau, **pas une
  frontière de sécurité** : le module WC reste libre d'appeler toute
  collection permise par le token du visiteur, la frontière réelle reste
  `can()`/RLS côté cœur, inchangée). Exécuté en subagent-driven-development
  (10 tâches, revue par tâche + revue finale de branche modèle opus). 1
  Important trouvé et corrigé en cours de route (Task 10) : la spec E2E
  prouvait props/events/actions composées mais jamais la parité de thème,
  alors que la checklist finale du plan l'exige et que la fixture avait été
  écrite exprès pour ça (`var(--gs-color-text,...)`) — fixé en réutilisant
  exactement le patron `getComputedStyle` de `wc-widget-bridge.spec.ts`
  (SP-8a). Revue finale de branche : aucun Critical/Important, **ready to
  merge**, 5 Minor non bloquants tous par conception ou compromis déjà
  documenté (délai fail-open ~5-7s dû aux retries par défaut de react-query ;
  désactivation effective seulement au reload complet, pas en navigation SPA,
  car le registre est un singleton sans dé-enregistrement — cohérent avec le
  critère E2E qui teste bien le reload ; `permissions.collections` cosmétique
  côté panneau — commentaire ajouté au code ; import rejeté caché pour la
  durée de la page ; `GET /extensions` anonyme résout au tenant par défaut
  seulement, cohérent avec le reste du système). **369 tests cœur passed/62
  skipped**, **435 tests shell** (421 avant SP-8a + 14), **30 specs E2E
  vertes** (28 + `extension-widget.spec.ts`, 2 tests). PR ouverte
  (sp8b-extensions-registry→dev).
- 2026-07-09 : brainstorm **Analytics Platform** validé (Q-A1→Q-A5) et décliné
  dans la feuille de route — SP-14/SP-15, arbitrages A28–A30, amendements
  A22/A27, jalons M11/M12. Rien à exécuter avant SP-11 (sauf quick wins
  « vague 0 » opportunistes au fil de SP-4/SP-5).
- Suivi non bloquant en attente : tags d'images Docker `pgbouncer`/`martin`/
  `titiler` repinnés vers des versions résolubles (2026-07-09) ; documenter
  dans `.env.example` si de nouveaux tags dérivent à nouveau.
- Questions produit encore ouvertes : Q2 (premiers utilisateurs réels),
  Q10 (temps réel), Q11 (offline) — cf. comparatif §8. Seule Q2 peut réordonner
  SP-3/SP-6.
