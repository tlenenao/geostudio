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
  verte (dernière mesure après intégration de SP-45/46/47/49/52/53/55/56/58/
  51/54, 2026-09-06 : 156 passed / 4 skipped / **1 failed** —
  `e2e/pipeline-builder.spec.ts:111`, timeout sur le bouton « Exécuter »,
  confirmé préexistant à SP-43 en checkoutant le commit d'avant sa Tâche 1 ;
  cause non encore investiguée, ne pas imputer à un futur travail sans
  vérifier d'abord si ce test échoue déjà sur `dev`).
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
npm run test         # Vitest — dernier compte mesuré après intégration
                     # complète de SP-45/46/47/49/52/53/55/56/58/51/54
                     # (2026-09-06) : 235 fichiers, 2064 tests, tous passed.
                     # Couverture 90,51 % (seuil 88).
npm run e2e          # Playwright — 156 passed / 4 skipped / 1 failed à la
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
uv run pytest        # dernier compte mesuré après intégration complète de
                     # SP-45/46/47/49/52/53/55/56/58/51/54 sur dev
                     # (2026-09-06) : 2589 passed / 5 skipped / 0 failed,
                     # couverture 94,05 % (seuil 85), sur un conteneur
                     # postgis-test réel (CORE_TEST_DATABASE_URL positionné —
                     # sinon ~185 tests marqués postgis skippent silencieusement,
                     # piège vécu pendant la clôture de SP-43 elle-même). Piège
                     # vécu par SP-42 : ce conteneur n'est PAS tracké par Alembic —
                     # après une migration qui ajoute des colonnes, il faut un
                     # ALTER TABLE manuel, sinon des dizaines de tests
                     # échouent en cascade sur UndefinedColumn sans rapport
                     # avec le code sous revue. Les 5 skips = marqueur qgis
                     # (sidecar réel requis). Piège supplémentaire vécu à la
                     # clôture de SP-49 : 2-3 sessions concurrentes lancées
                     # sur des worktrees différents mais un même conteneur
                     # postgis-test partagé produisent des dizaines
                     # d'échecs/erreurs par collision (UniqueViolation sur
                     # tenants_pkey, DuplicateTable) — aucun rapport avec le
                     # code sous revue, confirmé en rejouant chaque test en
                     # isolation (repasse au vert systématiquement une fois
                     # la contention retombée). Deux échecs INTERMITTENTS
                     # déjà documentés, à ne pas imputer à son propre travail
                     # sans vérifier : test_features_rls.py::
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
  privilèges (`automation.secrets.manage`, `tasks.view_all`) ne gardaient
  encore aucune route** — 8 des 10 trouvés par SP-42 ont été refermés
  pendant cette même revue ; les 2 restants (`REV-097`) fermés par **SP-47**
  (cf. `### Livré` plus bas).
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
- **SP-47** — ferme `REV-097` (les 2 des 18 privilèges sans route) et
  `GAP-71`/`GAP-28` (`audit_log` en écriture seule, aucune vue d'usage) par
  une seule construction : `require_any_privilege` (OR de privilèges,
  `app/roles/guards.py`) ; garde de `/secrets` élargie à
  `automation.secrets.manage` **OU** `admin.secrets.manage` ; rôle Créateur
  gagne `automation.secrets.manage` (**décision produit à confirmer par
  Tanguy a posteriori** — appliquée par défaut par la spec/le plan, cf.
  décision §2.2 de la spec) ; nouveau domaine `app/usage/` (query-only sur
  `audit_log`, jamais d'écriture — `app.audit.writer` reste l'unique point
  d'écriture), `GET /usage/tasks` (`tasks.view` restreint à soi,
  `tasks.view_all` = tenant entier) et `GET /usage/summary` (agrégats
  activité-par-acteur + popularité-des-ressources, `tasks.view_all` seul) ;
  `UsagePage` remplace `TasksComingSoonPage` sur `/tasks`. 3 fixtures miroir
  du rôle Créateur trouvées et resynchronisées au-delà des 2 listées par le
  plan (`DEFAULT_ME` e2e/mocks.ts, `BASE_PROFILE` DomainBar.test.tsx) — un
  4e mirroir (`BUILT_IN_ROLE_PRIVILEGES["creator"]` lui-même dans
  `test_roles_guards.py`/Task 1) a dû être corrigé en cours de plan : le
  test `require_any_privilege` de la Tâche 1, écrit avant la Tâche 2,
  utilisait un `creator` par défaut comme témoin « ne porte aucun des deux
  privilèges » — cassé par la Tâche 2, corrigé en réassignant ce témoin au
  rôle `reader` (zéro privilège). `lint-imports` : `app.usage` placé
  au-dessus d'`app.roles`, aucune exemption nommée nécessaire. Suite
  finale : core 2340 passed/5 skipped (qgis)/0 failed (postgis-test réel,
  2 défauts d'environnement trouvés et corrigés en session — colonnes
  SP-41/SP-42 manquantes sur ce conteneur, tables de jobs pipeline
  résiduelles d'un run précédent) ; shell 226 fichiers/1952 tests ; E2E 143
  passed/4 skipped/1 échec préexistant (`pipeline-builder.spec.ts:111`,
  inchangé).
- **SP-49** (7 tâches, 2026-09-06) — ferme GAP-56/63/64/76 (revue SP-42),
  explicitement laissés hors périmètre de SP-43 : `downgrade()` de la
  migration 0024 (report_runs.export_job_id) devient un no-op documenté
  (retendre la contrainte NOT NULL était irrécupérable sur toute base
  ayant une ligne `NULL`, situation normale de fonctionnement) ; index
  manquants sur `alert_evaluations`/`pipeline_runs` (migration 0035) ;
  batching des 3 balayages cron (`get_latest_runs_for_items`/
  `get_latest_evaluations_for_items`, fenêtre `ROW_NUMBER() OVER`, une
  requête au lieu d'une par pipeline/alerte/rapport) ; N+1 de
  `GET /harvest/layers`/`feature-layers` fermé sur le patron de
  `_permissions_by_id` (`get_access_facts_by_ids` + `decide()` en mémoire) ;
  `get_job`/`mark_running` déplacés dans le bloc `try` d'export/appexport
  (patron pipelines/ingestion, invariant SP-39 préservé) ; reprise
  périodique des jobs appexport (`reclaim_stuck_jobs` existait, jamais
  appelée) et ingestion (nouvelle, ancrée sur `updated_at` faute de
  `started_at` dédié) ; `scripts/healthcheck_worker_stalled.py`
  (`JobManager.get_stalled_jobs`, `async` sur cette version verrouillée
  3.9.0, encapsulé `asyncio.run`) chaîné sur `worker`, seule sonde sur
  `export-worker` (aucune avant), `pgrep -f server.py` sur `qgis-worker`
  (aucune avant, pas de route HTTP de vivacité côté sidecar, hors
  périmètre d'en ajouter une). **Revue finale de branche (piège CLAUDE.md
  n°4) a trouvé un vrai croisement Tâche 2/Tâche 3** : l'index créé
  `(tenant_id, <item>_id, created_at)` est ignoré par le batching de la
  Tâche 3 (`WHERE <item>_id IN (...)` sans `tenant_id`, cross-tenant par
  construction) — mesuré par `EXPLAIN ANALYZE` à échelle réaliste (2000
  items, 300k runs, 2,5% sélectivité) : Seq Scan avant correction (28,6ms),
  Bitmap Index Scan après réordonnancement `<item>_id` en tête (7,2ms, 4x),
  sans rien coûter aux requêtes tenant_id+item_id existantes. Suite finale
  (contention réelle mesurée : 2-3 sessions concurrentes sur le même
  `postgis-test` partagé pendant cette clôture, cf. piège n°9 — chaque
  échec de la première passe re-vérifié en isolation, confirmé transitoire
  à chaque fois) : 2348 passed/5 skipped/0 failed. Reste hors périmètre,
  assumé : N+1 de `configs_repo.list_configs_by_kind` sur
  `_latest_revision` (trouvaille annexe, jamais assignée à ce plan),
  pagination complète GAP-57, montée de version procrastinate future
  (`nb_seconds` déprécié sur `get_stalled_jobs`).

- **SP-46 — découvrabilité : navigation manquante** (5 tâches, spec
  `docs/superpowers/specs/2026-09-05-sp46-navigation-manquante-design.md`,
  plan `docs/superpowers/plans/2026-09-05-sp46-navigation-manquante.md`)
  — ferme GAP-30/GAP-32/GAP-39/GAP-67 identifiés par l'analyse de gaps
  SP-42 : quatre écrans complets et gardés côté serveur mais atteignables
  uniquement en tapant leur URL à la main deviennent atteignables par un
  lien réel : `AdminExtensionsPage.tsx` gagne un tableau `ADMIN_LINKS`
  (déclarations `{to, label, privilege}`) filtré par
  `useMe().data?.privileges`, remplaçant les cinq `<Link>` — trois
  historiques (`/admin/infrastructure`, `/admin/roles`, `/admin/users`,
  jusqu'ici affichés sans garde, GAP-67) et deux nouveaux
  (`/admin/collections` GAP-30, `/admin/harvest` GAP-39, gardés dès leur
  introduction) — doctrine identique à `capabilities.ts` : un privilège
  manquant masque le lien, jamais ne le grise. `CatalogPage.tsx` gagne un
  lien conditionnel `type === "pipeline" && !fixedType` vers `/reports`
  sous le sélecteur de type (GAP-32, atterrissage du domaine
  Automatisation uniquement — jamais sur `/`, `/bookmarks`, `/reports`
  lui-même ou toute autre vue à `fixedType` fixé), sans garde de
  privilège (`/reports` n'est protégée par aucun `RequirePrivilege`).
  Aucun changement côté cœur (les quatre routes gardent exactement leur
  garde/absence de garde déjà en vigueur) — diff OpenAPI/types TS vide,
  vérifié. TDD strict : chaque test de masquage falsifié avant
  correctif — en particulier GAP-67, où lancer la suite existante
  **avant** correctif confirme que les deux tests `/admin/roles`/
  `/admin/users` passaient déjà sans mocker aucun privilège (preuve
  directe du bug), et où introduire `visibleLinks.map()` à côté des
  liens en dur (transitoire, Tâches 1-2) produit une vraie duplication
  observée (`getByRole` échoue en « multiple elements found ») une fois
  les tests réécrits avec un privilège mocké — écart au texte du plan
  (qui prédisait ces deux tests déjà verts à ce stade), refermé par le
  Step suivant du plan lui-même (bascule complète vers `ADMIN_LINKS`,
  suppression des `<Link>` en dur). `shell/e2e/admin-collections.spec.ts`
  contenait déjà un test couvrant un scénario proche (non-admin, message
  de refus sur navigation directe) — sans rapport direct avec le lien de
  découverte depuis `AdminExtensionsPage`, mais confirmé non régressé.
  Suite shell complète : 224 fichiers / 1908 tests, 0 échec ; couverture
  90,30 % (seuil 88) ; `npm run build` propre ; E2E ciblée (8 specs
  nommées par le plan) 10/10 ; E2E complète sans régression de compte
  (piège n°6).
- **SP-45 — durcissement sécurité immédiat** (5 tâches, spec
  `docs/superpowers/specs/2026-09-05-sp45-durcissement-securite-design.md`,
  plan `docs/superpowers/plans/2026-09-05-sp45-durcissement-securite.md`)
  — garde d'egress SSRF sur l'appel LLM sortant du copilote (GAP-02,
  `app/copilot/egress.py`, patron des 3 gardes d'egress déjà existantes) ;
  retrait de `MARTIN_SECRET`, réglée mais jamais consommée par `martin`
  (GAP-41) ; rate-limit dédié sur `POST /collections/empty` (GAP-58) ;
  rate limiter — clé anonyme par IP réelle (`ProxyHeadersMiddleware`,
  requis puisque `core` n'est jamais exposé directement, seul Traefik
  l'est), 2 routes ArcGIS live-query rattachées au groupe `harvest`,
  sweep périodique du cache module-global (GAP-61) ; `restart:
  unless-stopped` sur `traefik`, seul service durablement actif à en
  être dépourvu (GAP-79). GAP-77 (purge d'historique git de la clé
  privée `age` de test) et GAP-78 (réglages sécurité GitHub) — les deux
  seules tâches destructrices/production du plan — laissées en attente
  d'un accord explicite, **puis exécutées séparément après confirmation
  de Tanguy** : `git filter-repo --replace-text` sur un clone miroir,
  vérifié absent de `HEAD` et de tout ancêtre de branche avant
  force-push des 26 branches d'origin (2 branches Dependabot apparues
  entre le clone miroir initial et la vérification finale ont nécessité
  un second passage, capturées à temps) ; `secret_scanning`/
  `secret_scanning_push_protection`/`dependabot_security_updates` bascu-
  lés à `enabled` via `gh api`. Suite finale (avant la purge, revérifiée
  identique après réintégration du contenu sur le nouveau `dev` purgé) :
  cœur 2022 passed/178 skipped/0 failed.
- **SP-52** (8 tâches, subagent-driven-development, 2026-09-06) — ferme 5
  manques d'UX du builder d'App identifiés par SP-42 : retrait du code mort
  `moveItem`/`resizeItem`/`styleFor` (GAP-33) ; suppression d'un widget
  depuis le canevas (bouton + `Delete`/`Backspace`, `GridCanvas.onRemoveItem`
  désormais obligatoire, GAP-66a) ; suppression d'une variable (GAP-66c) —
  toutes deux purgent désormais `config.messages` de tout câblage
  `ActionsPanel` orphelin via une fonction pure partagée
  (`actionMessages.ts::pruneMessagesForIds`, posée en tâche dédiée avant ses
  deux consommateurs pour ne pas écrire la même règle deux fois) ; `setFilter`
  du copilote fusionne désormais la requête au lieu de la remplacer (GAP-66b,
  symétrique de `DataSourcePanel::patchQuery`) ; le widget Onglets affiche le
  contenu réel de l'onglet actif sur le canevas principal en édition, pas
  seulement un bandeau vide (GAP-54) ; éditeur d'enregistrements JSON pour
  les sources de données Statique (GAP-51) ; nouveau widget builtin
  `variableInput`/« Saisie » lisant et écrivant directement une variable
  typée par son `id` stable (jamais son `name` renommable), nouveau hook
  `useVariableDefs()` sur `VariablesContext.tsx` + prop optionnel
  `variables?: Variable[]` threadé sur `PropsPanel`/`LayoutEditor` et les 3
  widgets conteneurs (GAP-13, chantier 4.24). **Limitation connue laissée
  telle quelle** (spec §3.1) : le canevas principal du widget Onglets en
  édition prévisualise toujours le premier onglet (`activeId` interne au
  `Component`, bandeau non cliquable) — indépendant de l'onglet sélectionné
  dans le panneau Propriétés ; l'édition du contenu reste au panneau
  Propriétés, cette tâche n'ajoutait qu'un aperçu. Falsification exécutée
  systématiquement sur les filets ajoutés : un premier test E2E GAP-54 s'est
  révélé vacuo (le texte du panneau Propriétés faisait déjà matcher
  l'assertion) et a dû être re-scopé sur `<main>` ; de même le test de purge
  de câblage à la suppression de widget (visuel seul) ne détectait pas
  l'absence réelle de purge — corrigé en asserttant sur l'objet
  `saveAppConfig` plutôt que sur l'affichage (`ActionsPanel.
  resolvesOnThisPage` masque déjà visuellement un message orphelin, purgé ou
  non). Effet de bord cross-tâche trouvé par la suite complète (pas par
  tâche) : le nouveau widget porte le catalogue à 23 types, `addWidget`'s
  enum copilote (`clientTools.test.ts`) avait un compte figé à 22, corrigé.
  Suite finale : shell 227 fichiers/1964 tests, tous passés ; E2E 146
  passed/4 skipped/1 échec **préexistant, sans rapport**
  (`e2e/pipeline-builder.spec.ts:111`, cf. entrée SP-43) ; diff OpenAPI/types
  TS vide (plan shell-only, vérifié plutôt que supposé). Aucun fichier
  `core/` touché.
- **SP-56** — formats d'import manquants (GAP-09/GAP-29, chantier 4.14) :
  XLSX (`parse_xlsx_latlon`, même contrat que le CSV, coercition
  `datetime`→`isoformat()` — openpyxl rend des types Python natifs par
  cellule, contrairement au CSV où tout est déjà une chaîne), KML/KMZ
  (`parse_kml`, réutilise `_read_features` tel quel — GDAL/pyogrio lit KML
  nativement, driver LIBKML ; `.kmz` se lit **directement**, sans le
  préfixe `/vsizip/` qu'exige `.zip` Shapefile), GeoParquet
  (`parse_geoparquet`, via `geopandas.read_parquet` — **pas** `pyogrio`,
  aucun driver Parquet dans ce build ; aller-retour testé contre
  `app.cdc.parquet_writer.write_geoparquet`, SP-11). Aucune nouvelle
  dépendance (`pyogrio`/`geopandas`/`pyarrow`/`openpyxl` déjà présentes).
  `POST /uploads/inspect` gagne `InspectResponse.fields` (XLSX) ;
  `ImportFileButton.tsx` accepte les 9 extensions, nouvelle phase
  `selecting-latlon` (parallèle à `selecting-layer`, sans re-upload).
  **2 défauts réels trouvés par exécution, absents du texte du plan**
  (piège CLAUDE.md n°3) : (1) une géométrie manquante revient de
  `geopandas.read_parquet()` en `NaN` (float), pas en `None` — le
  pseudo-code de la spec ne testait que `is None` ; (2) le driver KML de
  GDAL impose un champ `"id"` sur **tout** Placemark (même minimal, sans
  schéma personnalisé) — collision systématique avec la colonne `id` (PK
  serial) de `run_import`, qui aurait cassé tout import KML sans
  exception ; `parse_kml` renomme désormais `id`/`tenant_id`/`geom` en
  `kml_id`/`kml_tenant_id`/`kml_geom`. Les deux corrigés et vérifiés par
  falsification.
- **SP-55** — catalogue : tri/facettes/recherche spatiale/SEO (GAP-05/06/07,
  chantiers 4.7/4.8/4.10). **GAP-05** : `sort` (5 valeurs, écrase l'ordre
  RRF quand `q` est posé), `owner`, `keyword` (ET, filtré en Python comme
  `list_published_items`), `GET /items/facets` (compteurs propriétaire/
  mot-clé, plafond 50) — sélecteurs + chips à bascule dans `CatalogPage`.
  **GAP-06** : emprise spatiale persistée sur `Item` (4 colonnes, migration
  0035), recalculée au point d'écriture unique
  `app.configs.bbox::recompute_item_bbox` appelé depuis les trois fonctions
  de bas niveau de `configs/repository.py` (create/update/rollback) —
  jamais dupliqué côté route ni MCP, prouvé par un test qui appelle
  `save_app_config` sans jamais toucher la route HTTP ; filtre
  `bbox=minX,minY,maxX,maxY` composé avec le chemin RRF ; `CatalogSpatialFilter`
  (carte MapLibre autonome, `dragPan`/`boxZoom` désactivés) dessine le
  rectangle. **GAP-07** : `sitemap.xml`/`robots.txt`/aperçu social
  (`og:*`, canonical, échappement HTML) rendus côté serveur
  (`app/public/routes.py`), routés via deux routeurs Traefik
  (`seo-static`/`seo-bots`, priorité 20/25) au-dessus du catch-all shell —
  nouvel env `PUBLIC_BASE_URL` ; `useDocumentMeta` complète côté JS
  (titre/description/canonical) pour Googlebot et l'onglet navigateur.
  **Écarts réels trouvés en exécutant (pas dans le plan, piège CLAUDE.md
  n°3)** : `app.collections` importe déjà `app.configs`
  (`dataset_validation`/`routes`), donc `recompute_item_bbox` ne peut PAS
  vivre dans `app.items` (sous `app.configs` dans le contrat de couches) —
  placé dans `app.configs.bbox` avec 4 exceptions nommées dans
  `ignore_imports` (même patron que le cycle déjà documenté pour
  `app.analytics`) ; côté GAP-07, l'overlay prod (`labels: !override`) remplaçait
  intégralement les labels Traefik du fichier de base — les deux nouveaux
  routeurs auraient disparu silencieusement en production sans être
  redéclarés dans `docker-compose.prod.yml` avec ses propres conventions.
  **Volet SEO (Traefik) partiellement vérifié** : la syntaxe des labels
  (`HeaderRegexp`, `replacepathregex`) a été confirmée contre la
  documentation Traefik v3.0 réelle et contre `docker compose config`
  (résolution par valeur) ; la vérification bout-en-bout via une requête
  HTTP à travers Traefik n'a **pas** pu être complétée dans la session qui
  l'a écrit — le conteneur `traefik` ne parvenait pas à joindre le socket
  Docker (`Error response from daemon`), limitation de cet environnement
  reproduite à l'identique sur le routeur `core` préexistant (non liée à
  ce changement) ; les routes `app/public/routes.py` elles-mêmes ont été
  vérifiées directement sur le port du service `core` (200, contenu
  correct, `PUBLIC_BASE_URL` résolu). À revérifier contre une stack Docker
  standard avant mise en production.
- **SP-58** — conformité RGPD (spec
  `docs/superpowers/specs/2026-09-05-sp58-conformite-rgpd-design.md`, plan
  `docs/superpowers/plans/2026-09-05-sp58-conformite-rgpd.md`), 10 tâches :
  compteurs et mesure de stockage par tenant (`GET /admin/usage`, 4
  buckets tenant-préfixés paginés + 2 buckets de sortie de job via
  `byte_size`, migration 0035) ; capacité `CORE_QUOTAS_ENABLED` + 3
  limites instance-wide, garde appliquée aux 6 points de création réels
  (items/collections/stockage — tileset3d/terrain3d/ingestion ne
  connaissaient pas la taille du fichier confirmé avant cette tâche, un
  `head_object` a dû être ajouté à chacun) ; anonymisation d'utilisateur
  (`POST /compliance/users/{id}/erase`, RGPD Art. 17 — écrase l'identité,
  préserve les objets possédés, migration 0036 `users.erased_at`) ;
  privilège `compliance.manage` (19e, domaine `settings`, **exclu même de
  l'Administrateur** — `list(ALL_PRIVILEGE_VALUES)` l'y aurait glissé
  silencieusement sans exclusion explicite) ; `purge_tenant` — suppression
  complète et irréversible d'un tenant (27 tables tenant-scoped réelles,
  énumérées via `Base.registry.mappers`, pas une liste recopiée à la main
  — 5 tables manquaient au texte de la spec : `collection_shares`/
  `pipeline_runs`/`report_runs`/`harvest_records`/`alert_evaluations`),
  **DROP réel de la table dynamique de chaque collection** (trouvaille :
  aucun code existant du dépôt, `unregister_collection` compris, ne le
  faisait jamais) ; route de déclenchement asynchrone avec confirmation
  par slug (jamais une case à cocher), `GET /compliance/purges/{id}` (202
  tant qu'aucun `purge_receipts` n'existe — pas de ligne de statut
  intermédiaire dans ce plan, limitation de portée assumée) ; UI
  `ComplianceAdminPage` avec anonymisation et purge dans deux panneaux
  visuellement distincts (jamais rapprochés, risque explicite de la
  spec). Garde anti-lockout ajoutée à l'anonymisation au-delà du texte du
  plan (trouvée nécessaire à l'exécution, falsifiée comme le reste) : le
  dernier titulaire d'un privilège anti-lockout ne peut pas s'auto-effacer
  (changer `oidc_sub` l'empêcherait de jamais se reconnecter). Trouvaille
  au passage : `GET /me` ne renvoyait jamais `tenantId` au shell (seulement
  `tenantSlug`) alors que le cœur le sert déjà — chemin de lecture oublié
  (piège CLAUDE.md n°5), corrigé. **Rappel de priorité (spec §0, à ne pas
  oublier en relisant cette ligne plus tard)** : ce chantier reste noté
  par la feuille de route révisée comme pertinent seulement dès qu'un
  tenant externe réel est onboardé (question produit Q2, toujours
  ouverte) — livrer ce plan ne tranche pas cette question.
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
- **SP-59** — exploitation : rotation des secrets + restauration scriptée
  (spec `docs/superpowers/specs/2026-09-06-sp59-exploitation-sauvegarde-
  oidc-design.md`, plan `docs/superpowers/plans/2026-09-06-sp59-
  exploitation-sauvegarde-oidc.md`), 8 tâches en deux volets. **Volet A
  (GAP-75)** : `crypto.py` accepte une clé explicite (`encrypt`/`decrypt`,
  `key: bytes | None = None`, défaut inchangé) ; `list_all_secrets` —
  seule fonction cross-tenant d'`app/secrets/repository.py`, réservée au
  script de rotation ; `rotate_all_secrets` — rotation atomique en deux
  passes strictes (tout déchiffrer avec l'ancienne clé AVANT toute
  écriture, puis rechiffrer et flush une seule fois), audit par tenant
  (`actor_kind="system"`, premier usage réel de cette valeur dans
  `core/app`) ; script CLI `scripts/rotate_secrets_master_key.py`
  (`--dry-run`, patron `seed_demo.py`) + runbook dédié. Ni le script ni
  `CORE_SECRETS_MASTER_KEY_NEW` ne sont câblés dans
  `docker-compose.yml`/`.env.example` — script d'exploitation ponctuel,
  pas une capacité de service. **Volet B (GAP-70)** : `deploy/backup/
  restore.sh` scripte les étapes 3+4 du runbook de restauration
  (Postgres + MinIO), embarqué dans l'image `backup`. **Trouvaille
  réelle** : le runbook (et la première version de `restore.sh`) ne
  recréait que **5** buckets MinIO alors que `backup.sh` en sauvegarde
  **7** depuis SP-33/SP-40 (`mapicons`/`attachments` jamais reportés côté
  restauration) — perte de données silencieuse après tout sinistre réel,
  corrigée dans les deux fichiers, garantie par un nouveau test de parité
  (`test_restore_recreates_every_bucket_backup_mirrors`). Contradiction
  interne du runbook corrigée (le paragraphe « Non prouvé à ce jour »
  contredisait la section « 6. Vérifier » plus bas dans le même fichier) ;
  nouvelle section 7, checklist de vérification OIDC réelle. **Constat
  Tâche 8, sans arrondir** : aucun Keycloak réel ni stack complète ne
  tournait dans cette session (`.env` jamais bootstrappé dans ce
  worktree, ports 9000/9001 déjà pris par un conteneur d'une autre
  session concurrente, charge machine mesurée à 10-29 avec 6-13 process
  `pytest` concurrents d'autres sessions au même instant) — la checklist
  reste rédigée, **non rejouée**, `REV-164` passe d'ouvert à
  partiellement fermé (même limite d'environnement que SP-32/SP-55,
  précédent déjà documenté). Garde de branche vérifiée : aucune route
  REST ni outil MCP ajouté par erreur (`grep` vide sur `rotate_all_secrets`/
  `list_all_secrets`/`restore.sh` dans `app/mcp/`, `secrets/routes.py`
  inchangé). Suite finale : cœur **2603 passed/5 skipped (qgis)/0
  failed** (les 4 échecs observés sur une exécution complète sous forte
  contention machine — `test_pipeline_runtime.py` ×6 sur table
  dupliquée d'une session concurrente, `test_copilot_routes.py` sur une
  assertion de non-blocage de l'event loop sous charge, piège CLAUDE.md
  n°7 — ont été reproduits comme passants à 100 % en isolation, sur un
  conteneur Postgres dédié à cette vérification, non liés aux fichiers
  touchés par ce plan) ; couverture 94,15 % (seuil 85) ; ruff/mypy
  --strict (6 modules)/lint-imports tous verts. Aucune migration (spec
  §4, vérifié : `alembic heads` inchangé).

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
- `REV-096` clos par **SP-45** : garde d'egress SSRF sur l'appel LLM
  sortant du copilote (`app/copilot/egress.py`), même patron que les 3
  autres surfaces sortantes.
- `REV-097` clos par **SP-47** : `automation.secrets.manage` garde `/secrets`
  (OR avec `admin.secrets.manage`, rôle Créateur mis à jour — décision à
  confirmer a posteriori par Tanguy) ; `tasks.view`/`tasks.view_all` gardent
  `GET /usage/tasks`/`GET /usage/summary` (nouveau domaine `app/usage/`,
  lecture seule sur `audit_log`).
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
