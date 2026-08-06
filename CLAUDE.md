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
- **SP-15** (a, c, d) — Pipeline no-code « équivalent FME » (A39) :
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
  - **A39 : Phases 1+2 (socle headless + étage 1+2 spatial) livrées** —
    canvas visuel du graphe complet (branchements DAG au-delà de
    linéaire+join), automatisation/déclencheurs restent SP-15e+ (non
    planifié).

### À venir

- **SP-14** — seule reste la **requête visuelle** (Filtrer → Joindre →
  Résumer → Trier compilant vers l'API analytique) ; le moteur qu'elle
  consommera est désormais livré (SP-15a, A39), la requête visuelle elle-même
  reste à construire par-dessus — toujours pas livrée. Toutes les autres
  sous-parties (datasets, contexte global, cross-filter y compris
  inter-datasets, widgets, SQL Lab, source arcgis, MCP, bookmarks) sont
  livrées. Jalon M11 non atteint tant que la requête visuelle n'est pas
  livrée.
- **SP-15** — reste : canvas visuel du graphe `Pipeline` au-delà de la
  topologie linéaire+join actuelle (branchements DAG), automatisation/
  déclencheurs au-delà de la planification simple, vérification réelle des
  5 tests `@pytest.mark.qgis` de SP-15d (sidecar + `/scratch` réels, non
  exécutée à ce jour). SP-15e+, non planifié. Jalon M14 non atteint (socle
  + étage 1+2 spatial livrés, DAG/automatisation restent).
- **SP-16** — alertes & rapports planifiés (exports secs CSV/XLSX). Jalon M12.
- **SP-17** — reste à cadrer (cf. feuille de route, ordre SP-12/SP-14/SP-16/SP-17
  à arbitrer avant lancement).
- Reste de la vision post-v0.1 : 3D (deck.gl `Tile3DLayer` + terrain raster-dem),
  impression (Playwright en worker).
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
