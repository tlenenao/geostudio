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
  suite E2E complète est le filet de la migration : elle reste verte
  (référence 2026-08-27 : 108 passed / 4 skipped / 0 failed).
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
npm run test         # Vitest (162 fichiers, 1463 tests — mesuré 2026-08-27)
npm run e2e          # Playwright (108 passed / 4 skipped, VITE_AUTH_MODE=mock)
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
uv run pytest        # 1896 passed + 5 skipped + 1 failed (mesuré 2026-08-27,
                     # avec un conteneur postgis-test ; compte croissant SP
                     # après SP, non remesuré à chaque clôture — 2015+ à la
                     # clôture de SP-29a). Les 5 skips = marqueur qgis (sidecar
                     # réel requis). Deux échecs PRÉEXISTANTS possibles, à ne
                     # pas imputer à son propre travail :
                     # test_features_rls.py::test_scope_preserves_original_sql_error
                     # (dérive psycopg2/transaction, non diagnostiquée —
                     # confirmé INTERMITTENT à la clôture de SP-29a : absent
                     # sur un run, présent sur un autre, mêmes commit/config) ;
                     # test_deployability.py::test_every_compose_substitution_is_documented
                     # (VITE_AUTH_MODE absent de .env.example malgré sa
                     # substitution dans docker-compose.yml — trouvé et
                     # reproduit à plusieurs reprises pendant SP-29a, jamais
                     # corrigé, hors périmètre de ce plan).

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
- **SP-1** (a→d) — socle du cœur : auth JWT OIDC + mock, tenants/users/audit_log,
  lint de frontières, module `items`, partage/publication (`can()`), shell
  basculé sur `CoreItemClient`, realm Keycloak. **Jalon M1 (GeoNode-free)**.
- **SP-2** (a+b) — MCP v0 (`/mcp` OAuth 2.1+PKCE) + 7 outils + schéma JSON
  `AppConfig`. **Jalon M2 (AI-operable)**.
- **SP-3** — registre de collections, rôle admin, RLS par collection, OGC API
  Features Part 1+4, shell lisant ses couches depuis le cœur.
- **SP-4** — formulaires dans le builder (widget Formulaire, édition depuis la
  sélection carte/table, `canWrite` par utilisateur).
- **SP-5** — moteur CEL : `visibleWhen`, colonnes calculées, actions composées,
  bindings généralisés + variables typées.
- **SP-6** — jobs procrastinate + ingestion GeoJSON/CSV/GeoPackage/Shapefile,
  `feature_count`. **Jalon M4** (GPKG 50k → carte).
- **SP-7** — recherche sémantique (pgvector, RRF trigram+vecteur) + MCP v1.
- **SP-8** — SDK widgets Web Components (contrat, `WidgetHost`, registre
  d'extensions + chargement dynamique ES). **Jalon M5 (SDK ouvrable)**.
- **SP-9** (6 sous-parties) — durcissement produit public v0.1 : gestion
  collections, gouvernance légale, CI publique/release, install/secrets, sécurité
  minimale, démo lecture seule.
- **SP-10** — OTel sur cœur/worker + observabilité packagée (profil
  `observability`, dashboards Grafana + SLO).
- **SP-11** — lakehouse : CDC→GeoParquet (réplication logique), compaction,
  module DuckDB (`POST /collections/{id}/aggregate`), SQL analyste sandboxé.
- **Storytelling** — mode narratif `story` sur `PageManager`.
- **SP-12** (a→g) — fédération STAC/DCAT : API STAC native, export DCAT-AP,
  moteur de moissonnage + **les cinq connecteurs** (STAC, ArcGIS FS,
  GetCapabilities WMS/WFS/WMTS, CSW/OGC Records, CKAN) + garde d'egress SSRF.
  **A22 complet**.
- **SP-13** — Portails & Sites : `/sites/{slug}`, widgets de contenu, fiche
  dataset + téléchargement. **Jalon M13**.
- **SP-14** (l/m/n/o) — MCP analytique, Bookmarks (`bookmark`, 5e kind),
  cross-filter inter-datasets (`crossFilterLinks`), requête visuelle no-code
  Filtrer→Joindre→Résumer. **Jalon M11, SP-14 clos**.
- **SP-15** (a/c/d/e/f/g/h) — pipeline no-code « équivalent FME » (A39) : socle
  headless (`kind="pipeline"`, runtime DuckDB, file `etl`, `CORE_ETL_ENABLED`),
  étage spatial 1 + 2 (`transform.qgis` en sidecar isolé, allowlist de 50 ids),
  coffre de secrets AES-GCM, `reader.connector.rest/postgres` (dlt, garde SSRF
  dédiée), canvas DAG (branchements/fusion), planification cron.
  **A39 phases 1+2 livrées**.
- **SP-16** (a+b) — exports secs CSV/XLSX/GeoJSON/GPKG ; alertes de seuil
  (`AlertRule`, 8e kind, webhook/email sur transition d'état seulement).
  **Jalon M12** sous périmètre resserré — **il n'y a pas de SP-16c**.
- **SP-17** (a+b) — worker d'export Playwright + `printLayout` déclarative
  (`CORE_EXPORT_ENABLED`) ; `ReportSchedule` (9e kind) : Bookmark rendu en PDF
  sur cron, notifié par lien présigné.
- **3D** — rendu (`kind: "tiles3d"` deck.gl + `MapConfig.terrain` raster-dem),
  puis hébergement de tilesets uploadés (zip S3 jamais extrait, validation par
  lecture par plage, proxy authentifié, `CORE_TILESET3D_ENABLED`).
- **SP-18** (a/b/c) — export d'apps : Statique (données gelées), Connecté (CORS
  étroit + `geostudio-connection.json`), Autoporté (conteneur + snapshot
  GeoParquet + mini-serveur). **Jalon M15**.
- **SP-19** — undo/redo général du builder (`useUndoableDraft`, pile de 50
  instantanés, coalescing 400 ms). Prérequis de SP-20.
- **SP-20** — copilote IA dans le builder : outils MCP orchestrés en loopback
  HTTP réel sur `/mcp`, 6 outils allowlistés, micro-actions annulables par le
  seul undo SP-19, tout derrière `CORE_LLM_PROVIDER`. **Jalon M16** ; vague 0 du
  plan d'action close.
- **Release v0.1.0** (2026-08-21) — huit images `ghcr.io/tlenenao/geostudio-*`
  publiées et anonymement téléchargeables (vérifié au registre) ;
  `.env.example` passe de `latest` à `v0.1.0`, plus aucun `:latest` dans le
  compose de production résolu.
- **SP-21** — déployabilité (vague 1) : garde-fou de **9 règles** qui testent le
  **dépôt** (`core/tests/test_deployability.py`), 4 images ajoutées à la
  release, `build: !reset null` sur l'overlay prod, 9 variables d'env câblées,
  2 buckets ajoutés à la sauvegarde, 4 images repinnées, healthchecks sur 7
  services, notices GPL/AGPL embarquées.
- **SP-22** — filet qualité statique (vague 2) : ruff, contrat de couches
  complété (30 entrées), ESLint+Prettier, `mypy --strict` sur 4 modules, seuils
  de couverture non régressifs, pre-commit + commitlint, CodeQL/gitleaks/Trivy/
  SBOM/Dependabot.
- **SP-23** — quatre bouchons : agrégats manquants (countDistinct/median/
  percentile avec `p` en %/stddev), six grains temporels, catalogue voyant les
  12 types, historique de versions atteignable (`ConfigHistoryPanel` sur les
  cinq éditeurs + revalidation du rollback).
- **SP-24** — carte interrogeable (chantier 4.1) : popups (`PopupConfig`,
  gabarit markdown `${expr}` CEL) + tuiles vectorielles servies par le cœur
  (`ST_AsMVT` sous `rls_scope`+`can()`, plafond 5000 lignes + timeout 10 s) ;
  route publique Martin retirée.
- **SP-25** — symbologie déclarative (chantiers 4.2/4.3) dans l'éditeur de
  cartes **et** le widget carte : catégoriel/continu/classé (quantile,
  intervalle égal, Jenks, 2→9 classes), palettes curatées + palette de thème,
  éditeur partagé, domaines figés à l'enregistrement.
- **SP-26** — durcissement avant v0.1 publique (vague 3) : conteneurs non-root
  (uid 1001), `CORE_AUTH_MODE=mock` refusé hors `CORE_ENV=development`, erreurs
  RFC 7807 partout, rate limiting différencié, arrêt propre `cdc-worker`,
  `AppErrorBoundary` racine, CSP/Permissions-Policy (Report-Only), alertes SLO
  notifiées, suite E2E sur OIDC réel (`shell/e2e-oidc/`).
- **SP-27** (20 tâches, chantiers 4.4/4.5) — symbologie avancée de la carte :
  contour data-driven (fixe puis classé), opacité, icônes catégorielles
  (catalogue Lucide curaté + bibliothèque d'icônes personnalisées tenant-scoped,
  `app/mapicons/` au cœur, assainissement SVG côté serveur), étiquettes CEL
  multi-champs (source GeoJSON dédiée), outil de mesure/croquis éphémère —
  câblés dans l'éditeur de carte **et** le widget carte (D2, périmètre élargi).
  E2E 108/4/0 → **111/4/0**. Revue finale de branche : 0 Critique, 4 Important
  (tous des défauts d'interaction croisée entre tâches, tous fermés et
  re-vérifiés) — **Ready to merge**.
- **SP-28** (4 tâches) — symbologie des couches `feature` (URL GeoJSON) :
  résout l'item resté ouvert par SP-27 — `LayerSymbologyEditor`/
  `LayerPopupEditor` ne retournent plus `null` pour une couche sans
  `collectionId` ; nouveau module `geojsonIntrospect.ts` (fetch client-side,
  jamais via `ItemClient`), `LayerPicker` gagne un formulaire d'ajout par
  URL GeoJSON. E2E 111/4/0 → **112/4/0**. Revue finale de branche : 1
  Critique (`renderAs` ne survivait pas à un rechargement — 3e occurrence
  du piège n°5, fermé, avec une 2e occurrence du même défaut trouvée et
  fermée en vérification de clôture), 1 Important documenté en suivi non
  bloquant (bug de largeur de titre dans `LayersPanel`, préexistant,
  partagé avec `kind: "vector"`, non introduit par cette branche) —
  **Ready to merge**.
- **SP-29a** (12 tâches) — fondation de la refonte UI (spec
  `2026-08-29-refonte-ui-triptyque-design.md`, socle triptyque retenu parmi
  quinze directions) : `decide()` extraite de `can()` avec parité prouvée sur
  256 cas, `roles_for_items()`/`roles_for_collections()` en une requête par
  page, **`ItemRead.permissions`** (read/write/delete/share) calculé par le
  cœur et lu côté shell par une porte unique (`Gate`/`hasPermission`/
  `Locked`), état des neuf domaines dérivé du profil (`capabilities.ts` —
  rôle masque, capacité verrouille), `GET /me` porte les sept capacités de
  l'instance (parité avec `GET /instance` renforcée par un test paramétré sur
  les sept), couche i18n (français seul, A12), tokens en deux ambiances
  (`styles/tokens.css`, contrat testé mécaniquement) et trois fontes
  empaquetées (Radix UI retenu pour SP-29b à l'issue d'un spike mesuré, doc
  `docs/superpowers/plans/2026-08-29-sp29a-spike-primitives.md`). Aucun écran
  modifié **sauf** `ItemActions`, qui cesse de proposer les actions produisant
  un 403 (exception assumée §10.1.7 ; suit le cœur, pas la maquette, sur
  Publier). E2E 112/4/0 → **113/4/0**. Revue finale de branche : 0 Critique,
  2 Important (permissions incohérentes sur `PATCH /items` et 6 outils MCP —
  la valeur servie contredisait l'action qui venait de réussir — et test de
  parité `/me`/`instance` plus faible qu'annoncé ; les deux fermés et
  re-vérifiés indépendamment), 1 Important **plan-mandaté** (même raison de
  verrouillage répétée trois fois dans le menu `ItemActions` pour Modifier/
  Publier/Miniature) tranché par Tanguy : laissé tel quel, reporté en suivi
  non bloquant pour SP-30. Écarts assumés du plan lui-même, à reprendre : les
  permissions de collection restent à `roles_for_collections()` seul (pas de
  `CollectionPermissions`, cf. SP-30), le profil « Lecteur » de la spec n'est
  pas dérivable du modèle actuel (`isAdmin`/`isAnalyst` seulement), « Publier »
  reste ouvert à tout éditeur (restriction au propriétaire = SP-32 si voulue).
- **SP-29b** (31 tâches) — kit de ~40 primitives UI headless (Radix UI +
  tokens GeoStudio) sous `shell/src/ui/kit/`, additif à côté de `ui/*`
  existants (intouchés, vérifié à plusieurs reprises) : formulaires
  (Field/Input/Textarea/Select/Combobox/Checkbox/Radio/Switch/Slider/
  Segmented/ColorField/NumberField), structure (Tabs/Tree/Table/DataTable/
  Panel/Section/Breadcrumb/Toolbar/Splitter), surfaces (Popover/Menu/
  Tooltip/Dialog/ConfirmDialog/Drawer), états (Badge/Chip/Toast/Skeleton/
  EmptyState/Banner/Progress/Spinner), divers (Button/IconButton/Avatar/
  Kbd) + galerie interne admin (`/internal/kit-gallery`), référence
  visuelle pour SP-30. 18 paquets Radix/lucide-react épinglés en versions
  exactes. E2E 113/4/0 inchangé, couverture shell 90,75 % (seuil 88).
  Revue par tâche systématique + revue finale de branche (modèle le plus
  capable) : 0 Critique, 3 Important trouvés et corrigés — **tous
  re-vérifiés par falsification empirique après coup, pas seulement par
  suite de tests** (le filet `expectTokenizedClasses()` semblait corrigé
  sur les 7 composants portalisés visés après un premier correctif, mais
  ne couvrait en réalité encore rien sur 3 d'entre eux — cf. piège n°10 ;
  4 chaînes françaises hors `t()` ; 2 `aria-label` interpolant un
  `ReactNode` arbitraire, bug latent pour SP-30). 6 Minor documentés en
  suivi non bloquant pour SP-30. **Ready to merge** — PR #102 (dev→main,
  avec SP-29a).
- **SP-30c** (7 tâches + 2 correctifs post-hoc, famille 3 « Cartes » du
  §6.1 de la spec SP-30) — `MapEditorPage` sur `TriptychLayout` : onglets
  « Couches » (`LayersPanel` seul, aucun nouveau composant) / « Carte »
  (`MapView` plein volet) / « Inspecter » (fond de carte, terrain, caméra,
  impression, historique, export, Enregistrer). Kit-ification de
  `CameraControls`/`ConfigHistoryPanel`/`LayerPicker`/`BasemapSelect`/
  `TerrainPanel`/`PrintLayoutPanel`/`LayersPanel` (Button + tokens, aucun
  import cassant). Élimine les deux derniers `<Dialog>` de cette famille :
  `ExportPanel` et `Terrain3DUploadButton` deviennent des panneaux en
  ligne (bouton Annuler explicite, plus d'Escape/backdrop), chacun avec un
  test falsifiable `queryByRole("dialog")` (piège n°10). Branche
  `isExportRender` (rendu nu du worker Playwright, SP-17a) vérifiée
  structurellement intacte. E2E 113/4/0 → **118/4/0** (SP-30b avait déjà
  porté la référence à 113 ; ce plan n'ajoute aucun nouveau spec).
  Couverture shell 90,85 % (seuil 88), suite complète 222 fichiers/1815
  tests. **2 correctifs post-hoc trouvés en fin de plan, tous deux fermés
  et re-vérifiés indépendamment** : (1) suite E2E complète (Step 3 de la
  tâche de vérification finale) a trouvé une régression croisée réelle —
  `shell/e2e/export.spec.ts` et `shell/e2e/terrain3d-hosting.spec.ts`,
  hors de la liste de specs nommée par ce plan, utilisaient encore
  `getByRole("dialog", ...)` pour les deux composants convertis en
  panneau en ligne — exactement le piège n°6 (lancer la suite E2E
  complète avant de clore un plan) ; (2) revue finale de branche (opus) a
  trouvé 1 Important cross-tâche invisible en revue par tâche : les deux
  conversions Dialog→Panel divergeaient sur la garde `busy` du
  déclencheur (`ExportPanel` le désactivait pendant l'envoi,
  `Terrain3DUploadButton` non, malgré un commentaire affirmant le
  contraire) — **racine identifiée dans le texte même du plan** (le
  prose de Task 5 promettait la garde, son bloc de code littéral ne la
  contenait pas : piège n°3, défaut de plan pas de l'implémenteur).
  6 Minor reportés en suivi non bloquant pour SP-30d (détail ci-dessous).
  **Ready to merge.**
- **SP-30d** (3 tâches + 1 correctif post-hoc, famille 4 « Données » du
  §6.1 de la spec SP-30) — `DatasetEditPage` sur `TriptychLayout` :
  onglets « Catalogue » (retour + `<dl>` Type/Modifié, même idiome
  qu'`ItemDetailPage.tsx:79-95`, pas de panneau-liste métier équivalent à
  `LayersPanel` sur cette page) / « Dataset » (métadonnées, colonnes,
  champ temporel, cross-filter — le contenu directement éditable) /
  « Réglages » (export, `AlertRuleEditor`, `ConfigHistoryPanel`, requête
  source, Enregistrer — même regroupement que « Inspecter » sur
  `MapEditorPage`, SP-30c). Kit-ification préalable d'`AlertRuleEditor`/
  `CrossFilterLinkEditor` (Button + tokens, aucun des deux n'important
  `ui/dialog` — rien à convertir côté modal, à la différence des familles
  Catalogue/Cartes). Prérequis `CollectionPermissions` déjà livré par
  SP-30a (vérifié par lecture directe du code avant d'écrire ce plan,
  piège n°3), donc aucun changement au cœur dans ce plan. E2E 118/4/0
  inchangé (aucun nouveau spec ; le filet nommé par le plan omettait
  `analytics-context.spec.ts`, 6e consommateur réel de la page — défaut
  du texte du plan, piège n°6, sans conséquence car la suite E2E
  complète l'a couverte). Couverture shell 90,85 % (seuil 88), suite
  complète 222 fichiers/1816 tests. **1 correctif post-hoc trouvé en fin
  de plan par la revue finale de branche (opus), fermé et re-vérifié
  indépendamment** : le volet « Dataset » (work) n'avait pas
  `h-full overflow-y-auto` comme ses deux jumeaux `CatalogPage`/
  `ItemDetailPage` — la cellule `work` de `TriptychLayout` est
  `overflow-hidden` par construction, chaque consommateur doit fournir
  son propre conteneur de défilement ; contenu le plus haut de la page
  (tableau des colonnes, éditeurs cross-filter) tronqué et inatteignable
  sur viewport large, **invisible aux deux filets de test** (jsdom ne
  fait pas de layout, Playwright fait défiler programmatiquement les
  conteneurs `overflow-hidden` — les specs E2E cliquaient des éléments
  qu'un humain ne pouvait pas atteindre ; les suites vertes n'étaient pas
  une preuve). 5 Minor reportés en suivi non bloquant pour SP-30e+
  (détail ci-dessous). **Ready to merge.**
- **SP-30e** (3 tâches + 2 correctifs post-hoc, famille 5 « Apps & sites » du
  §6.1 de la spec SP-30) — `AppBuilderPage` sur `TriptychLayout` : onglets
  « Structure » (`PageManager` + `WidgetPalette`) / « Canevas » (en-tête
  local Édition/Aperçu, Annuler/Rétablir, rupture, Capturer une miniature,
  puis `AppRenderer` plein volet) / « Propriétés » (`PropsPanel` du widget
  sélectionné en tête, puis Sources de données/Actions/Navigation/
  Interactions/Variables/Thème/Impression/`ConfigHistoryPanel`/export
  standalone/copilote/Enregistrer — inspecteur volontairement **non**
  scindé « widget sélectionné » vs « réglages de l'app » malgré la
  maquette : la suite de tests existante exige `ActionsPanel`/
  `DataSourcePanel` accessibles pendant qu'un widget reste sélectionné,
  et le mode Aperçu ne masque plus les volets latéraux). Kit-ification
  préalable d'`AppExportPanel` (Dialog→panneau en ligne, busy guard) et
  `CopilotPanel` (Button + tokens). E2E 118/4/0 inchangé (aucun nouveau
  spec). Couverture shell 90,85 % (seuil 88), suite complète 222
  fichiers/1817 tests. **1 Critical trouvé en Task 3, fermé** : le volet
  Propriétés était passé d'`<aside>` à `<div>`, cassant 3 tests de
  `shell/e2e/containers.spec.ts` — non listé dans le filet à 5 specs du
  plan, 3e occurrence consécutive du piège n°6 (SP-30c, SP-30d, SP-30e) ;
  fix : le volet Propriétés redevient `<aside>` (volet Structure reste
  `<div>`, asymétrie assumée). **2 Important + 1 récidive trouvés en
  revue finale de branche (opus), tous fermés** : la rangée de boutons du
  sélecteur de mode d'export débordait de la colonne Propriétés (fix
  `flex-wrap`) ; deux boutons « Annuler » d'`AppExportPanel` entraient en
  collision avec le bouton d'annulation (undo) d'`AppBuilderPage` (fix :
  renommage en « Fermer »/« Ne pas exporter ») ; le premier fix a reproduit
  son propre défaut sur la rangée jumelle de l'avertissement (`flex-wrap`
  oublié là aussi, 2e correctif). Recommandation actée pour SP-30f+ : ne
  plus nommer de liste de specs E2E dans le texte du plan, exiger
  directement la suite complète avant tout commit qui change la structure
  DOM d'une page. 6 Minor reportés en suivi non bloquant pour SP-30f+
  (détail ci-dessous). **Ready to merge.**
- **SP-30f** (6 tâches + 2 correctifs post-hoc, famille 6 « Automatisation »,
  volet 1 du §6.1 de la spec SP-30) — `PipelineBuilderPage` sur
  `TriptychLayout` : onglets « Étapes » (`PipelinePalette` seul) / « Canevas »
  (en-tête local titre seul ; Enregistrer déménagé en bas du volet
  Propriétés, aligné sur les trois familles précédentes) / « Propriétés »
  (nœud sélectionné + `PipelinePreviewPanel` si sélectionné — aucun message
  de repli inventé pour l'inspecteur vide, comportement préexistant
  préservé —, puis Exécution/`PipelineRunPanel`, Planification/
  `PipelineScheduleEditor`, `ConfigHistoryPanel`, Enregistrer, tous gated
  `pk !== null`). Kit-ification préalable de sept fichiers
  `builder/pipeline/*` (tokens + `Button` du kit sur `PipelineRunPanel`) ;
  `PipelineRunPanel`/`PipelineScheduleEditor` désormais définitivement
  kit-ifiés pour la future `VisualQueryWizardPage` aussi (même composants
  partagés, aucun retravail attendu côté SP-30g). `onDragOver`/`onDrop`
  déplacés du conteneur de rangée disparu (palette+canevas+inspecteur
  n'étaient plus dans le même conteneur) vers le conteneur externe `-m-6`.
  E2E 118/4/0 inchangé (aucun nouveau spec). Vitest 12/12 sur
  `PipelineBuilderPage.test.tsx` (11 existants + 1 nouveau test d'onglets,
  RED→GREEN vérifié), couverture shell 90,85 % (seuil 88), suite complète
  222 fichiers/1818 tests. **2 Important trouvés en revue finale de branche
  (opus), tous fermés et re-vérifiés indépendamment** : le canevas DAG
  restait à une hauteur fixe de 480px héritée de l'ancien layout défilant,
  incohérente avec la colonne Canevas désormais pleine hauteur — corrigé
  en `h-full` via la chaîne flex déjà éprouvée par SP-30c/d/e ; la question
  `<main>`/`<aside>` posée par `CLAUDE.md` (entrée SP-30e, explicitement
  assignée à ce plan) n'avait pas été traitée par le texte du plan et la
  branche avait ajouté une 3e forme divergente (`<main>` orphelin sans
  `ref` ni rôle fonctionnel autour du volet Canevas) — tranchée : `div`/
  `div`/`div` (`AppBuilderPage` reste la seule exception documentée, son
  `<main ref={mainRef}>` servant la capture de miniature). 7 Minor
  reportés en suivi non bloquant pour SP-30g+ (détail ci-dessous).
  **Ready to merge.**
- **SP-30g** (4 tâches + 1 correctif post-hoc, famille 6 « Automatisation »,
  volet 2 du §6.1 de la spec SP-30) — `ReportEditPage` sur `TriptychLayout` :
  onglets « Catalogue » (retour + `<dl>` Type/Modifié, **absente tant que le
  rapport est un brouillon non enregistré** — `pk` nullable ici comme sur
  `PipelineBuilderPage`, à la différence de `DatasetEditPage` où `pk` est
  toujours défini ; `<dd>Type</dd>` utilise correctement
  `RESOURCE_TYPE_LABELS[item.resourceType]`, pas de littéral en dur —
  n'a pas répété le défaut logué sur `DatasetEditPage.tsx` par SP-30d) /
  « Rapport » (titre local + `ReportScheduleEditor`) / « Réglages »
  (`ReportRunPanel`/`ConfigHistoryPanel` si `pk !== null`, Enregistrer +
  erreur). `useItem` (`shell/src/api/hooks.ts`) gagne un second paramètre
  optionnel `{ enabled?: boolean }` sur le patron exact de
  `useDatasetConfig`/`useReportScheduleConfig` — rétrocompatible, ses trois
  call sites existants (`ItemDetailPage`, `DatasetEditPage`,
  `AppRuntimePage`) inchangés. Kit-ification préalable de
  `ReportRunPanel.tsx`/`ReportScheduleEditor.tsx` (tokens seuls, aucun des
  deux n'important `ui/*`). Dette de test refermée, pas répétée : le
  nouveau stub `matchMedia` de `ReportEditPage.test.tsx` est accompagné
  d'un `vi.unstubAllGlobals()` en `afterEach` dès son introduction.
  `VisualQueryWizardPage` (volet 3 de la même famille) reste hors
  périmètre — granularité une page par plan, confirmée par SP-30f et
  reconduite ici. E2E 118/4/0 inchangé (aucun nouveau spec, le consommateur
  direct `report-schedule.spec.ts` reste vert). Vitest 222 fichiers/1821
  tests, couverture shell 90,85 % (seuil 88). **0 Critical, 2 Important
  trouvés en revue finale de branche (opus), tous deux fermés et
  re-vérifiés par lecture directe du diff par le contrôleur** : un
  commentaire committé affirmait à tort que `MapEditorPage.test.tsx`
  n'avait pas de `vi.unstubAllGlobals()` (il l'a déjà — seuls
  `DatasetEditPage.test.tsx`/`AppBuilderPage.test.tsx` en manquent encore),
  texte faux hérité verbatim du plan lui-même (piège n°3) ; `useSaveReportSchedule`
  était le seul hook de sauvegarde de la famille sans invalidation de
  cache (`useSaveMap`/`useSaveDataset`/`useSavePipeline` invalident déjà
  leur propre clé de config), devenu porteur de conséquence par ce plan
  puisque le volet Catalogue affiche désormais `item.date` — corrigé en
  ajoutant l'invalidation de `["report-schedule", pk]`, même patron que
  les trois autres, sans étendre à `["item", pk]` (aucun sibling ne le
  fait). 6 Minor reportés en suivi non bloquant (détail ci-dessous).
  **Ready to merge.**
- **SP-30h** (4 tâches, famille 6 « Automatisation », volet 3 et dernier du
  §6.1 de la spec SP-30 — **clôt la famille 6**) — `VisualQueryWizardPage`
  sur `TriptychLayout` : onglets « Catalogue » (retour + `<dl>` Type/Modifié,
  visible seulement une fois `existingDatasetItemQuery.data` résolu — cette
  page référence un item **Pipeline** via `pipelinePk` mais affiche la fiche
  du **Dataset** produit, réutilisant la requête déjà existante plutôt que
  d'interroger le mauvais item ; `<dd>Type</dd>` utilise correctement
  `RESOURCE_TYPE_LABELS[...]`, pas de littéral en dur) / « Requête » (titre
  local + sélection de la collection de base + Filtrer/Joindre/Résumer,
  conteneur `overflow-y-auto` propre posé dès l'écriture — défaut que
  SP-30d avait dû corriger a posteriori, non répété ici) / « Réglages »
  (Planifier, alertes de validation, erreur de sauvegarde, bouton
  Créer/Mettre à jour). Aucun `ConfigHistoryPanel` ajouté (cette page n'en
  a jamais eu, hors périmètre assumé). Kit-ification préalable de
  `QueryFilterBuilder.tsx`/`QueryJoinPicker.tsx`/`QuerySummaryBuilder.tsx`
  (+ défaut du `className` de `PercentileInput.tsx`, no-op vérifié sur les
  deux sites d'appel de `DataSourcePanel.tsx`) — les trois composants de
  requête visuelle confirmés API-neutres, consommés inchangés par la page.
  Stub `matchMedia` local avec `vi.unstubAllGlobals()` dès l'introduction
  (dette loguée 3 fois sur SP-30d/e, non répétée). E2E 118/4/0 inchangé
  (aucun nouveau spec, `visual-query.spec.ts` reste vert). Vitest 222
  fichiers/1824 tests, couverture shell 90,84 % (seuil 88). **0 Critical,
  0 Important, 7 Minor en revue finale de branche (opus) — Ready to merge
  sans correctif.** 7 Minor reportés en suivi non bloquant (détail
  ci-dessous), dont plusieurs désormais répétées 3-4 fois dans la famille
  sans jamais avoir été tranchées pour de bon — actées à trancher une fois
  pour toute la famille avant SP-30i+ plutôt que reportées une fois de plus.
- **SP-30i** (4 tâches, famille 7 « Analytique » du §6.1 de la spec SP-30)
  — `SqlLabPage` sur `TriptychLayout` : onglets « Catalogue » (lien retour
  seul, `Panel`) / « Requête » (éditeur/résultat existants, conteneur
  `overflow-y-auto` posé dès l'écriture — piège déjà documenté 5 fois par
  SP-30d→h, non répété ici) / « Historique » (liste ou `EmptyState` si
  vide). Le vrai garde-fou de sécurité reste côté serveur
  (`core/app/features/routes.py:421-431`, 403 si `!user.is_analyst`) :
  retirer le check `isAnalyst` interne à la page n'est donc pas une
  régression, `RequireRole` (déjà posé sur les trois routes admin par
  SP-29a) devient la défense en profondeur pour ce 4e consommateur —
  générique, vérifié structurellement identique à `KitGalleryPage.tsx`.
  `SqlLabPage.tsx` disparaît de la liste des 9 occurrences de comparaison
  de droits en dur visée par SP-30 (décompte réel révisé à 11
  occurrences/6 fichiers : le texte de la spec §6.5 sous-comptait, il
  omettait `KitGalleryPage.tsx`). E2E 118/4/0 inchangé, Vitest 223
  fichiers/1829 tests, couverture shell 90,85 %. Revue finale de branche
  (opus) : 0 Critical, 1 Important fermé (deux commentaires de test
  affirmaient à tort que `SqlLabPage` refuse encore l'accès en interne,
  alors que ce plan déplace ce refus vers `RequireRole` — corrigé,
  attribution remise à jour, aucun changement de logique), 10 Minor
  reportés en suivi non bloquant, plusieurs explicitement adressés à
  SP-30j (inventaire `RequireRole` sous-compté ; `useMe()` consommé pour
  deux usages distincts sur les pages admin — le garde ET
  `enabled: isAdmin` sur leur requête, les deux à retirer ensemble).
  **Ready to merge.**
- **SP-30j** (5 tâches + 1 correctif hors-tâche du contrôleur, famille 8
  « Administration » du §6.1 de la spec SP-30 — dernière des neuf
  familles nommées) — `AdminExtensionsPage`/`HarvestSourcesAdminPage`/
  `CollectionsAdminPage` sur `TriptychLayout`, les trois routes admin
  enveloppées dans `<RequireRole role="admin">` (suivi SP-30i consommé :
  `useMe()`/`isAdmin` disparus des trois pages, garde ET `enabled` de
  requête retirés ensemble). Cinq dialogues Radix convertis en panneaux
  (`CreateHarvestSourcePanel`/`EditHarvestSourcePanel`/
  `EditCollectionPanel`/`CollectionSharePanel`/`RegisterCollectionPanel`),
  exclusivité mutuelle entre panneaux posée par chaque gestionnaire de
  clic (2 états sur Harvest, 3 sur Collections). E2E 118/4/0 inchangé
  (specs harvest/collections mises à jour pour cibler `region` au lieu de
  `dialog`). Vitest 219 fichiers/1830 tests, couverture 91,09 %.
  **Correctif hors-tâche du contrôleur** : régression de
  `routes.test.tsx` introduite par Task 1 (test synchrone n'attendant pas
  la résolution de `RequireRole`/`useMe()`), trouvée en aparté par
  l'implémenteur de Task 4 — aucune tâche ni revue par tâche ne relance
  la suite vitest complète — corrigée directement par le contrôleur.
  Deux tâches ont trouvé le même défaut plan-mandaté (test d'exclusivité
  mutuelle absent du texte littéral du brief) à des stades différents :
  Task 3 en 2 rounds de correctif avec falsification, Task 4 dès le
  premier passage de revue grâce au briefing explicite du risque de
  récidive. Revue finale de branche (opus) : 0 Critical, 1 Important
  fermé — la décision 6 du plan (exempter `deleting` de la remise à zéro
  croisée) était trouée identiquement sur les deux pages admin à
  panneaux : supprimer une ligne pendant que SON PROPRE panneau
  d'édition/partage est ouvert ne le refermait pas, ces panneaux n'étant
  plus modaux depuis cette branche — fixé (remise à zéro conditionnelle
  sur l'id après succès de la mutation), vérifié par falsification
  indépendante du re-reviewer — 9 Minor reportés en suivi non bloquant
  pour SP-30k+/SP-31 (dont : `aria-expanded`/`aria-controls` toujours
  absent sur cinq déclencheurs, 5e famille consécutive à différer la
  question, plus aucune famille suivante dans SP-30 pour la trancher ;
  deux doctrines de mode démo différentes coexistent désormais sous le
  même layout — `HarvestSourcesAdminPage` masque sous `!readOnly`,
  `CollectionsAdminPage` ne le fait pas). **Ready to merge.**
- **SP-30k** (4 tâches, dernier reliquat nommé de la spec §2.1 —
  `ImportFileButton`/`NewItemButton`/`Tileset3DUploadButton`) — bascule
  des trois derniers composants de **chrome** (montés dans `TopBar`, sur
  toutes les routes protégées, à la différence de toutes les pages
  SP-30a→j) de `ui/dialog.tsx` vers `ui/kit/Drawer` (+ `Button`/`Input`
  du kit, tokens) : premier consommateur de production de `Drawer`
  (livré SP-29b, jamais consommé hors `KitGalleryPage` avant ce plan).
  Ancien funnel `onClose()` devient `onOpenChange={(next) => !next &&
  <funnel>()}` (vérifié empiriquement avant écriture du plan : Radix
  appelle `onOpenChange(false)` sur Échap et clic hors zone).
  `NewItemButton`/`ImportFileButton` préservent à l'identique l'absence
  de garde `busy` sur la fermeture ; `Tileset3DUploadButton` est seul à
  en avoir une réelle (`requestClose()`), préservée sur ses trois chemins
  de fermeture, test réécrit ciblant `dialog.previousSibling` (l'`Overlay`
  Radix ne porte pas `aria-hidden="true"`, contrairement à l'ancien fond
  fait main). `ui/button"`/`ui/input"`/`ui/dialog"` désormais absents de
  tout `shell/src/shell/` (grep élargi au dossier entier) — seuls deux
  consommateurs de `ui/dialog` restent dans tout le shell, tous deux hors
  périmètre par doctrine (`AppRuntimePage.tsx`, rendu public ;
  `builder/widgets/modal.tsx`, widget runtime « Modale »). E2E 118/4/0
  inchangé, suite complète relancée après **chaque** tâche (Global
  Constraint du plan). Vitest 219 fichiers/1833 tests, couverture shell
  91,07 %. Un implémenteur de tâche s'est arrêté une fois en attendant
  une notification de fond qui ne pouvait pas lui parvenir (piège déjà
  noté SP-29a) — relancé par message direct, sans conséquence. Revue
  finale (opus) : 0 Critical, 1 Important non bloquant
  (`ImportFileButton`/`NewItemButton` n'ont — et n'avaient déjà — aucune
  garde `busy` sur leur fermeture, comportement préexistant que le plan
  interdisait explicitement de « corriger » ici ; à tracker
  explicitement car SP-30k est la dernière brique nommée de la spec
  §2.1, aucun SP-30l ne l'héritera), 7 Minor (dont : `ui/kit/Drawer.tsx`
  sans `overflow-y-auto` sur son contenu — dette du **kit** lui-même,
  invisible aux deux filets de test, même classe que le Critical trouvé
  par SP-30d ; `Drawer.test.tsx` ne couvre que Échap, pas le clic hors
  zone, dont dépend désormais un consommateur réel ; modalité Radix
  (focus trap, scroll lock, `aria-hidden` sur le reste de la page)
  jamais mentionnée par le plan bien que ces trois composants soient
  montés sur toutes les routes protégées — vérifié qu'aucun portail
  Toast/Tooltip global n'en pâtit). **Ready to merge.** Avec cette
  branche, les neuf familles du §6.1 (SP-30a→j) et le dernier reliquat
  nommé du §2.1 (chrome) sont tous clos ; ne reste que la revue
  transverse de sortie de SP-30 (§7) et la dette de symbologie/popup
  imbriquée dans `LayersPanel` (notée SP-30c, hors périmètre de tout
  plan SP-30 jusqu'ici).
- **SP-30l** (3 tâches + round 2 de correction, revue transverse de sortie —
  §7 de la spec ; **ne clôt PAS SP-30**, cf. paragraphe round 2 en fin
  d'entrée et `### À venir`/SP-30) — les huit critères de sortie vérifiés un
  par un, pas supposés acquis parce que les neuf familles et le chrome sont
  clos. 1 bug réel
  trouvé : `useNarrowViewport` basculait sous `max-width: 389px`, classant
  390 px — la largeur CSS réelle des iPhone 12/13/14 et le seuil que la
  maquette elle-même nomme — comme *large* plutôt qu'étroit ; aucun test
  unitaire existant ne pouvait le voir, chacun stubbant `window.matchMedia`
  avec une valeur fixe plutôt que la vraie chaîne de requête (piège n°10).
  Second trou comblé : le badge de rôle (§7.8) n'était vérifié que par des
  tests unitaires MSW, jamais par un compte de test E2E dédié à cette
  question précise. Les six autres critères (chrome neuf partout, neuf
  domaines navigables, suites + portes de qualité vertes,
  `CollectionPermissions` sans `canWrite`, `ItemActions` sans raison de
  verrou dupliquée) étaient déjà acquis par SP-30a→k, re-vérifiés
  mécaniquement plutôt que supposés.
  **Revue finale de tout le plan (2026-09-02) : 4 Important, tous fermés** —
  (1) le seuil corrigé une première fois à `max-width: 390px`
  (`70146c8d`) ne suffisait pas : mesure réelle, de ~391 px à ~540 px la
  grille triptyque desktop (`grid-cols-[minmax(220px,280px)_1fr_
  minmax(260px,320px)]` de `TriptychLayout.tsx`) clippe toujours du
  contenu (clippé à 540 px, sans casse à partir de 640 px) — une bande qui
  couvre des téléphones réels courants (iPhone 14/15 Plus/Pro Max, Pixel
  7/8 Pro, iPhone XR/11). Décision (Tanguy) : seuil relevé à
  `max-width: 640px` (le seuil `sm` conventionnel de Tailwind), constante
  désormais exportée (`NARROW_QUERY`, `useNarrowViewport.ts`) plutôt que
  répétée en dur. Un second groupe de 8 tests vérifie désormais 641 px
  (juste au-dessus du seuil relevé) : 7 écrans passent sans contenu
  clippé, le 8e (Catalogue) est `test.skip()` avec un **nouveau défaut
  trouvé et documenté, non corrigé ici** (hors périmètre explicite de ce
  correctif) — la colonne centrale (`work`, 1fr) de `TriptychLayout` est
  affamée par les deux colonnes latérales, qui grandissent d'abord vers
  leur maximum (280+320=600 px) avant que la piste `1fr` ne reçoive quoi
  que ce soit (algorithme standard de dimensionnement CSS Grid) — un effet
  potentiellement partagé par les 8 écrans mais qui ne clippe visiblement
  que sur `CatalogPage.tsx` (résumés d'items effondrés à largeur 0)
  **(affirmation infirmée par le round 2 de vérification ci-dessous : le
  filet lui-même était vacant sur les 5 autres écrans concernés, et une
  fois corrigé il révèle un clipping stable sur 6 des 8 écrans, pas 1 —
  voir le paragraphe « Round 2 de correction » plus bas pour le détail
  exact)** ; un chantier de layout distinct, à ouvrir séparément, pas un
  simple réglage de seuil. (2) le filet `expectNoHorizontalOverflow()`
  d'origine (lisant `document.documentElement.scrollWidth`) était lui-même
  vacant — il peut lire 0 alors que du contenu réel est clippé, parce que
  le conteneur de contenu d'`AppLayout.tsx` est `overflow-y-auto` (l'axe X
  visible calcule
  alors à `auto` par la spec CSS, absorbant tout débordement avant le
  document) et que les cellules de la grille desktop sont
  `overflow-hidden` (elles clippent sans rien remonter) ; remplacé par
  `expectNoClippedContent()`, qui scanne tous les éléments dont le
  débordement X est significatif (`hidden`/`auto`/`scroll`) et vérifie
  qu'aucun n'a de contenu dépassant sa propre boîte — vérifié par
  falsification (piège n°10) : le nouveau filet échoue bien quand le
  seuil est délibérément re-régressé à 390 px, sur un vrai clippage
  mesuré (390 → 500 px, `CatalogPage.tsx`), pas seulement « les tests
  passent toujours ». (3) les trois copies quasi-identiques du littéral
  `GET /me` (`e2e/mocks.ts`, et les `meRoute()` locales des deux nouvelles
  specs) retombées sur un seul helper exporté `mockMe()` dans
  `e2e/mocks.ts`. (4) les deux tests `item-detail-panels.spec.ts` qui
  figeaient encore `width: 389` avec un commentaire défendant l'ancienne
  borne au pixel près sont repassés à 390 px (largeur représentative,
  plus de borne à défendre — le point même de ce correctif). Le critère
  « OpenAPI/types à jour » a nécessité une double vérification du fait de
  sessions concurrentes actives sur `core/` pendant ce correctif (module
  rôles/privilèges, capacité `adminToolsEnabled`) : un premier passage a
  trouvé `adminToolsEnabled` absent de `core/openapi.json`/
  `core-schema.d.ts` alors que déjà présent dans
  `core/app/auth/routes.py`/`instance/routes.py` — pas un défaut de ce
  plan, une dérive introduite par une branche concurrente non regénérée —
  résolue par cette même session concurrente avant la clôture de ce
  correctif (revérifiée par grep juste avant ce commit). Rappel pour la
  suite : dans un dépôt à sessions concurrentes, ce critère se revérifie à
  chaque clôture, il ne se suppose jamais acquis d'une vérification à
  l'autre. E2E 118/4/0 → 137/5/0 (118 pré-existants + 16
  `triptych-narrow.spec.ts` [8×390 px + 8×641 px, 1 skip documenté ci-
  dessus] + 4 `account-badge.spec.ts`).
  **Round 2 de correction (2026-09-02), sur ré-examen indépendant : la revue
  finale ci-dessus était elle-même trouée, et l'affirmation « SP-30 est clos »
  qui suivait était prématurée — corrigée ici.** Le filet ajouté par round 1,
  `expectNoClippedContent()` (`shell/e2e/triptych-narrow.spec.ts`), enveloppait
  sa mesure dans `expect(...).toPass({ timeout: 3000 })` — qui s'arrête au
  **premier** succès, jamais garanti d'observer l'état stabilisé. Sur 5 des 8
  écrans qui rendent réellement la grille de `TriptychLayout.tsx` (Cartes,
  Apps & sites, Analytique, Administration, Automatisation — Catalogue déjà
  correctement attrapé par round 1), le tout premier sondage tombait pendant
  la peinture
  initiale vide/chargement (0 offenseur), `toPass` déclarait la réussite
  immédiatement, et la mise en page réellement installée n'était jamais
  observée — un défaut du filet de test lui-même, pas de l'implémentation
  qu'il prétendait vérifier (piège n°10). Corrigé par un settle-poll réel :
  `expectNoClippedContent()` attend `networkidle` puis sonde le nombre
  d'offenseurs toutes les ~150 ms jusqu'à 3 mesures consécutives identiques
  (ou 5 s écoulées), et n'affirme qu'une fois sur cette mesure stabilisée —
  **vérifié par falsification réelle**, pas supposé : le check corrigé, lancé
  contre les écrans concernés, rapporte bien un nombre d'offenseurs stable et
  non nul (pas 0), confirmant qu'il peut désormais échouer sur une vraie
  casse. Une fois ce filet honnête, il révèle un clipping stable et réel à
  641 px sur **6 des 8 écrans**, pas 1 : Catalogue (5 offenseurs, inchangé),
  Cartes (3), Apps & sites (2), Analytique (1), Administration (1), et
  Automatisation (2, mais seulement après avoir corrigé un second défaut —
  voir ci-dessous). Seuls Tâches et Paramètres passent pour de vraies
  raisons (`TasksComingSoonPage.tsx`/`SettingsComingSoonPage.tsx` ne rendent
  qu'un `<EmptyState>`, aucune grille `TriptychLayout` à mesurer — confirmé
  par lecture directe du fichier). Racine commune, désormais nommée dans le
  code (`WIDE_BOUNDARY_ROOT_CAUSE`, `triptych-narrow.spec.ts` — supprimé par
  SP-33 une fois le défaut corrigé ; l'explication vit désormais dans la
  spec SP-33 et son entrée ### Livré) : la grille
  `grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]` de
  `TriptychLayout.tsx` maximise d'abord ses deux colonnes latérales (jusqu'à
  280+320=600 px combinés, algorithme standard de dimensionnement CSS Grid)
  avant de donner quoi que ce soit à la colonne centrale (`work`, piste
  `1fr`) — à 641 px elle n'hérite que de 41 px, quel que soit l'écran. Ce
  n'est pas propre à 641 px : la même famine plausiblement jusqu'à
  ~1000 px+ selon l'écran (ex. une fenêtre desktop en demi-écran) — un vrai
  chantier de layout sur `TriptychLayout` lui-même, partagé par les neuf
  familles SP-30, **non corrigé par ce round** (décision de Tanguy : borné,
  pas de correctif de layout improvisé dans ce round de correction de
  filets de test — un futur plan dédié le reprendra). Second défaut trouvé
  en vérifiant le premier : le test « Automatisation à 641 px » passait déjà
  avant round 2, mais pour une raison entièrement différente et sans
  rapport — sous les mocks e2e existants, `GET /pipelines/ops` n'était pas
  répondu du tout, `PipelineBuilderPage.tsx:62` restait bloqué sur
  `<p role="status">Chargement…</p>`, et la grille `TriptychLayout` n'était
  donc jamais atteinte (0 offenseur mesuré parce qu'il n'y avait rien à
  mesurer) — un faux vert, pas un écran correct. Corrigé en ajoutant un mock
  minimal de cette route dans le `before` de l'écran Automatisation
  (`AUTOMATISATION_OPS_CATALOG`), ce qui fait quitter la page son état de
  chargement et révèle la même famine de colonne centrale (2 offenseurs
  stables) que les cinq autres écrans. Un test de non-régression du seuil
  lui-même a aussi été ajouté (absent jusqu'ici : revenir `NARROW_QUERY` à
  `(max-width: 390px)` laissait toute la suite committée verte, puisqu'aucun
  test ne visait un viewport dans la bande 391-640 px) — un viewport à
  500 px doit rendre le mode étroit (`BottomNav`/« Navigation », onglets),
  pas la grille desktop ; vérifié par falsification (le test échoue bien
  quand le seuil est délibérément re-régressé à 390 px, puis le fichier est
  restauré). Le commentaire de `useNarrowViewport.ts` affirmant à tort que
  la grille tient « sans aucun clipping » à partir de 640 px a été réécrit
  pour dire le vrai : 640 px élimine la pire famine (colonne centrale à
  `clientWidth` 0 de 391 à 540 px) mais ne garantit rien au-dessus — le
  clipping résiduel de `TriptychLayout` y est désormais documenté et pointé
  vers cette même entrée (commentaire depuis réécrit par SP-33, qui pointe
  vers sa propre spec et le lot Carte plutôt que vers cette entrée — le
  défaut lui-même est corrigé, cf. ### Livré/SP-33). E2E 137/5/0 → **143
  tests (133 passed/10
  skipped/0 failed)** — 5 skips 641 px supplémentaires (Cartes/Apps &
  sites/Analytique/Administration/Automatisation, en plus du skip Catalogue
  déjà présent) et 1 test de non-régression du seuil en plus. Vitest 220
  fichiers/1839 tests, tous passés. **Conséquence assumée avec Tanguy :
  SP-30 N'EST PAS déclaré clos par ce round** — le critère de sortie §7
  « aucun écran ne clippe au-dessus du seuil » n'est en réalité vérifié que
  sur 2 des 8 écrans de référence (Tâches, Paramètres) ; le défaut de
  `TriptychLayout` ci-dessus reste le seul bloquant avant de pouvoir
  redéclarer SP-30 clos (cf. `### À venir`, entrée SP-30, pour le suivi
  scopé ; blocage levé par SP-33, cf. son entrée dans ### Livré) — ce
  correctif règle l'honnêteté des tests et de la documentation, pas le
  défaut de layout lui-même.

Jalons atteints : **M1, M2, M4, M5, M11, M12, M13, M15, M16**. **M14** reste
bloqué par la seule vérification réelle des 5 tests `@pytest.mark.qgis`.

- **SP-32 — Traefik /admin/\*** (7 tâches, spec
  `2026-09-01-traefik-admin-tools-design.md`, plan
  `2026-09-01-traefik-admin-tools.md`) — URLs cohérentes
  `/admin/martin`, `/admin/titiler`, `/admin/grafana` derrière un gate
  cookie que seul un admin peut ouvrir depuis le shell : module
  `core/app/admin_tools/` (jeton de lancement HMAC à durée de vie courte
  (60s), non révocable avant expiration, sans suivi de consommation
  (même choix que `app/auth/export_tokens.py`, SP-17a) :
  `POST /admin-tools/launch/{tool}` Bearer-admin → jeton de lancement →
  `GET /admin-tools/session/{tool}` échange le jeton contre un cookie
  `gs_admin_session` HttpOnly/Secure/SameSite=Strict/Path=/admin de 30 min
  — **premier cookie de tout ce dépôt** — vérifié par `GET
  /admin-tools/verify`, la cible du `forwardAuth` Traefik), les trois
  routes montées uniquement si `CORE_ADMIN_TOOLS_ENABLED` (même convention
  que `terrain3d`/`tileset3d`/`copilot`, absentes de l'export OpenAPI par
  défaut). Sous-chemin par outil vérifié contre l'image réelle : `--base-path`
  pour Martin, `TITILER_API_ROOT_PATH` pour Titiler, `GF_SERVER_ROOT_URL`/
  `GF_SERVER_SERVE_FROM_SUB_PATH` pour Grafana (seul des trois SANS
  `stripprefix`, préfixe conservé — vérifié empiriquement contre
  `grafana/otel-lgtm:0.11.4` réel). Overlay prod (`docker-compose.prod.yml`)
  reprend les mêmes noms de routeur/service/middleware, substitue
  `entrypoints=web`/`${GEOSTUDIO_PUBLIC_HOST}` (pas d'ACME). Shell :
  `ItemClient.launchAdminTool`/`useLaunchAdminTool`, page
  `AdminInfrastructurePage` (`/admin/infrastructure`, `RequireRole
  role="admin"`, trois boutons masqués — pas juste désactivés — quand la
  capacité est inactive, lien de découverte depuis `AdminExtensionsPage`)
  + lien MinIO direct non gaté (limite technique assumée, cf. spec §1/§5).
  E2E 130/4/0 → **inchangé** (aucun nouveau spec E2E dans ce plan, cf.
  spec §7) ; suite complète relancée en contexte élargi (post-SP-30l) :
  Vitest shell 220/220 fichiers, 1839/1839 tests, E2E 141 (136 passed/5
  skipped, 1 flake de contention confirmé et effacé en isolation — cf.
  ci-dessous). Suite core : 69/69 tests admin_tools-spécifiques,
  `test_deployability.py` 35/35, portes qualité (ruff/mypy --strict/
  lint-imports/couverture 85,69 %) toutes vertes. **Exécuté sur un
  checkout partagé avec une session concurrente active** (refactor
  "roles/privileges", `2026-09-02-roles-privileges-implementation.md`) :
  contention réelle de ports/build shell (E2E, coordonnée directement avec
  l'autre session) et 14 échecs de la suite core préexistants/hors-scope
  (retrait de `user.is_analyst`, confirmé en isolant les 5 fichiers
  concernés → 0 échec restant). **Le smoke test réel de bout en bout
  (Step 6 : lancement→session→cookie→accès Martin via Traefik) n'a PAS pu
  être rejoué dans cet environnement** — deux blocages indépendants, ni
  l'un ni l'autre imputable à ce plan : (1) `traefik:v3.0.4` ne peut pas
  parler au démon Docker de cette machine (`Error response from daemon:
  ""` en boucle, TOUS les routeurs Traefik répondent 404, y compris une
  route préexistante sans rapport testée en contrôle) — skew de version
  probable entre l'image pinnée et un moteur Docker très récent
  (29.4.3/API 1.54), persiste après redémarrage du conteneur ; (2) requête
  authentifiée directe contre `core` (contournant Traefik) répond 500 —
  `relation "roles" does not exist`, la session concurrente
  "roles-privileges" n'a pas encore écrit sa migration Alembic (ses
  propres tests passent en SQLite mémoire, schéma construit hors Alembic,
  trou invisible à sa propre suite). Décision actée avec Tanguy : clore ce
  plan sur la preuve statique (`docker compose config`, Tâches 4/5) + la
  preuve TDD (Tâche 3, 10/10, `GET /admin-tools/verify` sans cookie
  confirmé 403 en direct contre `core:8200`) plutôt que d'attendre la
  résolution de ces deux éléments externes — **à rejouer réellement une
  fois les deux résolus**, ni l'un ni l'autre dans le périmètre de ce
  plan.
  **Suivi non bloquant, sécurité, à trancher séparément** : le nouveau
  bloc `otel-lgtm` de l'overlay prod ne fait pas `ports: !reset []`
  (contrairement à `martin`/`titiler`) — Grafana (3001) et les deux ports
  OTLP (4317/4318) restent publiés directement sur l'hôte en prod, hors du
  gate `/admin/grafana` ; conforme au texte littéral du plan, pas un
  défaut de son exécution.

- **SP-31 — rôles à base de privilèges** (17 tâches + 1 correctif hors-plan
  + 1 lot de correctifs de revue finale, spec
  `2026-09-01-roles-privileges-design.md`, plan
  `2026-09-02-roles-privileges-implementation.md`) — remplace
  `User.is_admin`/`User.is_analyst` (deux booléens plats) par un modèle de
  rôles nommés à privilèges cochés : **18 privilèges** catalogués
  (`app/roles/privileges.py::Privilege` — le texte du plan disait « 17 »
  partout, coquille de prose jamais reflétée dans le code, corrigée ici),
  **4 rôles prédéfinis immuables par tenant** (Administrateur/Créateur/
  Analyste/Lecteur — API rejette 400 sur tout PATCH, nom **et** privilèges,
  y compris sur le rôle Admin — décision explicitement tranchée avec Tanguy
  après qu'une revue a trouvé le texte littéral du plan auto-contradictoire
  entre son code de garde et son propre test) + rôles sur mesure créés par
  tenant. `User.role_id` (FK NOT NULL) remplace `is_analyst` (colonne
  supprimée) ; `is_admin` **survit** comme colonne synchronisée
  exclusivement par la logique de rôle (jamais réglée indépendamment,
  ~20 sites de lecture existants inchangés). Nouveau module `app/roles/`
  (modèle, catalogue, repository, garde `require_privilege`, routes CRUD
  `/roles`+`/roles/catalog` gardées `admin.roles.manage`, anti-lockout sur
  `PATCH /roles/{id}` et `PATCH /users/{id}`), migration Alembic 0030
  testée dans les deux sens sur base non vide réelle. Cinq modules migrés
  de `_require_admin(user)` local vers `require_privilege(session, user,
  Privilege.X.value)` (extensions, harvest, secrets, collections, SQL
  Lab — dernier consommateur de `is_analyst`). Côté shell :
  `Me.role`/`Me.privileges` remplacent `isAdmin`/`isAnalyst`/
  `hasAnyEditorRole` ; `capabilities.ts` gagne un `requiresPrivilege` sur
  cinq domaines (Données/Apps/Automatisation/Analytique/Tâches,
  auparavant visibles à tout authentifié quel que soit son rôle) — ferme
  enfin le trou « le profil Lecteur n'est pas dérivable du modèle actuel »
  documenté depuis SP-29a ; `RequireRole` supprimé, remplacé par
  `RequirePrivilege` sur les 4 routes `/admin/*`+`/analytics/sql`
  existantes **et** la 5e route `/admin/infrastructure` ajoutée entre
  temps par la session Traefik concurrente (découverte et convertie au
  passage, sans quoi la suppression de `RequireRole` l'aurait cassée) ;
  nouvel écran `RolesAdminPage` (créer/éditer/supprimer un rôle sur
  mesure, cases à cocher par domaine) — patron répliqué de
  `HarvestSourcesAdminPage`.
  Exécuté sur un **checkout partagé avec une session concurrente active**
  (Traefik `/admin/*`, ci-dessus) — coordination directe tout au long
  (heads-up avant chaque build/e2e, diagnostic conjoint d'un conflit
  d'index git résiduel sans rapport avec l'un ou l'autre plan). Débloque
  le blocage (2) noté par l'entrée Traefik ci-dessus (`relation "roles"
  does not exist`) : la migration 0030 existe désormais, le smoke test
  Traefik bout-en-bout reste à rejouer par une future session.
  Suite complète cœur **1912→1915 passed** / 168 skipped / 0 failed
  (référence CLAUDE.md pré-plan : 1896+5+1 intermittent — delta positif,
  aucune régression, les 2 échecs pré-existants documentés non reproduits
  dans cet environnement). Suite shell **221 fichiers/1846 tests, 0
  failed**, couverture 90,5 % (seuil 88), `tsc --noEmit` propre.
  **E2E cassé puis réparé en cours de vérification finale** (piège n°6
  concrétisé à grande échelle) : aucune des tâches shell n'avait fait
  tourner la suite E2E complète (seulement Vitest+tsc, comme spécifié par
  leurs briefs respectifs) — au premier run complet, 121 échecs sur ~135,
  tous tracés à `shell/e2e/mocks.ts` et 11 specs encore construits sur
  l'ancienne forme de `/me` (`isAdmin`/`isAnalyst`/`hasAnyEditorRole`),
  faisant planter `AppErrorBoundary` sur quasi toute page authentifiée.
  Diagnostiqué (pas supposé) et corrigé : 4 profils canoniques exportés
  dans `mocks.ts`, alignés item-pour-item sur `BUILT_IN_ROLE_PRIVILEGES`.
  **133 passed / 10 skipped / 0 failed** après correctif — vérifié via
  `test-results/.last-run.json`, pas le tail tronqué et trompeur du
  reporter Playwright `list` sur un run de ~14 minutes (piège
  méthodologique à retenir pour toute future vérification E2E longue).
  **Revue finale de branche (opus, package scopé par pathspec — `dev`
  avait reçu ~20 commits étrangers interleaved de la session Traefik
  pendant l'exécution) : 0 Critical, 9 Important.** Mécanisme
  d'autorisation lui-même jugé correct, complet, bien testé (aucune route
  n'a perdu de garde, `can()`/`decide()` intact, migration saine dans les
  deux sens). Lot de 10 correctifs appliqué et re-revu (0 Critical/
  Important restant, « Ready to merge: Yes », les 3 correctifs à plus
  fort enjeu vérifiés par falsification active, pas seulement lus) :
  - `ensure_built_in_roles` ne resynchronisait jamais un rôle prédéfini
    déjà créé — un privilège futur serait resté inatteignable à jamais
    pour tout tenant existant (rôle prédéfini totalement figé côté API,
    aucune réparation possible hors migration). Corrigé : resynchronise
    nom+privilèges à chaque appel (déjà sur le chemin chaud de toute
    requête authentifiée, coût nul mesuré — colonne JSON inchangée
    suppressée du flush par SQLAlchemy).
  - **Le plus sérieux** : le chemin de connexion (`get_or_create_user`,
    branche `bootstrap_analyst`) pouvait écraser silencieusement le rôle
    sur mesure d'un utilisateur vers "analyst" à la connexion suivante si
    son sub apparaissait dans `CORE_ANALYST_SUBS` — sans passer par aucun
    des deux gardes anti-lockout HTTP, contournement réel de l'invariant
    que la spec design demandait explicitement en couche service.
    Régression par rapport à l'ancien code (qui n'ajoutait jamais, ne
    retirait jamais). Corrigé : la promotion ne part plus que des rôles
    prédéfinis non-privilégiés (creator/reader), ne touche plus jamais un
    rôle sur mesure.
  - 3 commentaires vivants attribuant encore une garde à `_require_admin`
    supprimé — même classe de défaut déjà payée 2x sur ce dépôt
    (SP-30g/SP-30i).
  - Docstring `CollectionPermissions` (réécrite par ce même plan) corrigée
    pour dire le vrai : `delete` reflète encore `actor_is_admin`
    (`is_admin`), pas le privilège `admin.collections.manage` — écart
    architectural documenté en suivi ci-dessous, PAS résolu par ce
    correctif (portée délibérément limitée au commentaire).
  - Test `DELETE /roles/{id}` "encore utilisé" (409) ne testait jamais ce
    chemin (supprimait un rôle prédéfini, heurtait la garde d'immutabilité
    400 avant d'atteindre la garde de compte de porteurs) — corrigé sur un
    rôle sur mesure réel.
  - `DomainBar.test.tsx` figeait l'ancien comportement (Créateur sans
    Analytique) sous une fixture prétendant refléter le cœur mais fausse —
    contredisait `capabilities.test.ts`, qui teste le changement
    délibéré inverse. Corrigé — **révèle un suivi produit non résolu, cf.
    ci-dessous**.
  - `RolesAdminPage` (fonctionnalité phare de ce plan) inatteignable
    depuis l'UI — aucun lien, seule la route existait. Corrigé (patron
    répliqué du seul lien `/admin/*` existant).
  - `app/roles` ajouté à `mypy --strict` (CI + commande locale) ; 2
    erreurs réelles trouvées et corrigées (annotation + branche morte,
    aucun changement de comportement).
  - Post-condition perdue sur `test_patch_user_cross_tenant_returns_404`
    restaurée ; nouveau test du scénario « conjoint » explicitement non
    testé par ce plan (rôle sur mesure porteur des deux privilèges
    anti-lockout, seul porteur, tentative de le lui retirer via
    `PATCH /users/{id}`) — vérifié par falsification qu'il exerce bien la
    garde `count_users_with_privileges`, distincte de celle déjà couverte
    côté `PATCH /roles/{id}`.
  Suivis non bloquants documentés, non corrigés (décisions de périmètre
  plus larges qu'un lot de correctifs sans nouvelle décision produit) —
  **la divergence `is_admin` vs `require_privilege` sur les 3 sites
  ci-dessous (`extensions.include_disabled`, scope de liste
  `/collections`, `CollectionPermissions.delete`) est désormais traitée,
  cf. `### Livré`/SP-35** :
  cast `entry.labelKey as MessageKey` non gardé dans les deux panneaux de
  rôle (aucun test ne lie le catalogue cœur aux clés `catalog.fr.ts`) ;
  5 des 18 privilèges (`catalog.manage`/`maps.manage`/`data.manage`/
  `automation.secrets.manage`/`tasks.view_all`) n'imposent rien nulle
  part — hérité du périmètre de la spec design elle-même (§3.2 prévoyait
  une paire view/manage par domaine, seul `data.view` existe côté
  Lecteur), pas un défaut de cette exécution ; **corriger la fixture
  `DomainBar.test.tsx` légitime un lien de nav vers le domaine Analytique
  pour un Créateur dont l'unique destination (`/analytics/sql`) le
  refuse** (`analytics.sql_lab.access`, que Créateur n'a pas) — exactement
  l'anti-pattern qu'`ItemActions` avait éliminé (SP-29a) ; décision
  produit à trancher (gater le domaine sur `analytics.sql_lab.access`, ou
  donner une autre destination), pas improvisée ici ; même défaut sur le
  nouveau lien `/admin/roles` lui-même (ungated pour qui n'a pas
  `admin.roles.manage`, mais cohérent avec le seul précédent existant,
  `/admin/infrastructure`) ; `/admin/harvest`/`/admin/collections`
  toujours inatteignables depuis la nav (préexistant, confirmé contre le
  commit de base — sans rapport avec ce plan) ; privilèges du Créateur
  triplement dupliqués (cœur + 2 fixtures test shell) sans lien
  mécanique — le prochain privilège ajouté rouvrira la même classe de
  défaut que `DomainBar.test.tsx` ci-dessus ; `GET /users` en N+1 (une
  requête de rôle par utilisateur) contre la doctrine SP-29a d'une seule
  requête par page.
- **SP-33 — TriptychLayout : fin de l'affamement de la colonne centrale**
  (4 tâches, spec/plan
  `2026-09-02-sp33-triptychlayout-colonne-centrale-*.md` — **clôt le
  blocage documenté par SP-30l/round 2**, seul point qui empêchait de
  redéclarer SP-30 clos) — deux changements ciblés dans
  `shell/src/shell/chrome/` : la grille de `TriptychLayout.tsx` passe de
  `grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]` à
  `grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)]`
  (plancher CSS explicite de 360px sur la colonne centrale, au lieu d'une
  piste `1fr` nue affamée par les deux colonnes latérales) ; le seuil
  partagé étroit/large `NARROW_QUERY` (`useNarrowViewport.ts`) passe de
  `(max-width: 640px)` à `(max-width: 899px)` — calé juste au-dessus de la
  somme des trois planchers (220+360+260=840px, +~60px de marge) pour que
  la grille à trois colonnes ne soit jamais rendue en dessous du point où
  les trois peuvent coexister sans dépassement. Hypothèse 360px/899px
  confirmée **dès le premier essai empirique**, aucun palier
  intermédiaire nécessaire. Effet de bord mesuré dans la bande 900-959px
  (juste au-dessus du nouveau seuil) : les deux colonnes latérales
  elles-mêmes rendent plus étroites que leur ancien maximum —
  `browse` ~250-260px au lieu de 280px, `inspect` ~290-300px au lieu de
  320px — toujours confortablement au-dessus de leurs planchers déclarés
  (220px/260px), donc sans clipping : comportement CSS Grid correct et
  attendu, pas une régression, mais qui distingue le changement de
  *source* (« seules la colonne centrale et le seuil bougent ») du
  *rendu* réel dans cette bande. Exclusion explicite et documentée (commentaire
  `useNarrowViewport.ts` + `shell/e2e/triptych-narrow.spec.ts`) de deux
  défauts pré-existants et sans rapport sur l'écran Cartes (colonne
  `browse` trop étroite pour `LayersPanel` ; `<span>` de titre
  `LayersPanel` à largeur nulle — cf. lot **Carte** ci-dessous) : ce test
  reste seul `test.skip()` de `triptych-narrow.spec.ts`. Un commentaire
  devenu stale dans
  `shell/e2e/item-detail-panels.spec.ts` (deux occurrences citant encore
  le seuil 640px de SP-30l) corrigé pour citer 899px/SP-33. Suite complète
  relancée avant clôture (piège n°6) : Vitest shell 221 fichiers/1848
  tests, 0 échec, couverture 90,51 % (seuil 88) ; Playwright 143 tests —
  138 passed/5 skipped/0 failed (4 skips pré-existants sans rapport —
  `connected-export.spec.ts`, `static-export.spec.ts` ×3 — + le seul skip
  Cartes ci-dessus ; `triptych-narrow.spec.ts` seul : 16 passed/1
  skipped/0 failed). Aucun changement sous `core/` (confirmé par
  `git diff --stat` scopé aux commits de ce plan) : pas de régénération
  OpenAPI/TS nécessaire. **Avec cette branche, SP-30 est clos** : les huit
  critères de sortie du §7 sont désormais tous acquis. Ne restent, par
  ailleurs et sans rapport avec cette clôture, que les items déjà listés
  en suivi non bloquant sous `### À venir` (permissions de collection et
  profil « Lecteur », raison de verrouillage triplée d'`ItemActions`,
  retrait des anciens fichiers `ui/*`, le lot **Carte**, et la longue
  liste de suivis Minor accumulés SP-29b→SP-30k) — ce plan ne les résout
  pas et ne prétend pas les résoudre.
- **SP-34 — dette de tokens `LayersPanel`/`MapSymbologyEditor` et voisins**
  (10 tâches, spec/plan `2026-09-03-sp34-dette-tokens-layerspanel-*.md` —
  referme le chantier que SP-30c avait explicitement mis de côté et que
  « Conventions tranchées (2026-09-01) » ci-dessous avait acté comme son
  propre chantier séparé) : les **48 occurrences** de couleurs Tailwind
  brutes (`slate-*`, `red-*`, `amber-*`, `blue-700`, `bg-white`/`white`)
  recensées sur les 8 fichiers de `shell/src/map/` remplacées par les
  tokens sémantiques (`ink`/`ink-2`/`ink-3`/`rule`/`danger`/`warn`/
  `accent`/`surface`/`sunken`), sans aucun changement de comportement —
  `formFieldStyles.ts` (1 occurrence, + `inputCls` relevé `h-8`→`h-9`,
  convention 2026-09-01), `FieldClassificationPicker.tsx` (4),
  `MapSymbologyEditor.tsx` (28, en deux tâches — bascule de 5 actions
  autonomes vers `Button` du kit (« Recalculer… »×3, « Ajouter un
  contour/des icônes/une étiquette ») puis tokens restants), `PopupEditor.tsx`
  (7, + abandon de
  sa copie locale de `labelCls`/`inputCls` au profit de l'import de
  `formFieldStyles.ts`, fermant la duplication que son propre commentaire
  signalait), `LayersPanel.tsx` (0 couleur brute mais son séparateur
  `border-t` non tokenisé — noté par la revue finale SP-30c — tokenisé au
  passage), `MapMeasureSketchToolbar.tsx` (3), `MapPopup.tsx` (4),
  `MapLegend.tsx` (1). Décision de brainstorming actée explicitement : les
  **trois superpositions carte** (`MapMeasureSketchToolbar`/`MapPopup`/
  `MapLegend`, `position: absolute` par-dessus le canevas, catégorie
  distincte des cinq éditeurs de formulaire) sont **incluses et
  tokénisées complètement**, sans exception de fond figé en blanc — elles
  peignent leur propre fond avant tout texte, donc aucun risque de
  contraste contre les tuiles de fond de carte, et le dépôt n'avait établi
  nulle part de précédent « ce composant s'exclut de l'ambiance ».
  Exclusions hors périmètre, assumées et documentées dans la spec :
  `LayerPicker.tsx` (dette de `border-t` séparée, notée SP-30c, non
  reprise ici) ; conversion des `<select>`/`<input list=…>` (datalist)
  vers `Select`/`Combobox` du kit (changerait le comportement — liste
  fermée vs saisie libre — pas seulement l'apparence) ; conversion du
  toggle « Couleur de contour fixe/par attribut » vers `Segmented` du kit
  (encapsule une garde anti-reclic documentée Important en revue finale
  SP-27, resterait un changement structurel). Vérification finale (Task
  10) : grep de clôture sur les 8 fichiers avec la commande exacte de la
  spec (incluant l'angle mort `text-white`/`text-black` sans suffixe
  identifié par SP-30f) — un seul hit, faux positif attendu et vérifié
  (`-translate-x-1/2`/`-translate-y-full` de `MapPopup.tsx` contiennent la
  sous-chaîne littérale « slate » ; un grep affiné à `slate-[0-9]` sur les
  8 fichiers revient bien vide). Vitest shell 221 fichiers/1848 tests, 0
  échec — compte identique à la référence SP-33 (aucun test ajouté ni
  supprimé par ce plan, conforme à la spec : la suite de test de ces 13
  fichiers ne référence aucune classe Tailwind en dur, donc rester verte
  sans modification sert de garde-fou comportemental). `npm run build`
  propre (`tsc --noEmit` + `vite build`). Playwright 138 passed/5
  skipped/0 failed — identique à la référence SP-33 (vérifié via
  `test-results/.last-run.json`, pas le tail du reporter `list`, piège
  méthodologique documenté). **Contrôle visuel manuel réalisé contre un
  backend réel** (stack `docker compose up -d` complète, 11 services,
  `CORE_AUTH_MODE=mock`) plutôt que des mocks E2E : Map créée, couche
  ajoutée par URL GeoJSON (fonctionnalité SP-28, 6 points de test servis
  localement), symbologie configurée couleur classée (Quantiles, 5
  classes) + contour fixe + icônes + étiquette, popup liste de champs +
  gabarit avancé — capturés en écran clair **et** sombre (même session,
  `page.emulateMedia({colorScheme})`, sans rechargement) : tout paraissait
  lisible et cohérent dans les deux ambiances lors de ce contrôle — **constat
  incomplet, corrigé plus bas par la revue finale de branche.** **Constat
  fait pendant ce contrôle, pas un défaut de
  ce plan** : la barre de mesure/croquis (`MapMeasureSketchToolbar.tsx`)
  ne se monte jamais depuis l'onglet Carte de `MapEditorPage` lui-même —
  `interactiveTools` n'y est jamais passé à `MapView` (seul
  `mapWidget.tsx` le fait, via `ctx.mode !== "edit"`, pour le widget Carte
  du builder) ; comportement préexistant, confirmé par lecture directe des
  trois fichiers, à ne pas confondre avec une régression de cette
  branche — la légende et la popup au clic, elles, sont bien visibles
  directement dans l'éditeur de carte. Vérifiée à la place via une App
  minimale portant un widget Carte lié à une collection réelle, en mode
  Aperçu (`ctx.mode="preview"`) : légende et barre de mesure/croquis
  s'affichent, tokenisées correctement, dans les deux ambiances. Quelques
  erreurs 500 intermittentes observées dans les logs `core` pendant le
  contrôle (`psycopg.errors.DuplicatePreparedStatement` sous pgbouncer) —
  artefact d'infrastructure sans rapport avec ce plan (aucun changement
  sous `core/`, confirmé), sans conséquence sur les écrans vérifiés.
  **Revue finale de branche (opus) : 1 Important trouvé et corrigé, invisible
  au contrôle visuel manuel ci-dessus** — les trois superpositions carte
  (`MapLegend.tsx`, `MapMeasureSketchToolbar.tsx`, `MapPopup.tsx`) peignent
  leur conteneur flottant en `bg-surface`/`bg-surface/90` sans jamais
  l'associer à `text-ink`, alors que rien dans ce dépôt ne fixe de couleur de
  texte racine (le texte résout donc à la couleur par défaut du navigateur,
  noir, dans les deux ambiances). Avant cette branche, ces trois fichiers
  étaient protégés par construction : `bg-white`/`bg-white/90` forçait un
  fond blanc, rendant le texte noir non tokenisé toujours lisible quelle que
  soit l'ambiance. Cette branche a fait suivre le fond à l'ambiance (`#101a1e`
  en sombre) sans faire suivre le texte — texte noir sur fond quasi-noir en
  ambiance sombre, régression que le contrôle manuel ci-dessus n'a pas
  détectée (capturé en ambiance claire d'abord, où le défaut ne se voit pas).
  Corrigé en ajoutant `text-ink` aux trois conteneurs, à côté de la classe
  `bg-surface`/`bg-surface/90` déjà en place — className seul, aucun
  changement de comportement, les 46 tests existants des 3 fichiers +
  `PopupEditor.tsx` restent verts sans modification. 2 Minor également
  corrigés dans le même lot : commentaire `denseInputCls` de `PopupEditor.tsx`
  resserré pour ne revendiquer que la parité de hauteur `h-8` avec
  `QueryFilterBuilder.tsx`/`CrossFilterLinkEditor.tsx` (pas leur recette
  complète, qu'il n'a pas) ; ordre des deux tâches sur
  `MapSymbologyEditor.tsx` corrigé ci-dessus (bascule vers `Button` d'abord,
  tokens ensuite — l'inverse de ce que cette entrée affirmait initialement).
  **Re-revue de ce correctif (round 2, même jour) : même classe de défaut
  trouvée sur 2 sites de plus**, restés hors du lot ci-dessus — les deux
  boutons de bascule « Couleur de contour fixe »/« Couleur de contour par
  attribut » de `MapSymbologyEditor.tsx` (lignes ~415/437) peignaient leur
  fond actif en `bg-sunken` (`#16232a` en ambiance sombre) sans jamais
  l'associer à `text-ink` non plus — exactement le même mécanisme, le
  balayage de clôture (Task 10) ne portant que sur les couleurs Tailwind
  brutes, pas sur cette classe de défaut de contraste. Le correctif complet
  couvre donc **5 sites au total** (les 3 superpositions carte ci-dessus +
  ces 2 boutons de bascule), tous par simple ajout de `text-ink` au
  className statique, sans changement de comportement — `MapSymbologyEditor.
  test.tsx` 43/43 avant et après, fichier de test non modifié. Balayage
  indépendant de la re-revue (round 2) sur tout le plan (10 tâches +
  2 correctifs) confirmant qu'il n'existe pas de 6e site : aucun fond racine
  n'est jamais posé sur ce shell (`AppLayout`/`TriptychLayout`/`tokens.css`),
  donc seul un élément qui peint lui-même un fond suivant l'ambiance peut
  porter ce défaut — ensemble borné et désormais entièrement apparié.
  **Ready to merge** — les deux correctifs appliqués et re-vérifiés
  indépendamment.
- **SP-35 — cohérence privilège/`is_admin`** (6 tâches + 2 lots de
  correctifs de revue finale, spec
  `2026-09-03-sp35-coherence-privilege-is-admin-design.md`, plan
  `2026-09-03-sp35-coherence-privilege-is-admin.md` — referme le suivi non
  bloquant ouvert par SP-31 « visibilité `is_admin` vs garde
  `require_privilege` divergentes sur 3 sites ») : **4 sites** dans
  `core/app` où une lecture directe de `user.is_admin` gouvernait une
  décision de visibilité/autorisation migrés vers le privilège nommé
  correspondant — `list_visible_collections` (portée de `GET /collections`,
  paramètre renommé `is_admin`→`can_see_all`, câblé sur
  `admin.collections.manage`), `CollectionPermissions.delete` (via
  `_collection_permissions`/`collection_permissions_by_id`, même privilège
  — `read`/`write`/`share` inchangés), `list_extensions`'s
  `include_disabled` (`admin.extensions.manage`), et
  `app/admin_tools/routes.py::launch_admin_tool` (4e site, **trouvé par
  l'audit étendu de ce plan lui-même, jamais dans la liste SP-31** — ce
  module avait été bâti par l'effort Traefik concurrent, SP-32, antérieur
  au système de privilèges et jamais migré ; le local `_require_admin(user)`
  supprimé au profit de `require_privilege(…, Privilege.
  SETTINGS_INSTANCE_MANAGE.value)`, comblant un vrai trou où le shell
  gatait déjà le bouton sur ce privilège mais un porteur de rôle sur mesure
  obtenait un 403 réel au clic). Nouveau `has_privilege(session, user,
  privilege) -> bool` (`app/roles/guards.py`), variante booléenne sœur de
  `require_privilege` (qui délègue désormais à elle), même signature de
  paramètres, consommée identiquement par les 3 premiers sites.
  **Deux trous de plan trouvés et corrigés en cours d'exécution, pas
  improvisés en aparté** : Task 2 — le brief n'anticipait que 5 sites
  d'appel de test pour le paramètre renommé, 3 sites de *production*
  existaient aussi (`app/dcat/routes.py`, `app/features/routes.py`,
  `app/stac/routes.py`) — renommage de kwarg pur, aucun changement
  sémantique, corrigé et disclosé dans le commit. Task 3 — le test de bout
  en bout du texte littéral du plan exigeait qu'un porteur de rôle sur
  mesure obtienne un 204 sur `DELETE /collections/{id}`, mais la porte de
  visibilité partagée `get_readable_collection` (utilisée par
  GET/PATCH/DELETE sur une collection unique) n'avait aucune notion du
  nouveau privilège et renvoyait 404 avant même d'atteindre la garde de
  suppression — corrigé par un paramètre de contournement opt-in
  `can_manage_collections` (défaut `False`, ~14+3 sites d'appel existants
  non affectés, vérifié). **Escaladé à Tanguy comme une vraie décision de
  périmètre** : le contournement doit-il s'appliquer seulement à DELETE (le
  minimum prouvé nécessaire par le test), ou aussi à GET/PATCH (cohérence
  plus large, mais expose le champ `extent` de collections privées à des
  porteurs de privilège non propriétaires, et transforme un 404 en 403 sur
  PATCH sans accorder l'écriture) ? **Tanguy a explicitement choisi de
  garder les trois (GET+PATCH+DELETE)** pour la cohérence — une vague de
  correctifs a ensuite clarifié par commentaire que le contournement de
  PATCH ne joue que sur la visibilité (la garde d'écriture réelle reste
  intacte, toujours gardée par `actor_is_admin`), et retiré deux
  re-requêtes de privilège redondantes. Suite cœur **1912→1920 passed** /
  168 skipped / 0 failed (référence CLAUDE.md pré-plan : 1912-1915 selon
  l'entrée SP-31 — delta positif, aucune régression). Vérifications de
  clôture (Task 6) toutes vertes : `mypy --strict app/auth app/secrets
  app/analytics app/copilot app/admin_tools app/roles` propre (la spec
  affirmait à tort que `app/admin_tools` n'était pas dans le périmètre
  `--strict` CI — il l'est déjà, `.github/workflows/ci.yml:60`, corrigé en
  cours de planification) ; `ruff check`/`ruff format --check` propres ;
  `lint-imports` propre (30 entrées, aucun nouvel import cross-module) ;
  diff OpenAPI **vide** (seule la logique interne d'un booléen déjà
  existant change, aucune forme de route/schéma) ; `mypy app/` informatif
  — 3 erreurs préexistantes dans `app/collections/` (lignes identiques,
  vérifiées mot pour mot contre le commit de base `e03d521c`, non
  attribuables à ce plan), aucune nouvelle erreur sur les fichiers
  touchés.
  **Revue finale de branche (opus, package des 6 tâches) : 0 Critical, 3
  Important, 8 Minor.** (1) La spec elle-même se trompait sur son propre
  périmètre : « aucun autre site » (§Motivation) était faux — 3 sites de
  production (`app/dcat/routes.py`, `app/features/routes.py`,
  `app/stac/routes.py`) appelaient encore
  `list_visible_collections(can_see_all=user.is_admin)`, la même fonction
  que Task 2 avait re-clée sur le privilège, oubliée par une exclusion mal
  posée (le motif « alimente `decide()`/`can()` » ne s'appliquait pas à ces
  appels). (2) `permissions.read` reste à `false` sur une collection
  pourtant servie en 200 grâce au contournement `can_manage_collections` —
  un contrat de réponse qui se contredit lui-même (même classe de défaut
  qu'Important en SP-29a). (3) Les sous-ressources `GET`/`PUT
  /collections/{id}/sharing` et `GET /collections/{id}/schema` restaient
  404 pour ce rôle malgré la visibilité GET/PATCH/DELETE déjà étendue — le
  panneau Partager de `CollectionsAdminPage` affiche désormais la ligne
  (grâce à cette branche) mais 404 au clic. **Les trois soumis à Tanguy** :
  (1) corriger — accepté ; (2) documenter dans le docstring plutôt que
  changer le comportement — accepté ; (3) étendre le contournement à
  `/schema`+`/sharing` — accepté, cohérent avec la décision GET+PATCH+DELETE
  déjà prise en Task 3. Lot de correctifs (commit `f23fe291`, 6 correctifs :
  les 3 ci-dessus + branche `role is None` de `has_privilege` non testée,
  extraction d'un helper `privilege_required_error` pour ne plus dupliquer
  le format d'erreur en dur, test négatif manquant pour un rôle sur mesure
  sans le privilège sur `admin_tools`). Suite complète 1896 passed/3
  skipped/0 failed.
  **Re-revue (opus) : 0 Critical, 1 nouvel Important** — corriger la liste
  DCAT/STAC (finding 1) sans leurs routes de détail a réintroduit *le même
  piège n°5* que Task 3 avait fermé sur `/collections/{id}` :
  `GET /dcat/datasets/{id}`/`GET /stac/collections/{id}` restaient 404
  alors que la collection apparaît désormais dans `GET /dcat/catalog`/
  `GET /stac/collections`. **Soumis à Tanguy à nouveau, accepté.** Second
  lot de correctifs (commit `30ba1ac2`, exécuté en deux passes — le
  sous-agent s'est arrêté une fois avant de committer en attendant un run
  de test resté silencieux, relancé par message direct sans perte de
  travail, commit et rapport confirmés identiques à la reprise) :
  contournement étendu aux deux routes de détail + test négatif
  schema/sharing pour utilisateur non privilégié. Suite complète 1899
  passed/3 skipped/0 failed.
  **Deuxième re-revue (opus) : 0 Critical, 0 Important, 4 Minor** (tests
  négatifs authentifié-mais-non-privilégié manquants sur les 2 routes de
  détail dcat/stac — même asymétrie mineure que celle fermée sur
  schema/sharing, non bloquante ; ~25 lignes de boilerplate
  `create_role`/`set_user_role` dupliquées sur 4 tests, à factoriser à la
  prochaine occurrence ; observation confirmée hors-scope — les hrefs
  `items`/`features` des documents STAC/DCAT restent 404 pour ce rôle,
  frontière data-vs-métadonnées déjà ratifiée par Tanguy, pré-existante à
  ce round ; une imprécision triviale de numéros de ligne dans un rapport
  d'implémenteur). Suite cœur finale **1899 passed** / 3 skipped / 0
  failed. **10 commits au total.** **Ready to merge.**

### Conventions tranchées (2026-09-01)

Trois dettes Minor répétées famille après famille (SP-30c→SP-30j) sans jamais
être décidées, tranchées ici pour de bon — s'appliquent à tout nouveau code et
à l'occasion du prochain contact avec un fichier existant, pas de correctif
rétroactif en masse :

- **Hauteur des contrôles de formulaire** : `h-9`, alignée sur `Button`
  (`size="default"`) et sur `ui/kit/Input`/`ui/kit/Select`. `h-8` réservé aux
  contextes explicitement denses (`Button size="sm"`, ligne de tableau
  serrée) — jamais un choix par défaut. Les contrôles natifs encore en `h-8`
  ad hoc (`LayerPicker.tsx`, `CrossFilterLinkEditor.tsx`,
  `QueryFilterBuilder.tsx`, `PercentileInput.tsx`, `ReportScheduleEditor.tsx`,
  `PipelineScheduleEditor.tsx`, …) ne sont pas corrigés par cette décision
  seule — à migrer vers les contrôles du kit à l'occasion, pas en urgence.
- **`<button>` natif vs `Button` du kit** : `Button` pour toute action
  **autonome** (pas noyée dans une phrase, pas répétée par ligne dense) —
  `variant="default"` pour l'action principale d'un panneau, `outline` pour
  une action secondaire/alternative, `danger` pour une action destructive
  autonome, `ghost` pour un bouton d'icône/chrome. `<button>` natif réservé à
  deux cas : (a) une action stylée en lien inline dans une phrase
  (`underline`, ex. « Réessayer » de `LayerPicker.tsx`) ; (b) une action
  répétée par ligne dans une liste/tableau dense où la hauteur du kit
  casserait l'alignement (ex. « Supprimer » par ligne de filtre dans
  `QueryFilterBuilder.tsx`/`CrossFilterLinkEditor.tsx`). Conséquence concrète
  actée comme dette : les boutons d'export de `DatasetEditPage.tsx` (rangée
  fixe de 3-4 actions, pas une liste dense) auraient dû passer sur `Button` —
  à corriger à l'occasion, pas par cette décision seule.
- **`aria-expanded`/`aria-controls` sur un déclencheur de panneau en ligne** :
  obligatoire sur tout bouton qui bascule un panneau en ligne (`ExportPanel`,
  `Terrain3DUploadButton`, panneaux d'édition/partage SP-30j, etc.) —
  `aria-expanded={open}` + `aria-controls={panelId}` sur le bouton, `id`
  correspondant (+ `role="region"` si le panneau est substantiel) sur la
  cible. Aucune primitive du kit ne le fournit aujourd'hui hors `Combobox`
  (géré par Radix) — c'est au consommateur de le poser. Non appliqué
  rétroactivement par cette décision.
- **Dette de tokens `LayersPanel`/`MapSymbologyEditor.tsx` et voisins**
  (`PopupEditor.tsx`, `FieldClassificationPicker.tsx`,
  `MapMeasureSketchToolbar.tsx`, `MapPopup.tsx`, `MapLegend.tsx`,
  `formFieldStyles.ts`) : confirmée hors périmètre de tout plan SP-30 (aucun
  `Dialog` à convertir, ne bloque aucune tâche nommée). Volume potentiellement
  comparable à SP-29a+SP-29b réunis. Décision : son propre chantier
  (brainstorm si nécessaire → spec → plan dédiés), à ouvrir après la clôture
  complète de SP-30 (revue transverse §7 incluse) — pas fusionné dans une
  tâche SP-30 existante, pas improvisé en aparté. **Chantier exécuté et clos
  par SP-34 (2026-09-03), cf. `### Livré`/SP-34** : les 8 fichiers sont
  tokenisés, plus de suivi ouvert sur ce point.

### À venir

- **Suivis non bloquants pour SP-30 (désormais clos)** (SP-30a→l ; clôture
  confirmée par SP-33, cf. `### Livré`/SP-33 ci-dessous, qui corrige le seul
  blocage nommé par le round 2 de correction du 2026-09-02 — l'affamement de
  la colonne centrale de `TriptychLayout.tsx` sur 6 des 8 écrans de
  référence). Les huit critères de sortie du §7 sont désormais tous acquis
  (le 8e, « aucun écran ne clippe au-dessus du seuil relevé », vérifié par
  `shell/e2e/triptych-narrow.spec.ts` à 900px sur les 5 écrans qui rendent
  réellement la grille et la font passer — Cartes reste en `test.skip()`
  pour deux défauts pré-existants et sans rapport avec ce défaut de layout,
  Tâches/Paramètres ne rendent aucune grille à vérifier (`<EmptyState>`
  seul), cf. `### Livré`/SP-33 et le lot **Carte** ci-dessous). Reste, par
  ailleurs, hors traitement par aucun plan
  SP-30 à ce jour : les
  permissions de collection et le profil « Lecteur » qui restent à
  trancher (cf. entrée SP-29a) ; la raison de verrouillage triplée
  d'`ItemActions` (cf. entrée SP-29a) qui peut être regroupée si voulu ;
  le retrait des anciens fichiers `ui/*` — encore consommés par
  `AppRuntimePage.tsx`/`builder/widgets/modal.tsx`, hors périmètre par
  doctrine (cf. entrée SP-30k) ; et la longue liste de suivis non
  bloquants Minor accumulés SP-29b→SP-30k ci-dessous. Trois répétitions
  jamais tranchées pour toute la famille (hauteur des contrôles de
  formulaire, `<button>` natif vs `Button` du kit, `aria-expanded`/
  `aria-controls` sur un déclencheur de panneau en ligne — 5 familles
  consécutives sans décision) sont désormais **tranchées, cf.
  ### Conventions tranchées (2026-09-01)** ci-dessus — reste seulement à
  les appliquer au prochain contact avec chaque fichier concerné, pas de
  correctif rétroactif en masse. La dette de tokens `LayersPanel`/
  `MapSymbologyEditor.tsx` et voisins, elle, a été **exécutée et close par
  SP-34 (2026-09-03)** — plus un suivi ouvert, cf. `### Livré`/SP-34.
  Reste ouvert, non tranché par cette note : commentaires
  attribuant une garde de sécurité au mauvais composant après son
  déplacement, trouvé Important à deux reprises distinctes — SP-30g, SP-30i.
  6 suivis non bloquants
  hérités de SP-29b à traiter en chemin (détail dans son entrée `### Livré`
  et l'historique d'exécution) : `DataTable.sortDirection` mort, deux `id`
  DOM dupliqués dans la galerie, ambiance de la galerie non nettoyée au
  démontage, branche de fermeture de `ConfirmDialog` non couverte,
  asymétrie contrôlé/non-contrôlé entre surfaces, Providers Tooltip/Toast
  non exportés par le barrel. 6 suivis non bloquants hérités de SP-30c
  (revue finale de branche, tous cosmétiques, aucun ne bloquait le merge) :
  styles divergents entre les deux panneaux convertis en ligne
  (`ExportPanel` titre en `<p>`/`gap-2`, `Terrain3DUploadButton` en
  `<h4>`/`gap-3` — choisir un seul patron avant que SP-30d en copie un des
  deux) ; hiérarchie de boutons ambiguë sur `ExportPanel` (Annuler et PNG
  tous deux `variant="outline"`, aucun disqualifié visuellement de PDF) ;
  `border-t` non tokenisé (peint en `currentColor` sous Tailwind v4, sans
  impact visible aujourd'hui mais incohérent) dans `LayerPicker.tsx`
  (lignes ~143/173) et `LayersPanel.tsx` (~220) — fichiers que SP-30c
  vient de balayer par ailleurs ; ni `ExportPanel` ni `Terrain3DUploadButton`
  (ni `ItemActions`, préexistant) ne posent `aria-expanded`/`aria-controls`
  sur leur déclencheur de panneau en ligne — à trancher une fois pour toute
  la famille SP-30, pas au cas par cas ; stub `matchMedia` de
  `MapEditorPage.test.tsx` jamais désinstallé explicitement (`vi.stubGlobal`
  sans `vi.unstubAllGlobals`), sûr aujourd'hui car re-stubé à chaque
  `beforeEach`, dépendance d'ordre latente à surveiller. 5 suivis non
  bloquants hérités de SP-30d (revue finale de branche, tous cosmétiques,
  aucun ne bloquait le merge) : divergence de hiérarchie de boutons sur
  `DatasetEditPage.tsx` (les boutons d'export sont restés en `<button>`
  natif alors que « Créer la règle »/« Ajouter un lien » sont passés sur
  `Button` du kit dans cette même branche — même classe que la
  divergence `ExportPanel`/`Terrain3DUploadButton` de SP-30c) ; rangée
  des boutons d'export sans `flex-wrap`, dépassement possible dans la
  colonne étroite (260px min) du volet Réglages ; volet Catalogue code
  en dur `<dd>Dataset</dd>` au lieu de
  `RESOURCE_TYPE_LABELS[item.resourceType]` (idiome `ItemDetailPage`
  copié partiellement) ; `vi.stubGlobal` de `DatasetEditPage.test.tsx`
  sans `vi.unstubAllGlobals` — 3e occurrence de la même dette (même
  disposition que `MapEditorPage.test.tsx` ci-dessus) ; densité du volet
  Réglages (`AlertRuleEditor`+`ConfigHistoryPanel` resserrés dans une
  colonne étroite), à surveiller si le patron se répète en SP-30e+.
  6 suivis non bloquants hérités de SP-30e (revue finale de branche, tous
  cosmétiques, aucun ne bloquait le merge) : le volet Propriétés
  restauré en `<aside>` englobe désormais tout l'empilement (pas
  seulement `PropsPanel` comme avant), portée des locators E2E
  `propsPanel` élargie — risque de collision strict-mode Playwright si
  un futur composant réutilise un libellé déjà présent ; pas de
  `vi.unstubAllGlobals()` dans `AppBuilderPage.test.tsx` — 4e occurrence
  de la même dette, toujours sans traitement cohérent pour la famille ;
  décision « Aperçu garde les volets visibles » non vérifiée par un
  test (ni unitaire ni E2E ne clique jamais sur Aperçu puis n'interroge
  la présence des volets) ; commentaire perdu sur l'invariant
  `onRestored` (pas de `query.refetch()`, `ConfigHistoryPanel` invalide
  déjà la clé) ; capture de miniature scopée à la seule colonne Canevas
  au lieu de la pleine largeur (ancien comportement Aperçu, aujourd'hui
  impossible) — conséquence produit à confirmer avec Tanguy, pas un
  défaut de code ; `AppExportPanel` réimplémente à la main la recette de
  couleurs de `Banner variant="warn"` au lieu de l'importer.
  Question `<main>`/`<aside>` au niveau de `TriptychLayout` **tranchée par
  SP-30f** : aucun landmark imposé par défaut, chaque page choisit `<div>`
  sauf besoin fonctionnel documenté — `AppBuilderPage` reste la seule
  exception (`<main ref={mainRef}>` pour la capture de miniature,
  `<aside>` sur Propriétés) ; `PipelineBuilderPage`, qui avait introduit un
  `<main>` orphelin, a rejoint la majorité `div`/`div`/`div`.
  7 suivis non bloquants hérités de SP-30f (revue finale de branche, tous
  cosmétiques, aucun ne bloquait le merge) : `text-ink-2` (tokenisé,
  Task 2) posé sur les fonds catégoriels exemptés `bg-emerald/amber/
  sky-50` de `KIND_COLOR` (non tokenisés, décision explicite du plan) —
  contraste correct en ambiance claire aujourd'hui, incohérence latente
  si l'ambiance sombre devient un jour atteignable (rien ne fixe de
  `text-*` sur `body` actuellement) ; le motif de grep de vérification des
  couleurs en dur ne couvre pas `text-white`/`text-black` sans suffixe
  numérique (seul `bg-white/black` l'est) — angle mort à corriger avant
  qu'il masque un vrai hit non exempté sur une future famille ;
  `border-t` de `PipelineScheduleEditor.tsx` (composant partagé avec la
  future `VisualQueryWizardPage`) se retrouve collé sous le nouveau
  libellé « Planification » au lieu de servir de séparateur de section ;
  l'en-tête du volet Canevas affiche le placeholder « Pipeline » en
  permanence sur la route d'édition (`PipelineEditRoute` ne passe pas
  `initialTitle`, préexistant mais promu en chrome visible par cette
  bascule) ; en mode onglets étroit, changer d'onglet pendant qu'une
  exécution est en cours démonte `PipelineRunPanel` et gèle son polling
  (boucle sans `AbortController`, pattern préexistant SP-6a partagé avec
  `ImportFileButton`, chemin de démontage nouvellement atteignable) ;
  double padding dans le volet Propriétés (`p-2` de la page + `p-2` déjà
  interne à `PipelineNodeInspector`), même classe que la densité notée
  sur SP-30d ; `pk !== null` répété 4 fois dans le volet Propriétés au
  lieu d'un booléen `isPersisted` (hérité du code littéral du plan
  lui-même, cf. entrée SP-30f).
  6 suivis non bloquants hérités de SP-30g (revue finale de branche, tous
  cosmétiques, aucun ne bloquait le merge) : le test qui devait prouver
  l'usage de `RESOURCE_TYPE_LABELS[item.resourceType]` (plutôt qu'un
  littéral `"Rapport"` en dur) ne peut pas échouer pour cette raison —
  `findByText("Rapport")` matche indifféremment l'idiome correct et le
  défaut qu'il visait à exclure, la valeur coïncidant avec le libellé
  chrome de l'onglet « Rapport » (ambigu aussi en mode étroit, collision
  potentielle) — à corriger via le couple `<dt>`/`<dd>` ou un fixture dont
  le libellé diffère de toute chaîne de chrome ; séparateur `border-t`
  du volet Réglages rendu même quand les deux panneaux gated `pk !== null`
  au-dessus sont absents (mode brouillon), première ligne visible sans
  rien à séparer — `PipelineBuilderPage.tsx` gate la même règle sur
  `mt-3` en plus, cette page est désormais l'exception de la famille sur
  ce point précis ; `itemQuery.isError` non géré, une erreur 403/404 sur
  `getItem` en mode persisté rend le volet Catalogue visuellement
  identique à l'état brouillon (silencieux, 2e page à faire ce choix non
  documenté après `DatasetEditPage`, qui elle échoue franchement) ; les
  contrôles tokenisés de `ReportScheduleEditor.tsx` (`rounded border
  border-rule bg-surface px-2 py-1 text-ink`, sans hauteur fixe) divergent
  de `PipelineScheduleEditor.tsx` rendu juste en dessous dans le même
  composant (`h-8 …`) et de `DatasetEditPage` (`h-8 … text-xs`) — la
  famille n'a toujours pas une seule recette de contrôle de formulaire
  (texte littéral du plan lui-même, pas un écart d'implémentation) ;
  deux titres de test restent en anglais/mixte (« unsaved mode: no
  history panel before the first save (no report id yet) », « persisted
  mode: … ») malgré la règle « identifiants de test en français » —
  hérité du fichier avant ce plan, non corrigé au passage ; la question
  `aria-expanded`/`aria-controls` sur un déclencheur de panneau en ligne,
  déjà notée par SP-30c comme à trancher une fois pour toute la famille,
  reste ouverte.
  7 suivis non bloquants hérités de SP-30h (revue finale de branche, tous
  cosmétiques, aucun ne bloquait le merge — **famille 6 close, dernière
  occasion de trancher ces répétitions avant qu'elles migrent vers les
  familles 7/8**) : commentaire `VisualQueryWizardPage.tsx:82-83` devenu
  partiellement faux (la requête `existingDatasetItemQuery`, à l'origine
  documentée pour préremplir le Titre seul, sert désormais aussi la fiche
  Catalogue — même classe que le commentaire faux trouvé Important sur
  SP-30g, ici Minor car sans conséquence fonctionnelle) ; une erreur
  d'exécution peut devenir invisible sous 390px (le remontage de
  `TriptychLayout` après l'écran de sondage post-création réinitialise
  l'onglet actif sur « Requête », l'erreur restant dans « Réglages » —
  seule page de la famille dont les retours anticipés démontent le
  layout) ; le nouveau test de la fiche Type/Modifié n'est pas
  falsifiable pour la propriété qu'il nomme (`findByText("Dataset")`
  passerait aussi avec un littéral en dur) — plan-mandated, même classe
  que le défaut déjà logué sur SP-30g (`findByText("Rapport")`) ;
  `existingDatasetItemQuery.isError` non géré — **3e page** de la famille
  à faire ce choix silencieusement après `ReportEditPage` ; `border-t`
  inconditionnel en mode création avant sélection de collection — **3e
  occurrence** dans la famille (après `PipelineBuilderPage`/
  `ReportEditPage`), toujours jamais tranchée ; ordre alertes/bouton
  divergent de `ReportEditPage` (alertes avant le bouton ici, l'inverse
  là-bas — deux ordres coexistent dans la famille sans règle commune) ;
  bouton natif `Supprimer` à côté d'un `Button` du kit dans
  `QueryFilterBuilder.tsx` (même dette de hiérarchie de boutons que
  SP-30c/d, pré-existante). **Aucune de ces répétitions n'a été tranchée
  pour toute la famille avant sa clôture** — à faire explicitement au
  démarrage de SP-30i si elles doivent être réglées plutôt que
  perpétuées dans les familles 7/8.
  10 Minor reportés en suivi non bloquant hérités de SP-30i (revue finale
  de branche, tous cosmétiques, aucun ne bloquait le merge) : décompte de
  référence de la spec §6.5 sous-comptait `RequireRole`
  (`KitGalleryPage.tsx` en 4e consommateur, absent de l'inventaire —
  consommé par SP-30j) ; les pages admin utilisent `useMe()` pour deux
  usages distincts, le garde ET `enabled` de requête (consommé par
  SP-30j) ; étape « couverture » du gabarit de Task de vérification finale
  lance `npm run build` puis lit `coverage-summary.json`, que seul
  `vitest run --coverage` écrit — défaut de texte copié plan après plan
  depuis au moins SP-30d, sans conséquence à ce jour (toujours détecté et
  contourné en session) ; `RequireRole.tsx` sans gestion de
  `meQuery.isError` (fail-closed silencieux, 4e page de la série à faire
  ce choix sans jamais le trancher) ; retourne `children` nu au lieu de
  `<>{children}</>` comme son jumeau `RequireAuth.tsx` ; rechargement
  d'historique invisible sous viewport étroit (bouton et cible dans deux
  onglets différents, nécessiterait un changement d'API `TriptychLayout`) ;
  SQL long en colonne étroite : débordement horizontal scrollable plutôt
  qu'un layout cassé, jamais tranché pour la famille ; seul `<h1>` du
  shell (`text-lg font-bold`) contre `<h2 font-semibold>` des pages
  sœurs ; fixture `RequireRole.test.tsx` divergente du type `Me` réel,
  héritée verbatim de l'ancienne fixture `SqlLabPage`.
  9 Minor reportés en suivi non bloquant hérités de SP-30j (revue finale
  de branche, tous cosmétiques, aucun ne bloquait le merge) : commentaire
  « décision 5 » au lieu de « décision 6 », commité deux fois (Collections
  et Harvest) ; `ui/ConfirmDialog.tsx` (l'ancien, pas `ui/kit/ConfirmDialog`)
  devenu orphelin, supprimable ; paramètres `options?: { enabled? }` morts
  sur 5 hooks (plus aucun appelant réel après cette branche, sauf
  `useCollectionsAdmin`) ; les deux tests d'exclusivité mutuelle
  (Harvest/Collections) utilisent des idiomes de locator différents,
  celui de Collections dépendant silencieusement d'une fixture vide ;
  `CollectionSharePanel` seul panneau à ne pas nommer son sujet dans son
  titre (contrairement à ses jumeaux « Éditer {title} ») ; erreur de
  mutation figée non effaçable au re-clic sur la même ligne, sur les deux
  pages à panneaux ; perte nette d'assertions unitaires vs les 4 anciens
  fichiers de test de dialogue supprimés, compensée par l'E2E ;
  `aria-expanded`/`aria-controls` toujours absents — **5e famille
  consécutive** (SP-30c→SP-30j), plus de famille suivante dans SP-30 pour
  trancher, reporté à SP-31 ; sous viewport étroit, cliquer Éditer/
  Partager/Ajouter ne produit aucun retour visuel tant que l'onglet n'est
  pas changé manuellement — plus grave ici que sur les familles
  précédentes car ce sont les déclencheurs CRUD primaires de la page.
  Deux défauts de texte de plan notés pour référence (pas des défauts
  d'implémentation) : la décision 3 du plan SP-30j promettait « même
  test-par-composant sauf EditHarvestSourceDialog » mais son texte
  exécutable mandatait la suppression des 4 fichiers de test de dialogue
  — même classe que le défaut de plan trouvé par SP-30c Task 5 (prose et
  bloc de code en désaccord, seul l'exécutable suivi) ; la justification
  de la décision 6 (exempter `deleting`) n'était correcte que dans un
  sens — à reformuler si le patron est réutilisé (« tout état qui monte
  quelque chose dans l'onglet Détail doit être remis à zéro par tout
  autre déclencheur, y compris les déclencheurs destructifs au succès »).
  Divergence pré-existante notée en passant, pas introduite par SP-30j :
  deux doctrines de mode démo différentes coexistent désormais sous le
  même layout (`HarvestSourcesAdminPage` masque sous `!readOnly`,
  `CollectionsAdminPage` ne le fait pas) — à trancher en SP-31 plutôt que
  laisser une 3e variante apparaître.
  7 Minor reportés en suivi non bloquant hérités de SP-30k (revue finale
  de branche, tous cosmétiques, aucun ne bloquait le merge — **dernière
  brique nommée de la spec §2.1, aucun SP-30l ne les héritera** : à
  trancher à la revue transverse de sortie SP-30 §7 ou à défaut en
  suivi séparé) : `ui/kit/Drawer.tsx` sans `overflow-y-auto` sur son
  contenu — dette du **kit** lui-même (pas de ces trois fichiers),
  invisible aux deux filets de test par construction (jsdom ne fait pas
  de layout, Playwright fait défiler les conteneurs `overflow-hidden`
  programmatiquement), même classe que le Critical trouvé par SP-30d ;
  `Drawer.test.tsx` ne couvre que Échap, pas le clic hors zone, dont
  dépend désormais un vrai consommateur (`Tileset3DUploadButton`) ;
  Annuler de `Tileset3DUploadButton` reste `onClick={close}` +
  `disabled={busy}` plutôt que `onClick={requestClose}` (un seul
  invariant, deux mécanismes, d'où un commentaire nécessaire pour
  l'expliquer) ; vocabulaire "dialog"/"backdrop" de l'ère `ui/dialog.tsx`
  resté dans le test voisin non retouché de `Tileset3DUploadButton` ;
  titres de test en anglais (chaîne littérale imposée par le plan) ;
  recette `<select>` natif dupliquée huit fois entre les deux fichiers
  sans anneau de focus visible, contrairement à `Input` du kit juste à
  côté dans le même formulaire — dette à consommer par un futur plan qui
  adopterait un `Select` du kit ; modalité Radix (focus trap, scroll
  lock, `aria-hidden` sur le reste de la page) jamais mentionnée par le
  plan bien que ces trois composants soient montés sur toutes les routes
  protégées — vérifié qu'aucun portail Toast/Tooltip global n'en pâtit,
  mais à garder en tête si un futur portail global apparaît.
  **Important non bloquant hérité de SP-30k, à ne pas perdre faute de
  SP-30l pour l'hériter** : `ImportFileButton`/`NewItemButton` n'ont — et
  n'avaient déjà avant SP-30k — aucune garde `busy` sur leur fermeture
  (contrairement à `Tileset3DUploadButton`) ; fermer le tiroir pendant
  l'upload/le sondage/la mutation laisse la chaîne async tourner en
  arrière-plan, qui rappellera `close()`/`navigate()` sur un tiroir
  éventuellement rouvert entre-temps. Comportement strictement
  préexistant à SP-30k (le plan interdisait explicitement de le
  « corriger » dans son périmètre), donc aucune action de code prise ;
  à rattacher explicitement à la revue de sortie SP-30 §7 plutôt que le
  laisser disparaître silencieusement.
- Reste **SP-15** : événements/déclencheurs durables au-delà du cron (non
  planifié) ; exposition MCP des noms de secrets (non planifiée) ; **exécuter
  réellement les 5 tests `@pytest.mark.qgis` de SP-15d** avant d'activer
  `transform.qgis` en production — seul point bloquant M14.
- Reste **3D** : terrain servi par notre propre TiTiler depuis un DEM COG
  hébergé, encodage `mapbox` en plus de `terrarium`, conversion (py3dtiles,
  nuages de points). Non planifié.
- Reste **SP-20** : garde d'egress sur l'appel LLM sortant (vague 6.2) — 4e
  surface sortante, les trois autres en ont une.
- Reste lot **Carte** (bug UI, pas une fonctionnalité manquante) : dans
  `LayersPanel.tsx`, le `<span>` de titre d'une couche `vector`/`feature`
  peut avoir une largeur de layout nulle (interaction flex
  `flex-1 truncate` + sibling `basis-full` toujours déployé pour ces deux
  kinds) — trouvé par SP-28/Task 4, contourné dans son propre test E2E par
  un sélecteur différent (`getByRole("button", { name: "Retirer …" })`),
  jamais corrigé (hors périmètre fichiers de cette tâche). *Éditeur de
  symbologie pour les couches `kind: "feature"` résolu par SP-28. Jenks sur
  le widget carte des apps/dashboards résolu par SP-27/Task 19 : le widget
  délègue désormais toute la compilation de peinture à `MapView`, même
  pipeline que l'éditeur.* Un futur correctif doit tenir compte du fait
  que la colonne `browse` peut désormais rendre aussi étroite qu'~250px
  dans la bande 900-959px (juste au-dessus du seuil relevé par SP-33), pas
  seulement son ancien maximum fixe de 280px — cf. `### Livré`/SP-33.
- Questions produit ouvertes (comparatif §8) : **Q2** (premiers utilisateurs
  réels — la seule qui puisse réordonner le phasage), Q10 (temps réel), Q11
  (offline).

### Suivis non bloquants — ce qu'il faut savoir avant de toucher la stack

Liste complète (une centaine d'entrées, par SP) dans l'archive. Ce qui change
le comportement d'une session :

- **Stack par défaut vérifiée de bout en bout (2026-08-29)** : les 11 services
  démarrent tous `healthy` (`docker compose up -d`, image `core`/`worker`/
  `cdc-worker` reconstruite). Trois entrées ci-dessous, documentées comme
  bloquantes depuis SP-21, ne se sont **pas reproduites** à cette date et ont
  été corrigées ou requalifiées à la vérification réelle — piège n°3 :
  - `mcp==2.0.0` cassant `mcp.server.fastmcp` : ne se reproduit plus.
    `pyproject.toml` contraint déjà `mcp>=1.12,<2.0` ; le build installe
    `mcp==1.29.1` et l'import passe. Cause probable : la contrainte a été
    ajoutée depuis, sans mise à jour de cette note. Si ça revient, vérifier
    d'abord `pip show mcp` dans l'image avant de ré-imputer à `uv.lock`.
  - GUC `output_plugin_libraries` sur `postgis` : **valide**, pas une panne —
    `SHOW output_plugin_libraries;` le confirme dans le conteneur réel.
  - `libexpat.so.1` manquant pour `defusedxml` (`app/mapicons/svg.py`,
    `app/harvest/connectors/ows.py`) : **réel**, reproduit (`worker` et
    `cdc-worker` en crash-loop au premier import de `app.jobs`) —
    `python:3.12-slim` (Debian trixie) n'embarque plus `libexpat1` par
    défaut. Corrigé dans `core/Dockerfile` (`apt-get install libexpat1`) ;
    corrige les trois images qui partagent ce Dockerfile.
- **Volume `pg-data` du projet compose par défaut** : la commande de `core`
  applique déjà `alembic upgrade head` avant `uvicorn` (idempotent) — pas de
  correctif de plus à apporter là. Ce qui bloquait réellement un démarrage
  `docker compose up -d` à blanc, ce jour-là : `.env` local avec
  `CORE_SECRETS_MASTER_KEY` vide et `CORE_ENV` absent (les deux font
  crash-looper `core` — gardes SP-15e §4/§8 et SP-26/3.1 — *après* que les
  migrations se sont appliquées, donc sans lien avec `pg-data` lui-même mais
  avec le même symptôme observable : `shell` reste `Created`). `.env.example`
  a `CORE_ENV=development` ; un `.env` plus ancien copié avant son ajout ne
  l'a pas. Si `shell` reste `Created` : vérifier `docker logs core` avant de
  soupçonner `pg-data`.
- **Martin (:3000 hôte) en conflit de port** : pas une panne du dépôt — un
  process déjà présent sur la machine de l'opérateur (ex. un `node.exe`
  Windows côté hôte WSL2, invisible de `ss` côté Linux) fait échouer le
  port-forwarding de Docker Desktop (`/forwards/expose ... status: 500`).
  Corrigé de façon pérenne en déplaçant le mapping hôte vers `3010`
  (`docker-compose.yml`) — 3000 est un port trop commun côté dev JS pour
  rester un bon choix par défaut ; sans incidence, cf. le commentaire sur
  place (accès dev uniquement depuis SP-24, `docker-compose.prod.yml` désactive
  déjà ce port en prod).
- `deploy/postgis/Dockerfile` + `pg_hba.conf` (non commités) sont **inertes** —
  Postgres lit `$PGDATA/pg_hba.conf`. Ne pas les câbler : ils affaibliraient
  `scram-sha-256` en `md5`.
- **CSP en Report-Only**, jamais basculée en enforcing : 4 bloqueurs concrets
  documentés en commentaire dans `docker-compose.prod.yml`.
- **Restauration de sauvegarde jamais rejouée de bout en bout** (chantier 1.4) :
  le périmètre est vérifié mécaniquement, le succès d'une restauration ne l'est
  pas.
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
