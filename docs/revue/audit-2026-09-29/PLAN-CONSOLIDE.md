# Audit GeoStudio 2026-09-29 — plan consolidé (k01)

Consolidation des 375 findings dédoublonnés (`merged.jsonl`, sortie de
`audit_findings.py dedup`) et des verdicts de rejeu de `v01/findings.jsonl`.
Ce document **ne corrige rien** : il ordonne ce qu'il faut corriger, combler ou
ajouter, par cause racine, en **30 tâches réparties en 6 phases de 5**.

## 0. Chiffres et méthode

| | S1 | S2 | S3 | S4 | Total |
|---|---|---|---|---|---|
| Findings dédoublonnés | 7 | 92 | 211 | 65 | 375 |

- **99 S1/S2** : 80 `verified` rejoués par v01 sur une stack réinitialisée
  (**79 confirmés**, **1 non reproduit** : j01-004, artefact de l'outillage
  `stack-reset.sh`, corrigé depuis : `scripts/audit/stack-reset.sh:89` pose
  désormais `GRANT USAGE ON SCHEMA public TO PUBLIC`) ; **19 `probable`** non
  rejoués (lecture de code), à confirmer par le test d'acceptation de leur tâche.
- Par nature : 125 bug, 65 improvement, 47 gap, 37 security, 31 a11y, 30 debt,
  25 perf, 14 test-gap, 1 feature.
- Méthode : regroupement par **cause racine** (§2) avant découpage en tâches ;
  chaque cause racine a été relue dans le code au commit `19a536f7` (pas dans
  les rapports d'agents, piège n°12). Toutes les `locations` des 375 findings
  ont été vérifiées mécaniquement (fichier présent, lignes dans le fichier :
  0 écart). Les `depends_on` ont été contrôlés (§2.9). La table de traçabilité
  (§7) est vérifiée par script (ids S1/S2 de `merged.jsonl` ⊆ ids du plan).
- Convention : `fichier:début-fin` = lignes relues ; « acceptation » = le test
  d'audit correspondant (souvent en `test.fixme`, qui encode déjà le
  comportement attendu) passe **sans fixme**, plus un test pérenne dans la suite
  du dépôt (`core/tests/` ou `shell/e2e/`), car les specs `shell/e2e/journeys/`
  ne tournent pas en CI.

## 1. Le constat en une phrase

La suite E2E du dépôt est verte (166/0) **parce qu'elle tourne en auth mock sur
un cœur mocké** (`shell/e2e/*.spec.ts`, `mocks.ts`) : les quatre défauts qui
cassent le plus de parcours sur la stack réelle — `.defer()` hors App
procrastinate ouverte, CORS MinIO non implémenté, worker MapLibre servi en
`octet-stream`, secret HMAC de lien de partage vide — ne sont visibles **que**
sur une stack composée réelle, que ni la CI ni les E2E n'exercent. La phase 1
les traite ; T25 ajoute le filet qui les aurait attrapés.

## 2. Causes racines communes (vérifiées dans le code)

### RC-1 — `.defer()` synchrone depuis le process API sans App procrastinate ouverte
- Code : `core/app/main.py:136-141` — le `lifespan` n'ouvre que
  `mcp_server.session_manager`, jamais `app.jobs.app` ; `core/app/jobs/__init__.py:56-80`
  documente l'hypothèse « crée un SyncPsycopgConnector à la demande », fausse
  avec procrastinate 3.10 réellement déployé (`AppNotOpen`).
- Écart de version : `core/Dockerfile:48` installe depuis `pyproject.toml`
  sans `uv.lock` (j03-018) — la CI teste une autre version que l'image.
- Sites d'appel côté API relus (12) : `core/app/ingestion/routes.py:66-70`,
  `core/app/harvest/routes.py:116-120`, `core/app/alerts/service.py:73`,
  `core/app/pipelines/service.py:73`, `core/app/compliance/routes.py:76-85`,
  `core/app/appexport/routes.py:56`, `core/app/export/routes.py:62`,
  `core/app/tileset3d/routes.py:87`, `core/app/terrain3d/routes.py:52`,
  `core/app/mcp/tools/pipelines.py:104`, et les deux avalés en silence
  `core/app/items/repository.py:51-70`, `core/app/collections/repository.py:21-44`.
- Findings : **j03-001 (S1)**, j03-018, j07-002, j09-001 (+j09-002, j11-003
  fusionnés), t02-004, j03-003 (conséquence : job fantôme), et en aval
  j07-003, j03-020, t02-010, c02-007.
- Effet de bord sur l'audit : import, moissonnage, évaluation d'alerte et
  indexation sémantique n'ont jamais tourné de bout en bout ; plusieurs agents
  ont semé leurs données en SQL direct (j02, j07, j09, j10, j11) — voir §5.

### RC-2 — Files et tâches procrastinate non câblées au worker
- `docker-compose.yml:439-440` : `-q ingestion,search,cdc,etl,tileset3d,terrain3d,appexport`
  — pas de `harvest` ; pas de `--concurrency` (défaut 1).
- `core/app/jobs/__init__.py:66-80` : `import_paths` sans `app.compliance.jobs`.
- Findings : **c02-003 (S1)** (+j07-001), c02-004, c09-001, c09-002 (S3).
- Classe : piège n°2 (« livré ≠ câblé ») — `test_deployability.py` ne compare
  pas les files déclarées aux `-q` des services.

### RC-3 — Stack de référence : défauts de config qui cassent une capacité
- MinIO reconstruit : `core/app/ingestion/storage.py:39-45` appelle
  `put_bucket_cors` sans rattraper `NotImplemented` → **j02-002 (S1)** (+j03-002).
- Secrets HMAC vides par défaut : `docker-compose.yml:323`, `:327`, `:339`
  (`CORE_EXPORT_TOKEN_SECRET`, `CORE_SHARE_LINK_TOKEN_SECRET`,
  `CORE_ADMIN_TOOLS_TOKEN_SECRET` en `${…:-}`), `.env.example:230` vide,
  absents de `scripts/bootstrap-env.sh` ; `core/app/sharing/share_links.py:34-35`
  lit `os.environ[...]` sans refuser `''` → **j13-001** (+ embed GAP-19, j13-011).

### RC-4 — Shell servi par nginx : types MIME et cache
- `shell/nginx.conf:20-22` : un seul `location /` avec `try_files … /index.html`,
  aucun type `mjs` → **j12-001 (S1)** (worker MapLibre jamais démarré), t03-002
  (hors gzip), t03-001 (pas de Cache-Control), t03-003 (chunk absent → 200 HTML).
- **Invalide des mesures** : j03-017 (rendu non observable), les mesures carte
  de t03 (prises avec le contournement `fixWorkerMime`), l'a11y carte de t01,
  et les findings tactiles j12-005/j12-009/j12-011 (`depends_on: j12-001`).
  À rejouer après T04 (§5).

### RC-5 — Nom de colonne géométrie du lac (`geometry` vs `geom`)
- `core/app/cdc/parquet_writer.py:72` écrit le GeoDataFrame avec la colonne
  `geometry` ; `core/app/analytics/sql_sandbox.py:90-108` et
  `core/app/analytics/aggregate.py:230-266` sélectionnent/filtrent
  `table_info.geometry_column` (`geom` pour une collection importée).
- Findings : **j05-001 (S1)**, j05-002 (+j05-003, j05-018 fusionnés), et en
  aval j05-012/j05-024 (S3, `depends_on: j05-003` → fusionné dans j05-002).

### RC-6 — Session OIDC remontée et destination perdue
- `shell/src/builder/copilot/useMcpToken.ts:52-86` appelle `signinSilent()` à
  chaque tour ; `shell/src/auth/RequireAuth.tsx:28-33` rend « Connexion… » dès
  `isLoading` et démonte tout le shell. `shell/src/auth/AuthProvider.tsx:38-58`
  ne transporte pas `returnTo`.
- Findings : **j11-007 (S1)**, j02-004, j02-010, j11-009, j11-015, t02-008 (S3).
  Les tests E2E copilote passent uniquement grâce au `mock-mcp-token`.

### RC-7 — Autorisation : garde de privilège absente sur les chemins voisins
Le modèle `can()`/`decide()` est correct ; ce sont les **chemins jumeaux** qui
oublient `require_privilege` (piège n°4) :
- `core/app/items/repository.py:335-349` : `else` implicite = aucun filtre
  (`scope` non typé) → j02-001.
- `core/app/public/routes.py:117-124` : sert la config de tout item publié,
  quel que soit son kind → j10-001.
- `core/app/items/routes.py:130-160` : `PATCH /items` (publication, partage)
  sans garde de kind → j13-002.
- `core/app/auth/routes.py:140-198` : pas de plafond « ≤ mes privilèges » →
  c01-002 (+j08-007 S3).
- `core/app/collections/routes.py:599-686` : `sensitiveFields` modifiable sans
  `data.view_sensitive` → c01-001.

### RC-8 — Masquage GAP-22 non reporté sur les chemins d'écriture et d'export
`core/app/appexport/freeze.py:24-66`, `core/app/appexport/snapshot.py:56-88`
(lecture non masquée), `core/app/features/routes.py:632-665` (PUT = remplacement
intégral, efface les colonnes masquées) → c01-001, c01-004, j10-007, j07-015 (S3).

### RC-9 — Pas de version de base à l'enregistrement d'une config
`core/app/configs/routes.py:397-434`, `core/app/configs/repository.py:211-225` :
dernier écrivain gagne → j04-008 (+c03-006, t02-002), t02-003.

### Contrôle des `depends_on` (S1/S2)
Tous les `depends_on` des S1/S2 pointent vers un id présent dans `merged.jsonl`,
sauf **t02-003 → t02-002**, fusionné dans **j04-008** (même tâche T09) ;
j05-012/j05-024 (S3) → j05-003, fusionné dans **j05-002** (T05). j08-002 (S2)
dépend de j08-006 (S3), traité dans la même tâche (T11). Chaque dépendance est
reprise dans l'ordre des tâches (§6, colonne « Dépend de »).

## 3. État des lieux par parcours

Comptes par agent émetteur (un finding fusionné compte pour chacun de ses
agents). État : **bloqué** = l'action principale du parcours échoue sur la
stack réelle ; **dégradé** = fonctionne avec pertes ou failles ; **non
couvert** = capacité éteinte pendant l'audit.

| Parcours | S1 | S2 | S3 | S4 | État | Causes dominantes |
|---|---|---|---|---|---|---|
| j01 Visiteur anonyme | 0 | 3 | 5 | 2 | dégradé | catalogue public inexistant côté shell (j01-001), lecture publique non paginée en SQL (c09-006), SEO incomplet |
| j02 Lecteur connecté | 1 | 6 | 4 | 3 | bloqué (pièces jointes) | RC-3 MinIO, RC-6 deep-link perdu, RC-7 `scope` inconnu, lecteur routé vers les éditeurs (j02-008) |
| j03 Créateur de carte | 2 | 6 | 11 | 2 | **bloqué** (import) | RC-1, RC-3, couche plafonnée à 100 entités (j03-008), publication sans ses données (j03-012) |
| j04 Créateur d'app | 0 | 5 | 7 | 2 | dégradé (perte de travail) | ids d'actions perdus (j04-001), pas de `beforeunload`, écrasement concurrent (RC-9), Retour arrière supprime le widget |
| j05 Analyste | 1 | 2 | 14 | 1 | **bloqué** (SQL Lab sur import) | RC-5, injection de formule CSV/XLSX (j05-009) ; requête visuelle et copilote non couverts (flags) |
| j06 Data engineer | 0 | 4 | 7 | 4 | **non couvert** | `CORE_ETL_ENABLED=false` (j06-001) ; lecture de code : topologie non validée, DSN sans garde d'egress |
| j07 Data steward | 1 | 5 | 12 | 2 | **bloqué** (moissonnage) | RC-2 file `harvest`, RC-1, source en erreur martelée (j07-006), `/stac/search` 500 sur table cassée |
| j08 Admin de tenant | 0 | 2 | 13 | 3 | dégradé | anonymisation annulée au prochain login (j08-001), page conformité inaccessible à l'Administrateur (j08-002) ; quotas non couverts |
| j09 Ops / instance | 0 | 3 | 10 | 2 | bloqué (alertes manuelles) | RC-1, échec de livraison invisible (j09-003), dataset vide → erreur (j09-013) ; passerelle admin non couverte |
| j10 Sites / export | 0 | 3 | 7 | 1 | dégradé | config publique de tout kind (j10-001), export non masqué (j10-007) ; exports non couverts (flags) |
| j11 Copilote / MCP | 1 | 4 | 9 | 2 | **non couvert** (LLM) + bloqué OIDC | RC-6, erreurs fournisseur en 500 opaque (j11-005), MCP bloque la boucle (c02-009) |
| j12 Mobile / tactile | 1 | 4 | 7 | 3 | **bloqué** (carte) | RC-4, barre du haut 517 px, grille non bornée, croquis sans tactile |
| j13 Partage | 0 | 5 | 6 | 1 | bloqué (liens) | RC-3 secret HMAC, RC-7 publication par un Lecteur, groupes sans CRUD, carte partagée sans ses données |
| t01 Accessibilité | 0 | 4 | 13 | 5 | dégradé | fond/texte absents en sombre (t01-005/006), `document.title` fixe, menu Actions non ARIA |
| t02 Résilience | 0 | 4 | 8 | 2 | dégradé | RC-1 avalé (embeddings), tables Keycloak registrables (t02-005), 401 non traité |
| t03 Performance | 0 | 5 | 6 | 1 | dégradé | vendor-map sur l'accueil (t03-005), troncatures 100/1000/10 000 silencieuses, fuite DOM éditeur de carte |
| t04 Cohérence UI/i18n | 0 | 0 | 12 | 15 | cosmétique | énumérations brutes, dates ISO, états d'erreur hétérogènes (S3/S4 seulement) |
| c01 Authz/RLS | 0 | 4 | 8 | 2 | — | RC-7, RC-8, secrets sans ACL (c01-003) |
| c02 Correctness | 1 | 5 | 8 | 0 | — | RC-2, commit après réponse (c02-001), runs réclamés en double (c02-005), MCP bloquant |
| c03 Migrations | 0 | 6 | 3 | 1 | — | FK sans `ON DELETE` (c03-001), downgrade 0030 élève les Lecteurs (c03-002), index manquants |
| c04 Qualité shell | 0 | 0 | 5 | 1 | — | `fetch` nu hors `base.request` (S3) |
| c05 Qualité tests | 0 | 1 | 4 | 1 | — | tests postgis skippés silencieusement (c05-001) |
| c06 CI / déploiement | 1 | 5 | 6 | 2 | — | versions d'images vs branche (c06-004), `sed` de l'installeur, sauvegarde sans healthcheck |
| c07 Dérive doc | 0 | 0 | 4 | 4 | — | CLAUDE.md contredit le backlog (S3/S4) |
| c08 Parité REST/MCP | 0 | 2 | 7 | 2 | — | schémas de config permissifs, erreurs non RFC 7807 |
| c09 Perf backend | 0 | 7 | 9 | 0 | — | DuckDB sans limites, index, balayages N+1, worker à concurrence 1 |
| d01 Benchmark | 0 | 3 | 10 | 1 | — | écarts produit (MCP client, offline, co-édition) |

## 4. Matrice de couverture des tests

Colonnes : **U** = tests unitaires/intégration cœur (`core/tests`, 365
fichiers) ; **E2E-mock** = `shell/e2e/*.spec.ts` (cœur mocké, CI) ;
**E2E-OIDC** = `shell/e2e-oidc/` (un seul fichier : `auth-oidc.spec.ts`) ;
**Audit** = tests Playwright écrits pendant l'audit contre la stack réelle
(`npx playwright test -c playwright.journeys.config.ts --list` : **620 tests
dans 69 fichiers**, hors CI) ; **Réel** = le parcours a-t-il pu être exercé de
bout en bout sur la stack composée.

| Domaine | U | E2E-mock | E2E-OIDC | Audit (tests) | Réel | Trou principal |
|---|---|---|---|---|---|---|
| Catalogue public / SEO / embed | oui | `catalog`, `embed` | non | j01 : 34 | partiel | aucun catalogue anonyme ; embed nominal non exercé (j13-001) |
| Lecture, fiche, bookmarks, notifications | oui | `bookmarks`, `item-detail-panels` | non | j02 : 30 | partiel | pièces jointes (RC-3) ; deep-link (RC-6) |
| Import → carte | oui | `ingestion*`, `map-*` | non | j03 : 40 | **non** | RC-1 + RC-3 : aucun import réel ; rendu carte (RC-4) |
| App builder | oui | `app-builder*`, `actions`, `variables` | non | j04 : 40 | oui | rechargement après enregistrement (ids perdus) jamais testé |
| SQL Lab / agrégats / exports | oui | `sql-lab`, `chart`, `export` | non | j05 : 35 | partiel | colonne géométrie (RC-5) ; requête visuelle et copilote : flags |
| Pipelines / connecteurs | oui | `pipeline-builder` | non | j06 : 57 | **non** | `CORE_ETL_ENABLED=false` |
| Moissonnage / STAC / DCAT | oui | `harvest-*` (6) | non | j07 : 59 | **non** | file `harvest` non consommée ; aucun serveur distant joignable |
| Admin tenant / RGPD / quotas | oui | `compliance-admin`, `quota-guard` | non | j08 : 35 | partiel | quotas : flag ; anonymisation d'un persona évitée |
| Ops, alertes, rapports, passerelle | oui | `alert-rule`, `report-schedule`, `tasks` | non | j09 : 25 | partiel | RC-1 ; passerelle, rapports : flags |
| Sites, story, export d'apps | oui | `sites-portal-*`, `static-export`, `connected-export` | non | j10 : 30 | partiel | export et PDF : flags |
| Copilote / MCP | oui (fournisseur fake) | `copilot*` (jeton mock) | **non** | j11 : 24 | **non** | LLM éteint ; chemin OIDC du jeton MCP (j11-015) |
| Mobile / tactile | non | `map-touch`, `responsive`, `triptych-narrow` | non | j12 : 30 | partiel | RC-4 : carte jamais rendue |
| Partage / permissions | oui | `item-permissions`, `publication` | non | j13 : 34 | partiel | liens (RC-3) |
| Accessibilité | — | `a11y-audit` (9 pages) | non | t01 : 40 | partiel | thème sombre non audité en CI ; pipelines/rapports : flags |
| Résilience | — | — | non | t02 : 37 | oui | arrêt worker non signalé ; 401 |
| Performance | perf import (temps mur, c05-003) | `check-bundle-size` | non | t03 : 34 | partiel | mesures carte sur contournement RC-4 |
| Cohérence UI / i18n | lint i18n | `theme` | non | t04 : 30 | oui | — |
| Déploiement / compose | `test_deployability.py` | — | — | — | — | files vs `-q`, secrets vides, MIME, images/versions non contrôlés |

Conséquence pour le plan : chaque tâche de phase 1 livre, en plus du correctif,
une **règle de déployabilité** ou un test sur stack composée (T25), faute de
quoi la même classe revient à la prochaine capacité.

## 5. Angles morts (non couverts par cet audit) et passe complémentaire

Capacités **éteintes** pendant l'audit (stack non modifiable par les agents) ;
leurs zones ne sont **pas saines**, elles sont **non auditées** :

| Capacité | Valeur pendant l'audit | Zones non exercées | Findings qui le signalent |
|---|---|---|---|
| `CORE_ETL_ENABLED` (+ `CORE_PIPELINE_FILE_IO_ENABLED`) | `false` (`docker-compose.yml:285`, `:459`) | builder de pipeline (palette 57 op, aperçu, runs, cron, webhook), connecteurs, exécution de la requête visuelle, outils MCP de pipeline, a11y du canvas DAG | j06-001, j06-009, j06-012, j06-013 ; resume j05/j06/j11/t01/t04 |
| `CORE_EXPORT_ENABLED` / `CORE_APPEXPORT_ENABLED` | `false` (`:322`, `:582`) | export asynchrone `/v1/export`, PDF `printLayout`, `ReportSchedule`, les 3 modes d'export d'app | j10-011, t03-008 ; resume j05/j09/j10/j11 |
| `CORE_ADMIN_TOOLS_ENABLED` | `false` (`:335`) | passerelle `/admin/martin|titiler|grafana`, jeton de lancement, cookie `gs_admin_session`, forwardAuth | j09-016 ; resume j08/j09 |
| `CORE_QUOTAS_ENABLED` | `false` (`:343`) | blocage par quota à l'import, au terrain 3D, à la création ; affichage des quotas | j08-017, t02-014 |
| `CORE_LLM_PROVIDER` | vide (`:264`) | tour de copilote réel, loopback `/mcp`, génération SQL/requête visuelle, historique | j11-001, j11-006 ; resume j05/j11 |
| `CORE_TILESET3D_ENABLED` | `false` (`:328`) | hébergement de tilesets 3D (upload, proxy) | aucun finding (angle mort muet) |
| Embeddings | fournisseur `fake` | pertinence de la recherche sémantique | j02-012 (S3, probable) |
| Profil `observability` | non démarré | Grafana, SLO, OTel | resume j09 |
| Egress de moissonnage | allowlist vide | moissonnage réel ArcGIS/WMS/WFS/WMTS/CSW/CKAN, livraison réelle webhook/SMTP | resume j07/j09 |
| Traefik / CSP enforcing | shell servi en direct sur :8300 | CSP réelle, compression, routage `seo-bots`, `sitemap.xml` racine | resume j10/t03 |

Autres angles morts : données semées en SQL direct à cause de RC-1/RC-3/j02-003
(le chemin d'import réel n'a donc jamais produit les données testées) ; lecteur
d'écran réel non utilisé (t01) ; appareils mobiles réels (j12) ; `purge_tenant`
jamais déclenché (consigne) ; mesures de rendu carte sur contournement (RC-4).

**Recommandation — passe complémentaire « flags allumés »** (après la phase 1,
sinon RC-1/RC-2 masquent tout) :
1. Ajouter à `scripts/audit/stack-reset.sh` un profil `--profile full`
   posant `CORE_ETL_ENABLED`, `CORE_PIPELINE_FILE_IO_ENABLED`,
   `CORE_EXPORT_ENABLED`, `CORE_APPEXPORT_ENABLED`, `CORE_ADMIN_TOOLS_ENABLED`,
   `CORE_QUOTAS_ENABLED` (avec `CORE_QUOTA_MAX_*` bas), `CORE_TILESET3D_ENABLED`,
   `CORE_LLM_PROVIDER=fake`, les secrets HMAC, les profils compose `export`,
   `appexport`, `observability`, et une allowlist d'egress vers des serveurs de
   test locaux (STAC/WMS/CKAN factices, SMTP de capture type MailHog).
2. Relancer **j06, j09, j10, j11** intégralement, **j05** (requête visuelle,
   export async), **j08** (quotas), **t01** (pipelines/rapports) et **t03**
   (carte sans contournement, après T04), puis **v01** sur les nouveaux S1/S2.
3. Relancer **j03, j07, j02** sans semis SQL une fois T01–T03 fusionnées
   (import, moissonnage et pièces jointes réels).

## 6. Plan : 30 tâches en 6 phases de 5

Effort : XS < ½ j, S ≈ 1 j, M ≈ 2–3 j, L ≈ 1 sem, XL > 1 sem. Les ids entre
parenthèses sont des S3/S4 traités au passage (même cause racine), sans
obligation de traçabilité.

### Phase 1 — Débloquer les parcours sur la stack réelle (S1)

**T01 — Ouvrir l'App procrastinate dans le process API (RC-1)** — effort M
- Findings : j03-001, j03-018, j07-002, j09-001, t02-004 (j09-002, j11-003 fusionnés).
- Fichiers : `core/app/main.py:136-141` (ouvrir `app.jobs.app` dans le
  `lifespan`, ou `defer_async` dans les routes async) ; `core/app/jobs/__init__.py:56-80` ;
  `core/Dockerfile:48` (`uv sync --frozen` depuis `uv.lock`) ; sites d'appel de
  RC-1 ; `core/app/items/repository.py:51-70` et
  `core/app/collections/repository.py:21-44` (ne plus avaler l'erreur sans
  compteur) ; `core/app/harvest/routes.py:116-120` (audit après l'enqueue).
- Dépend de : —
- Acceptation : `j03-001`, `j07-002`, `j09-001`, `t02-004` passent sans fixme
  (repro de `merged.jsonl`) ; nouveau test d'intégration cœur **sans deferrer
  mocké** qui appelle `POST /v1/uploads` et constate une ligne
  `procrastinate_jobs` ; un job `embed_item` existe après création d'item ;
  l'image `core` et la CI résolvent la même version de procrastinate.

**T02 — Câbler toutes les files et tâches au worker (RC-2)** — effort S
- Findings : c02-003, c02-004, c09-001 (c09-002).
- Fichiers : `docker-compose.yml:439-440` (ajouter `harvest`, `-c N` via env) ;
  `core/app/jobs/__init__.py:66-80` (`app.compliance.jobs`) ; compose prod et
  `deploy/ansible/` dérivés ; `core/tests/test_deployability.py` (règle
  « chaque `queue=` de `app.jobs.app.tasks` est consommée par un service ») ;
  `core/tests/test_jobs.py` (découverte automatique des modules `@app.task`).
- Dépend de : —
- Acceptation : `docs/revue/audit-2026-09-29/c02/repro/queues_vs_workers.py` ne signale plus aucune file
  orpheline ni tâche inconnue ; la nouvelle règle de déployabilité échoue si
  l'on retire `harvest` du `-q` (falsification, piège n°10).

**T03 — Défauts de config de la stack de référence : CORS MinIO et secrets HMAC (RC-3)** — effort S
- Findings : j02-002 (j03-002 fusionné), j13-001 (j13-011).
- Fichiers : `core/app/ingestion/storage.py:39-45` (rattraper `NotImplemented`,
  CORS via `MINIO_API_CORS_ALLOW_ORIGIN` dans `deploy/minio/` et le compose) ;
  `scripts/bootstrap-env.sh:17-28` et `scripts/audit/stack-reset.sh` (générer
  les 3 secrets HMAC) ; `core/app/sharing/share_links.py:34-35` (traiter `''`
  comme absent → 503 explicite) ; `docker-compose.yml:323`, `:327`, `:339`.
- Dépend de : —
- Acceptation : `j02-002` et `j13-001` passent sans fixme ; règle de
  déployabilité : aucun `*_SECRET`/`*_TOKEN_SECRET` requis par une route active
  n'a de défaut vide sans être généré par `bootstrap-env.sh`.

**T04 — nginx du shell : MIME `mjs`, gzip, cache, 404 des assets (RC-4)** — effort XS
- Findings : j12-001 (t03-001, t03-002, t03-003).
- Fichiers : `shell/nginx.conf:20-22` (`types { text/javascript mjs; }`,
  `gzip_types`, `location /assets/` immutable + `try_files $uri =404`) ;
  `shell/vite.copyMaplibreWorker.ts:29-35` ; `shell/src/map/maplibreWorkerSetup.ts:21` ;
  vérifier aussi l'image d'export d'app.
- Dépend de : —
- Acceptation : `j12-001` passe sans fixme **sans** le contournement
  `fixWorkerMime` ; test sur l'image construite : `GET /assets/maplibre-gl-worker.mjs`
  → `text/javascript`. Puis **rejouer** j03-017, les mesures carte de t03 et
  l'a11y carte de t01 (§5).

**T05 — Colonne géométrie du lac alignée (RC-5)** — effort S
- Findings : j05-001, j05-002 (j05-003, j05-018 fusionnés ; j05-012, j05-024).
- Fichiers : `core/app/cdc/parquet_writer.py:72` (ou renommage à la
  matérialisation) ; `core/app/analytics/sql_sandbox.py:90-108` ;
  `core/app/analytics/aggregate.py:230-266`.
- Dépend de : —
- Acceptation : `j05-001` et `j05-002` passent ; test cœur : collection
  **importée** (pas créée à la main) → `SELECT *` SQL Lab et agrégat filtré
  par `bbox` répondent 200.

### Phase 2 — S1 restants et pertes de données

**T06 — Session OIDC stable et destination conservée (RC-6)** — effort M
- Findings : j11-007, j02-004, j02-010, j11-009, j11-015 (t02-008).
- Fichiers : `shell/src/builder/copilot/useMcpToken.ts:52-86` (jeton MCP hors
  cycle `isLoading`, cache module) ; `shell/src/auth/RequireAuth.tsx:13-33` ;
  `shell/src/auth/AuthProvider.tsx:38-58` (`state.returnTo`) ;
  `shell/src/pages/AppRuntimePage.tsx:28-30`, `:140-150` ;
  `shell/src/builder/copilot/CopilotChat.tsx:60-67` (plafond d'historique).
- Dépend de : —
- Acceptation : `j11-007`, `j02-004`, `j02-010` passent ; nouveau
  `shell/e2e-oidc/copilot-oidc.spec.ts` (LLM fake) : brouillon et pile
  d'annulation intacts après 3 tours ; 25 tours sans 422.

**T07 — Installation et release reproductibles** — effort M
- Findings : c06-004, c06-001, c06-005.
- Fichiers : `.env.example:347`, `deploy/ansible/playbook.yml:27-72`,
  `docker-compose.prod.yml:30`, `scripts/install.sh:170-185`, `:413-420`.
- Dépend de : —
- Acceptation : installation à blanc depuis le tag publié : toutes les images
  résolues (aucun `manifest unknown`) ; test bats/pytest de `set_env_var` avec
  `&`, `|`, `\` ; le mot de passe temporaire est visible (ou remis par fichier
  0600) quand Docker préexiste.

**T08 — Intégrité des écritures et des suppressions** — effort M
- Findings : c02-001, c02-002, c03-001 (c02-011).
- Fichiers : `core/app/db.py:180-195`, `core/app/main.py:262-266` (commit avant
  réponse) ; `core/app/configs/routes.py:66-89`, `:311-352` (garde de références
  inverses sur les 3 routes, service unique) ; migration `ON DELETE` pour
  `core/alembic/versions/0018_pipeline_runs.py:24`,
  `core/alembic/versions/0036_pipeline_webhook_tokens.py:26` et tables voisines.
- Dépend de : —
- Acceptation : repro `docs/revue/audit-2026-09-29/c02/repro/test_c02_repro.py` (c02-001, c02-002) et
  `docs/revue/audit-2026-09-29/c03/probes/` (c03-001) inversés ; migration testée **sur base non vide**
  dans les deux sens (piège n°8).

**T09 — Ne plus perdre le travail d'édition (RC-9)** — effort M
- Findings : j04-008 (c03-006, t02-002 fusionnés), t02-003, j04-003.
- Fichiers : `core/app/configs/routes.py:397-434`,
  `core/app/configs/repository.py:211-225` (If-Match/version de base, 409) ;
  `shell/src/api/domains/apps.ts:89-93`, `shell/src/pages/AppBuilderPage.tsx:585-591` ;
  `shell/src/lib/useDirtyGuard.tsx:12-25` (`beforeunload`).
- Dépend de : T08 (le 409 doit être émis avant la réponse).
- Acceptation : `j04-008`, `t02-003`, `j04-003` passent ; mêmes gardes sur
  carte/dataset/bookmark ; régénération OpenAPI + types TS (piège n°1).

**T10 — Builder d'app et formulaires : round-trip et écriture** — effort S
- Findings : j04-001 (j10-006 fusionné), j04-010, j04-011, j02-003 (t01-014, j04-004).
- Fichiers : `core/app/configs/schemas.py:46-54` (`Message.id`) ;
  `shell/src/builder/ActionsPanel.tsx:66-68` ; `shell/src/builder/widgets/form.tsx:660-676` ;
  `shell/src/pages/AppBuilderPage.tsx:143-156` ;
  `core/app/features/validation.py:71-73`, `core/app/collections/provisioning.py:44-58`.
- Dépend de : —
- Acceptation : `j04-001` (retirer une action après rechargement n'en retire
  qu'une), `j04-010`, `j04-011`, `j02-003` passent ; test cœur : collection
  `POST /collections/empty` puis `POST …/items` → 201.

### Phase 3 — Autorisation et confidentialité

**T11 — Rôles, privilèges et conformité RGPD** — effort M
- Findings : c01-002, c03-002, j08-001, j08-002 (j08-006, j08-007, j08-005).
- Fichiers : `core/app/auth/routes.py:140-198` (plafond de privilèges) ;
  `core/alembic/versions/0030_roles.py:76-114` (downgrade refusé ou sûr) ;
  `core/app/compliance/service.py:79-83`, `core/app/users/repository.py:13-45`
  (tombstone `oidc_sub`) ; `shell/src/shell/chrome/SettingsNav.tsx:36-40`,
  `shell/src/shell/routes.tsx:327-337`, `core/app/roles/privileges.py:74-79`.
- Dépend de : —
- Acceptation : PoC `docs/revue/audit-2026-09-29/c01/poc/test_c01_authz_poc.py` (test `test_user_manager_can_grant_himself_the_…`)
  inversé ; `j08-001` (même jeton après effacement → 401/403) et `j08-002`
  passent ; test de migration 0030 sur base avec un Lecteur.

**T12 — Fuites de lecture et d'export** — effort S
- Findings : j02-001, j10-001, t02-005, j05-009 (j10-004).
- Fichiers : `core/app/items/repository.py:335-349`, `core/app/items/routes.py:62-72`,
  `:97-118` (`scope` en `Literal`) ; `core/app/public/routes.py:117-124`
  (allowlist de kinds publiables) ; `core/app/collections/routes.py:430-466`,
  `core/app/db.py:114` (denylist Keycloak/procrastinate) ;
  `core/app/analytics/export.py:45`, `:69-90` (neutralisation de formules).
- Dépend de : —
- Acceptation : `j02-001`, `j10-001`, `t02-005`, `j05-009` passent ; tests cœur
  de non-régression pour chacun (valeur de `scope` inconnue → 422).

**T13 — Partage : garde de privilège, groupes, données liées** — effort L
- Findings : j13-002, j13-004, j13-008 (j13-009 fusionné), j03-012 (j13-010, c01-006, c08-001, j13-005, j13-006).
- Fichiers : `core/app/items/routes.py:130-160`, `:246-255`,
  `core/app/items/service.py:48-74` ; `core/app/sharing/routes.py:30-98`,
  `core/app/sharing/repository.py:94-109` (CRUD groupes) ;
  `core/app/sharing/authorization.py:74-86` ; `shell/src/shell/ShareForm.tsx:248-266`,
  `shell/src/shell/ItemActions.tsx:26-40` (proposer de partager/publier les
  collections référencées).
- Dépend de : T11 (même règle de plafond de privilège).
- Acceptation : `j13-002`, `j13-004`, `j13-008`, `j03-012` passent ; outil MCP
  `set_sharing` soumis à la même garde (test de parité) ; méthodes `ItemClient`
  + types régénérés.

**T14 — Masquage GAP-22 sur tous les chemins (RC-8)** — effort M
- Findings : c01-001, c01-004, j10-007 (j07-015, j07-016).
- Fichiers : `core/app/collections/routes.py:599-686` ;
  `core/app/features/routes.py:632-665`, `core/app/features/repository.py:217-243`
  (préserver les colonnes masquées / PATCH partiel) ;
  `shell/src/builder/widgets/form.tsx:522-527` ;
  `core/app/appexport/freeze.py:24-66`, `core/app/appexport/snapshot.py:56-88`,
  `core/app/features/rls.py:32-40`.
- Dépend de : T10 (même chemin d'écriture de formulaire).
- Acceptation : PoC c01-001 inversé ; `j10-007` passe ; test : édition par
  formulaire d'un utilisateur masqué ne met aucune colonne sensible à NULL.
  Export d'app : à revérifier en passe « flags allumés » (§5).

**T15 — Coffre de secrets et connecteurs : ACL, egress, plafonds** — effort L
- Findings : c01-003, j06-004, j06-014 (j06-005, j06-003).
- Fichiers : `core/app/pipelines/connector_runtime.py:90-111`, `:283-346`,
  `:386` ; `core/app/secrets/repository.py:77-84`, `core/app/secrets/routes.py:42-52` ;
  `core/app/pipelines/runtime.py:525-541`.
- Dépend de : T01 ; vérification réelle soumise à la passe `CORE_ETL_ENABLED` (§5).
- Acceptation : `j06-004` passe (DSN vers `postgis:5432` refusé) ; test cœur :
  un Créateur ne peut pas référencer le secret d'autrui ; timeouts
  `connect_timeout`/`statement_timeout`/RESTClient prouvés par un serveur lent.

### Phase 4 — Robustesse des jobs et des surfaces d'API

**T16 — « Commit puis defer » robuste et jobs fantômes** — effort M
- Findings : j03-003 (c02-007, c02-006, t02-010, t02-013, j03-020, j09-014).
- Fichiers : `core/app/ingestion/repository.py:89-119`,
  `core/app/ingestion/tasks.py:173-205` ; `core/app/jobs/__init__.py` (santé de
  file exposée) ; `/health` et `/v1/instance`.
- Dépend de : T01.
- Acceptation : `j03-003` passe ; worker arrêté → le shell signale l'attente
  (t02-013) et le sondage s'arrête après un plafond.

**T17 — Pipelines : réclamation, audit, topologie, écriture en lot** — effort L
- Findings : c02-005, c03-003, j06-002, c09-010, j06-001.
- Fichiers : `core/app/pipelines/repository.py:180-197`,
  `core/app/pipelines/jobs.py:271-290` ; `core/app/pipelines/runtime.py:686-687`,
  `:826-898` ; `core/app/configs/pipeline_validation.py:29-48`,
  `core/app/configs/schemas.py:272-287` ; `core/app/features/repository.py:193-214` ;
  profil `CORE_ETL_ENABLED=true` de `scripts/audit/stack-reset.sh` (j06-001).
- Dépend de : T01, T02.
- Acceptation : repro c02-005 inversé (l'ancien run passe `failed`, pas de run
  concurrent) ; `j06-002` passe ; un run planifié écrit `pipeline.run` dans
  `audit_log` ; import de 50 000 lignes par `writer.collection` en lots ;
  **agent j06 rejoué** sur la stack ETL allumée.

**T18 — Moissonnage : backoff, retours UI, tolérance aux collections cassées** — effort S
- Findings : j07-003, j07-006, j07-008, j07-017 (j07-009, j07-010, j07-018).
- Fichiers : `core/app/harvest/service.py:66-73`, `core/app/harvest/repository.py:206-239` ;
  `core/app/stac/routes.py:344-399` ; `shell/src/pages/HarvestSourcesAdminPage.tsx:155-171`.
- Dépend de : T01, T02.
- Acceptation : `j07-003`, `j07-006`, `j07-008`, `j07-017` passent ; test
  cœur : une source en erreur n'est plus « due » avant son intervalle.

**T19 — Alertes : échecs de livraison visibles, dataset vide** — effort S
- Findings : j09-003, j09-013 (j09-011, j09-008, c01-008, c02-008).
- Fichiers : `core/app/alerts/jobs.py:188-192`, `:230-275` ;
  `core/app/alerts/routes.py:26-32` ; `shell/src/builder/AlertRuleEditor.tsx:27-50`.
- Dépend de : T01.
- Acceptation : `j09-003`, `j09-013` passent ; migration du statut de
  livraison testée sur base non vide ; `run_alert_rule` MCP soumis au mode
  lecture seule.

**T20 — Contrats d'API : validation stricte et erreurs RFC 7807** — effort M
- Findings : c08-004, c08-002, j03-011, j11-005 (j11-001, j04-013, j04-014, c08-006).
- Fichiers : `core/app/main.py:144-169` (handlers Starlette/RequestValidationError) ;
  `shell/src/api/base.ts:58-75` ; `core/app/configs/schemas.py:14-37`, `:71-131`,
  `:431-433` (`extra='forbid'`, bornes, union discriminée) ;
  `core/app/copilot/routes.py:157-190`.
- Dépend de : —
- Acceptation : `docs/revue/audit-2026-09-29/c08/probes/probe_7807.py` : 404/422 en `application/problem+json` ;
  `j03-011`, `j11-005` passent ; test c08-002 (widget inconnu refusé) inversé ;
  OpenAPI + types régénérés, suite E2E complète verte (les mocks écrivent-ils
  des clés inconnues ?).

### Phase 5 — Performance et exploitation

**T21 — Index manquants** — effort S
- Findings : c03-004, c03-005, c09-004 (c09-005, c03-007).
- Fichiers : `core/alembic/versions/0004_audit_log.py:18-30`,
  `core/alembic/versions/0001_baseline.py:18-35` (nouvelle migration),
  `core/app/configs/models.py:15-34`, `core/app/audit/models.py`.
- Dépend de : T08 (même série de migrations).
- Acceptation : `docs/revue/audit-2026-09-29/c03/probes/index_plans.py` n'affiche plus `SCAN` sur
  `audit_log`, `configs`, `config_revisions` ; comparateur modèle/Alembic vert.

**T22 — DuckDB borné (mémoire, threads, délai)** — effort M
- Findings : c09-008, c09-009.
- Fichiers : `core/app/analytics/duckdb_conn.py:21-38`,
  `core/app/features/routes.py:249-306`, `core/app/pipelines/routes.py:134-158`,
  `core/app/pipelines/runtime.py:765-830`, `core/app/alerts/jobs.py:158-163`.
- Dépend de : T05.
- Acceptation : `current_setting('memory_limit')` borné sur toute connexion
  ouverte par `open_connection` ; un agrégat pathologique est interrompu
  (timeout) ; rate-limit dédié sur `/aggregate` anonyme.

**T23 — Lectures publiques et balayages en SQL** — effort M
- Findings : c09-006 (j01-009 fusionné), c09-003 (c09-007).
- Fichiers : `core/app/items/repository.py:531-560`, `core/app/public/routes.py:22-32`,
  `:87-95` (embedding `deferred`, pagination SQL, sitemap léger) ;
  `core/app/configs/repository.py:41-46`, `:97-126`,
  `core/app/pipelines/repository.py:151-168`.
- Dépend de : T21.
- Acceptation : `GET /public/items` n'émet plus `embedding` dans le SQL et
  applique `LIMIT` ; balayage de 1000 configs en ≤ 2 requêtes (compteur de
  requêtes, pas de temps mur — piège n°7).

**T24 — MCP : ne plus bloquer la boucle asyncio** — effort M
- Findings : c02-009 (c02-010).
- Fichiers : `core/app/mcp/tools/catalog.py:55-79`, `core/app/mcp/tools/analytics.py:82-166`,
  `core/app/mcp/tools/configs.py:152-200` (helper `to_thread` commun).
- Dépend de : —
- Acceptation : `docs/revue/audit-2026-09-29/c02/repro/mcp_blocks_event_loop.py` : `/health` répond
  pendant un outil lent (mesure de **recouvrement** d'intervalles, piège n°7).

**T25 — Sauvegardes, images, filets de test d'infrastructure** — effort M
- Findings : c06-002, c06-003, c05-001, c06-009 (c05-002, c06-006, c06-014).
- Fichiers : `deploy/backup/entrypoint.sh:8-18`, `deploy/backup/backup.sh:86-105`,
  `deploy/backup/retention.py:32-39`, `docker-compose.prod.yml:318-350` ;
  `core/tests/conftest.py:30-33` (`--require-postgis` en CI) ;
  `shell/Dockerfile:1`, `.github/workflows/ci.yml:207`,
  `deploy/appexport-runtime-builder/Dockerfile:7`.
- Dépend de : T02, T03, T04 (les règles de déployabilité y sont posées).
- Acceptation : healthcheck `backup` rouge si `last_success` > 26 h ; CI échoue
  si un test postgis se skippe ; Node ≥ 22 partout ; job CI « stack
  composée » minimal (import GeoJSON + worker MapLibre + lien de partage) qui
  aurait attrapé RC-1/RC-3/RC-4.

### Phase 6 — Parcours lecteur, mobile, a11y et volumes

**T26 — Mise en page triptyque bornée et barre du haut mobile** — effort M
- Findings : j02-009, j12-003 (j12-004 fusionné), j12-002 (j03-016, j12-008).
- Fichiers : `shell/src/shell/chrome/TriptychLayout.tsx:22-28`,
  `shell/src/shell/AppLayout.tsx:70-79`, `shell/src/pages/MapEditorPage.tsx:189`,
  `shell/src/shell/chrome/TopBar.tsx:18-35`.
- Dépend de : —
- Acceptation : `j02-009`, `j12-002`, `j12-003` passent (scrollHeight ≤
  innerHeight à 360 et 1280 px) ; E2E `triptych-narrow` et `responsive` verts.

**T27 — Carte au doigt** — effort S
- Findings : j12-005, j12-009 (j12-006, j12-007, j12-011).
- Fichiers : `shell/src/map/MapPopup.tsx:68-76`,
  `shell/src/map/MapMeasureSketchToolbar.tsx:340-365`.
- Dépend de : T04.
- Acceptation : `j12-005` et `j12-009` passent **sans** stub de worker.

**T28 — Accessibilité transverse** — effort S
- Findings : t01-004, t01-005, t01-006, t01-009 (t01-001, t01-010, t01-011, t01-013).
- Fichiers : `shell/src/index.css:1-12`, `shell/src/styles/tokens.css:121-125`,
  `shell/src/shell/AppLayout.tsx:67`, `shell/src/pages/DatasetPage.tsx:84-88`,
  `shell/src/pages/AppRuntimePage.tsx:145-150`, `shell/index.html:6`,
  `shell/src/shell/routes.tsx:232-241`, `shell/src/shell/ItemActions.tsx:52-130`
  (→ `ui/kit/Menu`).
- Dépend de : —
- Acceptation : `t01-004`, `t01-005`, `t01-006`, `t01-009` passent ;
  `shell/e2e/a11y-audit.spec.ts` gagne un passage en thème sombre.

**T29 — Données complètes et troncatures annoncées** — effort L
- Findings : j03-008, j03-013, t03-007, t03-008, t03-011 (j10-010, t03-010).
- Fichiers : `core/app/ingestion/importer.py:308-315`, `core/app/features/routes.py:204`,
  `:375-431` (export streamé) ; `shell/src/map/geojsonIntrospect.ts:5-7`,
  `shell/src/map/LayersPanel.tsx:24-31` ; `shell/src/lib/datasetDownload.ts:12-33` ;
  `shell/src/api/domains/datasets.ts:235-262`, `shell/src/builder/widgets/data.tsx:271-312`,
  `shell/src/pages/DatasetPage.tsx:40-48`.
- Dépend de : T01, T04.
- Acceptation : `j03-008`, `j03-013`, `t03-008`, `t03-011` passent ;
  téléchargement GeoJSON de 500 000 entités complet ou « N sur M » affiché.

**T30 — Catalogue anonyme, lecteur routé vers l'usage, perf de l'accueil** — effort L
- Findings : j01-001, j02-008, t03-005, t03-012.
- Fichiers : `shell/src/shell/routes.tsx:251-253`, `core/app/public/routes.py:50-64` ;
  `shell/src/shell/useOpenItem.ts:81-87`, `shell/src/pages/ItemDetailPage.tsx:111-127` ;
  `shell/src/pages/CatalogSpatialFilter.tsx:50-166`, `shell/src/pages/CatalogPage.tsx:240-246`,
  `shell/vite.config.ts:30-50` ; `shell/src/map/MapView.tsx:1074-1215`.
- Dépend de : T23 (pagination publique), T06 (routage auth).
- Acceptation : `j01-001`, `j02-008`, `t03-005` (vendor-map absent de la charge
  de `/`), `t03-012` (8 cycles d'éditeur sans croissance de nœuds détachés)
  passent ; seuil de taille de bundle respecté (t03-006 : 0,1 Ko de marge).

### Vue d'ensemble des dépendances

```
Phase 1 : T01  T02  T03  T04  T05          (indépendantes, parallélisables)
Phase 2 : T06  T07  T08 → T09  T10
Phase 3 : T11 → T13   T12   T10 → T14   T01 → T15
Phase 4 : T01 → T16   T01,T02 → T17, T18   T01 → T19   T20
Phase 5 : T08 → T21 → T23   T05 → T22   T24   T02,T03,T04 → T25
Phase 6 : T26   T04 → T27   T28   T01,T04 → T29   T06,T23 → T30
Passe « flags allumés » (§5) : après phase 1 ; conditionne la clôture de T15, T17, T14 (export).
```

## 7. Table de traçabilité S1/S2 (99)

V = verdict v01 (C = confirmé, NR = non reproduit, — = `probable`, non rejoué).

| Finding | Sév. | Type | Parcours | V | Tâche / rejet motivé |
|---|---|---|---|---|---|
| c02-003 | S1 | bug | harvest | C | T02 |
| c06-004 | S1 | bug | transverse | — | T07 |
| j02-002 | S1 | bug | pieces-jointes | C | T03 |
| j03-001 | S1 | bug | j03 | C | T01 |
| j05-001 | S1 | bug | sql-lab | C | T05 |
| j11-007 | S1 | bug | transverse | C | T06 |
| j12-001 | S1 | bug | transverse | C | T04 |
| c01-001 | S2 | security | transverse | C | T14 |
| c01-002 | S2 | security | transverse | C | T11 |
| c01-003 | S2 | security | transverse | — | T15 |
| c01-004 | S2 | bug | transverse | — | T14 |
| c02-001 | S2 | bug | transverse | C | T08 |
| c02-002 | S2 | bug | transverse | C | T08 |
| c02-004 | S2 | bug | compliance | C | T02 |
| c02-005 | S2 | bug | pipelines | C | T17 |
| c02-009 | S2 | perf | mcp | C | T24 |
| c03-001 | S2 | bug | transverse | C | T08 |
| c03-002 | S2 | security | transverse | C | T11 |
| c03-003 | S2 | gap | transverse | — | T17 |
| c03-004 | S2 | perf | transverse | C | T21 |
| c03-005 | S2 | perf | transverse | C | T21 |
| c05-001 | S2 | test-gap | transverse | C | T25 |
| c06-001 | S2 | bug | transverse | C | T07 |
| c06-002 | S2 | bug | transverse | — | T25 |
| c06-003 | S2 | gap | transverse | C | T25 |
| c06-005 | S2 | bug | transverse | — | T07 |
| c06-009 | S2 | debt | transverse | — | T25 |
| c08-002 | S2 | gap | transverse | C | T20 |
| c08-004 | S2 | gap | transverse | C | T20 |
| c09-001 | S2 | perf | transverse | C | T02 |
| c09-003 | S2 | perf | transverse | — | T23 |
| c09-004 | S2 | perf | transverse | — | T21 |
| c09-006 | S2 | perf | transverse | C | T23 |
| c09-008 | S2 | perf | transverse | C | T22 |
| c09-009 | S2 | perf | transverse | — | T22 |
| c09-010 | S2 | perf | transverse | — | T17 |
| d01-001 | S2 | gap | transverse | — | **Rejet motivé** : fonctionnalité nouvelle (op de pipeline client MCP tiers), pas un défaut ; à instruire comme SP de feuille de route (OperationContract + garde d'egress), hors plan correctif |
| d01-003 | S2 | gap | transverse | — | **Rejet motivé** : app mobile / hors ligne = question produit ouverte Q11 (`REV-120`, GAP-26) ; aucun arbitrage §8 ne l'ouvre ; ne pas coder avant décision |
| d01-004 | S2 | gap | transverse | — | **Rejet motivé** : co-édition = question produit ouverte Q10 (GAP-20) ; la protection minimale contre l'écrasement est traitée par T09 |
| j01-001 | S2 | gap | catalogue-public | C | T30 |
| j01-004 | S2 | debt | transverse | NR | **Rejet motivé** : non reproduit par v01 ; artefact de `stack-reset.sh` (ACL du schéma `public` recréé), corrigé dans l'outillage (`scripts/audit/stack-reset.sh:89`), aucun défaut produit |
| j02-001 | S2 | security | droits-lecteur | C | T12 |
| j02-003 | S2 | bug | donnees | C | T10 |
| j02-004 | S2 | bug | connexion-oidc | C | T06 |
| j02-008 | S2 | gap | catalogue-lecteur | C | T30 |
| j02-009 | S2 | bug | carte-lecture | C | T26 |
| j02-010 | S2 | bug | liens-directs | C | T06 |
| j03-003 | S2 | bug | j03 | C | T16 |
| j03-008 | S2 | bug | j03 | C | T29 |
| j03-011 | S2 | bug | j03 | C | T20 |
| j03-012 | S2 | gap | j03 | C | T13 |
| j03-013 | S2 | bug | j03 | C | T29 |
| j03-018 | S2 | debt | j03 | — | T01 |
| j04-001 | S2 | bug | j04 | C | T10 |
| j04-003 | S2 | bug | j04 | C | T09 |
| j04-008 | S2 | bug | j04 | C | T09 |
| j04-010 | S2 | bug | j04 | C | T10 |
| j04-011 | S2 | bug | j04 | C | T10 |
| j05-002 | S2 | bug | analytics-aggregate | C | T05 |
| j05-009 | S2 | security | exports | C | T12 |
| j06-001 | S2 | test-gap | transverse | C | T17 (profil ETL de `stack-reset.sh`) + passe complémentaire §5 |
| j06-002 | S2 | bug | pipeline-builder | C | T17 |
| j06-004 | S2 | security | connecteurs-erreurs | — | T15 |
| j06-014 | S2 | perf | connecteurs-erreurs | — | T15 |
| j07-002 | S2 | bug | j07 | C | T01 |
| j07-003 | S2 | bug | j07 | C | T18 |
| j07-006 | S2 | bug | j07 | C | T18 |
| j07-008 | S2 | bug | j07 | C | T18 |
| j07-017 | S2 | bug | j07 | C | T18 |
| j08-001 | S2 | security | rgpd-anonymisation | C | T11 |
| j08-002 | S2 | bug | rgpd-anonymisation | C | T11 |
| j09-001 | S2 | bug | alertes | C | T01 |
| j09-003 | S2 | gap | alertes | C | T19 |
| j09-013 | S2 | bug | alertes | C | T19 |
| j10-001 | S2 | security | sites | C | T12 |
| j10-007 | S2 | security | export-apps | C | T14 |
| j11-005 | S2 | bug | transverse | C | T20 |
| j11-009 | S2 | bug | transverse | — | T06 |
| j11-015 | S2 | test-gap | transverse | C | T06 |
| j12-002 | S2 | bug | transverse | C | T26 |
| j12-003 | S2 | bug | transverse | C | T26 |
| j12-005 | S2 | a11y | transverse | C | T27 |
| j12-009 | S2 | bug | transverse | C | T27 |
| j13-001 | S2 | bug | partage-liens | C | T03 |
| j13-002 | S2 | security | partage-roles | C | T13 |
| j13-004 | S2 | gap | partage-groupes | C | T13 |
| j13-008 | S2 | gap | partage-donnees | C | T13 |
| t01-004 | S2 | a11y | transverse | C | T28 |
| t01-005 | S2 | a11y | transverse | C | T28 |
| t01-006 | S2 | a11y | transverse | C | T28 |
| t01-009 | S2 | a11y | catalogue | C | T28 |
| t02-003 | S2 | bug | transverse | C | T09 |
| t02-004 | S2 | bug | transverse | C | T01 |
| t02-005 | S2 | security | admin-collections | C | T12 |
| t03-005 | S2 | perf | catalogue | C | T30 |
| t03-007 | S2 | bug | catalogue-public | — | T29 |
| t03-008 | S2 | gap | catalogue-public | C | T29 |
| t03-011 | S2 | bug | apps | C | T29 |
| t03-012 | S2 | bug | cartographie | C | T30 |

Bilan : 95 S1/S2 affectés à une tâche, 4 rejets motivés (d01-001, d01-003,
d01-004, j01-004). Les 19 `probable` sont affectés et seront confirmés ou
infirmés par le test d'acceptation de leur tâche avant correction.

## 8. Suites à donner hors tâches

- **À la clôture de chaque tâche** (CLAUDE.md § Comment on travaille) : ligne
  `### Livré`, historique continu, `GAP-nn` concernés (GAP-05, GAP-12, GAP-19,
  GAP-22, GAP-42, GAP-56, GAP-62, GAP-64, GAP-71 sont cités par des findings),
  inventaire de fonctionnalités et bilan régénéré, OpenAPI + types TS.
- Les 211 S3 et 65 S4 non cités ci-dessus restent dans `merged.jsonl` ; ceux de
  c07 (dérive de CLAUDE.md contre le backlog) sont des corrections de
  documentation à faire dans un seul commit, hors de ce plan.
- Les tests d'audit `shell/e2e/journeys/` ne tournent pas en CI : la condition
  de sortie de chaque tâche inclut un test pérenne dans `core/tests/` ou
  `shell/e2e/`, et T25 ajoute un job « stack composée » minimal.
