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
   phasage SP-1→SP-20, périmètre exact du remplacement de GeoNode (= l'interface
   `ItemClient`), modèle de données du cœur v0, **40 arbitrages tranchés (§8)**,
   jalons M1–M16. Un arbitrage ne se rediscute pas en session ; s'il doit changer,
   on met à jour ce document explicitement.
2. `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` — pourquoi
   l'option C, décisions produit (§9).
3. `docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md` — vision
   long terme.
4. `docs/vision/2026-07-09-brainstorm-geostudio-analytics-platform.md` — vision
   analytics/BI/decision support (validée, déclinée en SP-14/SP-16 et A28–A30) :
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
- Post-v0.1 (SP-10/SP-11/SP-12/SP-14/SP-16/SP-17 ; A27 amendé : OTel puis Lakehouse, ordre
  SP-12/SP-14/SP-16/SP-17 ensuite à arbitrer avant leur lancement) : observabilité **OTel + profil
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
  opt-in par dataset, A29 —, cross-filter, SQL Lab) et SP-16 alertes & rapports
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
uv run pytest        # 606 exécutés + 87 skipped (postgis marqués, nécessitent docker)

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 9 services
                      # (postgis, pgbouncer, minio, martin, titiler,
                      # core, keycloak, shell, traefik)
```

## Feuille de route (état d'avancement)

Suivi minimal des étapes superpowers (spec → plan → exécution). Chaque SP
livré a sa spec dans `docs/superpowers/specs/` et son plan dans
`docs/superpowers/plans/` ; le détail d'exécution est dans l'historique git.

### Fait

- **SP-0** — shell (catalogue, partage/publication, éditeur de carte, builder
  complet) + core (configs versionnées + rollback). Renommage `→core/` (A14).
- **SP-1** (a→d) — socle du cœur (auth JWT OIDC + mock, tenants/users/audit_log,
  lint de frontières), module `items`, partage/publication (`can()`), bascule du
  shell sur le cœur (`CoreItemClient`), realm Keycloak câblé. **Jalon M1
  (GeoNode-free)**.
- **SP-2** (a+b) — serveur MCP v0 (`/mcp` OAuth 2.1+PKCE) + 7 outils métier +
  schéma JSON `AppConfig`. **Jalon M2 (AI-operable)**.
- **SP-3** (a+b+c) — registre de collections, rôle admin, RLS par collection,
  OGC API Features Part 1+4 dans le cœur, shell lisant ses couches depuis le cœur.
- **SP-4** (a+b+c) — formulaires dans le builder (widget Formulaire, édition
  depuis la sélection carte/table, `canWrite` par utilisateur).
- **SP-5** (a+b+c) — moteur d'expressions CEL (`visibleWhen`, colonnes calculées),
  actions composées avec condition, bindings CEL généralisés + variables typées.
- **SP-6** (a+b+c) — infra jobs (procrastinate) + ingestion GeoJSON/CSV, puis
  GeoPackage/Shapefile zippé, puis `feature_count`. **Jalon M4** (GPKG 50k → carte).
- **SP-7** — recherche sémantique (pgvector, RRF trigram+vecteur) + MCP v1
  (`search_catalog`, `query_features`, `create_form_app`).
- **SP-8** (a+b+c) — SDK widgets Web Components (contrat + pont `WidgetHost`,
  registre d'extensions + chargement dynamique ES, widget tiers réel + admin).
  **Jalon M5 (SDK ouvrable)**.
- **SP-9** (6 sous-parties) — durcissement produit public v0.1 :
  gestion-collections, gouvernance-légale, ci-publique-release, install-secrets,
  sécurité-minimale, démo-lecture-seule.
- **SP-10** (a+b) — instrumentation OTel du cœur/worker + observabilité packagée
  (profil `observability`, dashboards Grafana + SLO).
- **SP-11** (a+b+c) — lakehouse : CDC→GeoParquet (réplication logique),
  compaction + module analytique DuckDB (`POST /collections/{id}/aggregate`),
  SQL analyste read-only sandboxé (`POST /analytics/sql`).
- **Storytelling** — mode narratif `story` sur `PageManager` (chapitres +
  `onEnter`/`map.flyTo`, barre de progression).
- **SP-12** (a→g) — fédération STAC/DCAT : API STAC native (lecture seule),
  export DCAT-AP (JSON-LD), moteur de moissonnage + connecteur STAC externe,
  connecteur ArcGIS FS + garde d'egress SSRF, connecteurs GetCapabilities
  WMS/WFS/WMTS + affichage raster (LayerPicker → `GET /harvest/layers`),
  connecteurs métadonnées CSW 2.0.2 + OGC API - Records (référencement pur,
  parser XML tolérant partagé avec WMS/WFS/WMTS), connecteur CKAN/data.gouv.fr
  (copie opt-in, `package_search` paginé). **A22 complet (les cinq
  connecteurs)**.
- **SP-13** (a+b+c) — Portails & Sites : modèle site/slug + route publique
  `/sites/{slug}`, widgets de contenu (Hero/RichSection/Gallery), fiche dataset
  + téléchargement + template galerie. **Jalon M13**.
- **SP-14l** — MCP analytique : outils `create_dataset`, `run_analytics_query`,
  `explain_dataset`, câblés sur les chemins de requête dataset déjà validés
  (SP-11b, SP-14a/k).
- **SP-14m** — Bookmarks : `bookmark` en cinquième `BuilderConfig.kind` (pas de
  migration), validation directe de `appId` (lisibilité + type app/dashboard)
  sur les trois routes d'écriture REST, outil MCP `create_bookmark`, page
  `/bookmarks` (« Mes vues ») réutilisant `CatalogPage`, bouton « Enregistrer
  la vue » sur `AppRuntimePage` capturant le contexte analytique courant
  (plage temporelle/emprise/cross-filter, y compris la forme `{from, to}` du
  filtre curseur).
- **SP-14n** — Cross-filter inter-datasets : `crossFilterLinks` (attribut ou
  spatial bbox/exact) déclaré sur un dataset cible un autre dataset, pour que
  la sélection sur un widget lié au dataset A cross-filtre aussi les widgets
  liés au dataset B — capacité `geomIntersects`/`geom_intersects` sur les
  deux endpoints serveur (DuckDB aggregate + OGC API Features, ce dernier non
  câblé côté shell par choix), résolution dans `derivePatch`, capture de
  géométrie au clic (carte/liste/table), UI d'auteur `CrossFilterLinkEditor`
  dans `DatasetEditPage`. **SP-14 fonctionnellement complet modulo la requête
  visuelle** (cf. « À venir »).
- **SP-15** (a, c, d, e, f, g, h) — Pipeline no-code « équivalent FME » (A39) :
  - **SP-15a** — socle headless : nouveau document déclaratif `Pipeline`
    (`BuilderConfig.kind="pipeline"`), catalogue de 8 opérations data-only
    (`reader.collection`, `transform.filter/select/derive/aggregate/join`,
    `writer.collection/export`), runtime d'exécution DuckDB nœud par nœud
    sans fusion (topologie linéaire+join seulement, DAG à embranchements
    différé), job procrastinate sur une nouvelle file `etl`, capacité
    instance-wide `CORE_ETL_ENABLED` (défaut `false`) qui coupe toute la
    surface REST+MCP. Réutilise verbatim la connexion DuckDB éphémère + le
    CTE de dédoublonnage CDC GeoParquet (SP-11b), le chemin d'écriture OGC
    Features (SP-3), le patron de file procrastinate (SP-6a/SP-12c). Un
    canvas shell existe (`PipelineCanvas`/`PipelinePalette`/
    `PipelineNodeInspector`/`PipelinePreviewPanel`/`PipelineRunPanel`,
    `PipelineBuilderPage`) couvrant l'édition de cette topologie
    linéaire+join.
  - **SP-15c** — étage 1 spatial + `writer.dataset` : 5 op spatiales
    (`transform.buffer/reproject/intersection/countWithin/h3Aggregate`,
    extension DuckDB `h3`), `writer.dataset` (crée/mets à jour un dataset
    analytique SP-14 depuis un pipeline), les 3 nouvelles op référençant
    une collection validées en écriture/lecture à la sauvegarde de config,
    5 entrées ajoutées au menu d'insertion du canvas.
  - **SP-15d** — étage 2 spatial (« long tail géo ») : op générique
    `transform.qgis` invoquant un algorithme QGIS Processing (allowlist
    gelée de 50 ids, `core/app/pipelines/ops/qgis_algorithms.json`, générée
    hors-ligne contre `qgis/qgis:release-3_34` — jamais `:latest`) via un
    sidecar `qgis-worker` isolé (stdlib `http.server`, aucune credential
    DB/accès réseau externe, profil compose `etl`, même porte que
    `CORE_ETL_ENABLED`) ; `runtime.py` matérialise la relation DuckDB amont
    en GeoPackage CRS-tagué (`SRS` explicite obligatoire), appelle le
    sidecar en HTTP, recharge le résultat via `ST_Read` en aliasant la
    colonne géométrie par **type** (jamais par nom — GDAL/QGIS ne la nomme
    pas forcément `geometry`). Auteur MCP/REST uniquement, pas de
    changement canvas. **Point ouvert non bloquant** : les 5 tests
    `@pytest.mark.qgis` (conteneur sidecar réel + `/scratch` inscriptible)
    n'ont jamais tourné pour de vrai à ce jour (contrainte d'environnement
    de la session de livraison, `sudo` interactif indisponible) — à
    exécuter avant d'activer `transform.qgis` en production ; le reste
    (param model, allowlist, SRID, wiring routes/compose, gestion d'erreur)
    est vérifié statiquement et par tests réels non-sidecar.
  - **SP-15e** — coffre de secrets pour connecteurs externes : nouveau
    module `core/app/secrets/` (chiffrement applicatif AES-256-GCM,
    `cryptography`'s `AESGCM`, clé maître `CORE_SECRETS_MASTER_KEY` requise
    au boot — échec rapide si absente/mal formée, jamais un défaut
    silencieux), union Pydantic discriminée `SecretPayload` sur 5 formes
    (clé API en-tête/query, jeton bearer, basic auth, OAuth2
    client-credentials, DSN Postgres — additive par construction, un
    nouveau kind = une nouvelle variante Pydantic, aucune migration),
    table `connector_secrets` tenant-scopée (unique `(tenant_id, name)`),
    trois routes REST (`POST`/`GET`/`DELETE /secrets`) admin-only auditées
    ne renvoyant jamais de valeur déchiffrée/ciphertext/nonce — pas de
    rotation, suppression+recréation seulement. Positionné dans le
    contrat de couches import-linter strictement **sous** `app.harvest`
    ET `app.pipelines`, ses deux futurs consommateurs anticipés (SP-12
    connecteurs de moissonnage, SP-15 pipelines) — ce plan rend le coffre
    *capable* de les servir sans construire ni l'un ni l'autre ; aucun
    outil MCP, aucun kind `BuilderConfig`, aucun changement canvas.
    Exposition MCP des *noms* de secrets (métadonnées seules) différée à
    un futur incrément (non planifié, non numéroté).
  - **SP-15f** — `reader.connector.rest`/`reader.connector.postgres` : deux
    nouveaux ops de lecture dans le pipeline no-code, premiers consommateurs
    réels du coffre SP-15e (authentification **par nom** de secret, résolue
    à l'exécution seulement, jamais à la sauvegarde). Matérialisation par un
    vrai pipeline `dlt` (extraction/normalisation/inférence de schéma) vers
    un fichier DuckDB scratch, `ATTACH`é en lecture seule puis sélectionné
    en `TEMP TABLE` (convention nœud-par-nœud identique aux autres readers).
    Garde SSRF **dupliquée** pour `requests` (`core/app/pipelines/egress.py`,
    variable `CORE_PIPELINES_EGRESS_ALLOWLIST` distincte de
    `CORE_HARVEST_EGRESS_ALLOWLIST`) — dlt's REST client utilise `requests`,
    pas `httpx`, et `app.pipelines` est sous `app.harvest` dans le contrat de
    couches, donc ne peut pas réutiliser sa garde. Requête Postgres libre
    bornée SELECT-only **à l'exécution seulement**, en réutilisant
    `app.analytics.sql_sandbox`. Aucun canvas, aucun outil MCP — les deux
    ops apparaissent automatiquement dans `ops_catalog()`. Deux Important
    trouvés et corrigés en revue (tous deux des surfaces où l'auth/l'échec
    contournait la garde SSRF : l'échange de jeton OAuth2 client-credentials
    utilisait la session non gardée de dlt ; les échecs survenant *pendant*
    l'extraction dlt elle-même, y compris un blocage SSRF sur l'URL de
    données, n'étaient pas traduits en erreur propre et ressortaient en 500
    opaque) — 0 Critical/Important non résolu au merge.
  - **SP-15g** — canvas DAG (branchements & fusion) : le graphe `Pipeline`
    gagne un embranchement réel au-delà de linéaire+join, côté runtime et
    canvas. `PipelineEdge.role` (`primary`/`secondary`) distingue, pour un
    nœud à deux entrées, l'arête primaire de l'arête secondaire ; le
    fan-out (un nœud alimentant plusieurs avals) était déjà possible et
    est désormais couvert par un test explicite, le fan-in (deux amonts
    convergeant sur un même nœud via primary+secondary) est nouveau.
    Nouvel op `transform.merge` (UNION ALL BY NAME des deux entrées).
    Validation XOR côté serveur et côté client entre `withCollectionId` et
    une arête secondaire pour les 4 op binaires (`transform.join`/
    `transform.intersection`/`transform.countWithin`/`transform.merge`) —
    la seconde entrée d'un nœud binaire vient soit d'une collection
    déclarée, soit d'une arête secondaire, jamais des deux. Progression
    d'exécution incrémentale : `PipelineRun.node_stats` s'écrit nœud par
    nœud via un callback pendant le run (plus seulement à la fin),
    consommée par le canvas pour des badges de progression/spinner par
    nœud en direct pendant qu'un run tourne. Nouveau panneau
    `PipelinePreviewMap` (MapLibre) à bascule avec l'aperçu tabulaire
    existant. Ferme le point que le résumé SP-15a-f qualifiait de non
    planifié : le canvas visuel supporte désormais un vrai embranchement
    DAG (une seconde poignée d'entrée visuellement distincte + arêtes
    secondaires en pointillés), pas seulement linéaire+join.
  - **SP-15h** — planification simple des pipelines : un `Pipeline`
    sauvegardé peut désormais s'exécuter seul sur un cron récurrent, sans
    nouvelle route REST ni nouvel outil MCP. Cœur : `PipelineRefreshPolicy
    {enabled, cron}` (validation `croniter`) sur `PipelinePayload`, une
    tâche procrastinate périodique (`run_pipeline_sweep_task`, sweep 5
    min, file `etl`) qui balaie tous les tenants (`list_configs_by_kind`,
    cross-tenant, jamais exposé par une route), dérive le "dernier run"
    depuis `pipeline_runs` (`get_latest_run`, aucune colonne dupliquée,
    aucune migration) et défère `run_pipeline_task` — même chemin
    d'exécution qu'un run manuel. `explain_pipeline` expose `refreshPolicy`
    en lecture (signature inchangée). Deux Important trouvés et corrigés en
    revue (aucun n'était visible tâche par tâche, tous deux des bugs de
    concurrence hérités du texte littéral du plan) : l'ancre de reclaim
    d'un run "stuck" utilisait `created_at` (jamais mis à jour) au lieu de
    `started_at`, réclamant à tort un run qui venait de démarrer après une
    longue attente en file ; le sweep déférait `run_pipeline_task` avant de
    committer la ligne `pipeline_runs` (un seul commit en fin de boucle),
    au lieu du patron `commit()` puis `defer()` déjà établi dans
    `routes.py`/`mcp/tools.py` — un worker aurait pu ramasser la tâche
    avant que la ligne ne soit visible, perdant silencieusement le run.
    Shell : `PipelineScheduleEditor` (3 préréglages sans syntaxe cron —
    intervalle/quotidien/hebdomadaire — plus un mode cron avancé en
    échappatoire), câblé dans le cycle `draft`/`onSave` existant de
    `PipelineBuilderPage` (pas d'action de sauvegarde séparée), erreurs de
    sauvegarde désormais surfacées près du bouton Enregistrer.
  - **A39 : Phases 1+2 (socle headless + étage 1+2 spatial) livrées**, plus
    SP-15e (coffre de secrets), SP-15f (premier consommateur réel du
    coffre), SP-15g (canvas DAG — branchements & fusion) et SP-15h
    (planification simple) — reste non planifié : événements/déclencheurs
    durables au-delà de la planification cron simple.
- **SP-16a** — export serveur secs CSV/XLSX (+ GeoJSON/GPKG quand la source a
  une géométrie) : `app.analytics.export` (sérialisation des 4 formats),
  4 routes d'export (`POST`/`GET .../export[/items]` sur `collections` et
  `datasets/{id}/arcgis`, agrégé et entités brutes), exemptées du garde
  lecture-seule démo ; `ItemClient.exportDataSource()`, `DataContext` expose
  `resolvedSource`/`hasGeometry` par source, `ExplorerMenu` + section Export
  de `DatasetEditPage` branchées sur les 6 widgets analytiques. Deux passes
  de fix en revue finale de branche (0 Critical/Important non résolu au
  merge) : (1) types OpenAPI/TS régénérés, encodage datetime/Decimal/UUID/
  bytes dans GeoJSON/GPKG/XLSX, pagination export ArcGIS suivant
  `exceededTransferLimit`, échecs d'export shell surfacés au lieu d'être
  avalés silencieusement ; (2) coercition UUID/bytes manquante dans la
  branche XLSX de l'export (même défaut que (1), fonction sœur oubliée),
  curseur de pagination ArcGIS avançant du mauvais pas (`limit` demandé au
  lieu du nombre de features reçues — perte silencieuse sur une page
  plafonnée côté service), message d'erreur shell traduit en français
  actionnable (413/403).
- **SP-16b** — alertes de seuil (`AlertRule`, 8e kind `BuilderConfig`) :
  condition scalaire bornée sur DuckDB (`app.configs.alert_condition`),
  validée à la sauvegarde (Pydantic) et évaluée à l'exécution contre un
  résultat d'agrégat live ; v1 = un seul scalaire par règle (pas de
  groupBy/split/bucket/bins, pas de géofencing) et datasets sourcés
  collection uniquement (arcgis échoue proprement en `error`, jamais
  mal-évalué silencieusement) ; notification webhook (garde SSRF dédiée
  `app.alerts.egress`) et/ou email (SMTP via un nouveau kind de secret
  `smtp` dans le coffre SP-15e) uniquement sur transition d'état
  (`ok↔firing`), jamais à chaque tick d'un balayage périodique
  procrastinate miroir du patron SP-15h ; routes `GET /datasets/{id}/alerts`
  + `GET /alerts/{id}/evaluations`, outil MCP `explain_alert_rule`, section
  « Alertes » sur `DatasetEditPage` (liste + création inline, réutilise
  `PipelineScheduleEditor` pour la planification cron). **Renumérotation
  actée avec l'utilisateur au moment de la spec** : `ReportSchedule`/
  rapports planifiés/PDF paginés (annoncés « 16c » dans SP-16a) partent
  entièrement dans SP-17 — SP-16b clôt SP-16, il n'y a pas de 16c ; jalon
  **M12 atteint** sous ce périmètre resserré (le critère de sortie M12 a
  été explicitement reformulé pour ne couvrir que le cycle alerte de
  seuil, les rapports planifiés diffusés restant à livrer sous SP-17).
  Exécution en subagent-driven-development avec revue systématique par
  tâche : 9 des 16 tâches ont vu un défaut réel du texte littéral du plan
  trouvé et corrigé avant merge (bien au-dessus de la moyenne des SP
  précédents), tous arbitrés explicitement, 0 Critical/Important non
  résolu au final — notamment deux failles de sécurité dans le sandbox
  DuckDB dicté par le plan (bypass par fonction de table permettant
  lecture fichier/SSRF, puis DoS par fonction de table calculatoire non
  bornée — corrigées par verrouillage moteur `enable_external_access`
  + timeout/limites en miroir de `app.analytics.sql_sandbox`), un union
  de canaux non discriminé laissant un payload ambigu se résoudre
  silencieusement en la mauvaise variante, une SSRF par redirection HTTP
  contournant une vérification unique (corrigée par la session gardée
  `build_guarded_session` déjà construite pour cet usage), un test seam
  `S3_CDC_BUCKET_BASE_URI` manquant cassant la lecture locale de
  partitions CDC en test, un scan cross-tenant explicitement interdit par
  sa propre docstring exposé quand même via une route REST, un décorateur
  MCP inexistant (`@mcp.tool()` au lieu de `@server.tool()`) plus un
  mauvais placement sous le flag `CORE_ETL_ENABLED` contredisant
  l'exigence d'enregistrement inconditionnel, une erreur de fetch avalée
  silencieusement dans l'UI (liste vide indiscernable d'un échec réel), et
  une assertion E2E finale ne prouvant qu'un POST avait eu lieu sans
  vérifier son contenu. `app.alerts` inséré dans le contrat de couches
  import-linter (sous `app.pipelines`, au-dessus de `app.secrets`).
- **SP-17a** — socle d'export (A25) : worker Playwright asynchrone qui rend
  la vraie page runtime du shell (carte ou app/dashboard) en PNG/PDF, mise
  en page `printLayout` déclarative embarquée dans `MapConfig`/`AppConfig`
  (page A4/A3, orientation, titre, légende/échelle/flèche nord, cartouche),
  bouton « Exporter » dans la visionneuse de carte et le runtime d'app/
  dashboard — tout derrière `CORE_EXPORT_ENABLED` (défaut désactivé).
  Nouveau module `core/app/export/` (jobs procrastinate file dédiée
  `export`, routes REST, modèle+repository) ; jeton d'export éphémère
  HS256 colocalisé dans `app.auth` (pas `app.export`, pour respecter le
  sens du contrat de couches — `app.export` importe `app.auth`, jamais
  l'inverse) fait naviguer le worker avec les droits réels de
  l'utilisateur demandeur, révocation par TTL court (~2 min) seul, aucun
  précédent de jeton à usage unique dans ce dépôt ; conteneur dédié
  `export-worker` (profil compose `export`, image séparée du worker
  partagé — Chromium est trop lourd pour lui). Shell : `printLayout`
  round-trippé sur `MapConfig`/`AppConfig`, mode `exportRender` (page nue
  sans chrome de builder NI chrome applicatif `AppLayout`, signal de
  disponibilité `data-export-ready="true"` sur `document.body` que le
  worker attend via sélecteur Playwright), panneau de poll générique
  (patron `PipelineRunPanel`, jamais `useQuery`/`refetchInterval`).
  Exécution en subagent-driven-development : 14 tâches, 6 défauts réels
  trouvés/corrigés en revue par tâche (KeyError non catché sur secret
  manquant → 500 non authentifié ; fuite Chromium/driver sur échec de
  lancement ; client S3 en dur au lieu du patron injectable + branche
  "done" non testée ; bug pré-existant `saveMapConfig` perdant
  silencieusement `printLayout` ; légende dupliquée par l'overlay export ;
  chrome applicatif complet visible dans les captures carte, avec bouton
  de déconnexion — `AppLayout` ignorait `exportRender`), plus **3 rounds
  de revue finale de branche** (0 Critical/Important non résolu au
  merge) : round 1 a trouvé 3 Critical + 8 Important invisibles à une
  revue scopée par tâche — mode export à hauteur DOM nulle (capture
  vide, mesuré empiriquement 0px vs 653px en vrai Chromium), aucune
  migration Alembic pour `export_jobs` (jamais créée sur Postgres),
  `docker-compose.yml` ne donnant `CORE_EXPORT_ENABLED`/
  `CORE_EXPORT_TOKEN_SECRET` qu'au worker jamais à `core` (routeur jamais
  monté, ou jeton jamais validable) ; round 2 a trouvé que le fix round 1
  lui-même cassait 2 jobs CI (spec OpenAPI régénérée avec le flag actif
  alors que la CI ne l'active jamais — reverti pour matcher le précédent
  `CORE_ETL_ENABLED`/pipelines déjà établi ; test `@pytest.mark.playwright`
  sans garde de skip, échouerait au lieu de sauter faute de Chromium en
  CI) plus `VITE_CORE_URL` jamais transmis au service `shell` du compose
  (export non fonctionnel contre la stack par défaut malgré une
  documentation ajoutée en round 1) ; round 3 a confirmé les 3 fixes
  fermés par reproduction indépendante des étapes CI et de la garde de
  skip dans les deux sens, et trouvé `SHELL_BASE_URL` avec exactement le
  même défaut inerte que `VITE_CORE_URL` (corrigé directement, motif déjà
  prouvé). Test `@pytest.mark.playwright` (Task 6) réellement exécuté et
  vérifié dans les deux sens (SKIPPED sans Chromium, PASSED avec) — pas
  seulement best-effort documenté comme le précédent SP-15d/qgis. Build
  Docker réel de `export-worker` réussi (Chromium/FFmpeg/Chrome Headless
  Shell téléchargés et installés). Suivis non bloquants restants : voir
  `### Suivis non bloquants ouverts`.
- **SP-17b** — `ReportSchedule` (9e kind `BuilderConfig`) : un `Bookmark`
  (app + page + contexte analytique figé) rendu en PDF sur cron via le
  worker d'export Playwright de SP-17a, notifié par webhook/email (canaux
  `AlertChannel` réutilisés tels quels de SP-16b) avec un lien de
  téléchargement présigné — jamais de pièce jointe, jamais de fusion PDF,
  jamais rejoué au tick suivant même en échec. Nouveau module
  `core/app/reports/` (au-dessus d'`app.alerts` dans le contrat de
  couches) : modèle `report_runs`, repository (CRUD + balayage cross-
  tenant `list_due_reports`/`list_unnotified_runs`), `encode_analytics_context`
  (miroir octet-compatible du format `?ctx=` du shell), une seule tâche
  procrastinate périodique à deux étapes (déclencher les planifications
  dues en créant une ligne `export_jobs` avec les nouvelles colonnes
  `page_id`/`ctx` puis en déférant `render_export_task` existant,
  notifier les runs dont le job joint est terminé), une route REST
  bespoke (`GET /reports/{item_id}/runs`), un outil MCP
  `explain_report_schedule`. `app.export` gagne deux colonnes nullable
  (`page_id`, `ctx`) et un pied de page PDF (date de génération) sur tout
  export, pas seulement les rapports. Shell : `ReportScheduleEditor`
  (formulaire contrôlé, miroir d'`AlertRuleEditor`), `ReportRunPanel`
  (historique en lecture seule, miroir de `PipelineRunPanel` moins le
  bouton d'exécution manuelle — un rapport ne se déclenche que par cron),
  `ReportEditPage` (create/edit `pk: string | null`, miroir de
  `PipelineBuilderPage`), point d'entrée « Programmer un rapport » sur les
  lignes de signet, E2E complet. Exécution en subagent-driven-development :
  19 tâches, plusieurs défauts réels trouvés/corrigés en revue par tâche
  (dont un bug de format `?ctx=` **dans le texte littéral du plan
  lui-même** — `entry.model_dump()` sans `by_alias=True` aurait cassé le
  décodage JS pour toute valeur `crossFilter` de type plage imbriquée ;
  un test manquant sur la branche « accès app perdu » de la double
  vérification de droits au déclenchement), puis **une revue finale de
  branche** (2 Critical + 5 Important, 0 non résolu après une passe de
  fix unique + re-revue) : spec OpenAPI/types TS jamais régénérés (aurait
  cassé `api-types-drift` en CI, reproduit empiriquement) ; pas de filet
  d'exception large sur l'étape de notification — une erreur inattendue
  (pas `NotifyError`) bloquait la notification de **tous les tenants pour
  toujours** au lieu d'un seul run, violant la contrainte « jamais rejoué »
  par un autre mécanisme que prévu ; même défaut sur l'étape de
  déclenchement (un échec inattendu tuait le reste du tick) ; un
  déclenchement en échec ne créait aucune ligne `report_runs`, donc un
  rapport en échec permanent se re-déclenchait toutes les 5 minutes pour
  toujours au lieu de respecter son propre cron (migration 0024,
  `report_runs.export_job_id` devient nullable) ; `CORE_EXPORT_ENABLED=false`
  laissait les jobs `pending` pour toujours (`export-worker` non démarré
  par défaut, `reclaim_stuck_jobs` ignore `pending`) — corrigé par un
  double verrou (création bloquée + échec rapide dans le balayage,
  décision explicite avec Tanguy) ; lien présigné de notification à durée
  de vie de 1h (mail du dimanche soir mort avant lundi) — étendu à 7
  jours sur le chemin notification uniquement (décision explicite) ;
  `ReportRunPanel` sondait indéfiniment sans jamais s'arrêter et avalait
  les échecs réseau en un état indiscernable de « aucun run ».

### À venir

- **SP-14** — seule reste la **requête visuelle** (Filtrer → Joindre →
  Résumer → Trier compilant vers l'API analytique) ; le moteur qu'elle
  consommera est désormais livré (SP-15a, A39), la requête visuelle elle-même
  reste à construire par-dessus — toujours pas livrée. Toutes les autres
  sous-parties (datasets, contexte global, cross-filter y compris
  inter-datasets, widgets, SQL Lab, source arcgis, MCP, bookmarks) sont
  livrées. Jalon M11 non atteint tant que la requête visuelle n'est pas
  livrée.
- **SP-15** — reste : événements/déclencheurs durables au-delà de la
  planification cron simple (livrée SP-15h) — non planifié, non numéroté ;
  vérification réelle des 5 tests `@pytest.mark.qgis` de SP-15d (sidecar +
  `/scratch` réels, non exécutée à ce jour). Exposition MCP des noms de
  secrets (métadonnées seules) non planifiée, non numérotée. Jalon M14 non
  atteint (socle + étage 1+2 spatial + coffre de secrets + premier
  connecteur authentifié + canvas DAG branchements/fusion + planification
  simple livrés ; seule la vérification des tests qgis réels bloque encore
  M14, les événements durables étant hors périmètre du jalon tel que
  cadré).
- **SP-16** — clos (SP-16a + SP-16b livrés, jalon M12 atteint sous le
  périmètre reformulé — cf. `### Fait`). Aucun SP-16c : le renumérotage
  acté avec l'utilisateur au moment de la spec SP-16b déplace
  `ReportSchedule`/rapports planifiés/PDF de dashboards paginés
  entièrement dans **SP-17**, où le socle export CSV/XLSX/GeoJSON/GPKG de
  SP-16a sera réutilisé tel quel plutôt que reconstruit.
- **SP-17** — clos sous le périmètre exécuté (SP-17a socle export + SP-17b
  `ReportSchedule`, cf. `### Fait`) : le socle export (worker Playwright +
  `PrintLayout`) et les rapports planifiés PDF sont livrés. La 3D
  (deck.gl `Tile3DLayer` + terrain raster-dem), qui faisait partie du
  périmètre « 3D & impression » d'origine de la feuille de route, n'a
  **pas** été exécutée sous ce nom de SP — elle reste dans le reste de la
  vision post-v0.1 (bullet suivant), non planifiée, non numérotée.
- Reste de la vision post-v0.1 : 3D (deck.gl `Tile3DLayer` + terrain raster-dem).
- **SP-18** — export d'apps déployables sans GeoStudio (modes Connecté/
  Autoporté/Statique, dépend de SP-11). Jalon M15.
- **SP-19** — undo/redo général du builder (pile d'instantanés de config,
  prérequis de SP-20). Aucune dépendance amont.
- **SP-20** — copilote IA embarqué dans le builder (panneau de chat, outils
  MCP orchestrés en loopback réel, micro-actions sur la config en cours
  d'édition). Dépend de SP-19. Jalon M16. Arbitrages A32/A40, brainstorm
  2026-08-05 ; specs :
  `docs/superpowers/specs/2026-08-05-undo-redo-builder-design.md` et
  `docs/superpowers/specs/2026-08-05-copilote-embarque-design.md`.

### Suivis non bloquants ouverts

- Connecteur ArcGIS v0 = services publics seulement (pas de token/OAuth distant) ;
  résiduel DNS-rebinding TOCTOU sur la garde egress (pinning-IP différé).
- Tags d'images Docker `pgbouncer`/`martin`/`titiler` à repinner si dérive ;
  documenter dans `.env.example`.
- Volume `pg-data` du projet compose par défaut cassé (`alembic_version` jamais
  stampée) — réparation non destructive hors périmètre.
- Questions produit ouvertes : Q2 (premiers utilisateurs réels), Q10 (temps
  réel), Q11 (offline) — cf. comparatif §8. Seule Q2 peut réordonner SP-3/SP-6.
- Brainstorm Analytics Platform (2026-07-09) validé et décliné en SP-14/SP-16,
  arbitrages A28–A30, jalons M11/M12.
- SP-17a, Minor différés (non bloquants, trouvés en revue finale de branche) :
  géométrie d'impression (viewport Playwright) non dérivée de
  `PrintLayout.pageSize`/`orientation` ; `printLayout.showScaleBar`/
  `showNorthArrow` retirés du panneau d'édition (contrôles inertes, jamais
  rendus — cf. Fait) ; `POST /export` n'valide pas le kind de l'item
  (dataset/pipeline accepté, échoue après 30s au lieu d'un 422 immédiat) ;
  `export-worker` sans instrumentation OTel contrairement à `core`/
  `worker`/`cdc-worker`.
- SP-17b, Minor résiduels (non bloquants, trouvés en re-revue finale de
  branche après la passe de fix) : le filet d'exception large de l'étape
  de notification (`_notify_pending_reports`) ne fait pas
  `session.rollback()` avant son `finally` — une erreur côté base de
  données (hors les causes réalistes déjà couvertes : `S3_ENDPOINT_URL`
  manquant, échec AES-GCM) pourrait encore faire échapper
  `mark_notified`, contrairement à `_record_trigger_failure` qui, lui,
  fait le rollback en premier ; un échec transitoire de déclenchement
  consomme désormais un créneau de cron entier au lieu de se retenter au
  tick suivant (compromis délibéré, parité avec `AlertRule`, non signalé
  comme tel dans le rapport de fix d'origine) ; chemin très étroit où un
  échec *dans* le nouveau gestionnaire d'échec de `defer()` peut produire
  deux lignes `report_runs` pour un même tick (inoffensif, la cadence se
  base sur la plus récente) ; `downgrade()` de la migration 0024
  échouerait sur une base avec des lignes de déclenchement en échec (`SET
  NOT NULL` sur des `NULL` existants) — CI teste sur base vide, passe ; à
  savoir avant un rollback réel ; `stopped`-ref partagé entre exécutions
  d'effet dans `ReportRunPanel` (pré-existant au patron des panneaux de
  poll, non introduit par SP-17b).
