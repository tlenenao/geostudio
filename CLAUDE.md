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
7. `docs/superpowers/2026-08-27-historique-execution-continu.md` — **historique
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
  suite E2E complète est le filet de la migration : elle est **entièrement
  verte** depuis le 2026-09-06 (166 passed / 4 skipped / **0 failed**,
  commit `a320c317`). L'échec longtemps réputé « préexistant, cause non
  investiguée » (`e2e/pipeline-builder.spec.ts`, timeout sur le bouton
  « Exécuter ») est diagnostiqué et corrigé : le test ne mockait jamais
  `GET /configs/by-item/pipe-1`, le handler générique de `mocks.ts`
  répondait une config `kind: "app"`, `getPipelineConfig` levait, React
  Query réessayait, la page restait sur « Chargement… ». **Il n'y a donc
  plus d'échec E2E « connu » à qui imputer une régression : tout rouge est
  désormais réel.**
- Exécution en **subagent-driven-development** : une revue par tâche **et** une
  revue finale de branche, systématiquement — ce ne sont pas les mêmes défauts
  (cf. `## Pièges récurrents`).
- Commits **conventional** (`feat(shell): …`, `fix(core): …`), petits, un sujet.
- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Branche de travail : **`dev` uniquement, en local** (décision 2026-09-06,
  après la découverte qu'un `main` local resté figé depuis avant la
  réécriture d'historique de SP-45 divergeait de `origin/main` sur ~2000
  commits — un artefact sans valeur, jamais un état à préserver). Ne pas
  créer ni conserver de branche `main` locale. Promotion vers `main` = **PR
  GitHub `origin/dev` → `origin/main`** (`git push origin dev` puis
  `gh pr create --base main --head dev`), jamais un merge local suivi d'un
  push direct sur `main`. Les worktrees/branches de travail éphémères
  (`.claude/worktrees/agent-*`, branches de reprise) sont supprimés dès leur
  fusion dans `dev` — ne pas laisser le dépôt accumuler des dizaines de
  worktrees/branches orphelins (piège vécu le 2026-09-06 : 29 worktrees et
  autant de branches locales périmées retrouvés en une seule session,
  certains avec des fichiers root-owned laissés par des conteneurs Docker,
  supprimables seulement avec confirmation explicite).
- **À la clôture d'un SP** : une ligne dans `### Livré` ci-dessous, et l'entrée
  détaillée dans `docs/superpowers/2026-08-27-historique-execution-continu.md`
  (pas de récit long dans ce fichier — il est chargé à chaque session).
  **Obligatoire dans le même geste, jamais différé** : mettre à jour l'état
  des `GAP-nn` concernés dans `docs/revue/2026-09-04-analyse-gaps.md` (ouvert
  → fermé, référence à la SP), et **régénérer le bilan de fonctionnalités** —
  `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write` —
  après avoir ajouté à `docs/revue/inventaire-fonctionnalites.jsonl` toute
  surface nouvellement livrée (route REST, outil MCP, route shell). La CI
  refuse une surface non inventoriée (`core/tests/test_feature_inventory.py`) :
  ce n'est plus une discipline, c'est une porte. La matrice datée
  `2026-09-04-matrice-fonctionnalites.md` est **gelée** et ne se met plus à jour.
  Raison (piège n°12, vécu le 2026-09-06) : ces deux documents sont restés des
  mois sans être retouchés pendant que 17 SP fermaient des dizaines de gaps
  qu'ils décrivent — le récit de `### Livré` était correct, mais ces deux
  documents-là, non consultés, avaient dérivé au point de contredire le code
  réel (`backlog.md` gardait 8 entrées `ouvert` déjà fermées). Ne pas laisser
  ces documents rejouer ce piège.

## Commandes

```bash
# shell (d'abord, car commitlint en dépend)
cd shell && npm ci
npm run test         # Vitest ; doit être entièrement vert, couverture ≥ seuil
                     # (shell/.coverage-threshold)
npm run e2e          # Playwright (VITE_AUTH_MODE=mock) ; doit être
                     # entièrement vert (voir CI sinon)
                     # e2e-oidc/ : suite séparée contre un vrai Keycloak (SP-26)
npm run build        # tsc --noEmit + vite build ; filet de taille de bundle :
                     # node scripts/check-bundle-size.mjs
                     # dist/.vite/manifest.json .bundle-size-threshold

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
uv run pytest        # doit être entièrement vert, couverture ≥ seuil
                     # (.coverage-threshold). CORE_TEST_DATABASE_URL doit
                     # pointer un postgis-test réel, sinon ~185 tests marqués
                     # postgis skippent SILENCIEUSEMENT (piège SP-43). Ce
                     # conteneur n'est PAS tracké par Alembic — après une
                     # migration qui ajoute des colonnes, ALTER TABLE manuel
                     # nécessaire, sinon échecs UndefinedColumn en cascade
                     # sans rapport avec le code sous revue (piège SP-42).
                     # Skips qgis (conftest.py skip si CORE_TEST_QGIS_WORKER_URL
                     # manque, un skip ne rougit rien) : `./scripts/run-qgis-tests.sh`
                     # pour les exécuter vraiment (aussi en CI, job `core-qgis`).
                     # 2-3 sessions concurrentes sur le même postgis-test partagé
                     # produisent des collisions (UniqueViolation, DuplicateTable)
                     # sans rapport avec le code sous revue — rejouer en isolation
                     # avant de s'imputer une régression (piège SP-49). 2 échecs
                     # INTERMITTENTS déjà documentés, à vérifier avant de
                     # s'imputer une régression : test_features_rls.py::
                     # test_scope_preserves_original_sql_error ;
                     # test_deployability.py::test_every_compose_substitution_is_documented.

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

# régénérer le bilan de fonctionnalités (SP-61) — À FAIRE à la clôture de
# tout SP qui livre une surface nouvelle (route REST, outil MCP, route
# shell), après l'avoir ajoutée à docs/revue/inventaire-fonctionnalites.jsonl.
# La commande nue échoue en ModuleNotFoundError: scripts — il faut PYTHONPATH=. :
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
# --check (sans --write) est la porte CI : sort en erreur si une surface
# n'est pas inventoriée ou si la santé médiane passe sous le plancher mesuré
# (core/scripts/feature_health_thresholds.json).

# garde-fou de taille CLAUDE.md (§ Livré) — câblé en pre-commit et en CI
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 11 services par
                     # défaut (postgis, pgbouncer, minio, martin, titiler,
                     # core, worker, cdc-worker, keycloak, shell, traefik)
                     # + 5 derrière un profil : etl (qgis-worker), export
                     # (export-worker), appexport, observability (otel-lgtm,
                     # postgres-exporter)
```

## Feuille de route (état d'avancement)

Chaque SP a sa spec dans `docs/superpowers/specs/` et son plan dans
`docs/superpowers/plans/`.

### Livré

**Règle non négociable, sans exception : une ligne par chantier ci-dessous,
jamais plus.** Tout récit d'exécution — revue finale, défauts trouvés,
déviations de plan, décisions de scope, chiffres de suite de tests — va
exclusivement dans `docs/superpowers/2026-08-27-historique-execution-continu.md`
(archive continue, croît à chaque SP) : à lire avant de reprendre un chantier
ouvert ou de rouvrir une surface déjà livrée. Ne jamais coller un paragraphe
long ici — ce fichier est chargé à chaque session ; cette règle existait déjà
en prose avant le nettoyage du 2026-09-17 et a été ignorée pendant ~35 SP
d'affilée — voir `scripts/check_claude_md_size.py` (§ Commandes) pour le
garde-fou posé depuis.

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
- **SP-42** — revue globale du dépôt : matrice de fonctionnalités, analyse de
  79 gaps (`GAP-nn`), backlog unique (173 `REV-nnn`), rapport de revue,
  feuille de route révisée, spec SP-43.
- **SP-44** — débloque le jalon **M14** (GAP-01) : les 5 tests
  `@pytest.mark.qgis` exécutés pour la première fois contre un sidecar réel
  trouvent et corrigent 2 défauts de production jamais vus (`_lock_down()`
  bloquait `transform.qgis`, `fid` GeoPackage non filtré). Câblage CI
  (`core-qgis`) ajouté ensuite.
- **SP-43** — ferme 6 classes de duplication mécanique (registre de
  privilège, comparateur modèle↔Alembic, fixtures E2E, module de job
  partagé, ARIA) puis découpe les 3 fichiers les plus mélangés du dépôt
  (`itemClient.ts`, `mcp/tools.py`, `pipelines/runtime.py`) en domaines,
  avec 3 couches de service REST↔MCP partagées pour la première fois.
- **SP-47** — ferme `REV-097` (2 privilèges sans route) et `GAP-71`/`GAP-28` :
  `require_any_privilege`, garde OR sur `/secrets`, nouveau domaine
  `app/usage/` en lecture seule sur `audit_log`, `UsagePage` sur `/tasks`.
- **SP-49** — ferme GAP-56/63/64/76 : index manquants, batching des
  balayages cron, N+1 fermés sur `GET /harvest/*`, reprise périodique des
  jobs appexport/ingestion, sondes de healthcheck worker/export-worker/
  qgis-worker.
- **SP-46** — découvrabilité : ferme GAP-30/32/39/67, quatre écrans gardés
  côté serveur mais invisibles côté UI deviennent atteignables par un lien
  réel.
- **SP-45** — durcissement sécurité immédiat : garde d'egress SSRF sur
  l'appel LLM du copilote (GAP-02), retrait de `MARTIN_SECRET` inutilisé,
  rate-limit sur `POST /collections/empty`, purge d'historique git d'une
  clé `age` de test, réglages de sécurité GitHub activés.
- **SP-52** — 5 manques d'UX du builder d'App : suppression de
  widget/variable avec purge de câblage `ActionsPanel`, `setFilter` du
  copilote fusionne au lieu de remplacer, contenu réel de l'onglet actif
  sur le canevas, éditeur d'enregistrements JSON pour sources Statique,
  widget `variableInput`.
- **SP-56** — formats d'import manquants (GAP-09, GAP-29 partiel) : XLSX,
  KML/KMZ, GeoParquet.
- **SP-55** — catalogue : tri/facettes/recherche spatiale/SEO
  (GAP-05/06/07) : `sort`/`owner`/`keyword`/`GET /items/facets`, emprise
  spatiale persistée + filtre `bbox`, `sitemap.xml`/`robots.txt`/aperçu
  social côté serveur.
- **SP-58** — conformité RGPD : quotas de stockage par tenant,
  anonymisation d'utilisateur (RGPD Art. 17), `purge_tenant` (suppression
  irréversible complète, 27 tables), privilège `compliance.manage` exclu
  même de l'Administrateur.
- **SP-51** — parité carte App Builder / éditeur autonome : outils de
  mesure/croquis, opacité raster, basemap/terrain/caméra sur le widget
  carte, éditeur JSON avancé pour `layer.paint`, UI d'auteur pour une
  couche `deck`.
- **SP-54** — surfaces API shell (`ItemClient`) + partage avancé : schéma
  `AppConfig` factorisé, cache dataset TTL, recherche de
  collections/groupes côté MCP, `geomIntersects` sur `query_features`,
  liens de partage à échéance (`share_link`).
- **SP-59** — exploitation : rotation des secrets (atomique en 2 passes) +
  restauration scriptée (`deploy/backup/restore.sh`) ; trouvaille : 2 des 7
  buckets MinIO jamais reportés côté restauration, corrigé.
- **SP-48** — bascule de la CSP en enforcing sur img-src/connect-src
  (allowlist calculée dynamiquement, poussée à Traefik) ; `script-src` pour
  les widgets d'extension tiers reste une question produit ouverte.
- **SP-50** — robustesse des surfaces publiques de fédération
  (GAP-57/59/60/62) : pagination `/collections`/STAC/DCAT/historiques,
  plafond de taille sur l'egress de moissonnage, collection cassée ne fait
  plus échouer tout `/stac/collections`.
- **SP-60** — performance frontend & filets de test (GAP-68/69) : boucles
  de sondage annulées au démontage, découpage du bundle par route
  (`lazy()`), filet de non-régression sur la taille du bundle.
- **SP-57b** — ferme GAP-14 (contrat d'API `/v1/`, ADR rétroactifs,
  gabarits GitHub) : les 33 routeurs du cœur passent sous `/v1/` (health et
  `/mcp` exclus).
- **SP-57a** — i18n complète (1343 clés, détecteur de couverture câblé en
  CI) + audit d'accessibilité (axe-core sur 9 pages).
- **SP-53** — Automatisation : complète les éditeurs (secrets, moissonnage,
  alertes) + déclenchement de pipeline par webhook entrant
  (`PipelineWebhookToken`).
- **GAP-62 (reste) + GAP-15 (volet 1)** — `GET /dcat/datasets/{id}` dégrade
  sur collection cassée ; `core/app/sql_ident.py` factorise le quoting
  d'identifiant dupliqué sur 11 fichiers.
- **SP-61** — remplace la matrice de fonctionnalités écrite à la main par
  une commande rejouable (`feature_health_cli.py`) : santé 0-100 pondérée
  par fonctionnalité, CI refuse toute surface non inventoriée.
- **GAP-16** — connecteur entrepôt cloud analytique `reader.connector.snowflake`.
- **SP-62** — ferme GAP-17 (génération de requête en langage naturel avec
  revue humaine) : outils MCP `generate_sql_query`/`generate_visual_query`,
  copilote monté sur SQL Lab et la requête visuelle ; le brouillon généré
  n'est jamais exécuté ni écrit automatiquement.
- **GAP-29 (reste)** — 6 formats d'import supplémentaires (Excel
  multi-feuilles, Parquet non-géo, JSON Lines, CSV/WKT, GML/INSPIRE, XML
  générique) ; reste `Partiel` (positionnement produit face au marché non
  tranché).
- **GAP-19** — SDK d'embedding App/Dashboard : route publique
  `/embed/:token`, portée du lien de partage recoupée avec les droits
  réels de son créateur (contournement de `can()` trouvé et corrigé en
  revue finale), exemption `X-Frame-Options` dédiée.
- **GAP-22** — sécurité au niveau colonne : masquage de champ sensible par
  collection sur les 3 mécanismes de lecture (RLS Postgres par colonne,
  exclusion de la matérialisation DuckDB) ; revue finale a trouvé et
  corrigé 1 Critical (routes STAC non masquées).
- **`priorite-moyenne-sante-90`** — fait passer 32 des 33 fonctionnalités
  `priorite: "moyenne"` du bilan au-dessus de 90 de santé, plancher
  verrouillé en CI.
- **OperationContract** — remplace, pour les 19 op de pipeline déjà
  livrées, 5 structures parallèles par un registre unique `OPERATIONS`
  (schéma/moteur/licence/modèle d'exécution/compilateur/SRID).
- **IPC d'échange DuckDB↔Arrow** — pose le seam d'échange DuckDB↔futurs
  moteurs natifs (`app/pipelines/exchange.py`), non consommé par aucun
  moteur réel à ce stade.
- **Portage arm64 multi-arch** — `deploy/postgis` rebasé sur
  `postgres:16-bookworm` (multi-arch, + initdb restaurant `postgis`,
  perdu au rebasage puis corrigé en revue finale) ; `deploy/titiler`
  (nouveau) rapatrie la recette officielle 0.18.4 au lieu de l'image
  tierce mono-arch ; `deploy/backup` télécharge `mc` par arch cible
  depuis les GitHub Releases AGPL de `minio/mc` (`dl.min.io` mort,
  `curl -f` durci) ; `release.yml` publie 8/9 images en
  `linux/amd64,linux/arm64` (qgis-worker exclu, base mono-arch) derrière
  une nouvelle porte de tests native arm64 (`test-gate-arm64`, jamais
  sous QEMU). Détail complet (revue finale : 1 Critical + 1 Important
  trouvés et corrigés) dans l'archive.
- **Provisioning OCI** — module OpenTofu `deploy/oci/terraform/` (Ampere A1
  Flex arm64, tier gratuit), playbook Ansible extrait en commun
  (`deploy/ansible/`), `CORE_ETL_ENABLED` découplé du sidecar QGIS (jamais
  démarré sur cette cible arm64). Revue finale : 3 Critical (playbook cassé
  pour Proxmox et OCI par l'extraction, test de déployabilité et inventaire
  de fonctionnalités désynchronisés du chemin déplacé) + 4 Important trouvés
  et corrigés — détail dans l'archive.
- **Vague 1 transformers DuckDB** — 15 nouvelles op `transform.*` (permutation, translation,
  échelle, rotation, création/arrondi de géométrie, extraction/construction de coordonnées,
  SRID en lecture/écriture, formatage DMS), catalogue à 34 op ; 18 des 90 lignes `planned_duckdb`
  de la matrice FME passées à `implemented`.
- **Socle sidecar desktop-etl (seams SecretResolver + RunTracker)** —
  deux Protocol additifs dans `core/app/pipelines/` (`SecretResolver`/
  `PostgresSecretResolver` sur `connector_runtime.py`, `RunTracker`/
  `PostgresRunTracker` sur `jobs.py`) préparant la réutilisation de
  `run_pipeline()` par un futur sidecar desktop sans Postgres (design
  2026-09-17 §3/§4) ; comportement observable inchangé, pas encore
  consommé par une 2e implémentation.
- **`reader.file`/`writer.file` (desktop-etl)** — 2 op fichier-local via
  DuckDB spatial (`ST_Read`/`COPY GDAL`), gardées par
  `CORE_PIPELINE_FILE_IO_ENABLED` (défaut `false`, hors périmètre serveur) ;
  revue finale a trouvé et corrigé 1 Critical (élargissement de
  `allowed_directories` non gardé par le flag = lecture de fichier
  arbitraire même flag éteint, via un nœud `writer.file` jamais exécuté —
  variante du piège n°11 : le consommateur vérifié n'était pas le seul) +
  2 Important (colonnes `fid`/`OGC_FID` non exclues en lecture, collision
  de nom avec la colonne `geometry`).
- **Pipeline builder UX** — 22 tâches (undo/redo, connexion/suppression de
  nœud au clic, zones annotées persistées, palette recherchable + récents,
  tri/pagination/formatage de l'aperçu tableau, détail par run, prochaine
  exécution planifiée) + revue finale + 2 rondes de correctifs :
  autorisation de l'aperçu resserrée à `action="write"` (secrets
  connecteur non scopés par pipeline) et un vrai hang E2E trouvé et
  corrigé (`recordUse` dans `dragstart` gelait le drag natif Chromium,
  déplacé sur `dragend`).
- **Fiabilisation déploiement Proxmox + fraîcheur images** — realm
  Keycloak (`redirectUris`/`webOrigins`/`post.logout.redirect.uris`)
  resynchronisé à chaque lancement d'`install.sh`, service d'init dédié
  pour la propriété du volume `csp-dynamic-conf`, export OTel conditionné
  au profil `observability`, matrice de build extraite en workflow
  réutilisable `_build-and-push.yml` + `publish-edge.yml` (tag `edge` sur
  merge `main`) + porte de complétude `check_published_images.py`
  (authentifiée GHCR) sur les deux workflows de publication ; revue
  finale a trouvé et corrigé 1 Critical (permissions manquantes sur
  l'appel réutilisable) + 2 Important, puis un correctif de correctif
  (permission `contents` implicitement retirée par le premier correctif).
- **`cloture-rev-190-191-192-193`** — ferme 4 entrées indépendantes du
  backlog : durcissements exchange.py/parquet_writer.py, rattachement de
  preuve useOpenItem.ts, variante liste/array de bout en bout sur
  FieldType (collections). GAP-83 clos.
- **Page Paramètres fusionnée avec Administration** — remplace l'écran
  `/settings` « bientôt disponible » par une vraie page (profil,
  préférence de notifications, lien de compte Keycloak) ; fusionne la
  navigation Administration/Paramètres en un seul point d'entrée
  toujours visible (`SettingsNav`), visibilité des 7 destinations admin
  inchangée.
- **Vague 2 transformers DuckDB (schéma/cardinalité)** — 11 nouvelles op
  (bulkRemoveAttributes/bulkRenameAttributes/scanSchema/explodeList/
  explodeGeometry/exposeAttributes/validateAttributes/sort/detectChanges/
  mergeChildren/mapSchema), mécanisme `needs_columns` pour l'introspection
  de schéma à l'exécution ; catalogue exposé (`GET /pipelines/ops`) à 45 op,
  registre brut (`OPERATIONS`, `reader.file`/`writer.file` inclus derrière
  leur propre flag) à 47 ; 12 lignes `planned_duckdb` de la matrice FME
  passées à `implemented`.

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

Détail complet (194 entrées `REV-nnn`, 16 ouvertes, recompté le 2026-09-20
par classification robuste de chaque ligne `**État :**`) dans
**`docs/revue/2026-09-04-backlog.md`** — revalidé le 2026-09-06 après une
dérive documentaire (piège n°12, ce document était resté 21 SP sans être
retouché). Ce qui suit est un **pointeur**, pas un résumé — ne pas y
recoller le détail que le backlog porte déjà :

- Jalon **M14** atteint (SP-44, `REV-095`) : `@pytest.mark.qgis` tourne
  contre un sidecar réel, câblé en CI (`core-qgis`) ; en local
  `scripts/run-qgis-tests.sh`.
- `REV-073`/`075`/`076`/`077` + GAP-68/69 clos par **SP-60** : filets de
  déployabilité/E2E/perf frontend.
- `REV-096` clos par **SP-45** : garde d'egress SSRF sur l'appel LLM du
  copilote.
- `REV-097` clos par **SP-47** : `automation.secrets.manage` garde
  `/secrets`, domaine `app/usage/` créé.
- `aria-expanded`/`aria-controls` câblé par SP-43 (`REV-088` largement
  fermé, pas de lint automatique).
- Restauration de sauvegarde : succès partiel, reconnexion OIDC jamais
  vérifiée (`REV-164`, détail dans la section suivante).
- `save_app_config` (MCP) saute des validateurs REST — connu, non corrigé
  (`REV-174`).
- 4 index fonctionnels pgvector/trgm filtrés nommément par le comparateur
  modèle/Alembic (`REV-175`).
- GAP-72 partiellement fermé par **SP-48** : CSP `enforce` par défaut en
  prod (`report-only` en dev, rollback via `CORE_CSP_MODE`) sur
  img-src/connect-src ; `script-src` pour les widgets d'extension tiers
  reste une question produit ouverte (spec SP-48 §4) — à trancher avant
  tout câblage. Vérification Traefik bout-en-bout toujours à faire sur un
  vrai déploiement (limitation SP-55).
- GAP-57/59/60/62 clos par **SP-50** (fédération : pagination, plafond de
  taille d'egress, dégradation gracieuse sur collection cassée).
  Pagination shell et `GET /dcat/datasets/{id}` restent hors périmètre.
- i18n (SP-29a) + a11y (SP-57a) outillés : `npm run lint` bloque le
  français en dur, `a11y-audit.spec.ts` audite 9 pages
  (`REV-176`/`177`/`178`).
- Bilan de fonctionnalités outillé (SP-61) : `docs/revue/
  bilan-fonctionnalites.{html,md}`, régénéré par
  `feature_health_cli.py --write`, CI refuse toute surface non
  inventoriée. Matrice `2026-09-04-matrice-fonctionnalites.md` **gelée**,
  ne plus l'éditer (`REV-179`/`180`).
- Questions produit ouvertes : Q10 temps réel (`REV-108`), Q11 offline
  (`REV-120`). Q2 répondue 2026-09-15 : produit horizontal, parité de
  couverture de connecteurs comme différenciateur face à FME —
  `OperationContract` envisagé pour `core/app/pipelines/`, pas encore
  lancé.

### Suivis non bloquants — ce qu'il faut savoir avant de toucher la stack

Contexte détaillé par SP dans l'archive. Pointeurs seulement — ce qui
change le comportement d'une session sur la stack/l'environnement de dev :

- Stack vérifiée de bout en bout (11 services `healthy`) ; `libexpat1`
  manquant sur `python:3.12-slim`/trixie, corrigé dans `core/Dockerfile`.
- `core` applique `alembic upgrade head` avant `uvicorn`. `shell` restant
  `Created` = généralement `CORE_SECRETS_MASTER_KEY` vide — `docker logs
  core` avant de soupçonner `pg-data`.
- Martin : port hôte déplacé à `3010` (conflits fréquents côté hôte).
- `deploy/postgis/Dockerfile`/`pg_hba.conf` (non commités) sont inertes —
  ne pas les câbler, affaibliraient `scram-sha-256`.
- Conteneur `postgis-test` non tracké par Alembic — `ALTER TABLE` manuel
  après une migration qui ajoute des colonnes, sinon échecs
  `UndefinedColumn` sans rapport.
- Rate limiter clé sur l'en-tête `Authorization` brut : budget « par
  jeton », réinitialisé à chaque rafraîchissement OIDC.
- Ne pas réintroduire `dependency-type` sur l'entrée Dependabot `uv`
  (silencieusement ignoré par GitHub).
- Clé privée `age` de test dans l'historique public (commit `0b4733a`,
  redactée, absente de `HEAD`) — à confirmer jetable ou rotationner.
  `secret_scanning`/`dependabot_security_updates` désactivés sur ce dépôt.
- Couverture shell : mesurer après nettoyage de `dist/`/`dist-export/`
  (comptés comme source non couverte sinon).
- Régénération OpenAPI/TS : commande nue échoue, incantation réelle dans
  `ci.yml` (`PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY` de test).

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
13. **Découper `shell/` en packages npm workspace fait fuir des bugs dans des
    endroits sans rapport apparent** (scan de sources Tailwind, contexte de
    build Docker, lockfile, seuils de couverture, conception de ports
    d'interface non vérifiée contre les signatures réelles) — chantier tenté
    (Tasks 1-5) puis abandonné le 2026-09-08 faute de besoin de réutilisation
    externe concret, intégralement annulé sur `dev`. Détail des 7 classes de
    défauts rencontrées avant de retenter :
    [`docs/superpowers/specs/2026-09-08-app-builder-package-extraction-postmortem.md`](docs/superpowers/specs/2026-09-08-app-builder-package-extraction-postmortem.md).
