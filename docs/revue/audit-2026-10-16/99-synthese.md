# 99 — Synthèse du programme d'audit GeoStudio (2026-10-16)

Sources : `00-baseline-*`, `concurrents/` (8 fichiers), `dimensions/d01` à `d35`, `parcours/` (6 personas). HEAD `c0251b66`, branche `dev`. Les constats « non vérifiés » des dimensions sont repris tels quels (sévérité Minor ou marqués dans la ligne). Aucune modification de `docs/vision` ni de `CLAUDE.md`.

## 1. État mesuré de la baseline

| Mesure | Résultat |
|---|---|
| Cœur, pytest | 5643 passés, 0 échec, 23 skippés, 46 min 53 s ; couverture 93,59 % (seuil 85) |
| Cœur, portes statiques | ruff, ruff format, mypy --strict (40 fichiers), lint-imports (1 contrat, 0 rompu) : OK |
| Skips | 17 `helm absent`, Snowflake/Redshift/Databricks sans DSN, MinIO sans `CORE_TEST_S3_ENDPOINT` |
| Shell, vitest | 346 fichiers, 3221 tests verts ; lint, format, build OK |
| Bundle | initial 616,3 Ko pour un seuil de 640 Ko (marge 23,7 Ko) ; chunk `MapView` 1180 kB (340 gz) |
| E2E mock | 323 tests, 316 passés, 4 skippés, 3 échecs flaky verts au rejeu (`ingestion-cancel.spec.ts:6`, `analytics-context.spec.ts:2620`, `touch-map.spec.ts:89` tablet-touch) |
| Stack réelle | services de base arrêtés (WSL), core/worker/martin en boucle ; `docker compose up -d` a suffi, 14 services healthy |
| Bilan de fonctionnalités | `feature_health_cli --check` RC=0, santé médiane 98,8 (plancher 96,0) |
| `e2e-oidc` | 3/3 verts une fois la stack configurée (`VITE_AUTH_MODE=oidc`, `CORE_LLM_PROVIDER=fake`) ; `restore-reconnect` skippé par conception |
| Non rejoué | restore-oidc (`down -v`), `up --build`, journeys, e2e-mock complet hors baseline, admin-tools, rebuild-images, smoke, REV-284d/286c manuels |

Pièges d'environnement mesurés : `/tmp/pytest-of-lenen` appartient à root (`--basetemp` requis) ; schéma périmé de `gis_test` (colonne `group_members.origin` absente) ; `DATABASE_URL` non exporté fait attendre ~60 s 10 tests (`app/jobs/__init__.py:42-50`), soit ~10 min perdues.

Lecture : la suite verte (5643 + 3221 + 316) prouve la tenue des chemins testés, pas la correction métier. Les 22 Critical ci-dessous ont tous passé cette suite verte (tampon faux, KPI plafonné, export vide, SLO aveugles). L'écart entre « vert » et « juste » est le constat transversal de l'audit.

## 2. Score de parité par domaine

Barème : capacité présente ou dépassée = 1, partielle = 0,5, absente = 0.

| Domaine de référence | Score | Détail |
|---|---|---|
| ArcGIS apps (Experience Builder, Dashboards, Survey123, Field Maps, Velocity, Hub, StoryMaps, Notebooks, GeoAnalytics) | 55 % (47 capacités) | EB 70, Dashboards 50, Survey123 56, Field Maps 12, Velocity 75, GeoAnalytics 0, Notebooks 50, Hub 62, StoryMaps 25 |
| ArcGIS Pro / Enterprise / Online | 68 % (30,5/45) | |
| FME écosystème (formats, raster, 3D, qualité, Hub) | 57 % (25/44) | 52 % sans les op expérimentales |
| FME Form / Flow / Hosted | 61 % (24,5/40) | |
| Data / BI / ETL (Superset, Metabase, Airbyte, dbt, Dagster, DuckDB) | 62 % (18,5/30) | BI 73 %, ETL 53 % |
| Tendances IA et standards | 68 % (13,5/20) | |
| OSS géo (QGIS Server, GeoNode, GeoServer, MapStore, Kepler, Felt, Carto, Mapbox) | 67 % (29,5/44) | |
| France (IGN, data.gouv, INSEE, RGAA, RGS, SecNumCloud) | 52 % (11,5/22) | |

Moyenne simple : environ 61 %. Le plus faible (France 52 %, FME formats 52-57 %, apps terrain 12 %) coïncide avec ce que les personas ont rencontré en parcours.

### Les 20 écarts qui comptent le plus

| # | Écart | Réf. concurrent | Lien backlog |
|---|---|---|---|
| 1 | Aucune capacité hors-ligne (PWA, service worker, sync) | Field Maps, Survey123, QuickCapture | AUD-004 |
| 2 | Pas de temps réel / streaming (pas de `refetchInterval`, pas de flux) | Velocity, FME Streams | AUD-131 |
| 3 | Pas de jointure spatiale avec report d'attributs ni d'overlayer | FME AreaOnAreaOverlayer, ArcGIS Spatial Join | AUD-021 |
| 4 | Pas de FeatureServer / MapServer servi | ArcGIS Enterprise | AUD-143 |
| 5 | Pas de CSW / OGC API Records serveur, pas d'ISO 19139 / INSPIRE | GeoNetwork, GeoNode | AUD-047, AUD-048 |
| 6 | Formats 3D/BIM/nuages de points et PMTiles/MBTiles/FlatGeobuf absents ; écriture limitée à csv/xlsx/geojson/gpkg | FME | AUD-143 |
| 7 | Pas de langue d'interface ni de contenu multilingue (français seul) | tous | AUD-019, AUD-115, AUD-116 |
| 8 | Pas de validation/réparation de géométrie, pas de seuil de qualité | FME GeometryValidator | AUD-079, AUD-080 |
| 9 | Pas de custom transformers, PythonCaller, boucles de pipeline | FME | AUD-144 |
| 10 | Pas de Hub / portail multi-tenant réel (tenant « default » en dur) | ArcGIS Hub | AUD-010, AUD-076 |
| 11 | OGC incomplet : queryables/cql2-json, Tiles non déclaré, WMS 1.1.1, GetLegendGraphic, WFS-T, WCS, WPS | GeoServer, QGIS Server | AUD-041 à AUD-045, AUD-140 |
| 12 | Pas de RGAA démontrable, RGS, SecNumCloud, ProConnect | exigences collectivités | AUD-146 |
| 13 | Connecteur data.gouv inopérant (appelle l'API CKAN, 404 sur udata) ; pas d'INSEE/Cadastre/BD TOPO natifs ; fonds IGN absents | écosystème FR | AUD-127, AUD-128, AUD-122 |
| 14 | Collecte : XLSForm partiel (repeat, calculate, choice_filter), géométrie points seulement, pas de QuickCapture | Survey123 | AUD-070, AUD-071 |
| 15 | Pas de HA/PITR base ni de mise à jour sans interruption | ArcGIS Enterprise webgisdr | AUD-032, AUD-033 |
| 16 | Catalogue de connecteurs SaaS limité, pas de backfill, pas d'orchestration par assets, lac non transactionnel | Airbyte, Dagster, DuckLake | AUD-148 |
| 17 | Modèle sémantique pauvre, pas de cache analytique, SQL Lab sans requêtes sauvegardées | Superset, Metabase | AUD-062, AUD-063 |
| 18 | Pas de collaboration/commentaires de carte, pas d'export vidéo/GIF | Felt | AUD-147 |
| 19 | Pas de notebooks ni GeoAnalytics/Spark | ArcGIS Notebooks | AUD-145 |
| 20 | Un seul fournisseur LLM natif (openai-compatible), pas de suivi de consommation | tendances IA | AUD-106, AUD-149 |

Avantages réels, à ne pas perdre : Apache-2.0 auto-hébergé ; documents déclaratifs opérables par IA via MCP, copilote sous `can()` et audité ; cross-filter spatial et contexte temps×emprise ; pipeline no-code (~150 op brutes, 59 exposées) avec quarantaine `__rejected` et lineage ; sécurité unifiée (RLS, masquage de colonne, limites géographiques) sur toutes les surfaces ; chaîne données -> carte -> app -> portail avec STAC/DCAT-AP et BAN ; soumission publique modérée ; export d'app autoporté ; Helm HA ; script de restauration avec drill CI.

## 3. Backlog unifié, dédoublonné, priorisé

Légende. Sévérité : C = Critical, I = Important, M = Minor. Tags : bug, sécurité, parité, différenciateur, dette, polish. Effort : S (<= 1 j), M (2-5 j), L (> 1 sem.). Ordre : Critical, puis blocages de parité (Important parité/bug/sécurité), puis différenciateurs, puis polish. « d04,d15 » = dimensions ayant remonté le même constat (fusionné). Les lignes dont la dimension est marquée `(nv)` reposent sur des constats non vérifiés ligne à ligne.

### 3.1 Critical

| id | titre | sév | tag | dim | effort | fichiers |
|---|---|---|---|---|---|---|
| AUD-001 | Export d'app/dashboard (donc tout ReportSchedule) capturé sans attendre les widgets | C | bug | d04 | M | `shell/src/pages/AppRuntimePage.tsx:79`, `exportReady.ts` |
| AUD-002 | Source `features` par défaut plafonnée à 100 entités : KPI, graphique, tableau faux sans alerte | C | bug | d05, decideur | M | `DataSourcePanel.tsx:144`, `datasets.ts:210`, `indicator.tsx:163` |
| AUD-003 | Export d'app impossible pour toute source liée à un dataset (`layer=''`) | C | bug | d06 | M | `core/app/appexport/guard.py`, `freeze.py:41`, `DataSourceSelect.tsx:35` |
| AUD-004 | Aucune capacité hors-ligne : ni PWA, ni service worker, ni file de sync (Q11) | C | parité | d07, d35 | L | `shell/src/` (nouveau), `form.tsx` |
| AUD-005 | `transform.buffer` en mètres calculé en EPSG:3857 : ~34 % trop court à 49 N (66 m pour 100 m) ; libellé présente le défaut comme une fonction | C | bug | d08, d10, d34 | S | `core/app/pipelines/compiler.py:186-192`, `analysis.py:77-79` |
| AUD-006 | `snapToLayer` produit un produit cartésien | C | bug | d10 | S | `compiler.py:761` |
| AUD-007 | `detectChanges` ne projette que clés et statut : upsert inutilisable (un test verrouille le défaut) | C | bug | d10, d13 | M | `pipelines/ops`, `core/tests/test_pipeline_runtime.py:2985` |
| AUD-008 | Aperçu de pipeline relancé côté serveur à chaque frame de drag (clé de requête = brouillon entier) | C | bug | d14 | S | `shell/src/pipelines/pipelines.hooks.ts:69` |
| AUD-009 | Aperçu inaccessible sur un nouveau pipeline ; enregistrement bloqué tant que le graphe est invalide | C | bug | d14 | M | `pipelines.hooks.ts`, éditeur de pipeline |
| AUD-010 | Le tenant est toujours « default » (aucune résolution par jeton, portail mono-tenant en dur) | C | parité | d17, d09 | L | `core/app/auth/dependency.py:205`, `public/routes.py` |
| AUD-011 | Supprimer une collection ne supprime jamais sa table PostGIS (fuite de données et de quota) | C | bug | d17 | M | `collections/repository.py:173`, `routes.py:970` |
| AUD-012 | CDC wal2json v1 (une transaction = un message, échec au-delà de ~1 Gio) et slot sans `max_slot_wal_keep_size` (WAL illimité, saturation de `pg-data`) | C | bug | d18, d20 | L | `core/app/cdc/consumer.py:220`, `cdc/main.py:171`, `docker-compose.yml:37-46` |
| AUD-013 | Lecture du lac par `row_number()` sur tout l'historique : 34x plus lent qu'un anti-join (8,23 s contre 0,24 s à 40 M lignes) | C | bug | d18 | M | `core/app/analytics/aggregate.py:571` |
| AUD-014 | Import de fichier tout en mémoire : pic 2,9 Go pour 281 Mo, worker limité à 2 Go | C | bug | d18 | L | `core/app/ingestion/importer.py:216` |
| AUD-015 | Schéma procrastinate appliqué une fois, jamais migré (3.9.0 verrouillé) | C | bug | d19 | M | `core/scripts/ensure_procrastinate_schema.py:26` |
| AUD-016 | Liveness du worker Helm (`get_stalled_jobs(3600)`) : CrashLoop dès qu'un job sain dépasse 1 h | C | bug | d20 | S | `core/scripts/healthcheck_worker_stalled.py:34`, `deploy/helm/geostudio/templates/worker.yaml:41-50`, `export-worker.yaml` |
| AUD-017 | SLO latence Features : regex `http_route` périmée depuis `/v1` (série vide, alerte jamais déclenchée) ; vérifier la règle Martin et les dashboards | C | bug | d21 | S | `deploy/observability/grafana/provisioning/alerting/rules.yaml:17` |
| AUD-018 | Toutes les alertes SLO en `noDataState: OK` (5 règles) : core arrêté = aucune alerte | C | bug | d21 | S | `rules.yaml:29,56,85,112,141` |
| AUD-019 | Aucun mécanisme de langue : `t()` lit un catalogue français unique | C | parité | d27 | L | `shell/src/i18n/` |
| AUD-020 | Écriture OGC Features sur collection stockée en 2154 : GeoJSON lon/lat estampillé 2154 sans `ST_Transform` ; lecture par défaut en Lambert-93 brut | C | bug | d34 | M | `core/app/features/repository.py:263,425,449,490,517,565`, `routes.py:403`, `collection_writer.py:563`, `importer.py:558` |
| AUD-021 | Aucun report d'attributs par jointure spatiale (`spatialJoin`, `intersection`, `countWithin`), ni overlayer ; sans lui, parcelle x zonage PLU impossible | C | parité | d35, d08, d05 | M | `compiler.py:167,222-246`, `analysis.py:~190`, `ops/attrs.py:360` |
| AUD-022 | Gabarits métier = coquilles (collection inexistante, champs vides, ni schéma ni données) | C | différenciateur | d35 | M | gabarits déclaratifs `shell/src/`, `core/app/templates` |

### 3.2 Blocages de parité et défauts Important

| id | titre | sév | tag | dim | effort | fichiers |
|---|---|---|---|---|---|---|
| AUD-023 | Chromium du worker d'export sans garde d'egress (SSRF) | I | sécurité | d04, d15 | M | `core/app/export/jobs.py:159-199` |
| AUD-024 | Jeton d'export = bearer complet, TTL 120 s égal au budget de rendu, passé en URL (fixation de session) | I | sécurité | d04, d15, d16 | M | `auth/export_tokens.py`, `auth/dependency.py:230`, `exportAwareToken.ts` |
| AUD-025 | `defer()` non gardé : run/job orphelin (409 ~60 min) ; jumelles à traiter ensemble | I | bug | d12, d19 | M | `pipelines/service.py:124`, `jobs.py:488`, `export/routes.py:68`, `appexport/routes.py:60`, `raster/routes.py:78`, `terrain3d/routes.py:52`, `tileset3d/routes.py:86`, `dataexport/routes.py:30` |
| AUD-026 | Run vivant > 60 min déclaré périmé et toujours actif, sans heartbeat | I | bug | d12, d19 | M | `pipelines/repository.py:355` |
| AUD-027 | Jobs longs tués à chaque mise à jour ou drain : pas d'arrêt gracieux, pas de PDB ni `preStop` | I | bug | d20 | S | `worker.yaml:28-33`, `core.yaml:7-8`, `docker-compose.yml` (~533) |
| AUD-028 | Worker tué laisse le verrou (compaction/snapshot CDC bloqués) | I | bug | d19 | S | `core/app/cdc/` |
| AUD-029 | Aucun timeout sur les jobs synchrones | I | bug | d19 | M | `core/app/jobs/` |
| AUD-030 | Sous Helm : ni CSP, HSTS, frame-deny, rate-limit ; tâche CSP en `PermissionError` toutes les 5 min | I | parité | d20 | M | `shell/nginx.conf:23-30`, `core/app/security/jobs.py:38-39`, `ingress.yaml` |
| AUD-031 | Dimensionnement en dur incompatible avec la VM par défaut (8 Go/40 Go) ; sauvegarde en triple copie sur le même disque | I | bug | d20 | M | `docker-compose.yml:37-46`, `deploy/backup/backup.sh:32-139`, `deploy/proxmox/terraform/variables.tf:58-67` |
| AUD-032 | Aucune HA ni PITR de la base (slot logique non répliqué en PG16) | I | différenciateur | d20 | L | `docker-compose*.yml`, chart Helm |
| AUD-033 | Pas de mise à jour sans interruption ; Helm sans job de migration pré-upgrade ni garde N-1 | I | parité | d20 | M | `core.yaml:34-50`, `core/alembic/env.py:50-77` |
| AUD-034 | Helm sans sauvegarde/restauration ; scripts liés aux noms d'hôtes compose ; chart non publié, `appVersion` v0.1.0 | I | parité | d20 | M | `deploy/backup/*.sh`, `values.yaml`, `release.yml` |
| AUD-035 | Aucune alerte sur retard CDC ni sur échecs/âge des jobs (jauges existantes ou à créer) | I | parité | d21 | S | `core/app/observability.py:127,175,198` |
| AUD-036 | Logs jamais exportés en OTLP : Loki ne reçoit rien | I | bug | d21 | S | `observability.py:94-107`, `otelcol-config.yaml:81-84` |
| AUD-037 | `export-worker` sans `OTEL_*` en compose | I | bug | d21 | S | `docker-compose.yml:746+` |
| AUD-038 | Données otel-lgtm non persistées (compose et Helm) | I | dette | d21 | S | `docker-compose.yml:858-902`, `otel-lgtm.yaml:15-40` |
| AUD-039 | Alertes d'exploitation sans destinataire par défaut ; aucun runbook d'astreinte | I | parité | d21 | M | `docker-compose.yml:880`, `contactpoints.yaml`, `docs/runbooks/` |
| AUD-040 | Pas d'observabilité par tenant ni par fonctionnalité (pas de `tenant_id` sur spans, pas de `X-Request-ID`) | I | différenciateur | d21 | M | `observability.py:90-113` |
| AUD-041 | Conformance Features Part 3 revendiquée sans `/queryables` ni cql2-json | I | parité | d22 | M | `features/routes.py:106-120` |
| AUD-042 | OGC API Tiles servi mais non déclaré, sans TMS ni metadata | I | parité | d22 | M | `ows/routes.py:263-336`, `features/routes.py:106-146` |
| AUD-043 | STAC item-search : paramètres ignorés en silence, `ids` filtré après pagination | I | bug | d22 | S | `stac/routes.py:302-308,417-422` |
| AUD-044 | `GET /v1/collections` hors profil OGC (pas de `links`, pagination en Python) | I | parité | d22 | M | `collections/routes.py:289-329,546-598` |
| AUD-045 | WMS : seul 1.3.0, pas de GetLegendGraphic | I | parité | d22 | M | `ows/wms_routes.py:250-258` |
| AUD-046 | OpenAPI sans `securitySchemes`, 23/199 opérations taguées, version figée `0.1.0` ; pas de guide d'accueil API | I | différenciateur | d22, dev-tiers | S | `core/app/main.py:184`, `core/openapi.json` |
| AUD-047 | INSPIRE absent (ISO 19139, thèmes, ExtendedCapabilities WFS) | I | différenciateur | d22, d34 | L | `ows/wfs.py:61-140`, `collections/` |
| AUD-048 | Ni OGC API Records ni CSW serveur | I | différenciateur | d22 | L | `core/app/` (nouveau `records/`), `items.search` |
| AUD-049 | Carte : fond sans effet avant rechargement ; fenêtre temporelle ne filtre pas fx/dots/label ; fonds `xyz:` sans `glyphs` ; clic couche `feature` ignore `pkColumn` | I | bug | d01 | M | `MapView.tsx:321`, `mapApplyLayers.ts:337,570`, `basemaps.ts` |
| AUD-050 | Popups : valeurs injectées en markdown, HTML actif non-script conservé (formulaire de hameçonnage, pixel de pistage) | I | sécurité | d01, auditeur | S | `popupTemplate.ts:79`, `sanitizeMarkdown.ts` |
| AUD-051 | Ni filtre par couche ni plage d'échelle | I | parité | d01 | M | `MapView`, `MapConfig` |
| AUD-052 | Popup sans contexte CEL réel ni contenu riche | I | différenciateur | d01 | M | `popupTemplate.ts` |
| AUD-053 | Tilesets 3D illisibles pour un invité (`X-Share-Link-Token` non transmis) ; jeton OIDC figé dans `Tile3DLayer` | I | bug | d02 | S | `mapDeckTerrain.ts:45` |
| AUD-054 | Proxy tileset3d rouvre le zip à chaque tuile ; validation du zip insuffisante (2 Gio en RAM) | I | bug | d02 | M | `tileset3d/routes.py:240` |
| AUD-055 | Troncature silencieuse à 5000 entités par PK entre z8 et z14 | I | parité | d03 | M | `features/tiles.py:439` |
| AUD-056 | Tuiles sans quota ni cache serveur (y compris anonymes) ; proxy TiTiler garde la session DB pendant l'appel HTTP | I | dette | d03 | M | `ratelimit/limiter.py:136`, `raster/routes.py:224`, `terrain3d/routes.py` |
| AUD-057 | Atlas tronqué à 100 fiches, sans cartes (pas de map series), mise en page non composable | I | parité | d04 | M | `export/`, `PrintLayoutPanel` |
| AUD-058 | ReportSchedule mono-format sans retry ; 96 dpi fixe | I | parité | d04 | M | `export/`, `reports/` |
| AUD-059 | Pivot : totaux non additifs ; comparaison de périodes qui chevauche et perd les filtres ; cross-filter à entrée unique ; widget Période non resynchronisé | I | bug | d05 | M | `shell/src/widgets/`, `analytics/` |
| AUD-060 | Bookmark perd la géométrie spatiale | I | bug | d05 | S | `core/app/bookmarks/schemas.py:288` |
| AUD-061 | Retard du lac (`asOf`/`pending`) jamais montré à l'utilisateur | I | parité | d05 | S | `analytics/aggregate.py`, widgets |
| AUD-062 | SQL Lab : pas de requêtes sauvegardées côté serveur, matérialisation complète | I | parité | d05 | M | `analytics/sql_sandbox.py:94` |
| AUD-063 | Modèle sémantique pauvre (pas de top-N, mesure calculée, opérateurs), pas de cache de résultats | I | différenciateur | d05 | L | `analytics/`, `DatasetPayload` |
| AUD-064 | Widget Bouton : `window.open(href)` sans validation de schéma | I | sécurité | d06 | S | `shell/src/widgets/index.tsx:190` |
| AUD-065 | Exports statique/autoporté ignorent les filtres de DataSource ; mini-serveur sans parité avec l'API du cœur | I | parité | d06, d32 | M | `appexport/`, mini-serveur miroir |
| AUD-066 | Embed : portée invité incomplète (couches additionnelles), liens limités à 30 jours, sans restriction d'origine ni `frame-ancestors` | I | sécurité | d06 | M | `core/app/embed/guest_access.py` |
| AUD-067 | Pas de cycle brouillon/publié d'app ; variables non pilotables par URL ou `postMessage` | I | parité | d06 | M | `configs/`, `AppRenderer` |
| AUD-068 | Validation CEL partielle ; CEL sans cache (reparse) | I | dette | d06 | S | `core/app/cel/` |
| AUD-069 | Collecte : photo perdue en silence ; PUT S3 présigné rejeté (403) quand `file.type` est vide (cas par défaut Chromium/Linux, import `.gpkg` bloqué) | I | bug | d07, analyste | S | `form.tsx`, `ImportFileButton`, signature présignée |
| AUD-070 | XLSForm : libellés de choix perdus, repeat/calculate/choice_filter/default non portés, `required` non appliqué côté serveur | I | parité | d07 | M | `core/app/xlsform/parser.py:266` |
| AUD-071 | Collecte limitée aux points lon/lat ; audio/vidéo ; aucun écran citoyen pour la soumission publique | I | parité | d07 | L | `form.tsx`, `public_submit/` |
| AUD-072 | Job de géocodage en boucle (`get_geocoder()` hors du try) ; « succeeded » avec 100 % d'erreurs ; hors rate-limit et purge RGPD | I | bug | d08 | S | `geocoding/jobs.py:154`, `ratelimit/limiter.py:63` |
| AUD-073 | Géocodage sans privilège ni audit ; BAN : score, type, INSEE, code postal jetés, tout résultat « trouvé » | I | parité | d08, d34 | S | `geocoding/`, `geocoder BAN` |
| AUD-074 | Widget Analyse : résultat jamais visible ; catalogue de 11 outils ; zonalStats (centre de pixel, petites zones à 0) ; routage sous-exposé | I | parité | d08 | M | `pipelines/analysis.py`, widget Analyse |
| AUD-075 | Items `map` et `dataset` publiés mènent à « introuvable » : une carte publiée n'est visible par personne hors authentification | I | bug | d09, analyste | M | `shell/src/.../PublicItemPage.tsx`, `core/app/items/repository.py:627` |
| AUD-076 | Publication sans vérifier que les données référencées sont publiques ; fiche dataset pauvre ; catalogue public sans recherche/facettes ; Googlebot détourné vers un stub sans JSON-LD ; pas de lien profond par chapitre | I | parité | d09 | M | `docker-compose.yml:501`, `public/` |
| AUD-077 | ETL : `GROUP BY ALL` fusionne les lignes identiques ; `join` duplique géométrie et colonnes ; lignes à géométrie NULL écartées silencieusement ; `reproject` perd l'autorité du CRS | I | bug | d10 | M | `compiler.py`, `ops/` |
| AUD-078 | ETL : ops `execute.py` sans plafond ; TEMP VIEW recomptée ; `neighborFinder` en O(n²) | I | dette | d10 | M | `ops/execute.py`, `ops/reliquats.py` |
| AUD-079 | Pas de validateur/réparation de géométrie, de mesures géodésiques ni de déduplication | I | parité | d10, d13 | M | `pipelines/ops/` |
| AUD-080 | Qualité : clé NULL mal classée, `validateAttributes` pauvre, collision de colonnes de sortie, pas de seuil de qualité, quarantaine sans géométrie | I | parité | d13 | M | `ops/`, writer collection |
| AUD-081 | Lecteurs SQL externes sans read-only, garde SELECT purement syntaxique ; filtre Mongo sans types BSON | I | sécurité | d11 | M | `pipelines/connector_runtime.py:300` |
| AUD-082 | `reader.arcgisonline` et `reader.wfs` tronquent en silence (sans pagination) ; pas de détection de colonne géométrie dans les lecteurs SQL | I | bug | d11, d34 | M | `ops/readers*.py` |
| AUD-083 | Annulation inopérante hors writers collection/dataset ; retry refusé aux writers `append` | I | bug | d12 | M | `pipelines/jobs.py` |
| AUD-084 | Planification sans fuseau ni circuit-breaker, propriétaire anonymisé en boucle ; webhook entrant perdu en 409 sans idempotence ; déclencheur S3 sans clé ni etag | I | bug | d12 | M | `pipelines/scheduler`, `webhooks` |
| AUD-085 | Webhooks sortants désactivés après 5 échecs, événements détruits | I | bug | d12, d19 | S | `webhooks/` |
| AUD-086 | Lineage au niveau item seulement et sans surface dans le shell | I | parité | d12, data-engineer | M | `lineage/`, shell |
| AUD-087 | Éditeur de pipeline : drop palette en coordonnées écran, nœud inséré en (0,0), champ numérique vidé = 0, undo désynchronise les champs, connexion refusée en silence, erreur d'aperçu jetée, Exécuter lance la version enregistrée, pas de nœud fautif indiqué | I | bug | d14 | M | `shell/src/pipelines/` |
| AUD-088 | Pipeline : titre perdu à la création, pas de création de collection cible, échecs de schéma à l'écriture non détectés en amont, erreur SQL 500 sur `derive` | I | bug | data-engineer | M | `PipelineBuilder`, `pipelines/routes.py` |
| AUD-089 | CSP dynamique cassée par un hôte malformé ; CSP élargie par n'importe quel Créateur sans `frame-ancestors`/`base-uri`/`form-action` | I | sécurité | d15 | M | `security/csp_hosts.py:23`, `traefik_render.py` |
| AUD-090 | Multipart public sans plafond avant le rate-limit ; upload présigné sans plafond | I | sécurité | d15 | S | `public_submit/routes.py:62` |
| AUD-091 | Clés d'API et jetons MCP sans portée ; clé de service inutilisable avec le MCP | I | sécurité | d15, d16, dev-tiers | M | `apikeys/`, `mcp/` |
| AUD-092 | `audit_log` pauvre, mutable, sans rétention, supprimé avec le tenant ; PII résiduelle après anonymisation | I | sécurité | d15, d16, d17, d30 | M | `audit/`, `compliance/` |
| AUD-093 | Pièces jointes non masquables (GAP-22) | I | sécurité | d16 | S | `attachments/routes.py:281` |
| AUD-094 | Identité zombie après anonymisation (jetons webhook, partages, planifications) ; effacement de compte sans garde-fou (un appel, irréversible, y compris par clé d'API) | I | sécurité | d16, d30, auditeur | M | `compliance/service.py:63`, `jobs/common.py:48`, `auth/dependency.py:212` |
| AUD-095 | STAC/DCAT/WFS sans quota ni timeout (`ST_Extent` anonyme) | I | sécurité | d16 | S | `stac/routes.py:128` |
| AUD-096 | Le MCP n'applique jamais la synchro de groupes OIDC | I | sécurité | d16 | S | `mcp/tools/identity.py:64` |
| AUD-097 | Pas de RLS par attribut ni de vues filtrées ; partage limité aux groupes, sans expiration ni cible tenant/user/rôle | I | différenciateur | d16 | L | `sharing/`, `features/rls` |
| AUD-098 | Quotas instance-wide éteints par défaut et aveugles aux lignes PostGIS ; pas d'isolation de charge ; défense en profondeur absente sur tables du cœur | I | dette | d17 | L | `quotas/`, `configs/repository.py` |
| AUD-099 | Tuiles agrégées seulement à z <= 7 sans cache ; `/aggregate` sans cache ni limite de concurrence ; backfill CDC en mémoire ; aperçu pipeline matérialise toute la collection ; pas d'index d'attribut ni de `statement_timeout` sur GET /items | I | dette | d18 | M | `features/tiles.py`, `analytics/aggregate.py`, `cdc/backfill.py` |
| AUD-100 | Erreurs internes d'ingestion renvoyées brutes (SQL, schéma) à l'utilisateur | I | sécurité | auditeur, analyste | S | `ingestion/jobs.py`, `ImportFileButton` |
| AUD-101 | Budget de rate-limit par IP contournable via `X-Forwarded-For` quand le cœur est joignable directement | I | sécurité | auditeur | S | `ratelimit/limiter.py` |
| AUD-102 | Copilote : la confirmation d'écriture valide un nom d'outil, pas les arguments | I | sécurité | d23 | M | `core/app/copilot/`, shell copilote |
| AUD-103 | Audit copilote lacunaire : arguments non tracés, origine absente des audits métier, crash audité « ok » | I | sécurité | d23 | S | `copilot/`, `audit/` |
| AUD-104 | Aucune évaluation de qualité du copilote ni des générateurs ; `generate_sql_query` ne valide rien | I | différenciateur | d23 | M | `copilot/`, `mcp/tools/` |
| AUD-105 | MCP sans annotations, prompts ni resources ; parité REST/MCP partielle (~41 outils) | I | différenciateur | d23 | M | `core/app/mcp/` |
| AUD-106 | Contexte copilote plafonné à 64000 caractères ; aucun suivi de consommation LLM ni plafond tenant/utilisateur | I | dette | d23 | M | `copilot/context.py` |
| AUD-107 | Widgets d'extension non rendus sur pages publiques, embed et sites (« Widget inconnu ») | I | bug | d24 | S | `WidgetHost`, `PublicItemPage` |
| AUD-108 | `permissions.collections` contournable via la prop `dataSourceId` | I | sécurité | d24 | S | `WidgetHost` |
| AUD-109 | CSP enforcing bloque `connect-src`/`img-src` vers l'origine de l'extension ; aucune intégrité du code tiers (SRI, pinning, signature) | I | sécurité | d24 | M | `security/csp_hosts.py`, `extensions/` |
| AUD-110 | Contrat DOM du SDK minimal et sans version ; UI d'administration d'extensions limitée à un squelette | I | différenciateur | d24 | M | SDK widgets, `ExtensionsAdminPage` |
| AUD-111 | Image export-worker sans lockfile (hors pip-audit) ; aucun contrôle automatique des licences GPL/AGPL/LGPL | I | dette | d25 | M | `deploy/export-worker/`, CI |
| AUD-112 | Dependabot/audits ignorent sidecar Rust, images compose, Helm ; scans d'image informatifs seulement, absents du canal edge ; images de base sans digest ; `mc` sans vérification ; repli `:-latest` en compose de production | I | sécurité | d25 | M | `.github/`, `docker-compose.prod.yml`, `deploy/*/Dockerfile` |
| AUD-113 | Aucune vérification de signature ou d'attestation côté consommateur (cosign) | I | différenciateur | d25 | M | `release.yml`, `install.sh` |
| AUD-114 | Accessibilité : graphiques ECharts sans alternative ; sélection d'entités de la carte impossible au clavier | I | parité | d26 | M | widget graphique, `MapView` |
| AUD-115 | i18n : formats et fuseau codés en dur (fr-FR, Europe/Paris), buckets temporels UTC vs affichage Paris (jours décalés), RTL, traductions XLSForm ignorées, cœur (erreurs, copilote, e-mails, DCAT) en français seul, claim `locale` non consommé | I | parité | d27 | L | `shell/src/`, `core/app/` |
| AUD-116 | Contenu utilisateur non traduisible (apps, cartes, portails) | I | différenciateur | d27 | L | `AppConfig`, `MapConfig` |
| AUD-117 | Performance perçue : `MapView` embarque deck.gl/loaders 3D même en 2D ; pas de préchargement ; spinner à chaque frappe du catalogue ; widgets repassent en chargement à chaque filtre ; tableau trié côté client sur 100 lignes | I | polish | d28 | M | `shell/src/map/`, catalogue, widgets |
| AUD-118 | README périmé et contredit par le code ; aucune documentation utilisateur ni administrateur ; MCP non documenté ; seed de démo sans carte, app, dashboard ni pipeline | I | parité | d29 | M | `README.md`, `docs/`, seed |
| AUD-119 | Palette ⌘K sans « aucun résultat » ; pas d'aide CEL ; pas de parcours de première utilisation | I | polish | d29 | S | `CommandPalette`, aide contextuelle |
| AUD-120 | Aucun droit d'accès / portabilité (RGPD Art. 15/20) | I | parité | d30 | M | `compliance/` |
| AUD-121 | Effacements non rejoués après restauration ; `purge_tenant` : reçu « done » malgré nettoyage S3 raté, lac CDC non balayé | I | sécurité | d30 | M | `compliance/`, `deploy/backup/restore.sh` |
| AUD-122 | Souveraineté : fonds de carte tiers codés en dur, pas de fonds IGN préconfigurés, pas de mode « zéro sortie » | I | différenciateur | d30, d01, france | M | `basemaps.ts`, `tokens` cartes |
| AUD-123 | Tests : budgets de rate-limit analytics/jobs/llm/webhook non verrouillés (mutant survivant) ; `cdc/main.run()` 65 lignes sur 110 non couvertes | I | dette | d31 | S | `ratelimit/limiter.py`, `cdc/main.py` |
| AUD-124 | Garde d'egress SSRF copiée 6 à 9 fois avec parité testée partiellement | I | dette | d32, d31, d15 | M | `core/app/net_pin.py` et 6 copies |
| AUD-125 | Contrat de couches troué (53 exemptions, `app.jobs`/`app.ratelimit` hors contrat, cycle items<->jobs) ; mypy --strict sur 7 chemins seulement | I | dette | d32 | M | `core/.importlinter`, `pyproject.toml` |
| AUD-126 | UI : polices d'identité empaquetées jamais appliquées ; tokens `--gs-map-*` sans consommateur ; thème d'app à 6 couleurs ; 127 contrôles réécrits hors kit | I | polish | d33 | M | `shell/src/styles/`, `ui/kit` |
| AUD-127 | NTF/Lambert zones sans grille IGN (repli silencieux ~2 m) ; pas d'intégration native Cadastre/INSEE/BD TOPO/COG ni CRS DOM | I | parité | d34 | L | `ogc_crs.py`, connecteurs |
| AUD-128 | Connecteur « CKAN / data.gouv » inopérant sur data.gouv.fr (API `/api/1/datasets/` udata requise) | I | parité | d34, france | S | `harvest/connectors/ckan.py` |
| AUD-129 | Import : la première géométrie invalide rejette tout le fichier | I | bug | d35 | S | `ingestion/importer.py` |
| AUD-130 | Alertes : un scalaire par règle, plancher 5 min, 2 canaux, rien de spatial ni par entité ; alerte partagée à un groupe non notifiée au groupe | I | parité | d35, decideur | M | `alerts/` |
| AUD-131 | Pas de temps réel (Q10) | I | parité | d35, d05, concurrents | L | cœur + shell |
| AUD-132 | Démarrage rapide inutilisable (README `:8300/:8200` bloqué par CORS) ; realm de production avec comptes de démo actifs et flux mot de passe sur client public ; quota non numérique = 500 ; aucune procédure de montée de version ; runbook de rotation oublie `worker` ; version affichée figée | I | bug | admin-systeme | M | `README.md`, `deploy/keycloak/realm*.json`, `install.sh`, `docs/runbooks/` |
| AUD-133 | Export PDF/PNG échoue sur la configuration locale par défaut (message technique, filtres non transmis) | I | bug | analyste, decideur | S | `export/`, `.env.example` |
| AUD-134 | Parcours décideur : partager l'app exige trois partages séparés avec erreurs opaques ; filtre d'emprise ne touche que le graphique ; lisibilité et cibles tactiles mobiles ; runtime sans en-tête ni retour | I | parité | decideur | M | partage, `AppRuntimePage` |
| AUD-135 | Dev tiers : Swagger `/docs` inutilisable derrière Traefik/CSP ; OAuth MCP renvoie `localhost:8200` (`CORE_BASE_URL` absent de `.env.example`) ; défaut CORS présenté comme « lien expiré » ; guide d'extension périmé | I | bug | dev-tiers | M | Traefik, `mcp/oauth`, `.env.example`, doc SDK |
| AUD-136 | Stack locale servie par des images en retard sur `HEAD` (aucun contrôle de fraîcheur) | I | dette | analyste, dev-tiers | S | `docker-compose.yml`, runbooks |

### 3.3 Minor, dette, polish, paris de fond

| id | titre | sév | tag | dim | effort | fichiers |
|---|---|---|---|---|---|---|
| AUD-137 | 3 échecs E2E flaky (toast + région live dupliqués, analytics-context, touch-map tablet) | M | dette | baseline | S | `e2e/ingestion-cancel.spec.ts:6`, `analytics-context.spec.ts`, `touch-map.spec.ts:89` |
| AUD-138 | Bundle initial à 23,7 Ko du seuil ; `MapView` 1180 kB ; filet de taille fragile | M | dette | baseline, d28 | M | `shell/.bundle-size-threshold`, `vite.config` |
| AUD-139 | Pièges d'environnement de test non documentés (`DATABASE_URL`, `--basetemp`, `gis_test` périmée, helm absent) | M | dette | baseline | S | `CLAUDE.md` (hors périmètre ici), runbook de test |
| AUD-140 | DCAT-AP incomplet (keyword, theme, conformsTo, distributions par format) ; WFS 2.0 minimal (pas de FES, `featureID`, Transaction) ; STAC annonce `oas30` | M | parité | d22 (nv) | M | `dcat/serializers.py:99-160`, `ows/routes.py:151-220`, `stac/serializers.py:17` |
| AUD-141 | Pas de sauvegarde/restauration par tenant ou par item ; clé age vide = échec silencieux ; rotation offsite avant envoi réussi | M | différenciateur | d20 (nv) | M | `deploy/backup/` |
| AUD-142 | Raster : rendu minimal (3 paramètres, PNG, pas d'identify) ; ingestion limitée aux GeoTIFF hébergés | M | parité | d03 | L | `raster/` |
| AUD-143 | FeatureServer/MapServer servis ; formats 3D/BIM/LAS/COPC/IFC/glTF/DWG ; PMTiles/MBTiles/FlatGeobuf ; écriture élargie | M | parité | concurrents | L | `ows/`, `ingestion/`, `dataexport/` |
| AUD-144 | Custom transformers, PythonCaller, boucles de pipeline | M | parité | concurrents | L | `pipelines/` |
| AUD-145 | Notebooks, GeoAnalytics/Spark | M | parité | concurrents | L | hors périmètre actuel |
| AUD-146 | RGAA démontrable (audit tiers), RGS, SecNumCloud, FranceConnect/ProConnect | M | parité | d26, france | L | docs, `auth/` |
| AUD-147 | Collaboration (commentaires de carte), export vidéo/GIF, focus mode, iframe widget | M | différenciateur | concurrents | L | shell |
| AUD-148 | Catalogue de connecteurs SaaS (Airbyte), backfill, orchestration par assets, lac transactionnel (DuckLake/Iceberg) | M | parité | data-bi | L | `pipelines/`, `cdc/` |
| AUD-149 | Un seul fournisseur LLM natif ; pas de BYO-model par tenant | M | parité | tendances-ia | M | `copilot/llm/` |
| AUD-150 | Mineurs d01 à d35 non listés ci-dessus (ex. `__agg` sans interaction, export de style lossy, `timePlayer` en fin de plage, paramètres terrain non bornés, atlas D04-10/11, rapport qualité limité au writer, boutons d'upload dupliqués, grammaire de filtre dupliquée, code mort QGIS, 170 types TS manuels, Keycloak 24.0.5 sans plan de montée, extension DuckDB `h3` non épinglée) : à traiter au fil des lots | M | polish | multi | M | voir dimensions |

Compte : 22 Critical, 114 Important, 14 Minor (lignes AUD-001 à AUD-150, plusieurs constats sources fusionnés par ligne).

### Doublons fusionnés

Buffer 3857 (d08-1 = d10-C1 = d34-C1) ; `detectChanges` (d10-I7 = d13-01) ; Chromium d'export (d04-04 = d15-1) ; jeton d'export (d04-03 = d04-05 = d15-5 = d16-8) ; clés d'API (d15-6 = d16-3 = dev-tiers F5/F6) ; audit (d15-7 = d16-10 = d17-I3 = d30-2/8) ; `defer` perdu (d12-2 = d19-I4 = d19-I5) ; run périmé (d12-3 = d19-I3) ; webhooks sortants (d12-M4 = d19-I6) ; WAL CDC (d18-C1 = d20-2 = d21-I1) ; validation de géométrie (d10-I8 = d13-03) ; fonds français (d01-M3 = d30-6 = france) ; offline (d07-C1 = d35-I4 = Q11) ; tenant (d09-7 = d17-C1) ; export PDF local (analyste F10 = decideur F4 = d04) ; carte publique (d09-1 = analyste F6) ; PUT S3 (d07-I2 = analyste F4) ; KPI plafonné (d05-1 = decideur F2) ; erreur SQL d'ingestion (auditeur F2 = analyste F5).

## 4. Regroupement proposé en lots exécutables

Chaque lot = un SP au sens du dépôt (spec, plan, TDD, revue par tâche + revue finale, E2E). Règle transverse (piège n°14) : pour chaque correctif, lister les jumelles avant de clore.

| Lot | Contenu | Dépend de | Effort | Pourquoi à cet endroit |
|---|---|---|---|---|
| L0 « Chiffres justes » | AUD-005, 006, 007, 020, 002, 001, 003, 133, 069, 075, 129 | rien | M | Les résultats faux sans alerte sont le plus coûteux en confiance ; tout est petit ou moyen et indépendant |
| L1 « Socle d'exécution » | AUD-015, 025, 026, 027, 028, 029, 016, 012, 013, 014, 083, 085 | rien (L1a : 015 + 025 + 026 + 027 ; L1b : 012, 013, 014 en gros chantiers) | L | Fiabilité des jobs et du CDC ; AUD-015 avant toute montée de procrastinate ; jumelles de AUD-025 dans le même geste |
| L2 « Sécurité sortante et jetons » | AUD-023, 024, 050, 064, 066, 081, 089, 090, 091, 094, 096, 100, 101, 108, 109, 124 | AUD-124 (garde unique) avant AUD-023 | L | Fermeture des surfaces d'attaque ; AUD-124 factorise d'abord, les autres consomment |
| L3 « Observabilité et exploitation » | AUD-017, 018, 035, 036, 037, 038, 039, 040, 027 (partagé), 030, 031, 033, 034, 132, 135, 136 | L1a pour AUD-035 (jauges) | M-L | Les SLO doivent être justes avant toute campagne de fiabilité mesurable |
| L4 « Multi-tenant et gouvernance » | AUD-010, 011, 092, 093, 095, 097, 098, 120, 121 | décision D4 (multi-tenant réel) ; L2 (audit/jetons) | L | Tenant réel impose quotas, audit immuable, isolation de charge |
| L5 « ETL correct et éditeur » | AUD-008, 009, 087, 088, 077, 078, 079, 080, 082, 084, 086, 021, 022, 130 | L0 (AUD-005/006/007) | L | Le différenciateur ETL ne tient que si les ops sont justes ; AUD-021 débloque les cas d'usage vertical |
| L6 « Standards et ouverture API » | AUD-041, 042, 043, 044, 045, 046, 128, 140, 047, 048, 127, 122 | AUD-020 | L | OGC/INSPIRE/Records ; AUD-128 (S) en premier car bloquant sur data.gouv |
| L7 « Carte, 3D, tuiles, impression » | AUD-049, 051, 052, 053, 054, 055, 056, 057, 058, 059, 060, 061, 099 | L0 | L | Corrections de rendu puis capacités |
| L8 « Collecte terrain » | AUD-070, 071, 004 (offline) | décision D6 (offline) | L | Offline est un chantier à part entière : spec dédiée avant exécution |
| L9 « IA gouvernée » | AUD-102, 103, 104, 105, 106, 149 | L2 pour les scopes (AUD-091) | M-L | Consolide le pari n°1 |
| L10 « SDK et extensions » | AUD-107, 108, 109, 110 | décision D5 (ouverture SDK) | M | Ne pas ouvrir avant d'avoir réparé le rendu public et la frontière de permissions |
| L11 « i18n et accessibilité » | AUD-019, 115, 116, 114, 119, 126 | décision D8 (langues) | L | Mécanisme de langue d'abord, catalogue ensuite |
| L12 « Docs, onboarding, supply chain » | AUD-118, 111, 112, 113, 123, 125, 137, 138, 139, 150 | rien | M | Peu risqué, parallélisable avec n'importe quel lot |
| L13 « Parité long terme » | AUD-063, 062, 131, 143, 144, 145, 146, 147, 148, 142, 032 | décisions D2, D3, D7 | L (plusieurs SP) | Chantiers stratégiques, arbitrés plus bas |

Ordre recommandé : L0 -> (L1a, L3 en parallèle) -> L2 -> L5 -> L1b -> L6 -> L7 -> L4 -> L9 -> L8 -> L10 -> L11 -> L13, avec L12 au fil de l'eau. Justification : L0 et L1a retirent les défauts de confiance et de fiabilité, L3 rend la suite mesurable, L2 sécurise avant d'ouvrir (SDK, embed, API), L5 et L6 soutiennent les deux paris les plus rentables.

Contraintes d'exécution observées dans le dépôt : régénérer OpenAPI + types TS à chaque route modifiée ; inventorier toute surface nouvelle (`inventaire-fonctionnalites.jsonl`) ; migrations Alembic testées sur base non vide ; jamais de commit direct sur `main`.

## 5. Décisions pour Tanguy

| # | Décision | Contexte mesuré | Recommandation |
|---|---|---|---|
| D1 | Positionnement : SIG complet ou plateforme de données géospatiales horizontale | Q2 répondue « horizontal, parité de connecteurs face à FME » ; scores 52-68 % partout, aucun domaine > 75 % | Maintenir « horizontal », mais fixer 3 verticales de référence (collectivités/urbanisme, environnement, crise) pour ordonner le backlog ; ne pas courir après Field Maps ni GeoAnalytics |
| D2 | Modèle économique / pricing | Apache-2.0, aucune offre commerciale | Rester Apache-2.0 ; monétiser par support, hébergement et extensions certifiées (open-core sans casser le cœur) ; pas de fonction cœur payante |
| D3 | Offre SaaS / hébergée (équivalent FME Flow Hosted) | AUD-010 : tenant unique de fait ; AUD-032 : pas de HA/PITR | Ne pas lancer de SaaS multi-tenant avant L4 (tenant réel, quotas, isolation, audit immuable) ; viser d'abord l'hébergement dédié par client (une instance) sur Helm |
| D4 | Multi-tenant réel | AUD-010 et AUD-011 critiques | Trancher « instance dédiée d'abord » ; le multi-tenant réel devient un SP ultérieur ; corriger AUD-011 sans attendre |
| D5 | Ouverture du SDK (Web Components) aux tiers | AUD-107/108/109/110 : rendu public cassé, frontière contournable, pas d'intégrité | Reporter l'ouverture publique tant que L10 n'est pas fait ; publier en « préversion » avec contrat DOM versionné |
| D6 | Hors-ligne (Q11) | AUD-004 critique, Field Maps à 12 % | Faire un SP « collecte hors-ligne » restreint (formulaires + file de sync + photos, pas de cartes hors-ligne vectorielles complètes) ; sinon retirer la promesse de collecte terrain du positionnement |
| D7 | Temps réel (Q10) | AUD-131, Velocity 75 % de parité mais sans flux | Ne pas bâtir un moteur de streaming ; offrir un rafraîchissement planifié par widget + webhooks entrants + SSE sur alertes ; réévaluer sur demande client |
| D8 | Langues | français seul, mécanisme absent (AUD-019) | Mettre en place le mécanisme et l'anglais (marché OSS, doc) ; autres langues par contribution ; contenu utilisateur traduisible en second temps |
| D9 | Marque | nom GeoStudio fixé ; nom d'images `geostudio-*` | Vérifier la disponibilité de marque (INPI/EUIPO, classes 9 et 42) avant toute communication large ; conserver le nom en attendant |
| D10 | FeatureServer / compatibilité ArcGIS | écart n°4 | Ne pas imiter l'API propriétaire ; investir dans OGC (L6) et fournir un connecteur de lecture ArcGIS (déjà moissonné) |
| D11 | INSPIRE / CSW / Records | AUD-047/048 | Prioriser OGC API Records + export ISO 19139 pour les collectivités françaises ; CSW seulement si un client le demande |
| D12 | RGAA / RGS / SecNumCloud | AUD-114, 146 | RGAA : commander un audit tiers (avantage de vente public) ; RGS et SecNumCloud : hors portée du logiciel, à laisser à l'hébergeur |

## 6. Les 5 paris différenciants les plus rentables

1. **Plateforme IA-native gouvernée.** Tout objet est un document déclaratif, le MCP et le copilote passent par `can()` et sont audités : aucun concurrent n'a cela. Coût : L9 (confirmation d'arguments, audit complet, évaluation, scopes, suivi de consommation). Rentabilité : très forte, l'avance existe déjà et se périme vite.
2. **Chaîne intégrée données -> carte -> app -> portail, auto-hébergée et exportable.** Export autoporté, portails, STAC/DCAT-AP, Helm : peu de produits OSS couvrent tout. Coût : L0 (exports corrects), AUD-075 (carte publique), L7. Rentabilité : forte pour collectivités et bureaux d'études.
3. **Sécurité de données unifiée.** RLS, masquage de colonne, limites géographiques déjà sur toutes les surfaces ; ajouter RLS par attribut, vues filtrées, partage à échéance et audit immuable (AUD-097, 092, 094). Coût : M-L. Rentabilité : forte, argument décisif en secteur public.
4. **ETL no-code avec qualité, quarantaine et lineage.** Quarantaine `__rejected` et lineage existent ; ajouter validateur de géométrie, seuils de qualité, `detectChanges` utilisable, jointure spatiale à attributs, surface de lineage (AUD-079, 080, 007, 021, 086). Coût : L5. Rentabilité : forte face à FME sur le prix et l'ouverture.
5. **Souveraineté et données ouvertes françaises prêtes à l'emploi.** BAN déjà intégré ; corriger tampon et Lambert-93 (AUD-005, 020), connecteur udata (AUD-128), fonds IGN, INSEE/Cadastre/BD TOPO natifs, Records/INSPIRE, RGAA audité (AUD-122, 127, 047, 048, 146). Coût : M-L répartis. Rentabilité : forte et peu disputée par les acteurs internationaux ; la collecte hors-ligne (AUD-004) est le second candidat si D6 est tranché favorablement.

Limite de l'audit : plusieurs constats Minor sont marqués non vérifiés dans leur dimension d'origine ; les parcours n'ont pas rejoué la restauration destructive ni le build complet des images.

## 7. Errata et extension (passe de complément du 2026-10-16)

Le détail est dans [`complement/ADDENDUM.md`](complement/ADDENDUM.md) ; en cas de contradiction, l'addendum prime.

- **Nouveaux constats AUD-151 à AUD-192** (42 confirmés par double vérification) : à rattacher au lot L2 (sécurité) pour AUD-151 à AUD-157, au lot L7 pour le sidecar desktop (AUD-158 à AUD-161), le reste selon l'addendum §2.
- **AUD-151 (Critical : terrain3d copie puis supprime le DEM d'un tiers) passe en tête de L0**, avant tout autre lot : correctif petit, jumelle raster déjà durcie.
- **AUD-152** : injection de formule CSV via `writer.ftp` (`cloudfiles.py:859`), absente de cette synthèse. Les autres écritures CSV/XLSX sont neutralisées.
- **Corrections 2 à 14 de l'addendum §3** (libellés AUD-041/029/037/039/025/027/031/184/033, statut CI 7/12, restore-drill premier cron le 2026-10-19, lignes périmées, CLAUDE.md non-root) : à appliquer avant de lotir ces AUD.
- **Échantillon de 10 AUD revérifiés : 10/10 confirmés**, avec des réserves de détail sur 7.

## 8. Décisions tranchées (Tanguy, 2026-10-17)

D1 à D12 : **toutes tranchées conformément à la recommandation du §5** (horizontal + 3 verticales ; Apache-2.0 + services ; instance dédiée par client, pas de SaaS multi-tenant avant L4 ; SDK ouvert en préversion après L10 ; offline = SP restreint formulaires/sync/photos ; temps réel = rafraîchissement + SSE alertes ; i18n mécanisme + anglais ; vérification INPI/EUIPO avant communication ; OGC sans imiter FeatureServer ; OGC Records + ISO 19139 ; audit RGAA tiers, RGS/SecNumCloud à l'hébergeur).

Décisions de lot :
- **AUD-002** (avg/min/max sur source `features` échantillonnée) : **basculer sur la source `statistics`** (agrégat serveur exact), contre la recommandation (« — » non calculable). À traiter dans un SP dédié ; en attendant, le repli sur le total reste un défaut connu.
- **Lot suivant** : L1a + L3 en parallèle, puis L2, L5, L1b, L6, L7.
- **Rejeu réel de l'export** (AUD-133/001/003) : avant la fusion de la PR #185.

## Avancement (2026-10-17)

Lots exécutés et fusionnés dans `dev` : L1a, L3, L5, L2, L1b, L6. Détail des AUD fermés/partiels : `docs/superpowers/2026-08-27-historique-execution-continu.md` (section « Lots L1a/L3/L5/L2/L1b/L6 »). Restent : L4, L7, L8, L9, L10, L11, L12, L13.
