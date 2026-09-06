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
5. `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` — revue de projet et
   plan d'action en **vagues** (0 à 6) : c'est ce document que citent les SP-20
   à SP-27 (« vague 3 », « chantier 4.4 »).
6. `docs/superpowers/specs/` + `plans/` — chaque SP a sa spec puis son plan datés.
7. `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md` — **historique
   d'exécution détaillé** (extrait de ce fichier le 2026-08-27) : ce que chaque
   revue finale a trouvé, les décisions de scope, les déviations assumées, la
   liste complète des suivis non bloquants. À lire avant de rouvrir une surface
   déjà livrée.
8. `docs/archive/` — générations dépassées ; ne pas s'en inspirer sans lire la
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
- **TDD systématique** ; chaque feature visible a sa spec E2E Playwright. La
  suite E2E complète est le filet de la migration : elle reste globalement
  verte (dernière mesure, clôture SP-43 2026-09-05 : 141 passed / 4 skipped /
  **1 failed** — `e2e/pipeline-builder.spec.ts:111`, timeout sur le bouton
  « Exécuter », confirmé préexistant à SP-43 en checkoutant le commit
  d'avant sa Tâche 1 ; cause non encore investiguée, ne pas imputer à un
  futur travail sans vérifier d'abord si ce test échoue déjà sur `dev`).
- Exécution en **subagent-driven-development** : une revue par tâche **et** une
  revue finale de branche, systématiquement — ce ne sont pas les mêmes défauts
  (cf. `## Pièges récurrents`).
- Commits **conventional** (`feat(shell): …`, `fix(core): …`), petits, un sujet.
- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Branche de travail : `dev` ; `main` reçoit les états stables (merge).
- **À la clôture d'un SP** : une ligne dans `### Livré` ci-dessous, et l'entrée
  détaillée dans `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`
  (pas de récit long dans ce fichier — il est chargé à chaque session).

## Commandes

```bash
# shell (d'abord, car commitlint en dépend)
cd shell && npm ci
npm run test         # Vitest — dernier compte mesuré à la clôture SP-43
                     # (2026-09-05) : 225 fichiers, 1944 tests, tous passed.
npm run e2e          # Playwright — 141 passed / 4 skipped / 1 failed à la
                     # même mesure (VITE_AUTH_MODE=mock) — l'échec
                     # (pipeline-builder.spec.ts:111) est préexistant à
                     # SP-43, cf. ## Comment on travaille.
                     # e2e-oidc/ : suite séparée contre un vrai Keycloak (SP-26)
npm run build        # tsc --noEmit + vite build

# pre-commit (une fois par poste de travail, après npm ci)
# Note : commitlint dépend de shell/node_modules, donc cd shell && npm ci doit être exécuté d'abord
# `pip install pre-commit` échoue ici (`pip`/`pip3` absents du PATH, pas seulement
# PEP 668 externally-managed-environment).
# `uvx pre-commit` "marche" mais pose des hooks git qui pointent vers un
# binaire dans le cache uv (chemin volatile) : un `uv cache prune` casse
# alors tout commit jusqu'à réinstallation. `uv tool install` dépose un
# binaire persistant sur le PATH (~/.local/bin), hooks git stables.
uv tool install pre-commit
pre-commit install --hook-type pre-commit --hook-type commit-msg

# cœur
cd core && uv sync
uv run pytest        # dernier compte mesuré à la clôture SP-43 (2026-09-05) :
                     # 2326 passed / 5 skipped / 0 failed, sur un conteneur
                     # postgis-test réel (CORE_TEST_DATABASE_URL positionné —
                     # sinon ~185 tests marqués postgis skippent silencieusement,
                     # piège vécu pendant la clôture de SP-43 elle-même). Piège
                     # vécu par SP-42 : ce conteneur n'est PAS tracké par Alembic —
                     # après une migration qui ajoute des colonnes, il faut un
                     # ALTER TABLE manuel, sinon des dizaines de tests
                     # échouent en cascade sur UndefinedColumn sans rapport
                     # avec le code sous revue. Les 5 skips = marqueur qgis
                     # (sidecar réel requis). Deux échecs INTERMITTENTS déjà
                     # documentés, à ne pas imputer à son propre travail sans
                     # vérifier : test_features_rls.py::
                     # test_scope_preserves_original_sql_error (dérive
                     # psycopg2/transaction, non diagnostiquée) ;
                     # test_deployability.py::test_every_compose_substitution_is_documented
                     # (VITE_AUTH_MODE absent de .env.example malgré sa
                     # substitution dans docker-compose.yml).

# portes de qualité (mêmes invocations qu'en CI — cf. .github/workflows/ci.yml)
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports                      # contrat de couches (30 entrées)
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold   # 85
cd ../shell
npm run lint && npm run format:check
node scripts/check-coverage.mjs coverage/coverage-summary.json \
  .coverage-threshold                    # 88 ; nettoyer dist/ + dist-export/ avant
uvx pre-commit run --all-files           # 5 hooks (commitlint ne sort qu'au commit)

# régénérer la spec OpenAPI + les types TS — À FAIRE dès qu'une route ou un
# modèle change (classe d'oubli n°1 du dépôt). La commande nue échoue en
# ModuleNotFoundError: app ; il faut l'incantation d'api-types-drift :
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types     # → src/api/generated/core-schema.d.ts

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 11 services par
                     # défaut (postgis, pgbouncer, minio, martin, titiler,
                     # core, worker, cdc-worker, keycloak, shell, traefik)
                     # + 5 derrière un profil : etl (qgis-worker), export
                     # (export-worker), appexport, observability (otel-lgtm,
                     # postgres-exporter)
```

## Feuille de route (état d'avancement)

Une ligne par SP. **Le détail — revues finales, défauts trouvés, décisions de
scope actées avec Tanguy, déviations assumées vis-à-vis du texte des plans — est
dans `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`** : à lire
avant de reprendre un chantier ouvert ou de rouvrir une surface déjà livrée.
Chaque SP a sa spec dans `docs/superpowers/specs/` et son plan dans
`docs/superpowers/plans/`.

### Livré

- **SP-0** — shell (catalogue, partage/publication, éditeur de carte, builder) +
  cœur (configs versionnées + rollback). Renommage `→core/` (A14).
- **SP-1** (a→d) — socle du cœur : auth JWT OIDC + mock, tenants/audit_log,
  lint de frontières, module `items`, partage/publication (`can()`), shell
  basculé sur `CoreItemClient`, realm Keycloak. **Jalon M1 (GeoNode-free)**.
- **SP-2** (a+b) — MCP v0 (`/mcp` OAuth 2.1+PKCE) + 7 outils + schéma JSON
  `AppConfig`. **Jalon M2 (AI-operable)**.
- **SP-3** — registre de collections, rôle admin, RLS par collection, OGC API
  Features Part 1+4, shell lisant ses couches depuis le cœur.
- **SP-4** — formulaires dans le builder (widget Formulaire, édition depuis la
  sélection carte/table, `canWrite` par utilisateur).
- **SP-5** — moteur CEL : `visibleWhen`, colonnes calculées, actions
  composées, bindings généralisés + variables typées.
- **SP-6** — jobs procrastinate + ingestion GeoJSON/CSV/GeoPackage/Shapefile,
  `feature_count`. **Jalon M4** (GPKG 50k → carte).
- **SP-7** — recherche sémantique (pgvector, RRF trigram+vecteur) + MCP v1.
- **SP-8** — SDK widgets Web Components (contrat, `WidgetHost`, registre
  d'extensions + chargement dynamique ES). **Jalon M5 (SDK ouvrable)**.
- **SP-9** (6 sous-parties) — durcissement produit public v0.1 : gestion
  collections, gouvernance légale, CI publique/release, install/secrets,
  sécurité minimale, démo lecture seule.
- **SP-10** — OTel sur cœur/worker + observabilité packagée (profil
  `observability`, dashboards Grafana + SLO).
- **SP-11** — lakehouse : CDC→GeoParquet (réplication logique), compaction,
  module DuckDB (`POST /collections/{id}/aggregate`), SQL analyste sandboxé.
- **Storytelling** — mode narratif `story` sur `PageManager`.
- **SP-12** (a→g) — fédération STAC/DCAT : API STAC native, export DCAT-AP,
  moteur de moissonnage + 5 connecteurs (STAC, ArcGIS FS, GetCapabilities
  WMS/WFS/WMTS, CSW/OGC Records, CKAN), garde d'egress SSRF. **A22 complet**.
- **SP-13** — Portails & Sites : `/sites/{slug}`, widgets de contenu, fiche
  dataset + téléchargement. **Jalon M13**.
- **SP-14** (l/m/n/o) — MCP analytique, Bookmarks (5e kind), cross-filter
  inter-datasets, requête visuelle no-code Filtrer→Joindre→Résumer.
  **Jalon M11, SP-14 clos**.
- **SP-15** (a/c/d/e/f/g/h) — pipeline no-code (A39 phases 1+2) : socle
  headless (`kind="pipeline"`, runtime DuckDB, file `etl`,
  `CORE_ETL_ENABLED`), `transform.qgis` en sidecar isolé (allowlist 50 ids),
  coffre de secrets AES-GCM, `reader.connector.rest/postgres` (dlt, garde
  SSRF dédiée), canvas DAG, planification cron. Jalon M14 débloqué depuis par
  **SP-44** (cf. `### Livré` plus bas).
- **SP-16** (a+b) — exports secs CSV/XLSX/GeoJSON/GPKG ; `AlertRule` (8e
  kind, webhook/email sur transition d'état seulement). **Jalon M12** sous
  périmètre resserré — pas de SP-16c.
- **SP-17** (a+b) — worker d'export Playwright + `printLayout` déclarative
  (`CORE_EXPORT_ENABLED`) ; `ReportSchedule` (9e kind) : Bookmark rendu en
  PDF sur cron.
- **3D** — rendu (`kind: "tiles3d"` deck.gl + `MapConfig.terrain`
  raster-dem), puis hébergement de tilesets uploadés (zip S3 jamais extrait,
  proxy authentifié, `CORE_TILESET3D_ENABLED`).
- **SP-18** (a/b/c) — export d'apps : Statique, Connecté (CORS étroit),
  Autoporté (conteneur + snapshot GeoParquet). **Jalon M15**.
- **SP-19** — undo/redo général du builder (`useUndoableDraft`, pile de 50,
  coalescing 400 ms).
- **SP-20** — copilote IA dans le builder : 6 outils MCP allowlistés en
  loopback HTTP réel sur `/mcp`, derrière `CORE_LLM_PROVIDER`. **Jalon
  M16**. Reste : garde d'egress sur l'appel LLM sortant, 4e surface sortante
  sans garde (`REV-096`).
- **Release v0.1.0** — huit images `ghcr.io/tlenenao/geostudio-*` publiées,
  plus aucun `:latest` dans le compose de production résolu.
- **SP-21** — déployabilité : garde-fou `core/tests/test_deployability.py`,
  healthchecks sur 7 services, notices GPL/AGPL embarquées.
- **SP-22** — filet qualité statique : ruff, contrat de couches (30
  entrées), ESLint+Prettier, `mypy --strict` (4 modules), seuils de
  couverture non régressifs, pre-commit + commitlint, CodeQL/gitleaks/
  Trivy/SBOM/Dependabot.
- **SP-23** — agrégats manquants (countDistinct/median/percentile/stddev), 6
  grains temporels, catalogue à 12 types visibles, historique de versions
  (`ConfigHistoryPanel`) sur les cinq éditeurs.
- **SP-24** — carte interrogeable : popups (`PopupConfig`, gabarit CEL) +
  tuiles vectorielles servies par le cœur (`ST_AsMVT` sous `rls_scope`+
  `can()`, plafond 5000 lignes) ; route publique Martin retirée.
- **SP-25** — symbologie déclarative (catégoriel/continu/classé) partagée
  entre l'éditeur de carte et le widget carte.
- **SP-26** — durcissement pré-v0.1 : conteneurs non-root,
  `CORE_AUTH_MODE=mock` refusé hors `CORE_ENV=development`, erreurs RFC
  7807, rate limiting différencié, CSP/Permissions-Policy Report-Only,
  suite E2E sur OIDC réel (`shell/e2e-oidc/`).
- **SP-27** (20 tâches) — symbologie avancée de la carte : contour
  data-driven, opacité, icônes catégorielles (bibliothèque tenant-scoped),
  étiquettes CEL multi-champs, outil de mesure/croquis — éditeur et widget
  carte.
- **SP-28** — symbologie des couches `feature` (URL GeoJSON) :
  `LayerSymbologyEditor`/`LayerPopupEditor` ne retournent plus `null` sans
  `collectionId` ; `LayerPicker` gagne l'ajout par URL GeoJSON.
- **SP-29a** — fondation de la refonte UI (triptyque) : `decide()` extraite
  de `can()`, `ItemRead.permissions` calculé par le cœur, `capabilities.ts`
  (9 domaines dérivés du profil), i18n français seul, `styles/tokens.css`
  (contrat testé), Radix UI retenu pour SP-29b.
- **SP-29b** — kit ~40 primitives UI headless (Radix + tokens) sous
  `shell/src/ui/kit/`, additif à `ui/*` (intouchés), galerie interne
  `/internal/kit-gallery`.
- **SP-30** (a→l, 9 familles + chrome, spec
  `2026-08-29-refonte-ui-triptyque-design.md`) — bascule de tout le shell
  sur `TriptychLayout` : Cartes, Données, Apps & sites, Automatisation
  (Pipelines/Rapports/Requête visuelle), Analytique (SQL Lab),
  Administration (Extensions/Harvest/Collections), et le chrome
  (`ImportFileButton`/`NewItemButton`/`Tileset3DUploadButton` sur
  `ui/kit/Drawer`). Clôturé par **SP-33**.

**Jalons atteints : M1, M2, M4, M5, M11, M12, M13, M14, M15, M16.** M14
débloqué par SP-44 (cf. `### Livré` ci-dessus, `REV-095` clos).

- **SP-31** — rôles à privilèges : 18 privilèges catalogués
  (`app/roles/privileges.py`), 4 rôles prédéfinis immuables par tenant
  (Administrateur/Créateur/Analyste/Lecteur) + rôles sur mesure,
  `User.role_id` remplace `is_analyst` (`is_admin` survit, synchronisé par
  la logique de rôle), `RequirePrivilege` remplace `RequireRole`. **2 des 18
  privilèges (`automation.secrets.manage`, `tasks.view_all`) ne gardent
  encore aucune route (`REV-097`)** — 8 des 10 trouvés par SP-42 ont été
  refermés pendant cette même revue.
- **SP-32** — passerelle `/admin/martin`, `/admin/titiler`, `/admin/grafana` :
  jeton de lancement HMAC (60s, non révocable) → cookie
  `gs_admin_session` (HttpOnly/Secure/SameSite=Strict, premier cookie du
  dépôt) → `forwardAuth` Traefik.
- **SP-33** — `TriptychLayout` : plancher CSS de 360px sur la colonne
  centrale, seuil étroit/large `NARROW_QUERY` relevé à 899px. Clôt SP-30.
- **SP-34** — tokens sémantiques sur `shell/src/map/*` (8 fichiers :
  `LayersPanel`, `MapSymbologyEditor`, `PopupEditor`, superpositions carte…)
  — plus de couleur Tailwind brute hors ambiance.
- **SP-35** — cohérence privilège/`is_admin` : 4 sites migrés de
  `user.is_admin` vers `has_privilege`/`require_privilege`
  (`list_visible_collections`, `CollectionPermissions` read/delete + les
  sous-ressources schema/sharing, `list_extensions`, `admin_tools`).
- **SP-36** — `LayersPanel` : `flex-wrap` sur le `<li>` de couche, le titre
  ne s'écrase plus à largeur nulle.
- **SP-37** — `LayersPanel`/`PopupEditor`/`MapSymbologyEditor` : deux
  offenseurs de largeur (ligne d'ajout de champ, input file d'icône)
  corrigés — la colonne `browse` à 900px ne clippe plus. Clôt le lot
  « Carte » ouvert depuis SP-28.
- **SP-38** — `UsersAdminPage` (`/admin/users`) : sélecteur de rôle par
  ligne, recherche (`GET /users?q=`), pagination.
- **SP-39** — notifications in-app : domaine `app/notifications/` (routes
  inconditionnelles, sans flag), écriture best-effort dans un `try/except`
  **séparé** de celui qui committe le statut du job (patron à respecter
  pour toute future tâche procrastinate), `NotificationBell` dans `TopBar`
  (sondage 45s).
- **SP-40** — pièces jointes sur une entité : domaine `app/attachments/`
  (entre `features` et `collections` dans le contrat de couches), upload
  S3 présigné, lecture en proxy authentifié (`tenant_id` résolu via la
  collection, jamais via l'utilisateur), `MAX_ATTACHMENT_BYTES` 25 Mo,
  popup carte + MCP `list_attachments`. **Piège : `ST_AsMVT(...,
  feature_id_name)` retire une PK entière de `properties` vers `feature.id`
  top-level — tout code qui lit un fid MVT doit lire les deux
  (`f.id ?? properties[pkColumn]`).**
- **SP-41** — licence/métadonnées ouvertes DCAT-AP+STAC par collection (10
  champs), licence/langue par item (2 champs) ; module `app/catalog/`
  (catalogues curatés, zéro dépendance), migration 0033.
- **SP-42** — revue globale du dépôt (spec
  `docs/superpowers/specs/2026-09-04-sp42-revue-globale-design.md`, plan
  `docs/superpowers/plans/2026-09-04-sp42-revue-globale.md`) : matrice de
  fonctionnalités (`docs/revue/2026-09-04-matrice-fonctionnalites.md`),
  analyse des manques (`docs/revue/2026-09-04-analyse-gaps.md`, 79
  `GAP-nn`), backlog unique (`docs/revue/2026-09-04-backlog.md`, 173
  `REV-nnn`), rapport de revue (`docs/revue/2026-09-04-rapport-revue.md`),
  feuille de route révisée
  (`docs/vision/2026-09-04-feuille-de-route-revisee.md`), spec SP-43
  (`docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`),
  `README.md` réécrit, ce `CLAUDE.md` dégonflé. **Fait marquant : le
  critical d'autorisation trouvé par la revue avait déjà été déclaré clos
  trois fois et rouvert trois fois avant elle (REST → MCP →
  terrain3d/tileset3d), puis une 4e fois par la revue elle-même (sweep cron
  des pipelines planifiés, `run_pipeline_sweep_task`) — faute de point de
  passage unique pour l'écriture d'une config. Fermé au point d'écriture
  (`core/app/pipelines/runtime.py::_write_dataset`) ; c'est la motivation
  d'ouverture de la spec SP-43.**
- **SP-44** — débloque le jalon **M14** (GAP-01, seul gap bloquant de SP-42) :
  les 5 tests `@pytest.mark.qgis` exécutés pour la première fois pour de vrai
  contre un sidecar `qgis-worker` réel et un `postgis-test` réel (réseau
  Docker isolé dédié, aucune modification de l'hôte — pas de `sudo`). Ont
  trouvé, en session, **2 défauts de production réels, jamais vus avant faute
  d'avoir jamais exécuté ce chemin** : (1) `_lock_down()`
  (`enable_external_access=false`) bloquait le `COPY TO` du `in.gpkg` du
  sidecar — `transform.qgis` cassait pour toute exécution réelle, corrigé par
  `SET allowed_directories` scopé au seul scratch partagé ; (2)
  `_materialize_qgis_output()` ne filtrait pas `fid` (colonne imposée par la
  spec GeoPackage sur tout `.gpkg` GDAL), rejetée par `writer.collection`
  comme propriété inconnue — invisible via `writer.export` (pas de
  validation de schéma). Un test de régression non marqué `qgis` (donc
  toujours actif en CI) ajouté pour chacun, falsifié avant fix. Suite
  complète (2298 tests hors `qgis`) + les 5 `qgis` rejoués verts après coup.
  **M14 atteint.** Reste : ces 5 tests ne tournent toujours qu'en session
  manuelle, pas encore câblés en CI (`CORE_TEST_QGIS_WORKER_URL` absent de
  tout workflow) — non retenu dans le périmètre de SP-44, à câbler
  séparément si voulu.
- **SP-43** (10 tâches, subagent-driven-development, 2026-09-05) — ferme les
  6 classes de duplication mécanique identifiées par sa spec : registre
  `kind_registry.py::privilege_for_kind()` unique (5 sites réels, pas 4 —
  `terrain3d/routes.py` était un 5e site non documenté, découvert en
  session) ; comparateur `test_model_alembic_parity.py` modèle↔Alembic (24
  `server_default=` manquants corrigés + 8 index/contraintes réels + 4
  index fonctionnels pgvector/trgm filtrés nommément, `REV-175`) ; test
  caractéristique `toFrontLayer()` ; fixture E2E de collection unique
  (`mockCollection()` + `test_collections_json_contract.py`) ; module de
  job partagé `app/jobs/common.py` (6 fichiers, invariant try/except SP-39
  préservé) ; `aria-expanded`/`aria-controls` câblés sur 9 sites via
  `usePanelTrigger`. Puis découpage des 3 fichiers les plus mélangés du
  dépôt : `itemClient.ts` (1743→53 lignes, 15 domaines) + `hooks.ts`
  (732→14 lignes, 11 domaines) ; `mcp/tools.py` (1135 lignes, 21 tools) en
  11 domaines + 3 couches de service **partagées REST↔MCP pour la
  première fois** (`items/service.py`, `configs/service.py`,
  `pipelines/service.py`) ; `pipelines/runtime.py` en registres
  `READERS`/`WRITERS` (corps des fonctions restés dans `runtime.py` par
  nécessité — ~57 `monkeypatch.setattr(runtime, ...)` existants auraient
  cessé de faire effet si déplacés, `registries.py` n'agrège que des
  références). **Invariant critique `_write_dataset`/`Privilege.DATA_MANAGE`
  (rouvert 3× avant SP-42 + 1× par la revue SP-42) vérifié intact
  end-to-end** (REST/MCP/job passent tous par le même point de garde) —
  testé par un nouvel appel direct à `run_pipeline()`, jamais couvert à ce
  niveau avant. La revue finale de branche (croisement entre tâches,
  piège CLAUDE.md n°4) a trouvé 2 Important corrigés : (1) Tâche 9 avait
  recréé la classe de duplication que la Tâche 2 fermait, sur un fichier
  voisin (`configs/routes.py`/`configs/service.py`, 3 gardes dupliquées) ;
  (2) le câblage ARIA de la Tâche 7 utilisait une seule instance de hook
  par page au lieu d'une par ligne sur 3 pages admin (`aria-expanded`
  identique sur toutes les lignes dès qu'une était en édition). Un défaut
  réel supplémentaire trouvé et corrigé **dans** la Tâche 9 elle-même :
  `create_item` (MCP) dérivait silencieusement son `resource_type` depuis
  `config.kind` (plus large, jamais vérifié égal) au lieu du `kind` typé du
  tool, via le nouveau service partagé — gardé par un check explicite.
  Écart pré-existant trouvé et **documenté sans être corrigé** (règle du
  plan, jamais de correction silencieuse d'un écart accidentel outil↔route) :
  `save_app_config` (MCP) saute les 7 validateurs par kind + 2 gardes de
  capacité que la route REST équivalente exécute (`REV-174`). Suite finale :
  core 2326 passed/5 skipped (qgis, sidecar absent de cette session,
  jamais affirmés passés — déjà vérifiés réels par SP-44)/0 failed ; shell
  1944 tests/225 fichiers ; E2E 141 passed/4 skipped/1 échec **préexistant
  à tout ce plan** (confirmé en checkoutant le commit d'avant la Tâche 1 —
  `e2e/pipeline-builder.spec.ts:111`, sans rapport, non corrigé, hors
  périmètre).
- **SP-51** — parité carte App Builder / éditeur autonome (9 tâches, spec
  `docs/superpowers/specs/2026-09-05-sp51-parite-carte-design.md`) : GAP-46
  déjà résolu (vérification seule, aucun code touché) ; GAP-53 (outils de
  mesure/croquis montés en édition, `interactiveTools` sur `MapEditorPage`) ;
  GAP-35 (contrôle d'opacité raster) ; GAP-52 3 jumelles réelles fermées
  (basemap/terrain/caméra sur le widget carte de l'App Builder, réutilisant
  `BasemapSelect`/`TerrainPanel`/`CameraControls` — la 5e jumelle annoncée,
  palette theme-primary, était déjà implémentée, retirée du périmètre par
  la spec) ; GAP-45 (éditeur JSON replié pour `layer.paint`, mode avancé) ;
  GAP-52 Jenks (`ItemClient.sampleDataSourceField()`, symétrique de
  `queryDataSource`, résout un `collectionId` depuis un `DataSource`) ;
  GAP-36 (UI d'auteur pour une couche `deck` — création dans `LayerPicker`,
  réglages `radiusPixels`/`radius`/`elevationScale` dans `LayersPanel`).
  **Écart corrigé par rapport au texte du plan (piège CLAUDE.md n°3)** : la
  Tâche 9 proposait un contrôle de rayon unique partagé heatmap/hexbin —
  faux contre les `.d.ts` deck.gl réels (`HeatmapLayer.radiusPixels` ≠
  `HexagonLayer.radius`), corrigé en 3 contrôles distincts. `npm run build`
  (jamais exécuté avant la revue finale du plan) a aussi trouvé 2 erreurs
  tsc réelles introduites par la Tâche 9 (lecture non affinée de
  `MapLayer.props`, `StaticItemClient` non mis à jour pour la nouvelle
  méthode `ItemClient`), corrigées par un commit séparé. Suite finale :
  shell 225 fichiers/1962 tests ; E2E 141 passed/4 skipped/1 échec
  préexistant (`e2e/pipeline-builder.spec.ts:111`, sans rapport). Ce plan
  ne touche pas `shell/src/api/base.ts` (chevauchement anticipé par les deux
  specs avec SP-54, mais son seul point de contact possible — GAP-46 —
  était déjà résolu, donc sans impact) et
  n'ajoute qu'une méthode additive à `shell/src/api/types.ts`
  (`sampleDataSourceField`) — vérification croisée de l'absence de
  collision réelle avec SP-54 faite à la clôture de ce dernier.
- **SP-54** — surfaces API shell (ItemClient) + partage avancé (7 tâches,
  spec `docs/superpowers/specs/2026-09-05-sp54-itemclient-api-design.md`),
  exécuté après SP-51 (même recommandation de séquencement que les deux
  specs documentaient) : GAP-38 (schéma JSON `AppConfig` factorisé dans
  `app_config_json_schema()`, source unique pour la route REST et la
  ressource MCP, garantie identique par un test dédié ;
  `ItemClient.getAppConfigSchema()` lui donne un premier consommateur
  shell réel) ; GAP-65 1/3 (`getMe()` lit `id`/`email`/`tenantId`/
  `capabilities`, `capabilities` réutilise le type `InstanceInfo` déjà
  exporté plutôt qu'un doublon de type) ; GAP-65 2/3 (TTL de 5 min +
  `ItemClient.invalidateDatasetCache(pk?)` sur `datasetCache`, sans
  changer son type public ni les deux call sites existants) ; GAP-40/47
  volet collections (`listCollections(params?)` relaie `q`, champ de
  recherche sur `CollectionsAdminPage`, outil MCP `search_collections`) ;
  GAP-47 reste (`query_features` MCP relaie désormais `geomIntersects`,
  falsifié par une paire de tests point-qui-intersecte/point-qui-
  n'intersecte-pas) ; GAP-42/65 groupes (`createGroup`/`addGroupMember`
  côté `ItemClient`, `create_group`/`add_group_member`/`list_groups` côté
  MCP, section dédiée dans `ShareForm.tsx`, `READ_ONLY_TOOLS` mis à jour
  dans le même commit que le garde `is_read_only_mode()` des deux
  nouveaux tools) ; GAP-12 (liens de partage à échéance — nouvelle table
  `share_link`, migration 0035 testée upgrade/downgrade/upgrade sur base
  non vide, jeton HMAC `share_links.py` calqué sur `export_tokens.py`
  avec le premier mécanisme de révocation-avant-expiration de ce dépôt,
  4 routes REST dont la résolution publique `GET /share-links/{token}`
  sans dépendance `get_current_user`, section « Liens à échéance » dans
  `ShareForm.tsx`).
  **Écarts trouvés par rapport au texte du plan (piège CLAUDE.md n°3)** :
  (1) `search_collections` et `list_groups` (MCP) sont les deux premiers
  tools de ce dépôt à retourner une liste nue — vérifié empiriquement que
  FastMCP sérialise `content[0].text` comme l'élément unique (pas un
  tableau JSON) quand un seul résultat matche ; les tests concernés lisent
  `structuredContent["result"]`, forme fiable quel que soit le nombre
  d'éléments. (2) Le plan ne listait que 3 routes pour GAP-12
  (create/revoke/resolve) mais le besoin shell (`listShareLinks`) impose
  une 4e route GET liste, ajoutée avec le même garde d'autorisation.
  (3) `ShareLink.expires_at` (colonne `DateTime` naïve, cohérente avec le
  reste d'`app/sharing/models.py`) renvoie un datetime naïf à la lecture
  même après y avoir écrit une valeur aware — comparer directement à
  `datetime.now(UTC)` lève `TypeError`, corrigé par un helper de
  comparaison locale au repository. Consommation anonyme complète d'un
  lien de partage (rendu de l'app/carte pour un visiteur sans compte)
  restée hors périmètre explicite, comme documenté par la spec.
  Suite finale : core 2357 passed/5 skipped (qgis)/0 failed ; shell 225
  fichiers/1979 tests ; E2E 141 passed/4 skipped/1 échec préexistant
  (`e2e/pipeline-builder.spec.ts:111`, sans rapport, même échec que celui
  déjà mesuré à la clôture de SP-51). Diff `openapi.json`/
  `core-schema.d.ts` non vide et cohérent avec les 4 nouvelles routes de
  liens de partage (Tâches 1 et 4 : diff vide, attendu, aucune route
  REST créée par ces deux tâches). Aucune collision réelle avec SP-51 sur
  `shell/src/api/base.ts`/`types.ts` : vérifié après coup, les deux jeux
  d'ajouts additifs coexistent dans les mêmes fichiers sans conflit
  (`sampleDataSourceField` de SP-51 et les méthodes de SP-54 sont des
  entrées distinctes de l'interface `ItemClient`, `invalidateDatasetCache`
  est la seule méthode de SP-54 dans `base.ts`, jamais touché par SP-51).

### Conventions tranchées (2026-09-01)

- **Hauteur des contrôles de formulaire** : `h-9` par défaut (aligné
  `Button size="default"`, `ui/kit/Input`/`Select`) ; `h-8` réservé aux
  contextes explicitement denses. Contrôles natifs encore en `h-8` ad hoc
  non corrigés rétroactivement — à migrer à l'occasion.
- **`<button>` natif vs `Button` du kit** : `Button` pour toute action
  autonome (variant selon son rôle) ; `<button>` natif réservé à un lien
  inline dans une phrase, ou une action répétée par ligne dans une liste
  dense.
- **`aria-expanded`/`aria-controls`** : obligatoire sur tout déclencheur de
  panneau en ligne — jamais posé rétroactivement, reste ouvert (backlog
  `REV-088`).

La dette de tokens `LayersPanel`/`MapSymbologyEditor` et voisins évoquée par
cette décision a été fermée par SP-34 (cf. `### Livré` ci-dessus).

### Suivis et dette non bloquante

Le détail complet (43 trouvailles confirmées non corrigées, 35 minor, 79
gaps, la dette héritée SP-29b→SP-40, et 2 trouvailles SP-43 documentées sans
être corrigées) vit dans **`docs/revue/2026-09-04-backlog.md`** (175
entrées `REV-nnn`, numérotation stable et citable — ne pas renuméroter,
ajouter en fin de section). Ce qui, dans ce backlog, change le comportement
immédiat d'une session :

- Jalon **M14 atteint** (SP-44, `REV-095` clos) : les 5 tests
  `@pytest.mark.qgis` tournent contre un vrai sidecar — 2 défauts de
  production réels trouvés et corrigés au passage (`_lock_down()` bloquait
  `transform.qgis`, `fid` GeoPackage non filtré). Reste non câblé en CI
  (session manuelle uniquement).
- Egress LLM du copilote (SP-20) sans garde SSRF — seule des 4 surfaces
  sortantes à ne pas en avoir une (`REV-096`).
- 2 des 18 privilèges (`automation.secrets.manage`, `tasks.view_all`) ne
  gardent encore aucune route (`REV-097`).
- `aria-expanded`/`aria-controls` : câblé par SP-43 sur 9 sites via
  `usePanelTrigger` (`REV-088` largement fermé — reste à vérifier au cas par
  cas sur tout futur déclencheur de panneau en ligne créé après SP-43, la
  convention n'est pas outillée par un lint automatique).
- Restauration de sauvegarde : runbook rejoué une fois, succès partiel —
  données confirmées, reconnexion OIDC réelle jamais vérifiée (`REV-164`,
  détail aussi ci-dessous).
- `save_app_config` (MCP) saute les 7 validateurs par kind + 2 gardes de
  capacité qu'exécute la route REST équivalente — pré-existant, trouvé et
  documenté (pas corrigé) par SP-43 (`REV-174`).
- 4 index fonctionnels pgvector/trgm non représentés dans `Base.metadata`,
  filtrés nommément par le comparateur modèle/Alembic de SP-43 (`REV-175`).
- Questions produit ouvertes (comparatif §8) : Q2 (premiers utilisateurs
  réels — la seule qui puisse réordonner le phasage), Q10 (temps réel,
  `REV-108`), Q11 (offline, `REV-120`).

### Suivis non bloquants — ce qu'il faut savoir avant de toucher la stack

Contexte détaillé par SP dans l'archive. Ce qui change le comportement d'une
session, sur la stack et l'environnement de dev :

- **Stack par défaut vérifiée de bout en bout (2026-08-29)** : les 11
  services démarrent tous `healthy` (`docker compose up -d`, image
  `core`/`worker`/`cdc-worker` reconstruite). `libexpat.so.1` manquant pour
  `defusedxml` (`app/mapicons/svg.py`, `app/harvest/connectors/ows.py`)
  était réel (`python:3.12-slim`/Debian trixie n'embarque plus `libexpat1`
  par défaut) — corrigé dans `core/Dockerfile` (`apt-get install
  libexpat1`), corrige les trois images qui partagent ce Dockerfile.
- **`pg-data` / démarrage à blanc** : `core` applique déjà `alembic upgrade
  head` avant `uvicorn` (idempotent) — pas de correctif de plus à apporter
  là. Un `core` qui crash-loop avec `shell` restant `Created` vient
  typiquement de `CORE_SECRETS_MASTER_KEY` vide dans `.env` (gardes
  SP-15e/SP-26). **La vraie cause n'était pas un `.env` plus ancien** :
  `scripts/bootstrap-env.sh` ne générait jamais cette clé — corrigé par
  SP-42 (`openssl rand -base64 32`). Si `shell` reste `Created` : vérifier
  `docker logs core` avant de soupçonner `pg-data`.
- **Martin (:3000 hôte) en conflit de port** : pas une panne du dépôt — un
  process déjà présent sur la machine de l'opérateur (ex. un `node.exe`
  Windows côté hôte WSL2, invisible de `ss` côté Linux) fait échouer le
  port-forwarding de Docker Desktop. Corrigé de façon pérenne en déplaçant
  le mapping hôte vers `3010` (`docker-compose.yml`).
- `deploy/postgis/Dockerfile` + `pg_hba.conf` (non commités) sont **inertes** —
  Postgres lit `$PGDATA/pg_hba.conf`. Ne pas les câbler : ils affaibliraient
  `scram-sha-256` en `md5`.
- **CSP en Report-Only**, jamais basculée en enforcing : 4 bloqueurs concrets
  documentés en commentaire dans `docker-compose.prod.yml`.
- **Restauration de sauvegarde** : un runbook existe
  (`docs/runbooks/2026-07-24-restauration-sauvegardes.md`) et a été rejoué
  une fois avec succès partiel — survie des données prouvée (psql +
  `GET /items/{id}`), mais la reconnexion via un vrai flux OIDC/Keycloak
  n'a jamais été vérifiée (l'exercice substituait `CORE_AUTH_MODE=mock`) ;
  aucune automatisation, non rejoué depuis (avant SP-31/SP-32). Détail :
  `docs/revue/2026-09-04-backlog.md` (`REV-164`).
- **Conteneur `postgis-test` non tracké par Alembic** : après une migration
  qui ajoute des colonnes, un `ALTER TABLE` manuel est nécessaire sur ce
  conteneur, sinon des dizaines de tests échouent en cascade sur
  `UndefinedColumn` sans rapport avec le code sous revue (vécu SP-39,
  SP-40, SP-42).
- Rate limiter (SP-26/3.4) clé sur l'en-tête `Authorization` brut : budget « par
  jeton », donc réinitialisé à chaque rafraîchissement OIDC.
- Ne **pas** réintroduire `dependency-type` sur l'entrée Dependabot `uv` :
  l'option y est silencieusement ignorée par GitHub, pas rejetée.
- Une vraie clé privée `age` de test subsiste dans l'historique public (commit
  `0b4733a`, redactée depuis, absente de `HEAD`) — à confirmer jetable ou
  rotationner. `secret_scanning`/`dependabot_security_updates` sont
  **désactivés** sur ce dépôt.
- Couverture shell : mesurer **après** nettoyage de `dist/`/`dist-export/` — la
  config `vitest` de ce dépôt compte ces artefacts gitignorés comme source non
  couverte (piège documenté 4 fois).
- Régénération OpenAPI/TS : la commande nue échoue, il faut l'incantation réelle
  de `ci.yml` (`PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY` de test).

## Pièges récurrents de ce dépôt (classes de défauts déjà payées plusieurs fois)

1. **Régénérer la spec OpenAPI et les types TS** dès qu'une route ou un modèle
   change — classe d'oubli la plus fréquente du dépôt (≥5 occurrences, chaque
   fois trouvée en revue finale). Diff **vide** attendu, et légitime, quand la
   surface est derrière un flag éteint en CI.
2. **Livré + testé + mergé ≠ câblé.** Vérifier `docker compose config` **par
   valeur** (la variable est-elle dans l'`environment:` du bon service ?) — 5
   occurrences, dont une capacité entière inactivable en pratique
   (`CORE_ETL_ENABLED`), et une variable documentée dans `.env.example` qui
   donnait l'illusion du câblage. `core/tests/test_deployability.py` outille
   désormais cette classe (19 règles, 35 tests avec les paramétrages).
3. **Le texte littéral d'un plan ou d'un brief est régulièrement faux** sur les
   interfaces tierces : knobs d'action GitHub, ids d'algorithmes QGIS,
   commandes de sonde de healthcheck, signatures de fonctions, formes de
   schémas d'outils LLM. Vérifier contre la **source réelle** (l'image, le code
   du paquet, un conteneur qui tourne) — jamais contre la doc ou la mémoire.
   Corriger sans re-demander, en le consignant.
4. **Revue par tâche ≠ revue finale de branche.** Les défauts de croisement
   entre tâches (un garde-fou écrit sur une surface et jamais reporté sur sa
   jumelle, un chemin de lecture qui ne round-trippe pas un nouveau champ, un
   validateur ouvert par un élargissement voisin) ne sont visibles qu'à la
   revue de branche. Faire les deux, systématiquement.
5. **Chemin de lecture oublié** : un nouveau champ de config doit être ajouté à
   `toFrontLayer()` dans `shell/src/api/itemClient.ts`, sinon il ne survit pas
   à un rechargement (déjà arrivé pour `popup`, puis pour `symbology`).
6. **Lancer la suite E2E complète avant de clore un plan** : plusieurs
   régressions cross-tâches (mock périmé, changement cassant non propagé) n'ont
   été trouvées qu'à la première exécution complète, en toute fin de plan.
7. **Une assertion de durée ne prouve jamais une propriété de concurrence** —
   elle mesure la machine. Mesurer le recouvrement des intervalles.
8. **Tester une migration sur base non vide**, dans les deux sens : plusieurs
   `downgrade()` ne passaient que parce que la CI teste sur base vide.
9. **Sessions concurrentes sur le même arbre** : Tanguy en lance parfois
   plusieurs. Nommer les ledgers `.superpowers/sdd/sp<XX>-*`, jamais
   `task-N-report.md` générique — une contamination de rapport a déjà été
   observée.
10. **jsdom n'implémente pas plusieurs API navigateur consommées par Radix
    UI** (`ResizeObserver`, `hasPointerCapture`, `scrollIntoView`,
    `PointerEvent`) et ne fait jamais converger le repositionnement
    `shift`/`flip` de `@floating-ui/react-dom` (Popover/Select/Combobox/
    Menu/Tooltip) — stub/polyfill toujours **local au fichier de test**
    (jamais `shell/src/test/setup.ts` : un stub global y a cassé 2 tests
    sans rapport ailleurs, SP-29b/Task 8). **Un correctif de filet de test
    doit être vérifié par falsification** (injecter délibérément le défaut
    visé, confirmer que le test échoue, puis retirer) — « les tests
    passent toujours » ne prouve rien : sur SP-29b, un correctif qui
    semblait réparer `expectTokenizedClasses()` sur 7 fichiers ne
    vérifiait en réalité toujours rien sur 3 d'entre eux après le premier
    passage (baseElement pointant sur un `container` custom, contenu
    vérifié après démontage, contenu jamais ouvert).
11. **Un `grep` sur un mot ne prouve pas l'absence d'un comportement** quand
    le dépôt route par des primitives partagées (`Gate`, `hasPermission`,
    `require_privilege`) — une notation de la revue SP-42 s'est trompée
    ainsi en cherchant un nom de garde littéral plutôt qu'en suivant l'appel
    réel. Vérifier le chemin d'exécution, pas seulement le vocabulaire.
12. **Le récit prime trop souvent sur le code.** Pendant la revue SP-42,
    plusieurs agents — et le contrôleur lui-même — ont affirmé un état du
    dépôt démenti par une lecture directe du fichier. `CLAUDE.md`, les specs
    et les plans sont des récits d'intention, jamais une source de vérité :
    revérifier dans le code avant d'écrire qu'un point est réglé ou ouvert.
