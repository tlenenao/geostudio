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

## État au 2026-07-19 (mise à jour à chaque jalon)

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
  vertes** (28 + `extension-widget.spec.ts`, 2 tests). Fusionnée dans `dev`
  (`sp8b-extensions-registry`→`dev`, fast-forward local, sans PR formelle —
  cohérent avec le patron SP-6a/SP-6b/SP-6c/SP-7).
- **SP-8c livré et clos** (2026-07-13) : widget tiers réel, admin, permissions
  serveur, containment — **clôt SP-8, jalon M5 (« SDK ouvrable ») atteint**.
  Cœur : `isAdmin` exposé par `GET /me` ; `GET /extensions?all=true` réservé
  aux admins (`include_disabled = bool(user and user.is_admin and all)`,
  fail-closed pour anonyme/non-admin, vérifié pour les 4 combinaisons) ;
  **frontière de sécurité serveur réelle** (contrairement au filtre client
  `permissions.collections` de SP-8b, qui restait un confort d'autorat) :
  `validate_extension_permissions` (`core/app/configs/extension_permissions.py`)
  rejette (400) une config qui route la prop `dataSource` d'un widget
  d'extension hors de son scope déclaré, câblée avant toute mutation dans
  `create_config`/`update_config`/`update_config_by_item` **et** dans les 3
  outils MCP qui écrivent des configs (`save_app_config`/`create_item`/
  `create_form_app` — trouvé et corrigé en revue finale, cf. ci-dessous) ;
  traverse aussi bien `layout.items` racine que `pages[*].layout.items`
  (multi-pages, couverture ajoutée en revue de tâche après un défaut trouvé
  dans le brief : branche non testée par les 6 tests initiaux). Shell :
  `ActionBus.emit` isole chaque handler dans son propre try/catch — un widget
  d'extension défaillant ne bloque plus les messages composés suivants vers
  d'autres widgets ; `Me.isAdmin` ; page d'admin `/admin/extensions` (liste
  incl. désactivées, activer/désactiver, fail-closed à 3 niveaux : route
  cœur, gate `enabled` de la query, garde PATCH admin-only). Widget externe
  de référence zéro-dépendance/zéro-build (`examples/external-widget/`,
  copiable par un auteur tiers sans notre toolchain) ; serveur E2E statique
  cross-origin dédié (`shell/e2e/external-widget-server.mjs`, port distinct
  du serveur preview du shell) prouvant un `import()` réellement cross-origin,
  pas un fixture same-origin déguisé ; guide `docs/guides/2026-07-13-ecrire-un-
  widget-web-component.md` pour auteurs tiers.
  Exécuté en subagent-driven-development (11 tâches, revue par tâche + revue
  finale de branche modèle opus). **Revue finale : 1 Important trouvé et
  corrigé** — la validation de scope de Task 3 n'était câblée que sur les 3
  routes REST ; les 3 outils MCP qui écrivent des configs contournaient
  totalement le contrôle (un agent MCP pouvait créer/enregistrer une config
  hors scope, exactement ce que REST rejette désormais) — fixé en câblant
  `validate_extension_permissions` aux 3 sites MCP avec la convention
  `ValueError` déjà en place dans ce fichier (pas `HTTPException`, transport
  MCP), test de régression via un vrai handshake `tools/call` (pas un appel
  Python nu). 2 Minor corrigés dans la même passe (garde optionnelle
  `useAllExtensions` alignée sur `useActiveExtensions` ; `AdminExtensionsPage`
  surface désormais un échec de PATCH). **Ready to merge: Yes** en re-revue.
  Défauts trouvés **dans le plan lui-même** (pas le code produit) pendant
  l'exécution, chacun documenté et corrigé : un `ignore_imports` manquant
  dans le contrat `layers` d'import-linter (`app.db -> app.extensions.models`,
  trou pré-existant exposé par l'ajout de `app.extensions` au contrat) ;
  un pattern glob Playwright (`**/extensions*`) qui collisionnait avec la
  navigation SPA vers `/admin/extensions` (même classe de bug que le patron
  déjà documenté pour `/items/1`/`/items/9` dans `mocks.ts`) ; le compte
  final du plan disait "33 specs E2E", le compte réel est 34 (30+1+2+1,
  confirmée coquille arithmétique par comptage direct fichiers/tests, pas
  une régression). **384 tests cœur passed/62 skipped** (381 avant le fix
  final +3), **lint-imports clean**, **445 tests shell** (444 +1, tsc
  clean), **34/34 specs E2E** (mesurées en tâche 11, non affectées par les
  fixes ultérieurs qui ne touchent aucun fichier E2E). Fusionnée dans `dev`
  (fast-forward local) et poussée sur `origin/dev` ; PR #30 (dev→main)
  ouverte pour synchroniser `main` (regroupe SP-8b + SP-8c, `main` n'avait
  pas encore reçu SP-8b). **SP-8 est clos.**
- **SP-9 « gestion des collections » livré et clos** (2026-07-15, sous-partie
  de SP-9 durcissement produit public v0.1, brainstormée indépendamment du
  reste de SP-9 — cf. specs `2026-07-13-sp9-gestion-collections-design.md`
  et les 5 autres sous-parties écrites le même jour, `2026-07-15-sp9-{
  gouvernance-legale,ci-publique-release,install-secrets,securite-minimale,
  demo-lecture-seule}-design.md`, non encore planifiées/exécutées) : un
  admin gère le cycle de vie complet d'une collection depuis le shell —
  lister, enregistrer une table PostGIS candidate (sélecteur admin-only,
  candidats non-enregistrables désactivés + raison affichée, jamais de
  saisie manuelle de nom de table), éditer, partager (groupes×rôles),
  désenregistrer (la table PostGIS survit, inchangé) — en pure façade sur
  des routes déjà autorisées/auditées (aucun nouveau modèle de permission).
  Cœur : un seul nouveau point d'entrée, `GET /collections/candidates`
  (admin-only, réutilise l'`Introspector` existant, denylist des tables
  cœur + exclusion des tables déjà enregistrées **pour le tenant courant**,
  déclaré avant `GET /collections/{collection_id}` dans le routeur — ordre
  chargé de sens, sans quoi Starlette route `candidates` comme un
  `collection_id` littéral) ; `GET /collections` gagne un champ `owner`
  (résolu en une seule requête `IN (...)`, pas de N+1). Shell : 7 méthodes
  `ItemClient`/hooks react-query, `CollectionsAdminPage` + 3 dialogues
  (`RegisterCollectionDialog`, `EditCollectionDialog`,
  `CollectionShareDialog` — ce dernier un quasi-doublon assumé de
  `ShareDialog.tsx`, même arbitrage que les échos déjà actés dans ce
  projet), lien de nav « Administration » scindé en « Extensions »/
  « Collections » (gating `isAdmin` fail-open côté client, la frontière
  réelle reste les 403 serveur inchangés, vérifié sur tout le diff en
  revue finale). Exécuté en subagent-driven-development (8 tâches, revue
  par tâche + revue finale de branche modèle opus). 1 Important trouvé et
  corrigé en cours de route (Task 8, spec E2E) : le mock de test
  `GET /collections` après suppression avait un branchement mort
  (`deleted` jamais prioritaire), le test de suppression ne prouvait que
  l'envoi de la requête DELETE, jamais la disparition réelle de la ligne —
  fixé + assertions DOM ajoutées (post-suppression **et** post-édition),
  stabilité vérifiée sur 12 exécutions répétées. Une dérive `openapi.json`/
  `core-schema.d.ts` détectée et corrigée juste après la Task 1 (nouvelle
  route + nouveau champ jamais régénérés, trouvé par le reviewer de tâche,
  résolu par le contrôleur sans re-dispatch). Revue finale de branche :
  **Ready to merge: Yes**, aucun Critical/Important — frontière de sécurité
  vérifiée intacte sur les 10 commits (chaque route de mutation garde son
  403 serveur préexistant, la seule route neuve applique `_require_admin`,
  aucune décision d'autorisation shell non adossée à un contrôle serveur),
  duplication `CollectionShareDialog` confirmée fidèle (pas de divergence
  bugguée), E2E confirmée comme une vraie preuve bout-en-bout et pas 8
  tranches recousues. 5 Minor non bloquants notés (`EditCollectionDialog`
  n'a pas le garde `.trim()||undefined` de `RegisterCollectionDialog` —
  question produit, pas un bug évident ; bannière d'erreur de suppression
  persistante entre actions non liées ; introspection O(tables) par requête
  `/collections/candidates`, acceptable à l'échelle d'un dialogue admin peu
  ouvert ; petite duplication exclude-core/exclude-registered entre
  `register_collection` et `list_candidate_tables`). **387 tests cœur passed/64 skipped** (sans
  DB ; 451 avec Postgres+pgvector réel), **lint-imports clean**, **466
  tests shell** (445 avant cette sous-partie +21), **36/36 specs E2E** (34 + `admin-
  collections.spec.ts`, 2 tests). Poussé sur `dev` (checkout principal,
  pas de worktree dédié — cohérent avec SP-6a/SP-6b/SP-6c/SP-7/SP-8b).
- **SP-9 « gouvernance & légal » livré et clos** (2026-07-16, sous-partie de
  SP-9, cf. spec `2026-07-15-sp9-gouvernance-legale-design.md` et plan
  `2026-07-16-sp9-gouvernance-legale.md`) : `CONTRIBUTING.md` (prérequis,
  lancer le projet/les tests, convention de commits, process de PR, où
  trouver le contexte, comment signaler un bug/proposer une feature,
  convention d'en-tête de licence) et `CODE_OF_CONDUCT.md` (Contributor
  Covenant v2.1 verbatim, contact `lenenaon.tanguy@gmail.com`) à la racine,
  tous deux en anglais (exception documentée à la règle « docs en français »
  de ce fichier — convention GitHub habituelle pour ces deux documents de
  gouvernance communautaire) ; section « Contribuer » ajoutée au
  `README.md` ; en-têtes SPDX (`# SPDX-License-Identifier: Apache-2.0` /
  `// SPDX-License-Identifier: Apache-2.0`) posés sur les 314 fichiers
  source applicatifs de `core/app/`, `core/tests/`, `shell/src/` (hors
  `shell/src/api/generated/`, exclu) via un script ponctuel idempotent
  (`scripts/add-license-headers.py`, laissé dans le dépôt, pas un hook ni
  un job CI — YAGNI assumé pour un projet à un seul committer humain, cf.
  spec). Exécuté en subagent-driven-development (3 tâches, revue par tâche
  + revue finale de branche modèle opus). Aucun défaut Critical/Important
  sur les 3 tâches ni en revue finale — le seul point trouvé (revue finale)
  était cosmétique (« All four commands » pour une liste de 5 commandes
  dans `CONTRIBUTING.md`), corrigé dans la foulée. Diff du script
  d'en-têtes vérifié structurellement par le reviewer de tâche (376
  insertions/0 suppressions = 314 en-têtes d'une ligne + le script de 62
  lignes, aucune autre modification) et sa logique (exclusion, idempotence)
  ré-exécutée indépendamment dans un bac à sable isolé. **466 tests shell**,
  **387 tests cœur passed/64 skipped**, `lint-imports` clean — aucune
  régression (les en-têtes n'affectent ni tsc ni pytest). Poussé sur `dev`
  (checkout principal, pas de worktree dédié, même patron que les autres
  sous-parties SP-9).
- **SP-9 « CI publique & release » livré et clos** (2026-07-16, sous-partie
  de SP-9, cf. spec `2026-07-15-sp9-ci-publique-release-design.md` et plan
  `2026-07-16-sp9-ci-publique-release.md`) : nouveau job `shell` dans
  `.github/workflows/ci.yml` (npm ci → test → e2e Chromium seul → build) à
  chaque push/PR, aux côtés des jobs `migrations`/`core`/`api-types-drift`
  déjà existants (`retries: process.env.CI ? 2 : 0` ajouté à
  `playwright.config.ts`, comportement local inchangé) ; nouveau workflow
  `.github/workflows/release.yml`, déclenché sur push de tag `v*.*.*` :
  `test-gate` (migrations+core+shell dupliqués depuis `ci.yml` par choix
  explicite du spec — un tag est un événement rare, la duplication coûte
  moins cher que `workflow_call` pour ce dépôt) gate un `build-and-push`
  matriciel (3 images `core`/`shell`/`postgis`, tag double `vX.Y.Z`+
  `latest`, `ghcr.io/tlenenao/geostudio-*`, `packages: write` scopée au
  seul job qui pousse) ; `CHANGELOG.md` (Keep a Changelog, entrée
  rétroactive `[0.1.0]` résumant M1→SP-9 gouvernance/légal) ; section
  « Release process » dans `CONTRIBUTING.md` (bump version manuel,
  déplacement `Unreleased`→version datée, tag+push, vérification
  `docker pull` réelle, pas de suppression de tag en cas d'échec —
  retag à la place). Exécuté en subagent-driven-development (5 tâches,
  revue par tâche + revue finale de branche modèle opus). 1 défaut trouvé
  et corrigé en cours de route (Task 3, revue) : la section CHANGELOG
  « Fixed » attribuait à tort 2 des 3 correctifs à des revues de branche
  SP-5→SP-8, alors qu'ils avaient été trouvés en SP-6b/SP-7 mais corrigés
  dans une session de debug dédiée hors-SP le 2026-07-13 — corrigé, re-revue
  clean. **Validation réelle effectuée** (pas seulement lecture de logs,
  confirmation utilisateur obtenue avant chaque push/tag) : push `dev` réel
  → 4 jobs CI verts dont le nouveau `shell` (36/36 E2E) ; dry-run d'un tag
  jetable `v0.1.0-rc1` contre `release.yml` — 1er essai a révélé un défaut
  réel (hors périmètre de cette sous-partie, dans `admin-collections.
  spec.ts` de SP-9-gestion-collections) : `test-gate` fusionne
  migrations+core+shell dans un seul job (contrairement au job `shell`
  isolé de `ci.yml`), et le conteneur `ci-postgres` restait démarré pendant
  l'étape Playwright — contention suffisante sur le runner GitHub partagé
  pour faire échouer déterministiquement (3/3, retries inclus) l'assertion
  finale de ce test (fenêtre de 5s pour fermeture de dialogue + refetch),
  sans rapport avec le code de cette sous-partie ; `build-and-push`
  correctement sauté (garde conforme au spec). Root-cause investigué
  (`/systematic-debugging`), fixé par une étape `docker rm -f ci-postgres`
  ciblée juste après "Core tests" dans `release.yml` (pas de modification
  du test lui-même, hors périmètre). Re-dry-run : pipeline complet vert,
  **3 images vérifiées par un `docker pull` réel** depuis
  `ghcr.io/tlenenao/geostudio-{core,shell,postgis}:v0.1.0-rc1`, tag jetable
  supprimé ensuite. **Point de vigilance non résolu, signalé à
  l'utilisateur** : le pattern `v*.*.*` matche aussi les pré-releases, donc
  ce dry-run a réellement déplacé le tag `:latest` de GHCR vers le build
  rc1 — à corriger en retaguant un `v0.1.0` réel prochainement (`:latest`
  s'auto-corrigera au prochain tag stable). Revue finale de branche : aucun
  Critical/Important, **Ready to merge: Yes** ; 2 autres Minor notés (garde
  `api-types-drift` intentionnellement absente de `test-gate`, cf. spec ;
  cette entrée CLAUDE.md elle-même attendue en commit séparé, désormais
  faite). **387 tests cœur, 466 tests shell, 36/36 specs E2E** — aucune
  régression (validé par CI réelle, pas seulement en local). Poussé sur
  `dev`. Les 3 autres sous-parties de SP-9 (install/secrets, sécurité
  minimale, démo lecture seule) restent à planifier et exécuter — specs
  déjà écrites, cf. plus haut.
- **SP-9 « install & secrets » livré et clos** (2026-07-16, sous-partie de
  SP-9, cf. spec `2026-07-15-sp9-install-secrets-design.md` et plan
  `2026-07-16-sp9-install-secrets.md`) : `git clone` + un unique script de
  bootstrap + `docker compose up -d` produit désormais une installation
  fonctionnelle, sans étape manuelle oubliable et sans secret faible.
  `scripts/bootstrap-env.sh` (racine, nouveau) génère `.env` depuis
  `.env.example` avec 4 secrets alphanumériques forts (`PG_PASSWORD`,
  `MINIO_PASSWORD`, `KC_PASSWORD`, `MARTIN_SECRET` — `openssl rand`, jamais
  de `@`/`:`/`/` qui casserait un DSN Postgres), n'écrase jamais un `.env`
  existant ; `core/Dockerfile` embarque désormais `alembic/`, `alembic.ini`
  et `scripts/` (absents jusqu'ici de l'image — gap réel découvert en
  écrivant le plan, pas seulement supposé par la spec) et le service `core`
  du compose enchaîne `alembic upgrade head && uvicorn …` à chaque
  démarrage de conteneur (idempotent, même patron que le `worker`
  existant) — la migration manuelle documentée jusqu'ici comme une étape
  séparée dans le README disparaît. Exécuté en subagent-driven-development
  (3 tâches, revue par tâche + revue finale de branche modèle opus), les 3
  tâches et la revue finale toutes clean (0 Critical/Important). Un vrai
  piège découvert et documenté au passage (Task 3) : `seed_demo.py` exige
  un admin déjà existant (`SystemExit` sinon) — en mode `mock`, `mockuser`
  n'est promu admin qu'à la **première requête authentifiée**, jamais par
  un `curl` anonyme ; le README documente maintenant explicitement ce
  prérequis plutôt que de laisser la commande de seed échouer sur une
  install vraiment neuve. Test de bout en bout réel effectué contre un
  volume Postgres vraiment neuf (13 migrations 0001→0013 appliquées
  automatiquement, `GET /me` anonyme → 401 pas 500, bootstrap admin mock,
  `seed_demo` idempotent, `docker compose restart core` → migration no-op
  confirmée) — les 4 critères d'acceptation du spec §6 vérifiés
  empiriquement, pas seulement asserés ; déviation assumée du `docker
  compose down -v` littéral du plan (bloqué par le classifieur de
  permissions du harness, protection d'un volume de dev pré-existant) vers
  un projet compose isolé (`COMPOSE_PROJECT_NAME`), jugée preuve
  strictement plus forte par les deux revues. 1 Minor réel trouvé en revue
  finale et corrigé dans la foulée (commit séparé) : `CONTRIBUTING.md`
  pointait encore vers l'ancien flux `cp .env.example .env` (secrets
  faibles) et vers une phrase « planned... SP-9 sub-part » désormais fausse
  puisque cette sous-partie est justement celle-là — resynchronisé avec le
  README. **387 tests cœur passed/64 skipped, 466 tests shell, 36/36 specs
  E2E** — aucune régression (aucun de ces trois changements ne touche du
  code applicatif Python/TS). Poussé sur `dev`. Les 2 autres sous-parties
  de SP-9 (sécurité minimale, démo lecture seule) restent à planifier et
  exécuter — specs déjà écrites, cf. plus haut.
- **SP-9 « sécurité minimale » livré et clos** (2026-07-16, sous-partie de
  SP-9, cf. spec `2026-07-15-sp9-securite-minimale-design.md` et plan
  `2026-07-16-sp9-securite-minimale.md`) : ingress Traefik réellement câblé
  (jusqu'ici les labels `traefik.*` n'existaient sur aucun service malgré le
  service `traefik` déjà présent dans le compose) — `core`/`shell` routés
  par `Host(${DOMAIN})` (`core` en plus sur `PathPrefix(/api)`, priorité
  explicite 10 > 1, `strip-api` retire le préfixe avant le cœur), middleware
  d'en-têtes de sécurité partagé (HSTS, `nosniff`, `frameDeny`,
  `referrer-policy`) et de rate limiting (average=100/burst=200) définis une
  fois sur `core` et référencés `@docker` par les deux routers,
  `--api.dashboard=true`/`--api.insecure=true` et le port `8090:8080`
  retirés (dashboard non authentifié qui était exposé publiquement).
  **Revue authz complète** : les 48 endpoints REST + 11 outils MCP audités
  contre la couverture de test réelle (~25 fichiers, périmètre plus large
  que les 8 fichiers illustratifs cités par la feuille de route) —
  **0 trou de sécurité réel trouvé**, 9 trous de couverture comblés (tests
  ajoutés dans les fichiers existants les plus proches, jamais de nouveau
  fichier), rapport complet dans
  `docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md`.
  **Audit de dépendances en CI** : jobs `core-deps-audit` (`pip-audit`,
  bloquant sur toute vulnérabilité connue — `pip-audit` n'a pas de filtre de
  sévérité natif, déviation assumée du "High/Critical seulement" demandé)
  et `shell-deps-audit` (`npm audit --audit-level=high` derrière
  `shell/scripts/check-npm-audit.mjs`, un filtre accepted-risk nécessaire
  car une vraie vulnérabilité High préexistante et sans correctif upstream
  — `lodash-es` via `cel-js`→`chevrotain`, arbitrage SP-5a — aurait sinon
  cassé la CI immédiatement). Exécuté en subagent-driven-development (4
  tâches, revue par tâche + revue finale de branche modèle opus). **1
  Important trouvé en revue et corrigé** (Task 4) : `ALLOWLIST[pkg]` était
  un lookup d'objet brut vulnérable aux propriétés héritées
  d'`Object.prototype` — un paquet réellement nommé `constructor` (publié
  sur npm, vérifié) contournait silencieusement le gate ; corrigé par
  `Object.prototype.hasOwnProperty.call(ALLOWLIST, pkg)`. **Les deux jobs
  vérifiés bloquants sur un vrai run CI**, pas seulement en local : deux
  dry-runs réels (PR jetables non fusionnées, `ci.yml` ne déclenchant que
  sur push vers `main`/`dev` ou `pull_request` — un push nu vers une branche
  jetable ne suffit pas, découverte faite en exécutant) — `pyjwt==2.4.0`
  fait échouer `core-deps-audit` (9 vulnérabilités connues), `minimist@1.2.5`
  fait échouer `shell-deps-audit` (`critical`, non allowlisté) ; les deux PR
  fermées sans fusion et branches supprimées immédiatement après. Revue
  finale de branche : **Ready to merge: Yes**, aucun Critical/Important, 5
  Minor non bloquants (coquille "44" vs 48 endpoints dans la prose d'un
  rapport ; couplage `shell`→middlewares définis sur `core`, acceptable pour
  un déploiement stack complète ; `check-npm-audit.mjs` fail-open si la clé
  `vulnerabilities` est absente d'un rapport malformé ; pas de redirection
  `web`→`websecure`, hors périmètre explicite ; pas de re-run Vitest/
  Playwright, diff ne touchant aucun code applicatif shell). **395 tests
  cœur passed/65 skipped** (460 passed/0 skipped validé contre un
  PostGIS+pgvector jetable réel), **lint-imports clean**, **6/6 jobs CI
  verts sur `dev`** (les 4 existants + les 2 nouveaux). Poussé sur `dev`.
- **SP-9 « démo lecture seule » livré et clos** (2026-07-16, dernière
  sous-partie de SP-9 — **SP-9 est intégralement clos**, cf. spec
  `2026-07-15-sp9-demo-lecture-seule-design.md` et plan
  `2026-07-16-sp9-demo-lecture-seule.md`) : un déploiement démarré avec
  `CORE_READ_ONLY_MODE=true` refuse toute écriture (REST et MCP, tout
  utilisateur y compris admin) sans affecter la lecture ; le shell l'affiche
  (bannière) et masque en fail-open les actions d'écriture déjà identifiées
  (Formulaire, dialogues admin collections, page admin extensions) — la
  frontière réelle reste le 403 serveur. Cœur : `is_read_only_mode()`
  (`app/auth/dependency.py`), **un seul point d'interception** — middleware
  ASGI dans `app/main.py` qui 403 toute requête `POST`/`PUT`/`PATCH`/`DELETE`
  (hors `/mcp`) avant même le routing FastAPI, indépendant de l'utilisateur —
  plus une garde identique (`ValueError`) en tête des 4 outils MCP d'écriture
  (`save_app_config`, `create_item`, `create_form_app`, `set_sharing`), même
  message exact partout. Nouvel endpoint public `GET /instance` →
  `{"readOnly": bool}`. Shell : `useInstanceInfo()` (react-query, fail-open —
  jamais de faux positif `readOnly:true` sur panne réseau), consommé
  directement par chaque composant d'écriture (pas via `WidgetContext`/
  `WidgetHost`, qui reste sans `QueryClientProvider` dans ses tests),
  bannière `AppLayout`. Exécuté en subagent-driven-development (6 tâches,
  revue par tâche + revue finale de branche modèle opus, toutes clean, 0
  Critical/Important sur l'ensemble). Revue finale : **Ready to merge:
  Yes** ; 3 Minor non bloquants, tous des décisions de scope du plan plutôt
  que des défauts d'exécution — les boutons d'en-tête (`NewItemButton`/
  `ImportFileButton`) et le Save du builder/`ShareDialog` d'item ne sont pas
  masqués en mode démo (le 403 serveur les couvre déjà, mais l'UX reste
  incohérente pour une démo publique soignée, suivi optionnel) ; assertion
  MCP `in` plutôt que `==` sur le message (le SDK MCP enveloppe potentiellement
  le `ValueError`) ; message dupliqué en 6 littéraux + 3 constantes de test
  sans constante partagée, prescrit tel quel par le plan. **410 tests cœur
  passed/65 skipped** (395+9+6), **475 tests shell** (466+4+1+4), **37/37
  specs E2E** (36+1). Poussé sur `dev`. **SP-9 (durcissement produit public
  v0.1, 6 sous-parties : gestion-collections, gouvernance-légale,
  ci-publique-release, install-secrets, sécurité-minimale, démo-lecture-seule)
  est intégralement clos.**
- **SP-10a livré et clos** (2026-07-17, cf. spec
  `docs/superpowers/specs/2026-07-16-sp10a-instrumentation-otel-design.md`
  et plan `docs/superpowers/plans/2026-07-16-sp10a-instrumentation-otel.md`) :
  instrumentation OTel du cœur et du worker — un déploiement pointant
  `OTEL_EXPORTER_OTLP_ENDPOINT` vers un collecteur obtient traces, métriques
  et logs JSON corrélés bout-en-bout, comportement inchangé quand la
  variable est absente (défaut de `docker compose up` et de toute la suite
  de tests). `core/app/observability.py` (nouveau module) : `setup()`
  idempotent (providers traces/métriques, `logging.setLogRecordFactory()`
  pour corréler trace_id/span_id dans les logs JSON), auto-instrumentation
  FastAPI/SQLAlchemy/httpx/botocore, spans procrastinate par job
  (`worker_middleware`, exceptions enregistrées puis re-levées, jamais
  avalées). 3 métriques métier : `geostudio.items.created`/`geostudio.
  configs.published` dans `app/items/repository.py` (comptées aussi côté
  MCP, mêmes fonctions partagées que REST, cf. SP-2/SP-7) ;
  `geostudio.apps.runtime_executions` dans `app/configs/routes.py` (seule
  exception route-level, pilotée par `GET /configs/by-item/{id}?mode=
  runtime`, câblé jusqu'au shell — `AppRuntimePage` seul appelant, builder/
  éditeur non affecté). Protocole OTLP fixé HTTP/protobuf en dur (pas de
  dépendance grpcio) ; aucun changement `docker-compose.yml` dans cette
  sous-partie (SP-10b câblera le profil `--profile observability`).
  Exécuté en subagent-driven-development (6 tâches, revue par tâche + revue
  finale de branche modèle opus). Trois défauts de bibliothèque légitimes
  trouvés et corrigés en cours de route (pas des erreurs d'implémentation,
  des tests littéraux du plan qui ne survivaient pas à la réalité d'une
  suite de 400+ tests) : (1) le test du brief pour `JSONFormatter`
  formatait un log après la fin du span actif — premier essai par
  monkeypatch global et inconditionnel de `logging.Handler.handle` (effet
  de bord process-wide dès l'import), jugé Important en revue de tâche et
  remplacé par `logging.setLogRecordFactory()` posé dans `setup()` (gated
  par `_configured`) ; (2) `SQLAlchemyInstrumentor` est un singleton
  process-wide (`BaseInstrumentor.__new__`) — le premier `create_app()` de
  la suite fige son flag "instrumenté", tout appel ultérieur (dont celui du
  test dédié) devenant un no-op silencieux ; fixé en isolant ce test dans
  un sous-processus frais (même motif déjà utilisé par le Task 3 pour
  httpx/botocore, juste pas appliqué par le plan à ce test précis) ; (3)
  découvert à la vérification finale (Task 7, E2E complet) : le mock
  `configs/by-item` de `shell/e2e/mocks.ts` extrayait l'id via
  `url().split("/").pop()`, cassé par le nouveau `?mode=runtime` (11 specs
  E2E en échec, fixture attendue jamais servie) — fixé en retirant la query
  string avant extraction. **Revue finale de branche : 1 Important trouvé
  et corrigé** — le worker réel (`docker-compose.yml`, `python -m
  procrastinate --app app.jobs.app worker`) n'importe jamais `app.main`/
  `create_app()`, donc `observability.setup()` n'y tournait jamais : aucun
  exportateur OTLP installé côté worker, spans de job créés contre un
  tracer proxy no-op jamais exportés, métriques d'ingestion jamais
  envoyées — alors que le but explicite du plan est d'instrumenter
  « core/worker », pas seulement le process API. Aucun test de tâche ne
  pouvait le détecter (le test de la Task 4 injecte son propre
  `tracer_provider`). Fixé en appelant `observability.setup()` au niveau
  module dans `core/app/jobs.py` (seul point d'entrée réellement exécuté
  par le worker), idempotent donc sans risque en co-location avec
  `create_app()`. Fumée manuelle réalisée contre un vrai collecteur
  (`grafana/otel-lgtm` jetable, port OTLP seul publié pour contourner un
  conflit de port-forwarding WSL2 sur le port Grafana) : `GET /health`
  confirmé produire un trace réel `service.name="geostudio-core-smoke"`,
  requêté via l'API search de Tempo — export OTLP bout-en-bout vérifié
  contre un vrai collecteur, pas seulement des exporteurs en mémoire. 4
  Minor non bloquants notés en revue finale, aucun corrigé : nom de
  métrique `geostudio.configs.published` incohérent avec `items.created`
  (mandaté littéralement par le texte du plan §Global Constraints, donc
  non renommé unilatéralement — à reconsidérer avec l'utilisateur avant que
  SP-10b construise des dashboards dessus) ; `_items_published_counter`
  incrémenté avant `session.flush()` contrairement à `_items_created_counter`
  (après) ; docstring "zéro appel réseau" toujours légèrement imprécis
  cumulativement (httpx/botocore injectent des en-têtes de propagation même
  sans exportateur, déjà noté au Task 3) ; idiome `split("/").pop()`
  fragile aux query strings ailleurs dans `mocks.ts`, non déclenché
  actuellement. **422 tests cœur passed/65 skipped** (410+5+1+1+2+2+1),
  **477 tests shell** (475+2), **37/37 specs E2E**. Poussé sur `dev`.
  **SP-10a est clos.**
- **SP-10b livré et clos** (2026-07-17, cf. spec
  `docs/superpowers/specs/2026-07-17-sp10b-observabilite-dashboards-slo-design.md`
  et plan `docs/superpowers/plans/2026-07-17-sp10b-observabilite-dashboards-slo.md`) :
  observabilité packagée — un opérateur qui lance `docker compose --profile
  observability up` obtient 4 dashboards Grafana (cœur, Martin, jobs,
  Postgres) alimentés en données réelles, 4 SLO visibles dans Grafana
  Alerting, et peut déclencher une alerte de test de façon reproductible,
  sans rien changer à un `docker compose up` classique. Service
  `otel-lgtm` (Prometheus/Loki/Tempo/Grafana packagés, port hôte Grafana
  `3001` — `3000` déjà pris par `martin`) + `postgres-exporter`, tous deux
  `profiles: ["observability"]` ; `core`/`worker` gagnent un export OTLP
  inconditionnel (`http://otel-lgtm:4318`, sans risque si non démarré —
  vérifié empiriquement, `/health` reste rapide) ; `martin` bascule en
  `v0.18.0` (seule version exposant `/_/metrics`, `v0.13.0` ne l'expose
  pas). Config du collecteur OTel étendue (scrape Prometheus de
  `martin`/`postgres-exporter`, receiver nommé `prometheus/geostudio`).
  Nouveau `geostudio.jobs.backlog` (`ObservableGauge`, compte les jobs
  procrastinate `todo`/`doing` par file, `unit=""` — pas `"1"` — pour éviter
  le suffixe `_ratio` de la convention de nommage OTel→Prometheus). 4
  dashboards provisionnés par fichiers (Martin : 3 panneaux seulement, pas
  de cache-hit, métrique inexistante côté Martin) + 5 règles d'alerte
  Grafana (4 SLO réels + 1 règle de test toujours vraie, `isPaused: true`
  par défaut — preuve reproductible que le pipeline d'alerting fonctionne,
  jamais active en continu). Plan écrit avec 8 corrections empiriques
  documentées vs la spec initiale (version Martin, absence de cache-hit,
  nom du datasource Prometheus embarqué, layout de montage des dashboards
  Grafana — provider au niveau racine, JSON dans un sous-dossier séparé —,
  port Grafana, suffixe `_ratio`, colonne `queue_name` vs `queue`,
  non-idempotence de `apply_schema()`). Exécuté en
  subagent-driven-development (6 tâches, revue par tâche + revue finale de
  branche modèle opus). Aucun défaut Critical/Important sur les 6 tâches ni
  en revue finale — seuls des Minor cosmétiques/défensifs, 2 corrigés dans
  la foulée (coquille accentuée `géostudio_jobs_backlog` dans un docstring,
  garde `try/except` sur le callback de la gauge si `procrastinate_jobs`
  n'existe pas encore — pertinent car l'export OTLP est désormais
  inconditionnel). **Task 6 (validation empirique bout en bout contre la
  vraie stack) a confirmé les 5 critères d'acceptation** : dashboards
  alimentés (vérifié aussi en insérant une ligne de test dans
  `procrastinate_jobs`), traçage bout en bout avec spans SQL sous HTTP
  (`trace_id` réel documenté), 4 SLO visibles et évalués, alerte de test
  dépausée temporairement puis observée `firing` (fichier reverté avant
  commit), `docker compose up` par défaut inchangé. **Point de suivi
  hors-périmètre signalé, non corrigé par cette branche** : le service
  `worker` entre en boucle de redémarrage après un premier succès sous le
  profil observability (`schema --apply && worker` non idempotent une fois
  les types procrastinate créés) — vérifié par `git log -p` comme
  pré-existant depuis SP-6a/SP-7, non touché par SP-10b
  (`register_jobs_backlog_gauge` vit uniquement dans `app.main`, jamais
  dans `app.jobs`) ; n'affecte aucun des 5 critères d'acceptation, mais un
  déploiement réel laissé longtemps up pourrait perdre silencieusement son
  worker d'ingestion après ce premier crash — à traiter dans une session
  dédiée. **422 tests cœur passed/66 skipped** (422+1 nouveau test postgis
  skippé sans DB, 488 passed avec DB réelle), `lint-imports` clean. Poussé
  sur `dev`.
- **SP-11a livré et clos** (2026-07-17/18, cf. spec
  `docs/superpowers/specs/2026-07-17-sp11a-spike-cdc-geoparquet-design.md`
  et plan `docs/superpowers/plans/2026-07-17-sp11a-spike-cdc-geoparquet.md`) :
  spike CDC + pipeline de réplication PostgreSQL → GeoParquet — un nouveau
  service `cdc-worker` (connexion directe `postgis`, jamais pgbouncer)
  réplique en continu les écritures de toute collection enregistrée vers
  `s3://<bucket>/cdc/tenant_id=.../collection_id=.../dt=.../part-*.parquet`
  via réplication logique Postgres (`wal2json`, gate A18/A27 franchi
  empiriquement — spike réel 8/8 checks contre un PostGIS jetable
  reconstruit avec `wal2json`). `core/app/cdc/` : `parquet_writer.py`
  (écriture GeoParquet géré par geopandas/pyarrow, tombstone PK-seule sur
  delete), `storage.py` (S3), `buffer.py` (bufferisation par table,
  `safe_ack_lsn` re-dérivé indépendamment en revue — borné par le pending
  le plus ancien tous tableaux confondus), `consumer.py` (décodage
  wal2json, feedback de réplication via `cur.wal_end` — jamais `msg.
  data_start`, déviation empirique critique trouvée par le spike), `backfill.py`
  (backfill paresseux d'une collection tardive, normalisation Decimal/date/
  timestamp/UUID→types natifs pour éviter un crash PyArrow), `main.py`
  (assemblage, gauge `geostudio.cdc.lag_seconds` par collection). Publication
  logique Postgres gérée par `app/collections/publication.py`, câblée à
  l'enregistrement/désenregistrement d'une collection. Exécuté en
  subagent-driven-development (11 tâches, revue par tâche + revue finale de
  branche modèle opus). **1 FAIL réel trouvé en validation empirique finale
  (Task 11, critère 3 : redémarrage sans perte après kill -9)**, corrigé en 3
  commits revus (`c8d8289`/`448f50f`/`171f5dd`) : mélange `Decimal`(backfill)/
  `float`(flux live) pour une colonne NUMERIC dans un même batch de flush →
  crash PyArrow **permanent** (violait la garantie at-least-once) — généralisé
  au passage à DATE/TIMESTAMP/UUID (`_pg_timestamp_str` reproduit le format
  texte natif Postgres, troncature des zéros de fin des microsecondes).
  Re-validation empirique finale : 5/5 critères PASS (écriture visible <5min,
  collection tardive backfillée et suivie, redémarrage sans perte, gauge par
  collection, `docker compose up` par défaut inchangé), 37/37 specs E2E.
  **449 tests cœur passed/76 skipped** (512 avec DB réelle), lint-imports
  clean. **Défaut pré-existant signalé, non corrigé** : le volume `pg-data`
  du projet compose par défaut est cassé (`alembic_version` jamais stampée) —
  réparation non destructive hors périmètre de cette branche. Poussé sur
  `dev`.
- **SP-11b livré et clos** (2026-07-18, cf. spec
  `docs/superpowers/specs/2026-07-17-sp11b-compaction-analytique-duckdb-design.md`
  et plan `docs/superpowers/plans/2026-07-18-sp11b-compaction-analytique-duckdb.md`) :
  compaction GeoParquet + module analytique DuckDB — un widget Graphique/
  Indicateur agrège désormais les données d'une collection via une nouvelle
  API du cœur (`POST /collections/{id}/aggregate`, DuckDB in-process
  interrogeant le GeoParquet CDC de SP-11a) au lieu de fetcher les features
  brutes et d'agréger côté client, pendant qu'un job de compaction périodique
  réduit le nombre de fichiers Parquet par partition. Deux pièces
  indépendantes ne partageant que le layout S3 de SP-11a : (1) job
  procrastinate périodique (nouvelle queue `cdc`, tourne dans le process
  `worker` existant — jamais `cdc-worker`, occupé par la boucle de
  réplication bloquante), `core/app/cdc/compaction.py` fusionne les petits
  fichiers d'une partition en un seul, toujours écriture-avant-suppression
  (sûreté à l'interruption re-dérivée indépendamment en revue — un crash
  entre les deux laisse des doublons inoffensifs, jamais de perte), jamais
  de déduplication/suppression de tombstone à l'écriture (la sémantique du
  change-log reste inchangée) ; (2) nouveau domaine `core/app/analytics/`
  (aucune dépendance à `app.cdc`) : connexion DuckDB in-process éphémère par
  requête (`httpfs`+`spatial`), `run_collection_aggregate` réduit à l'état
  courant par fenêtre SQL (`QUALIFY row_number() ... = 1`, tombstone exclue,
  dans cet ordre avant tout filtre/group-by), noms de colonnes validés
  contre le schéma introspecté avant toute interpolation SQL (même
  frontière de confiance que `_where` pour `GET /items`), coercion
  numérique `TRY_CAST(...AS DOUBLE)`+`COALESCE(...,0)`. Shell :
  `queryDataSource` (source `statistics`) appelle le nouvel endpoint au
  lieu d'agréger côté client — `aggregateRecords`/`reduceValues`/
  `measureLabel` supprimés (code mort, aucun compat shim). Exécuté en
  subagent-driven-development (11 tâches, revue par tâche + revue finale de
  branche modèle opus). **Déviation empirique critique du spike d'ouverture
  (Task 1, gate bloquante)** : l'incantation bbox présumée par le plan
  (`ST_GeomFromWKB(...)`) ne fonctionne PAS contre un GeoParquet réel écrit
  par geopandas — l'incantation retenue est la lecture directe de la
  colonne géométrie comme `GEOMETRY` natif (DuckDB `spatial` la reconnaît
  nativement) ; appliquée proactivement en Task 6, reproduite
  indépendamment en revue (`ST_GeomFromWKB` sur une colonne déjà `GEOMETRY`
  lève `BinderException`). **Revue finale de branche : 1 Important trouvé
  et corrigé** (fix `fca6adb`, re-revue clean) : les extensions DuckDB
  `httpfs`/`spatial` n'étaient pas embarquées dans l'image au build (le
  docstring de `duckdb_conn.py` l'affirmait à tort) — un conteneur
  fraîchement démarré aurait déclenché un `INSTALL` réseau vers
  `extensions.duckdb.org` au premier `POST .../aggregate`, cassant
  silencieusement tout widget Graphique/Indicateur en déploiement à égress
  restreint ; corrigé par une étape `RUN` dédiée dans `core/Dockerfile`
  juste après l'installation des paquets Python, vérifié empiriquement à
  deux reprises indépendantes (conteneur réel lancé avec `--network none`,
  extensions chargées avec succès hors-ligne). Script de performance réel
  contre un scénario multi-fichiers réaliste (900k lignes backfill + 200
  lots incrémentaux de 500 lignes = 1M lignes/201 fichiers) : **~0.28s
  avant compaction, ~0.13s après**, très sous le budget de 2s. **482 tests
  cœur passed/80 skipped**, lint-imports clean, **477 tests shell** + tsc/
  build clean, **37/37 specs E2E**. 4 Minor notés en revue finale, non
  corrigés (déjà tracés/acceptés depuis la revue de Task 6 : validation
  `agg` invalide sur collection vide retourne `[]` au lieu de 400, sans
  risque de sécurité ; construction du glob dupliquée entre deux fonctions ;
  agrégats numériques sérialisés en float même pour des sommes entières ;
  test de sûreté à l'interruption vérifié via un helper pandas plutôt que
  la vraie requête DuckDB `QUALIFY`, logiquement équivalent ici). Poussé
  sur `dev`.
- **SP-11c livré et clos** (2026-07-18, cf. spec
  `docs/superpowers/specs/2026-07-18-sp11c-sql-analyste-sandbox-design.md` et
  plan `docs/superpowers/plans/2026-07-18-sp11c-sql-analyste-sandbox.md`) :
  endpoint SQL analyste read-only sandboxé — **clôt SP-11**. Un utilisateur
  porteur du nouveau rôle *analyste* (`users.is_analyst`, migration 0014,
  bootstrap `CORE_ANALYST_SUBS`, `PATCH /users {isAnalyst}`, `GET /me`,
  **admin ≠ analyste** : capacités distinctes, un admin non-analyste reçoit
  aussi 403) exécute du SQL read-only via `POST /analytics/sql` sur les
  collections qu'il a le droit de lire — chacune exposée comme une vue DuckDB
  déjà réduite à l'état courant sur le GeoParquet CDC (réutilise
  `_dedup_cte`/`_qi`/`_has_any_file` de SP-11b). **La frontière de sécurité
  est DuckDB, pas un parseur maison** : par requête, une connexion DuckDB
  éphémère **matérialise en tables temporaires les seules vues référencées ∩
  autorisées** (accès externe encore ouvert), **puis verrouille la connexion**
  (`SET enable_external_access=false; SET lock_configuration=true`) de sorte
  que DuckDB refuse tout accès fichier/S3/`ATTACH`/`LOAD`/`COPY`/`read_parquet`
  arbitraire à l'exécution du SQL analyste ; l'extraction d'AST natif
  (`json_serialize_sql`) sert seulement à rejeter tôt le non-SELECT et à
  choisir quoi matérialiser (jamais load-bearing pour la sécurité). Requête
  bornée (timeout 10s via `threading.Timer`+`conn.interrupt`, plafond 10 000
  lignes, `memory_limit=512MB`, `threads=2`), périmètre = `list_visible_
  collections` (même surface que `GET /items`), `tenant_id` toujours du
  principal authentifié (jamais du body), exemptée du middleware read-only/
  démo (c'est une lecture, exemption exacte `!=` non sur-large), auditée et
  comptée (`geostudio.analytics.sql_queries`, attribut `outcome`). Cœur only
  (pas de MCP, conforme spec). Exécuté en subagent-driven-development (10
  tâches + 1 fix post-revue, revue par tâche + revue finale de branche modèle
  opus). **Spike d'ouverture GATE (Task 1)** validé empiriquement contre MinIO
  réel (GO 10/10, dont les 7 cas d'abus bloqués incl. la ré-tentative de
  re-`SET` après verrouillage). **Découverte empirique répercutée sur tout le
  code (Tasks 7/8)** : `duckdb.Exception` N'EXISTE PAS en DuckDB 1.5.4 — la
  vraie classe de base est `duckdb.Error` (le code présumé du plan aurait levé
  `AttributeError` au runtime). **Revue finale de branche : 0 Critical/
  Important**, invariant de sécurité tracé bout-en-bout sous traçage
  adversarial (lecture cross-tenant, `read_parquet` arbitraire = TABLE_FUNCTION
  jamais matérialisé et bloqué par le lock via `PermissionException` APRÈS le
  verrouillage, shadowing de CTE confirmé leak-free, non-SELECT, admin-non-
  analyste, anonyme→401) ; **1 Minor corrigé sur décision utilisateur** (fix
  5ae2db8, re-revue clean) : l'audit + le compteur ne se déclenchaient qu'au
  succès — désormais les tentatives **rejetées** (SqlSandboxError→400) sont
  auditées aussi, l'audit d'échec `commit()`é explicitement sur la session de
  requête avant le raise (le `request_scoped_session` rollback sinon la trace ;
  seule écriture en attente sur ce chemin read-only, rollback ultérieur =
  no-op). 3 Minor différés en suivi non bloquant (introspection N par requête
  au lieu de `refs ∩ visible-ids` ; robustesse `_coerce` sur géométrie brute
  non wrappée `ST_AsText` → 500 possible, pas de fuite ; re-fetch `patch_user`).
  **Perf empirique réelle contre MinIO** : requête analyste ~0.5-1.0s sur
  ~992 500 lignes réparties sur 201 fichiers Parquet (10-20x sous le budget de
  10s). **510 tests cœur passed/80 skipped** (sans DB ; **589 passed/0 skipped
  contre PostGIS+pgvector+wal2json réel**), lint-imports clean, **477 tests
  shell** + build/tsc clean, **37/37 specs E2E** (aucune UI ajoutée, forme de
  `GET /me` élargie sans régression). Poussé sur `dev`, PR dev→main ouverte
  pour synchroniser `main` (qui n'avait pas encore SP-11a/b/c). **SP-11
  (lakehouse : CDC→GeoParquet, compaction+DuckDB analytique, SQL analyste
  sandboxé) est intégralement clos.**
- **Storytelling (mode narratif sur `PageManager`) livré et clos** (2026-07-18,
  cf. plan `docs/superpowers/plans/2026-07-18-storytelling-pagemanager.md`) :
  un auteur active un mode « story » sur une app existante, associe à chaque
  page/chapitre une action de navigation (`map.flyTo` vers une emprise
  statique), et obtient une narration séquencée (barre de progression +
  Précédent/Suivant) — sans nouveau widget, sans nouveau backend, sans code.
  Shell quasi exclusivement : `AppConfig.navigationMode?: "tabs" | "story"`
  (défaut `"tabs"`) et `Page.onEnter?: ActionMessage[]` (déclenchés à l'entrée
  du chapitre via le `ActionBus` existant, `ActionMessage` gagne un
  `payload?` statique pour l'emprise cible — un chapitre n'a pas d'émetteur
  runtime). `AppRenderer` rend la barre de story et dispatche les `onEnter`
  de la page active en preview/runtime (jamais en edit, jamais en mode
  `tabs` — gate unique `storyMode`). Nouveau panneau `NavigationPanel` dans
  le builder (déviation assumée du spec initial : **pas** une réutilisation
  d'`ActionsPanel`, qui est centré émetteur — incompatible avec un
  émetteur-page), `getConfigExpressionErrors` valide aussi les conditions
  `when` des `onEnter` (bouton Enregistrer désactivé si invalide), gabarit de
  galerie « Story cartographique » (3 chapitres texte+carte+flyTo). Seul
  changement cœur : déclaration Pydantic des 3 nouveaux champs dans
  `core/app/configs/schemas.py`, round-trip testé explicitement pour éviter
  de répéter la régression silencieuse de SP-5b (champ non déclaré supprimé
  par `model_validate`/`model_dump`). Exécuté en subagent-driven-development
  (7 tâches, revue par tâche + revue finale de branche modèle opus, 0
  Critical/Important sur les 7 tâches et en revue finale). **1 Important
  trouvé et corrigé** (Task 5) : `NavigationPanel.add()` acceptait
  Longitude/Latitude vides (`Number("")===0`, pas `NaN`) et posait
  silencieusement `payload:{center:[0,0]}` — fix + 3 tests de régression,
  re-revue clean. **1 vrai bug applicatif trouvé et corrigé en Task 7**, hors
  périmètre anticipé du brief E2E : `itemClient.ts`
  `getAppConfig`/`saveAppConfig` reconstruisaient le config champ par champ
  et omettaient `navigationMode`, perdu silencieusement à tout GET/PUT réel
  malgré le reste de la pile (types, `NavigationPanel`, gabarit) le posant
  correctement — même classe de bug que la régression `visibleWhen` SP-5b,
  cette fois côté TS ; seule l'E2E réelle l'a détecté (`Received:"tabs"` au
  lieu de `"story"`), aucun test unitaire de tâche ne le couvrait. Fix
  symétrique GET+PUT ; revue finale a vérifié indépendamment (chasse
  adversariale dédiée) que les 8 champs d'`AppConfig` sont désormais tous
  round-trippés symétriquement — pas seulement celui qui a révélé le bug.
  **Dérive OpenAPI détectée et corrigée après les 7 tâches** (commit
  bca3f61) : contrairement à la spéculation du plan, `BuilderConfig`/`Page`/
  `Message` sont des modèles Pydantic typés exposés par le schéma FastAPI —
  `core/openapi.json`/`core-schema.d.ts` régénérés. Revue finale de branche :
  **Ready to merge: Yes**, 0 Critical/Important, 3 Minor non bloquants (SPDX
  incohérent sur le seul fichier `shell/e2e/*.spec.ts` qui en a un ;
  restructuration DOM inconditionnelle d'`AppRenderer`, visuellement
  équivalente, sans régression observée ; `navigationMode` typé requis par
  openapi-typescript malgré son défaut Pydantic, quirk pré-existant inerte).
  **515 tests cœur passed/80 skipped** (sans DB), **497 tests shell**,
  build/tsc clean, **38/38 specs E2E** (37 + `storytelling.spec.ts`). Poussé
  sur `dev`.
- **SP-16a « modèle site/slug + route publique + résolution shell » livré et
  clos** (2026-07-18, première sous-phase de SP-16 « Portails & Sites », cf. spec
  `docs/superpowers/specs/2026-07-16-sp16a-modele-site-slug-design.md` et plan
  `docs/superpowers/plans/2026-07-18-sp16a-modele-site-slug.md`) : un admin/
  utilisateur crée un item de type `site` (slug auto-généré depuis le titre,
  éditable, validé), le publie, et un visiteur **anonyme** le consulte à
  `/sites/{slug}` qui rend `AppRenderer(config, "runtime")`. **Aucun nouveau
  chemin d'autorisation** : un `site` est un item ordinaire (`can()`, politique
  de publication SP-1c, `audit_log`). Cœur : helpers de slug purs
  (`app/items/slug.py` — `slugify`/`is_valid_slug`, format
  `^[a-z0-9]+(?:-[a-z0-9]+)*$` ≤100, repli `site`), colonne `items.slug` +
  **index unique partiel `(tenant_id, slug) WHERE slug IS NOT NULL`** (migration
  0015, unicité **par tenant** — deux tenants peuvent porter le même slug),
  génération à la création (collision implicite → suffixe silencieux ; collision
  explicite → 409 ; format invalide → 422, mêmes gardes en création via `POST
  /configs kind=site` et en édition via `PATCH /items {slug}`), `ItemRead.slug`
  sérialisé, `GET /public/sites/{slug}` **404 jamais 403** (non-publié/inexistant/
  autre-tenant/non-site — pas de fuite d'existence), tenant public résolu à
  `"default"` seulement (A33). Shell : `getItemBySlug`/`getPublicAppConfig`
  (miroir exact de `getAppConfig`, unwrap du wrapper `ConfigRead.config`),
  `slugify` client (**écho documenté du serveur, PAS une frontière** — le serveur
  reste l'autorité 409/422, même arbitrage que CEL/A8), page publique
  `SitePublicPage` sur route `/sites/:slug` **hors `ProtectedLayout`** (widgets
  builtin uniquement — pas d'extensions, évite le délai fail-open ~5-7s), type
  « Site » dans `NewItemButton` (champ slug auto-suivi du titre, éditable, validé,
  Créer désactivé si invalide). Exécuté en subagent-driven-development (10 tâches,
  revue par tâche + revue finale de branche modèle opus). Plusieurs hypothèses du
  plan corrigées à l'exécution (documentées, non des défauts de code) : la
  migration ne doit PAS utiliser `schema="app"` (aucune migration du dépôt n'en
  utilise) ; les fixtures de test route du plan (`client_admin`/`pg_session`/
  `seed_tenant_user`, répertoires `tests/configs|items|public/`) n'existent pas —
  tests écrits plats dans `core/tests/` sur le vrai patron SQLite `client()`/
  `session`/`tenant_and_user` (logique slug = SELECT pur, fidèle et always-run) ;
  le test `getPublicAppConfig` du plan lisait un layout top-level alors que
  l'endpoint renvoie un `ConfigRead` **wrappé** ; le plan aurait régressé
  `configId` (édit minimal `createConfigItem` : `String(data.id)` préservé) ; les
  tests shell utilisent MSW, pas `vi.spyOn(fetch)`. **Revue finale de branche :
  Ready to merge: Yes, 0 Critical/0 Important, 7 Minor non bloquants** (dont 2
  trouvés en revue finale, hardening hors périmètre : PATCH peut poser un slug
  sur un item non-site — namespace-squat, pas de fuite car filtré à la lecture ;
  TOCTOU sur unicité en création concurrente → 500 au lieu de 409, l'index garde
  l'intégrité). Propriété de sécurité tracée bout-en-bout sous inputs adverses.
  **Follow-up unique du reviewer fermé par le contrôleur** : l'index unique
  partiel de 0015 (vraie garantie d'unicité par-tenant, non couvrable par SQLite)
  vérifié empiriquement contre un PostGIS réel — `(td,'dup')` accepté puis REJETÉ
  au 2e insert (`uq_items_tenant_slug`), `(to,'dup')` autre tenant accepté, deux
  `slug=NULL` même tenant tous deux acceptés. **550 tests cœur passed/80 skipped**
  (sans DB ; migration 0015 apply/downgrade + rejet-doublon validés contre
  Postgres réel), lint-imports clean, **517 tests shell**, build/tsc clean,
  **40/40 specs E2E** (38 + `sites-portal-shell.spec.ts`, 2 tests). Poussé sur
  `dev`. **SP-16b/c (widgets de contenu de portail) restent à faire.**
- **SP-16b « widgets de contenu (Hero/RichSection/Gallery) » livré et clos**
  (2026-07-18, deuxième sous-phase de SP-16, cf. spec
  `docs/superpowers/specs/2026-07-18-sp16b-widgets-contenu-design.md` et plan
  `docs/superpowers/plans/2026-07-18-sp16b-widgets-contenu.md`) : trois
  nouveaux widgets de contenu (`Hero`, `RichSection`, `Gallery`) dans le
  builder, plus la plomberie cœur+shell minimale pour que `Gallery` liste et
  lie des items publiés à un visiteur anonyme. Cœur : `ItemRead.keywords`
  (colonne JSON déjà existante sur l'ORM, jamais sérialisée jusqu'ici),
  `list_published_items` — fonction repository **dédiée**, published-only,
  tenant-scopée, délibérément indépendante de `list_items` (jamais de
  `current_user_id`/`scope`) —, `GET /public/items` (anonyme, list-before-
  detail, leakage matrix non-publié/autre-tenant/tenant-défaut-publié).
  Shell : `ItemClient.listPublicItems` + `Item.keywords?` (optionnel, non-
  régression sur les literals `Item` existants), `PublicItemPage` sur route
  `/public/items/:pk` (simplification 1-requête de `SitePublicPage`, hors
  `ProtectedLayout`), `Hero` (bandeau titre/sous-titre/CTA, event `cta`
  câblé sur l'`ActionBus` réel), `RichSection` (Markdown via `sanitizeMarkdown()`
  — chokepoint unique et non-contournable `marked`+`DOMPurify`, jamais
  d'appel direct à `marked.parse` ailleurs), `Gallery` (liste `listPublicItems`,
  filtre `type`/`tag`/`limit` fixé par l'auteur du widget — aucun contrôle
  interactif pour le visiteur —, vignettes liées à `/public/items/{pk}`).
  Exécuté en subagent-driven-development (9 tâches, revue par tâche + revue
  finale de branche modèle opus). **Revue finale : 1 Important trouvé et
  corrigé** — le CTA `href` du `Hero` était passé sans validation de schéma à
  `window.open`, incohérent avec le hardening `RichSection` de la même
  branche (l'auteur d'un widget `Hero` est un utilisateur authentifié
  quelconque via SP-16a, donc semi-fiable du point de vue du visiteur
  anonyme d'un site publié) ; fixé par une allowlist de schéma (`http`/
  `https`/`mailto`, résolution via `new URL()` natif — jamais un check
  regex/substring maison, donc insensible par construction aux contournements
  de casse/espaces/tabs) avant tout `window.open`, événement `cta` toujours
  émis indépendamment de la validité du href. Fix re-vérifié par une revue
  dédiée : Resolved. 0 Critical, 0 Important résiduel, 8 Minor non bloquants
  (tag-filter et pagination en Python dans `list_published_items` — accepté,
  échelle catalogue public ; `NaN` possible sur `columns`/`limit` Gallery si
  prop auteur non numérique ; quelques stylings de `PropsPanel` non alignés
  sur les variables `--gs-*` du thème ; couverture de test non exhaustive sur
  quelques schémas d'URL rejetés par construction). Propriété de sécurité
  tracée bout-en-bout au niveau branche entière (pas seulement par tâche) :
  chaîne `Gallery→listPublicItems→GET /public/items→list_published_items`
  rederivée sans fuite d'identité/tenant possible ; chokepoint sanitize
  confirmé unique par grep sur tout le diff, pas seulement le commit qui
  l'introduit. Aucun scope creep vers SP-16c (`DatasetCard`/téléchargement
  multi-format/gabarit « Portail de données »). **564 tests cœur
  passed/80 skipped**, lint-imports clean, **541 tests shell**, build/tsc
  clean, **41/41 specs E2E** (40 + `sites-portal-content.spec.ts`). Poussé
  sur `dev`. **SP-16c (widgets dataset) reste à faire.**
- **SP-16c « fiche dataset + téléchargement + template galerie » livré et clos**
  (2026-07-18/19, dernière sous-phase de SP-16 — **SP-16 est intégralement clos,
  jalon M13 atteint**, cf. spec
  `docs/superpowers/specs/2026-07-18-sp16c-fiche-dataset-telechargement-design.md`
  et plan `docs/superpowers/plans/2026-07-18-sp16c-fiche-dataset-telechargement.md`) :
  un widget `DatasetCard` + une page publique `/public/datasets/:collectionId`
  permettent à un visiteur **anonyme** de voir les métadonnées/l'aperçu d'une
  collection publique et de la télécharger (GeoJSON toujours ; CSV sous 10 000
  entités), plus un gabarit de galerie « Portail de données » pré-câblant
  Hero+Gallery+DatasetCard+Carte/Table. **Shell-only, zéro changement cœur** :
  chaque lecture utilisée (`GET /collections/{id}`, `.../schema`, `.../items`)
  est déjà anonyme-lisible pour une collection publique via le chemin
  `get_readable_collection` (404-avant-403, non-fuyant), aucune nouvelle surface
  serveur. Pièces : `datasetDownload.ts` (URL GeoJSON directe capée à la page
  serveur de 1000 + export CSV côté client borné/paginé ≤1000, cap 10 000 lignes,
  échappement RFC4180), `ItemClient.getCollection` (lecture métadonnées mono-
  collection anonyme, réutilise `CollectionAdmin`), `DatasetDownloadButtons`
  (UI partagée widget×page, styling slate délibéré car réutilisée dans/hors
  thème), widget `datasetCard` (résout sa collection via `ctx.data?.layer`,
  convention `DataSourceSelect` des widgets map/table — pas une prop brute),
  route `/public/datasets/:collectionId` + `DatasetPage` **hors `ProtectedLayout`**
  (aperçu = `previewConfig` synthétisé en mémoire rendu par l'unique
  `AppRenderer(config, "runtime")`, A31 — pas de 2e moteur), gabarit
  `portail-de-donnees` (`Template.kind` élargi +`"site"`, additif). Exécuté en
  subagent-driven-development (7 tâches, revue par tâche + revue finale de
  branche modèle opus). **Aucun Critical/Important sur les 7 tâches ni en revue
  finale** — la revue finale (whole-branch, opus) a tracé bout-en-bout les deux
  propriétés critiques (frontière d'anonymat non-fuyante : les 2 branches
  « introuvable » sont structurellement sans interpolation d'id/nom ; bornes
  CSV/GeoJSON double-gardées de `datasetDownload` jusqu'au widget et à la page)
  et confirmé **Ready to merge: Yes**. Un seul Minor visible utilisateur corrigé
  dans la foulée (commit `6db1410`, sur décision utilisateur) : `csvAvailable(null)`
  étant faux, la bannière « trop volumineux » s'affichait à tort pour un
  `featureCount` inconnu (nombre inconnu, pas surdimensionné — état de fait
  inatteignable pour une collection enregistrée depuis SP-6c, mais faux message
  public) ; ajout de `csvTooLarge()` (vrai seulement pour un compte **connu**
  strictement au-dessus du cap) et bannière gatée dessus, le bouton CSV reste
  désactivé sur compte inconnu. 3 Minor résiduels non bloquants tracés en suivi
  (warning React `act()` sur un test ; injection de formule CSV non neutralisée
  — RFC4180-only scopé par le plan, à durcir avec l'export serveur SP-15 ;
  `getCollectionSchema` fetché inconditionnellement sans `retry:false`).
  Déviations mécaniques de tâche disclosed et vérifiées non affaiblissantes
  (`vi.waitFor` sur un test async, `getByRole heading`/`toContainText` en E2E).
  **573 tests shell** (568 + 5 du fix M1), build/tsc clean, **43/43 specs E2E**
  (`sites-portal-dataset.spec.ts` +2 tests, incl. 404 non-fuyant), **pytest cœur
  inchangé** (aucun fichier cœur touché), **aucun drift OpenAPI**. Poussé sur
  `dev`, PR dev→main ouverte pour synchroniser `main` (qui n'avait pas encore
  SP-16a/b/c). **SP-16 (Portails & Sites : modèle site/slug+route publique,
  widgets de contenu Hero/RichSection/Gallery, fiche dataset+téléchargement) est
  intégralement clos.**
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
