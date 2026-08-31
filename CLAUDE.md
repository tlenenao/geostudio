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
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
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

Jalons atteints : **M1, M2, M4, M5, M11, M12, M13, M15, M16**. **M14** reste
bloqué par la seule vérification réelle des 5 tests `@pytest.mark.qgis`.

### À venir

- **SP-30** : réécriture des écrans qui
  consomment enfin `Gate`/`capabilities.ts`/`tokens.css` — c'est là que les 9
  occurrences restantes de comparaison de droits en dur (`SqlLabPage.tsx`,
  `AdminExtensionsPage.tsx`, `HarvestSourcesAdminPage.tsx`,
  `CollectionsAdminPage.tsx`, `AppLayout.tsx`) doivent disparaître, que les
  permissions de collection et le profil « Lecteur » se tranchent, et que la
  raison de verrouillage triplée d'`ItemActions` (cf. entrée SP-29a) peut être
  regroupée si voulu. Basculera les écrans réels sur le kit `ui/kit/`
  (SP-29b) et retirera les anciens fichiers `ui/*`. SP-30c a traité la
  famille 3 (Cartes, `MapEditorPage`), SP-30d la famille 4 (Données,
  `DatasetEditPage`), SP-30e la famille 5 (Apps & sites, `AppBuilderPage`),
  SP-30f la famille 6 volet 1 (Automatisation, `PipelineBuilderPage`)
  du §6.1 de la spec SP-30 ; **restent le volet 2/3 de la famille 6 et les
  familles 7/8** (SP-30g+, à découper en plans séparés — la spec proscrit
  un seul plan pour tout le reste) : `ReportEditPage`/`VisualQueryWizardPage`
  (Automatisation, famille 6 — prochaines dans l'ordre du §6.1 ;
  `PipelineRunPanel.tsx`/`PipelineScheduleEditor.tsx` déjà kit-ifiés par
  SP-30f, consommables sans retouche par `VisualQueryWizardPage`),
  `SqlLabPage`
  (Analytique, famille 7), `AdminExtensionsPage`/`CollectionsAdminPage`/
  `HarvestSourcesAdminPage` (Administration, famille 8),
  `Tileset3DUploadButton`/`NewItemButton`/`ImportFileButton` (chrome,
  dette de `Dialog` documentée par SP-30a, non bloquante pour aucune
  famille). Éditeurs de symbologie/popup imbriqués dans `LayersPanel`
  (`MapSymbologyEditor.tsx` 797 lignes/27 couleurs, `PopupEditor.tsx`,
  `FieldClassificationPicker.tsx`, `MapMeasureSketchToolbar.tsx`,
  `MapPopup.tsx`, `MapLegend.tsx`, `formFieldStyles.ts`) : dette de tokens
  cosmétique laissée par SP-30c (aucun `Dialog`, ne bloquait pas la
  bascule de `MapEditorPage`), volume potentiellement aussi gros que
  SP-30a+SP-30b réunis — à traiter dans un plan dédié, possiblement hors
  SP-30 lui-même.
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
  pipeline que l'éditeur.*
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
