# Historique d'exécution SP-0 → SP-26 (+ release v0.1.0)

**Ce fichier est l'archive détaillée de la section « Feuille de route » de
`CLAUDE.md`**, extraite le 2026-08-27 parce qu'elle représentait ~2350 des
2480 lignes du fichier chargé à chaque session. Le contenu ci-dessous est
**repris verbatim**, sans réécriture ni tri : chaque SP livré, ce que la revue
finale de branche y a trouvé, les décisions de scope actées avec Tanguy, les
déviations assumées vis-à-vis du texte des plans, et la liste complète des
suivis non bloquants ouverts.

`CLAUDE.md` garde la version courte (une ligne par SP, jalons, et les suivis
ouverts qui changent le comportement d'une session). **Venir lire ce fichier
quand** : on reprend un chantier ouvert, on croise un bug qui « ressemble à un
truc déjà vu », on veut savoir pourquoi une décision a été prise, ou on cherche
la classe de défaut récurrente d'une surface donnée.

Les entrées de cette archive ne sont pas figées : un nouveau SP livré vient
s'ajouter ici (détail) **et** en une ligne dans `CLAUDE.md`.

---

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
  dans `DatasetEditPage`.
- **SP-14o** — Requête visuelle (dernière pièce de SP-14, **jalon M11
  atteint**) : assistant no-code Filtrer→Joindre→Résumer sur une collection ;
  provisionne une collection de sortie dédiée (`create_empty_collection`,
  précédent SP-6a réutilisé, route non-admin) + un item dataset + un
  `Pipeline` SP-15 contraint (`writer.dataset`) compilé et exécuté par
  l'assistant lui-même (aucune route bespoke, `/configs` générique) ;
  réouverture (« Modifier la requête ») avec vraie mise à jour en place
  (`savePipelineConfig` réutilisant les objets existants, pas de recréation).
  **SP-14 fonctionnellement complet.** Deux revues finales de branche (10
  commits de correction) : 1re revue (C1 Critical + 6 Important) — OpenAPI/TS
  jamais régénérés (4e occurrence du même oubli sur ce dépôt) ; schéma de
  sortie recompilé pas garanti cohérent avec l'écriture réelle (projection
  finale `transform.select` ajoutée au compilateur, avec vérification de
  position côté décompilation) ; pas de mode replace → un re-run (manuel ou
  planifié) dupliquait la sortie indéfiniment (`mode: "append"|"replace"`
  ajouté à `writer.collection`/`writer.dataset`, purge RLS-scopée avant
  réinsertion, défaut `"append"` non régressif pour SP-15) ; « Modifier la
  requête » ne modifiait rien (vraie mise à jour en place, avec titre
  restauré/protégé contre une course d'écrasement et persisté au
  renommage) ; 500 non catché sur nom de colonne réservé
  (`id`/`tenant_id`/`geom`) ; mitigation supposée absente entre deux tâches
  liées ; pas de validation de complétude avant écriture irréversible. 2e
  revue (focus intégration — croisement des fixes I1×I2×I3 avec le reste du
  système, invisible à une revue par tâche) — 4 défauts supplémentaires :
  le mode édition ne revalidait jamais le schéma de sortie recompilé contre
  la collection déjà provisionnée (une requête modifiée + planifiée pouvait
  se sauvegarder puis échouer à chaque tick de cron sans aucun signal —
  garde-fou bloquant ajouté) ; un run en échec laissait l'assistant bloqué
  indéfiniment sans erreur visible (poll désormais surface `status:
  "failed"` et repasse au formulaire) ; changer la collection de base ne
  réinitialisait pas filtre/jointure/résumé (références de colonnes
  obsolètes validées à tort) ; « Ajouter une jointure »/« Ajouter un
  résumé » étaient des portes sans retour (régression d'un fix de la 1re
  revue — boutons de suppression ajoutés) ; plus 1 défaut de gouvernance :
  `mode: "replace"` exposé sans avertissement dans l'inspecteur générique du
  canvas classique (n'importe quelle collection écrivable peut être ciblée)
  et sa purge n'écrivait aucune entrée `audit_log`, contraire à la règle
  CLAUDE.md — `write_audit` ajouté sur la purge (bug du brief lui-même
  auto-corrigé : l'appel initial à l'intérieur de `rls_scope` levait
  `permission denied for table audit_log`, `gis_rls` n'ayant pas ce grant),
  `description` Pydantic en français sur le champ + rendu générique des
  descriptions de champ dans `PipelineNodeInspector` (pas de cas spécial).
  0 Critical/Important non résolu au merge sur les deux revues. Reste non
  bloquant : croissance non bornée du journal CDC sous replace planifié
  (cf. `### Suivis non bloquants ouverts`).
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
- **3D (rendu)** — reste non planifié de la vision post-v0.1 (feuille de
  route §SP-17, A24) exécuté hors tout numéro de SP : nouveau `kind:
  "tiles3d"` sur `MapLayer` (deck.gl `Tile3DLayer` + loaders.gl, rendu par
  le même `MapboxOverlay` déjà utilisé par les couches `deck` — pas de
  deuxième moteur cartographique) et `MapConfig.terrain` (MapLibre
  `raster-dem` natif, encodage `terrarium` uniquement) ; caméra pitch/
  bearing sur `MapViewport`, persistée via le même round-trip `moveend`/
  `flyTo` que center/zoom. Périmètre resserré par rapport à l'A24
  d'origine (décidé en brainstorm 2026-08-13) : rendu seul — tileset 3D
  Tiles et terrain pointent vers des URL externes déjà hébergées, aucun
  pipeline d'upload/hébergement (zip→S3→item), aucun terrain servi par
  notre propre TiTiler, aucun outil MCP dédié.
- **3D (hébergement de tilesets uploadés)** — reste non planifié de la
  vision post-v0.1 exécuté hors tout numéro de SP, suite directe du "3D
  (rendu)" ci-dessus : un auteur peut uploader un zip contenant un
  tileset 3D Tiles (`tileset.json` + binaires, jusqu'à plusieurs Go /
  dizaines de milliers de fichiers), GeoStudio le stocke et l'expose comme
  item de catalogue cherchable/partageable, et un auteur de carte le
  choisit depuis `LayerPicker` au lieu de taper une URL externe. Le zip
  reste un objet S3 unique pour toute sa durée de vie — jamais extrait
  côté serveur : nouveau module `core/app/tileset3d/` (table transitoire
  `tileset3d_jobs` pour le cycle de vie de l'upload multipart seulement,
  aucune nouvelle table pour les métadonnées du tileset — elles vivent
  dans `BuilderConfig.tileset3d`, 10e kind), upload multipart direct
  navigateur→S3 (le cœur ne voit jamais les octets, arbitrage A6), tâche
  procrastinate de finalisation validant le zip par lecture par plage
  (`S3RangeFile` + stdlib `zipfile`, ne lit que l'EOCD + la table
  centrale — coût constant), proxy de lecture authentifié
  (`GET /tileset3d/{item_id}/{path}`, même porte `can()` que tout autre
  item — pas de bucket public, pas de CDN), le tout derrière
  `CORE_TILESET3D_ENABLED` (défaut désactivé). Shell : bouton d'upload
  (dialogue fichier+titre → upload multipart chunké avec progression →
  poll jusqu'à `done`/`error`), source hébergée dans `LayerPicker`, jeton
  de session attaché aux requêtes `Tile3DLayer` de deck.gl pour un
  tileset hébergé (jamais pour une URL externe). Exécution en
  subagent-driven-development, 13 tâches puis revue finale de branche en
  **3 rounds** (0 Critical/Important non résolu au merge à l'issue du 3e) :
  **1re revue par tâche** (1 Critical + 1 Important, invisibles à
  l'auteur du plan lui-même) — fuite du jeton de session vers un hôte
  externe si l'URL du tileset contenait la sous-chaîne `/tileset3d/` sans
  être réellement hébergée chez nous (vérification d'origine réelle
  ajoutée, `getCoreUrl` sur `ItemClient`) ; fermeture du dialogue d'upload
  pendant un envoi en cours pouvant corrompre l'état d'un 2e upload
  démarré ensuite (fermeture bloquée tant que `busy`) ; **revue finale de
  branche, round 1** (3 Critical + 4 Important + 5 Minor supplémentaires,
  invisibles à une revue par tâche) — worker ne consommant jamais la
  file procrastinate `tileset3d`, `CORE_TILESET3D_ENABLED` absent de
  l'environnement du service `core` dans `docker-compose.yml` (feature
  inopérante dans la stack packagée, 3e occurrence de cette classe de
  bug après SP-17a/SP-17b) ; upload multipart navigateur ne pouvant pas
  aboutir contre un vrai S3/MinIO (CORS du bucket n'exposait pas
  `ETag`) ; aucun validateur de payload sur `kind="tileset3d"` côté
  `/configs`, permettant à un utilisateur quelconque de s'approprier un
  `sourceKey` S3 arbitraire et de lire les données d'un tileset d'un
  autre tenant via son propre item (nouveau
  `core/app/configs/tileset3d_validation.py`, rejet inconditionnel — seul
  `finalize_tileset3d_task` produit légitimement ce kind, par appel
  direct au repository) ; poll infini du job de finalisation composé
  avec le garde de fermeture ajouté en revue par tâche (Task 12) pouvant
  rendre le dialogue définitivement infermable (délai de 5 min ajouté) ;
  zip d'un upload rejeté jamais purgé du bucket (purge ajoutée, avec
  `write_audit` conditionnel au succès réel de la suppression — la 1re
  passe de fix de ce round avait elle-même oublié cet audit, contraire à
  la règle CLAUDE.md, corrigé au round 2). **Round 2** a trouvé que le fix du
  plafond anti-déni-de-service (lecture d'une entrée du zip) réutilisait
  la même variable que le plafond de *validation* — la branche de rejet
  ne pouvait donc jamais se déclencher pour une archive déjà validée,
  laissant un zip de quelques Mo pouvoir forcer plusieurs Gio d'allocation
  mémoire par requête proxy via un taux de compression légitimement élevé
  (pas besoin de mentir sur les métadonnées) ; corrigé par un plafond de
  lecture indépendant et plus bas (`CORE_TILESET3D_MAX_PROXY_READ_BYTES`,
  128 Mio) vérifié contre la taille déclarée avant toute décompression,
  réponse convertie en vrai `StreamingResponse` (fini le `b"".join()` en
  mémoire). **Round 3** a trouvé que la conversion en streaming
  déplaçait la détection d'une corruption CRC (jamais vérifiée par la
  validation d'upload) après le point de non-retour HTTP pour une entrée
  de plus d'1 Mio — corps tronqué silencieusement au lieu d'un 422 propre
  (régression réelle par rapport au round 1, qui matérialisait l'entrée
  avant de répondre) ; mitigé par un en-tête `Content-Length` rendant le
  short-read détectable sans ambiguïté par tout client/proxy HTTP.
- **SP-18a** — export d'apps : mécanisme commun + mode Statique (premier des
  trois modes de SP-18, dépend de SP-11). Nouveau module `core/app.appexport`
  (`models`/`repository`/`guard`/`freeze`/`bundler`/`jobs`/`routes`, table
  `app_export_jobs`, capacité `CORE_APPEXPORT_ENABLED` défaut désactivé) :
  `POST /app-exports` garde chaque `DataSource` (collection sous-jacente
  `is_public=true` obligatoire — pas seulement `can()`-lisible, puisque le
  bundle tourne sans session authentifiée — et allowlist des 22 widgets
  builtin), gèle les sources `"features"` en `"static"` (lignes réellement
  requêtées in-process via `introspect_table`/`select_features`, RLS-scopées,
  même patron qu'`app/mcp/tools.py`), zippe le résultat avec un runtime
  générique prébâti (jamais reconstruit par export) et l'upload sur S3.
  Shell : `StaticItemClient` (les ~83 méthodes non optionnelles d'`ItemClient`
  écrites explicitement, sans cast d'échappement — TypeScript prouve
  qu'aucune n'a été oubliée), entrée Vite dédiée (`vite.export.config.ts` →
  `shell/dist-export/`), image Docker one-shot qui bâtit ce runtime une fois
  et le dépose dans un volume partagé avec `worker`, `AppExportPanel` dans le
  builder (déclenche/sonde/télécharge, avertissement si un widget Formulaire
  est présent), E2E prouvant que le bundle tourne avec zéro cœur GeoStudio
  dans la boucle (serveur HTTP jetable dédié, jamais `mockCore`).
  Exécution en subagent-driven-development, revue par tâche systématique :
  plusieurs corrections réelles trouvées et appliquées **avant** dispatch de
  l'implémenteur (signatures devinées par le plan vérifiées contre le code
  réel) — notamment un bug RLS dans le texte même du plan (`freeze.py`
  n'enveloppait pas `select_features` dans `rls_scope`, corrigé pour
  miroiter `app/mcp/tools.py` exactement) et un test conçu pour SQLite alors
  qu'`introspect_table` exige des catalogues système Postgres réels (réécrit
  en `pytest.mark.postgis` + vraie `CREATE TABLE`+`apply_collection_ddl`).
  Un Important trouvé et corrigé en revue de tâche (Task 8) : `POST
  /app-exports` non exempté du garde 403 mode démo lecture-seule,
  contrairement à son analogue `/export` (SP-17a) — aucune tâche suivante
  du plan ne touchait `main.py`, donc rien n'aurait rattrapé ça sans la
  revue par tâche. Câblage `docker-compose.yml` vérifié **par valeur**
  contre `docker compose config` résolu (pas seulement "ça parse") dès la
  revue de tâche — rompt le motif des 3 incidents précédents
  (SP-17a/SP-17b/tileset3d) où ce type de câblage n'était découvert cassé
  qu'en revue finale de branche. Régénération OpenAPI/TS correctement
  prédite comme un diff **vide** (le routeur n'est monté que si le flag est
  actif, jamais en CI) — même précédent que `CORE_ETL_ENABLED`, pas une 5e
  occurrence de l'oubli de régénération.
  **Revue finale de branche** (invisible à toute revue par tâche, la classe
  de bug que ce niveau de revue existe pour attraper) : 3 Critical + 6
  Important + 8 Minor. C1 — bundle cassé hors racine de domaine
  (`vite.export.config.ts` sans `base`, assets en chemins absolus `/assets/…`
  au lieu de relatifs) ; C2 — le garde de widgets et l'avertissement
  Formulaire étaient des no-op pour toute app mono-page (le cas courant : une
  config sans second `pages[]` garde ses widgets dans `layout` top-level,
  jamais scanné par le garde ni par `collectWidgetTypes`) ; C3 — navigation
  morte dans un export multi-pages (`entry.tsx` passait un `pageId` figé sans
  `onNavigate`, verrouillant `AppRenderer` sur la première page pour
  toujours). Plus 6 Important : preuve E2E jamais exécutée en CI (`npm run
  e2e` sans `build:export-runtime` au préalable, skip silencieux permanent) ;
  `CORE_APPEXPORT_ENABLED` non documenté dans `.env.example` ;
  `appexport-runtime-builder` sans profil compose, bloquant `worker` au
  démarrage pour une capacité désactivée par défaut (**décision explicite
  avec Tanguy** : profil `appexport`, même convention que
  `qgis-worker`/`export-worker`, dépendance dure retirée de `worker`) ;
  formulaire qui échouait *ouvert* en export statique (`canWrite` retombait
  à `true` quand la requête de permission échouait, au lieu de `false`) ;
  `featuresUrl()` levant une exception synchrone capable de faire planter
  tout le rendu si l'Explorer est ouvert (`interactions: "auto"`). Une
  passe de fix unique (suivant la discipline « un seul agent, pas un
  fixeur par trouvaille ») + re-revue complète : **0 Critical/Important non
  résolu au merge**. Écarté explicitement du périmètre de cette passe (pas
  un oubli) : filtres interactifs (`filter`/`selectFilter`/…) silencieusement
  inertes sur une source gelée — `freeze_config` ignore `DataSource.query`,
  aucune donnée n'est mal exposée (agit comme si aucun filtre n'était posé),
  mais l'expérience est trompeuse ; reste en suivi non bloquant, nécessite
  un choix produit (honorer `query` à la congélation vs. étendre
  l'avertissement d'export aux widgets de filtre).
- **SP-18b** — export d'apps : mode Connecté (deuxième des trois modes de
  SP-18) : réutilise quasi tel quel le mécanisme SP-18a (garde/job/route/
  panneau) — `check_export_guard` gagne un paramètre `mode` requis, sans
  défaut (tous les sites d'appel existants mis à jour explicitement) : en
  mode `"connected"` la restriction sur les sources `"statistics"` et
  l'allowlist de types de widgets disparaissent toutes deux (rien n'est
  figé côté serveur, `/collections/{id}/aggregate` est déjà anonyme-capable
  pour une collection publique ; un widget tiers charge son JS depuis sa
  propre origine, exactement comme dans le shell normal). `build_app_export_task`
  saute `freeze_config` pour ce mode (données vivantes) et embarque un
  `geostudio-connection.json` (`{"coreUrl": ...}`, sourcé de `CORE_BASE_URL`,
  déjà utilisé pour le même usage par le serveur MCP) dans le zip aux côtés
  de la config **non gelée**. Le runtime prébâti existant (un seul, partagé
  avec le mode Statique) devient sensible au mode au chargement : la
  présence de `geostudio-connection.json` bascule `createItemClient` (vrai
  réseau, `getToken` codé en dur à `() => undefined` — jamais câblé sur
  `useAuth()`, un piège identifié en conception : `enableMockAuth()` fait
  retourner `"mock-token"` à `getAccessToken()`, et le cœur traite tout
  `Authorization` présent comme devant être valide, sans repli anonyme sur
  un jeton invalide) au lieu de `createStaticItemClient`. Nouveau middleware
  CORS étroit et capacity-gated dans `core/app/main.py` (origine wildcard —
  sûr ici puisqu'aucune credential/cookie ne traverse cette frontière,
  Bearer-ou-rien — mais allowlist de chemins stricte : uniquement les
  endpoints déjà anonymes-capables qu'un bundle Connecté appelle). Exécution
  en subagent-driven-development, 9 tâches ; **revue finale de branche** (4
  Important, invisibles à une revue par tâche) : `loadConnection()` laissait
  une erreur de parse JSON se propager et casser le mode Statique déjà livré
  sur tout hôte statique à repli SPA (nginx `try_files`, Netlify, Firebase
  Hosting répondent 200+HTML sur un chemin non trouvé) — traité désormais
  comme « pas de fichier de connexion », repli sur Statique ; les extensions
  tierces actives n'étaient jamais enregistrées en mode Connecté (le garde
  les autorise sur la prémisse qu'elles chargent leur propre JS, mais rien
  ne les enregistrait — rendu en « Widget inconnu ») ; le widget Galerie
  builtin appelle `GET /public/items`, absent de l'allowlist CORS (bloqué) ;
  `.env.example` ne documentait ni la surface CORS wildcard ni l'obligation
  de régler `CORE_BASE_URL` en URL externe réelle pour un déploiement
  reverse-proxyé. Une passe de fix + **2 re-revues** ont trouvé et corrigé
  2 défauts supplémentaires introduits par le premier fix lui-même :
  `listActiveExtensions()` non gardé pouvait faire planter toute la page sur
  un 404/erreur réseau/CORS même pour une app sans widget tiers (try/catch
  ajouté) ; le try/catch, trop large dans sa première forme, avalait aussi
  les bugs réels de `registerExtensionWidget` — resserré au seul `fetch`.
  0 Critical/Important non résolu au merge sur les 3 rounds cumulés.
- **SP-18c** — export d'apps : mode Autoporté/standalone (troisième et
  dernier mode de SP-18, **jalon M15 atteint**) : contrairement aux modes
  Statique (données figées) et Connecté (cœur GeoStudio d'origine requis en
  ligne), l'Autoporté embarque données **et** un mini-serveur dans un seul
  conteneur Docker distribuable sans dépendance à une instance GeoStudio.
  Cœur : `write_snapshot` (un GeoParquet par collection référencée,
  réutilise le CTE de dédoublonnage CDC de SP-11b), `app.appexport.manifest`
  (forme partagée du manifeste de snapshot), `open_local_connection` +
  listing d'entités DuckDB-backed pour le mini-serveur, `build_standalone_bundle_zip`
  (bundle données+compose), une app FastAPI mini-serveur autonome, job
  d'export qui bascule sur `mode="standalone"`, `POST /app-exports` accepte
  ce mode. Déploiement : image Docker mini-serveur dédiée, publiée sur
  `ghcr.io` (`geostudio-appexport-standalone`) par la CI de release. Shell :
  `AppExportMode` gagne `"standalone"`, bouton « Autoporté » sur
  `AppExportPanel`. E2E : le conteneur standalone sert l'app depuis un vrai
  snapshot. Exécution en subagent-driven-development, 14 tâches (2 défauts
  trouvés et corrigés en revue de tâche : `build_standalone_bundle_zip` ne
  levait pas d'erreur claire sur un `snapshot_dir` manquant ; le listing
  d'entités du mini-serveur ne gardait pas contre un filtre spatial posé sur
  une collection non spatiale) + **1 round de revue finale de branche** :
  0 Critical/Important trouvé.
- **SP-18** — clos : les trois modes d'export (Statique SP-18a, Connecté
  SP-18b, Autoporté SP-18c) sont livrés. **Jalon M15 atteint.**
- **SP-19** — undo/redo général du builder (`shell/src/pages/AppBuilderPage.tsx`)
  : `Ctrl+Z`/`Ctrl+Shift+Z` + boutons « Annuler »/« Rétablir », pile
  éphémère unique d'instantanés `AppConfig` complets (past/future,
  plafond 50), derrière un seul hook `useUndoableDraft` qui remplace le
  `useState` de `draft` — aucun panneau/widget individuel modifié
  (vérifié contre le code réel : tous funnellent déjà par ce seul
  `setDraft`). **Correction de spec actée au moment du plan (2026-08-15,
  avec Tanguy)** : l'hypothèse initiale (panneaux bufferisant localement
  la saisie avant commit) était fausse pour ce dépôt — tous les champs
  texte appellent `setDraft` à chaque frappe, sans état local — remplacée
  par un **coalescing centralisé par minuterie d'inactivité (400ms)**
  dans le hook seul, pas par un buffer par panneau (§3/§4 de la spec
  amendées en conséquence). Raccourci clavier ignoré tant que le focus
  est dans un champ texte (préserve l'undo natif du navigateur).
  Exécution en subagent-driven-development, 4 tâches (0 Critical/Important
  en revue de tâche) + **revue finale de branche** : **2 Critical**
  invisibles à la revue par tâche — `undo()`/`redo()` mutaient des refs
  à l'intérieur d'un updater `useState`, cassé sous `<StrictMode>` (donc
  en `npm run dev`, jamais en E2E qui tourne contre un build de prod où
  le double-invoke DEV est compilé) : un seul edit puis `Ctrl+Z` ne
  faisait rien tout en affichant `canUndo=false` comme si l'undo avait
  réussi ; `activePageId` (state hors pile undo) devenait orphelin après
  annulation d'un « Ajouter une page », `setPageLayout` no-opant alors
  silencieusement tout edit suivant (« Enregistrer » sauvegardait sans
  erreur ni changement) — corrigés en une passe (`draftRef` synchrone
  remplaçant toute mutation de ref dans un updater ; `activePage` dérivé
  et validé contre `draft.pages` à chaque render), plus 1 Important
  (timer de coalescing non nettoyé au démontage) et 1 Minor de même
  classe (`selectedId` non réconcilié). Re-revue : 0 Critical/Important
  résiduel, E2E re-exécuté par le contrôleur (2/2). **Prérequis de SP-20
  rempli.**
- **SP-20** — copilote IA embarqué dans le builder (**jalon M16 atteint**,
  arbitrages A32/A40) : panneau de chat dans le builder d'app, outils MCP
  orchestrés par le cœur en **loopback HTTP réel** sur son propre `/mcp`
  (jamais un appel direct aux fonctions d'outil), micro-actions appliquées
  à la config en cours d'édition — annulables par le seul et même undo
  stack SP-19, sans bouton dédié. Tout derrière `CORE_LLM_PROVIDER`
  (défaut vide = capacité éteinte, routeur non monté, panneau absent).
  - **Cœur** : `core/app/copilot/` (`llm_provider` — `LLMProvider`
    enfichable, `FakeLLMProvider` déterministe pour dev/test +
    `OpenAICompatibleLLMProvider` ; `mcp_loopback` — session HTTP vers
    `/mcp`, poignée de main paresseuse ; `tools_allowlist` — 6 outils MCP
    seulement, jamais `save_app_config`/`set_sharing` ; `routes` — `POST
    /copilot/turn`, boucle d'outils bornée à 6 itérations, timeout 30 s,
    session fermée en `finally`). `app.copilot` inséré sous `app.mcp` dans
    le contrat de couches. Tout nom d'outil hors allowlist n'est **jamais**
    exécuté côté serveur : il repart au shell en `clientOps`.
  - **Shell** : `configSchema` sur `WidgetDefinition` (backfill des 22
    widgets builtin + widgets d'extension), `clientTools.ts` (5 outils
    client générés depuis le registre, pas maintenus à la main),
    `applyClientOp.ts` (pur ; tout patch de prop filtré par le
    `configSchema` du widget, un nom halluciné est rejeté),
    `useMcpToken.ts` (jeton d'audience MCP distincte, en mémoire seule),
    `CopilotPanel.tsx` (un seul `setDraft` par tour = une seule entrée
    undo).
  - Exécution en subagent-driven-development, 13 tâches, 0
    Critical/Important non résolu sur les 13 revues de tâche. **Revue
    finale de branche** : 3 Critical + 2 Important + 6 Minor, tous
    invisibles à la revue par tâche (chaque tâche testait avec
    `FakeLLMProvider`/mocks qui masquaient exactement les points cassés) —
    schémas d'outils envoyés en forme MCP (`inputSchema`) au lieu de la
    forme OpenAI (`parameters`), **présent verbatim dans le texte du
    plan** ; `tool_calls[].function.arguments` réinjecté comme dict Python
    au lieu d'une chaîne JSON (casse la 2e itération de toute boucle
    d'outil) ; `signinSilent({scope})` ignoré silencieusement par
    `oidc-client-ts` sur sa branche refresh-token, donc jeton MCP jamais à
    la bonne audience en OIDC réel ; `provider.chat()` synchrone appelé
    depuis une route `async` (gelait toute la boucle d'événements) ; jeton
    MCP mis en cache indéfiniment. Une passe de fix (C1/C2/C3/I1/I2 +
    M1/M2/M6), puis un **redesign de C3** en 2e tentative : l'appel direct
    au endpoint de token a été abandonné après vérification empirique
    contre un vrai Keycloak (un grant `refresh_token` ne réapplique jamais
    le mapper d'audience, quelle que soit la combinaison de scopes) au
    profit de `signinSilent({scope, forceIframeAuth: true})`.
  - **Clôture** (2026-08-20) : croisement avec la revue de projet
    `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, qui portait
    3 constats copilote de gravité Critique et 2 Important — chacun
    re-vérifié contre le code avant correction, puis corrigé en TDD :
    **confused deputy** sur `/copilot/turn` (la route authentifiait son
    appelant puis agissait sous l'identité d'un **second** jeton fourni
    par le client, jamais comparée — nouveau `app/copilot/mcp_token.py`,
    `sub` du jeton MCP exigé égal à `user.oidc_sub`, 403 sinon, audience
    MCP obligatoire pour qu'un jeton REST ne puisse pas satisfaire la
    comparaison) ; **copilote cassé par construction en prod** (le rappel
    `/mcp` ciblait `CORE_BASE_URL`, que l'overlay prod fixe à l'URL
    publique en TLS — hairpin NAT, et rejeté de toute façon par la garde
    anti-DNS-rebinding de FastMCP : nouvelle `CORE_INTERNAL_BASE_URL`,
    câblage vérifié **par valeur** sur le compose résolu) ; **entrée non
    bornée** (`CopilotTurnRequest` n'avait aucune contrainte et tout son
    contenu repartait au LLM à chaque itération — bornes sur tous les
    champs + taille sérialisée de `currentConfig`, `role` d'historique
    borné à `user`/`assistant` pour qu'un `system` client ne réécrive pas
    la consigne) ; **copilote éteint en mode démo lecture-seule** (les
    écritures y étaient déjà bloquées, mais un visiteur anonyme pouvait
    brûler le budget d'API LLM de l'opérateur — double verrou : capacité à
    False *et* exemption du garde retirée) ; **surface d'injection de
    prompt** via `currentConfig` (config interpolée nue dans la consigne,
    alors qu'elle porte des textes rédigés par des utilisateurs et peut
    venir d'un item partagé par un tiers — bloc désormais délimité par un
    marqueur à **nonce tiré par tour**, annoncé comme de la donnée, avec
    consigne de n'y obéir jamais). Le 3e Critique de cette revue (blocage
    de la boucle d'événements) était déjà fermé par le fix I1 de la revue
    de branche.
- **SP-21** — « Déployabilité » (vague 1 du plan d'action
  `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, constats C4, C5,
  I5, I8, I14) : un garde-fou de 9 règles (7 à la livraison, 2 ajoutées par la
  revue finale puis par la publication de la release) dans
  `core/tests/test_deployability.py` qui teste le **dépôt** (compose, overlay
  prod, `release.yml`, `.env.example`, `deploy/backup/backup.sh`, `ci.yml`)
  plutôt que `core/app/` —
  entorse assumée au découpage, écrite en réaction à quatre capacités
  livrées-testées-mergées qui se sont révélées non câblées dans la stack
  packagée (SP-17a, SP-17b, tileset3d, et `CORE_ETL_ENABLED` — trouvée en
  écrivant ces tests). Chaque règle correspond à une de ces découvertes et
  échouait sur le dépôt tel qu'il était avant SP-21, sauf deux gardes-fous
  purs qui protègent l'avenir sans corriger de défaut présent
  (`test_every_referenced_ghcr_image_is_released`,
  `test_every_compose_substitution_is_documented` — 43 substitutions déjà
  toutes documentées à l'arrivée). État à l'arrivée des 5 autres règles,
  toutes rouges avant SP-21 : `test_every_build_service_has_a_released_image`
  — 4 services construits sans image publiée (`export-worker`,
  `qgis-worker`, `appexport-runtime-builder`, `backup`) ;
  `test_prod_overlay_substitutes_every_build_with_an_image` — l'overlay prod
  ne substituait que 5 services sur 9, laissant `build:` actif pour les 4
  autres ; `test_every_core_env_var_is_wired_to_a_service` — 6 variables
  lues par `core/app/` n'étaient câblées sur aucun service ;
  `test_backup_covers_every_bucket_the_core_uses` — 2 buckets S3 utilisés
  par le cœur (`tileset3d`, `terrain3d`) n'étaient pas sauvegardés ;
  `test_images_are_pinned` — 4 images (`minio`, `keycloak`, `traefik`,
  `tailscale`) n'étaient pas pinnées au patch/digest.
  - **Images & overlay** — les 4 services manquants ajoutés à la matrice
    `build-and-push` de `release.yml` (8 entrées au total). Le critère de
    sortie du plan lui-même (« 0 `build:` dans le compose prod résolu ») —
    n'était **pas** atteint en suivant ses instructions littérales : mesuré
    8, parce que la fusion Compose est additive (retirer `build:` du
    fichier de base ne le retire pas de l'overlay qui en hérite). Écart
    tranché par Tanguy : `build: !reset null` appliqué aux 8 services
    concernés (dont 5 déjà pré-existants avant SP-21), règle durcie, et le
    `ComposeLoader` du garde-fou corrigé pour résoudre ce tag à un sentinel
    `RESET` plutôt qu'à la chaîne littérale `'null'` (qui aurait fait
    passer un `build:` supprimé pour un contexte de build valide). Vérifié
    indépendamment sur le compose résolu : `grep -c build:` → 0.
  - **6 variables câblées** : `CORE_ANALYST_SUBS`, `CORE_ETL_ENABLED`,
    `CORE_EMBEDDING_PROVIDER`, `CORE_EMBEDDING_API_URL`,
    `CORE_EMBEDDING_API_KEY`, `CORE_EMBEDDING_MODEL`, câblées sur `core`
    (les 6) et `worker` (les 5 hors `CORE_ANALYST_SUBS`), toutes avec un
    défaut identique au défaut applicatif — aucune capacité ne s'allume par
    effet de bord. **`CORE_ETL_ENABLED` est la 4ᵉ occurrence de la classe de
    bug que ce garde-fou existe pour attraper, et la plus large** : une
    capacité instance-wide entière (tout le module pipelines) restait
    inactivable en pratique malgré sa présence dans le code et ses tests —
    et sa **présence dans `.env.example` donnait l'illusion qu'elle était
    câblée**, alors que la ligne documentée n'était substituée dans aucun
    `environment:` de service. En élargissant la règle de lecture des
    variables (`ENV_READ_RE`) d'un simple grep vers un **résolveur AST**
    (pour voir les lectures indirectes via constante de module), la même
    tâche a trouvé 3 allowlists d'egress SSRF (`CORE_PIPELINES_/HARVEST_/
    ALERTS_EGRESS_ALLOWLIST`) câblées sur **zéro** service — 2 des 3
    pourtant déjà documentées dans `.env.example`, même piège que
    `CORE_ETL_ENABLED`. Décision Tanguy : les 3 câblées sur `core` et
    `worker`.
  - **Sauvegarde** : 2 buckets S3 amenés dans le périmètre de
    `deploy/backup/backup.sh` (`tileset3d`, `terrain3d`, rejoignant
    `thumbnails`/`uploads`/`cdc`) et 2 exclus **explicitement** avec leur
    raison écrite (`BACKUP_EXCLUDED_BUCKETS` : `S3_EXPORTS_BUCKET`,
    `S3_APPEXPORTS_BUCKET` — sorties recalculables, pas des données
    sources). Couverture réelle : 5 des 7 buckets lus par le cœur sont
    sauvegardés, 2 exclus par construction. Défaut trouvé en revue dans le
    runbook de restauration (`docs/runbooks/2026-07-24-restauration-
    sauvegardes.md`) : sa §4 promettait « cinq buckets restaurés » alors
    qu'elle n'en recréait que trois (`mc mb`) — le mode d'échec même que
    cette tâche existe pour supprimer, retrouvé un cran plus loin dans le
    même fichier ; corrigé, désormais piloté par les 5 `${S3_*_BUCKET}` que
    le service `backup` reçoit réellement.
  - **4 images repinnées**, résolues contre leurs registres et vérifiées par
    `docker manifest inspect` : `minio/minio` (sans tag) →
    `RELEASE.2025-09-07T16-13-09Z` ; `quay.io/keycloak/keycloak:24.0` →
    `24.0.5` ; `traefik:v3.0` → `v3.0.4` ; `tailscale/tailscale:latest` →
    `v1.102.3`. `grep -c ":latest"` sur le compose **de base** résolu → 0 —
    portée précisée en revue finale : l'overlay de production en résout six
    de plus tant que `GEOSTUDIO_VERSION` vaut `latest`, ce qui est un choix
    d'opérateur (documenté comme tel dans `.env.example`, exempté par
    `test_images_are_pinned`) et non un pin manquant de notre côté.
  - **Healthchecks posés sur les 7 services qui en manquaient** : `core`,
    `worker`, `cdc-worker`, `shell` (sonde CDC `scripts/healthcheck_cdc.py`
    sur `pg_replication_slots.active`, la seule des quatre capable de
    détecter « vivant mais ne consomme plus », vérifiée contre un vrai
    slot de réplication) puis `pgbouncer`/`martin`/`titiler` — les trois
    commandes de sonde **suggérées par le plan étaient fausses**, toutes
    remplacées après inspection réelle des images (`pgbouncer -d pgbouncer`
    rejeté par `FATAL: not allowed`, seul `gis` a une entrée dans
    `userlist.txt` ; `martin` n'a pas `curl` et `localhost` y résout en
    IPv6 alors que martin n'écoute qu'en IPv4 ; `titiler` n'écoutait sur
    aucun port testé). **5ᵉ occurrence de la classe de bug SP-21, trouvée
    par cette même tâche** : `titiler:0.18.4` (base tiangolo/uvicorn-
    gunicorn) écoute sur le port 80, `PORT` jamais câblé, alors que `core`
    proxifie chaque tuile terrain 3D en serveur-à-serveur vers
    `${TITILER_URL:-http://titiler:8000}` — connexion refusée, le terrain
    3D hébergé ne pouvait **pas fonctionner du tout** en stack packagée.
    Décision Tanguy : corrigé dans SP-21 (`PORT: "8000"` câblé, vérifié
    depuis un second conteneur sur le réseau docker : `http://titiler:8000/
    healthz` → 200). **Ce qui n'a pas pu être vérifié** : le
    `depends_on: core: service_healthy` d'`export-worker` reste vérifié
    **par lecture seulement** — `shell` et `export-worker` n'ont jamais atteint
    « started » dans les vérifications réelles de cette session, bloqués
    par des pannes de packaging **pré-existantes, sans rapport avec
    SP-21** (cf. `### Suivis non bloquants ouverts`).
  - **Notices GPL/AGPL** : notice + labels OCI embarqués dans
    `geostudio-qgis-worker` (QGIS + GRASS, GPL-2.0-or-later) — deux
    inexactitudes du plan corrigées au passage : « aucune modification »
    était faux (`qgis_process plugins enable grassprovider` grave une
    activation de plugin dans le profil QGIS de l'image, reformulé en
    « pas de modification des sources, un réglage de configuration ») et
    « QGIS 3.34 LTR » précisé en « 3.34.5 "Prizren", LTR » (lu depuis
    l'image réelle). En reprenant la checklist sur les 8 images publiées,
    la revue a trouvé que l'affirmation du plan « sept d'entre elles ne
    contiennent que du permissif » était **fausse** :
    `geostudio-postgis` embarque PostGIS (GPL-2.0-or-later) — puis que
    **`geostudio-backup` embarque le client MinIO `mc`, en
    AGPL-3.0-or-later**, et que c'est la tâche 1 de SP-21 elle-même
    (matrice de release) qui a fait de cette image un objet publié, donc
    distribué, pour la première fois. Décision Tanguy : embarquer la
    notice maintenant (`LICENSE-BACKUP.md` + 3 labels OCI, build et notice
    relus depuis un vrai conteneur). Constat supplémentaire, documenté mais
    non traité : `geostudio-core` et `geostudio-export-worker` embarquent
    `psycopg` (LGPL-3.0-only) et `psycopg2-binary`, copyleft faible jusqu'ici
    non documenté — l'opportunité d'une notice embarquée pour ces deux
    images **n'est pas tranchée** (leurs Dockerfiles étaient hors du
    périmètre de fichiers autorisés pour cette tâche).
    `geostudio-postgis` reste sans notice/labels embarqués, **bloqué** :
    son `Dockerfile` porte des lignes non commitées d'un autre travail en
    cours dans ce même arbre, et le stager emporterait ce travail.
  - **Revue finale de branche** (20 commits SP-21 isolés) : 1 Critical +
    4 Important + 5 Minor, tous invisibles tâche par tâche. Ce qu'elle
    confirme par ailleurs : les 9 références GHCR trouvent toutes une entrée
    de matrice (aucune faute de frappe), le graphe de `depends_on` est
    acyclique, et les règles sont toutes non vacuous sur le dépôt
    d'aujourd'hui. Les 4 Important et 4 des 5 Minor sont corrigés
    (`4a6bf6b`..`25e8309`) : sonde `shell` qui ne pouvait jamais passer
    (`localhost` → `::1` sous busybox, nginx n'écoute qu'en IPv4 — mesuré
    sur l'image réelle, piège identique à celui corrigé pour `martin` une
    tâche plus tôt) ; onze noms de `.env.example` présentés comme réglables
    et substitués nulle part (bloc S3 passé en lignes commentées,
    `MARTIN_SECRET` exempté avec sa raison) **plus une 8ᵉ règle** qui
    outille cette direction, `documenté ⇒ câblé ou déclaré inerte` — la
    direction de `CORE_ETL_ENABLED` elle-même, que les 7 premières ne
    couvraient pas ; `GEOSTUDIO_VERSION=latest` et la portée de la mesure
    « 0 :latest » (ci-dessus) ; matrice de `release.yml` sans
    `fail-fast: false`, où un échec sur `qgis-worker` (11,1 Go) annulait la
    publication des sept autres. Un défaut de plus, de la classe même que
    SP-21, trouvé en vérifiant le correctif : `S3_EXPORTS_BUCKET` est lue
    aussi par `worker` (`app/reports/jobs.py`, `app/pipelines/jobs.py`, file
    `etl`) et n'y était pas câblée — la règle 3 ne pouvait pas le voir, elle
    fait l'union de tous les services et ignore quel process lit quoi
    (limite désormais écrite dans sa docstring, avec celle du périmètre
    `core/app/` seul : la moitié shell d'une capacité n'est pas couverte).
    **Reste ouvert, seul point bloquant le merge : C1.** Effacer les
    `build:` de l'overlay prod (tâche 2, `!reset`) a supprimé le seul repli
    qui faisait fonctionner la prod sans release publiée. Mesuré : aucun tag
    git n'existe (`git ls-remote --tags origin` → 0) et 5 des 8 images sont
    absentes de ghcr.io, dont `geostudio-backup`, que `scripts/install.sh`
    tire sans profil → l'installation échoue au `pull`. **Une affirmation de
    la revue est fausse, corrigée ici** : elle déduisait de l'absence de tag
    que `release.yml` n'avait jamais tourné, donc que `core`/`shell`/
    `postgis` avaient été poussées à la main. `gh run list` dit le contraire —
    le workflow a tourné une fois, avec succès, le 2026-07-15 sur le tag
    `v0.1.0-rc1` (supprimé depuis, d'où les 0 tags), et c'est cette exécution
    qui a publié ces trois images ; la matrice n'en comptait que trois à
    l'époque. **Décision Tanguy : publier la première release d'abord** —
    exécutée le 2026-08-21 (cf. ci-dessous).

### Release v0.1.0 (2026-08-21) — fermeture de C1

Première release publiée du dépôt (PR #75 `dev`→`main`, tag annoté `v0.1.0`,
huit images `ghcr.io/tlenenao/geostudio-*`). Elle ferme C1 de la revue finale
SP-21 : l'overlay prod ne porte plus de `build:`, il n'avait donc plus de repli
tant que cinq des huit images manquaient au registre.

**Ce que la publication a coûté avant même de démarrer** : trois jobs de CI
rouges sur `dev`, hérités de la session SP-22 dont les 49 commits n'avaient
jamais été poussés — aucune CI n'avait donc tourné dessus depuis SP-20.
Corrigés ici parce qu'ils bloquaient la release :
- `ruff check` — `tests/test_check_coverage.py` livré avec un `import pytest`
  inutilisé, refusé par la porte `ruff` que le même chantier venait d'ajouter ;
- `lint-imports` — `app.analytics` ajouté au contrat, au plus bas, alors que
  ses modules lisent `app.collections.introspection`. **Aucune place linéaire
  ne résout ça** : le graphe réel porte un cycle au niveau paquet
  (`app.analytics` → `app.collections` → `app.configs` → `app.analytics`),
  antérieur à l'entrée d'`app.analytics` dans le contrat. Deux `ignore_imports`
  nommant l'arête au module près (patron des 18 entrées `app.db -> *.models`),
  étroitesse prouvée par sonde ;
- `api-types-drift` — la passe `mypy --strict` a annoté le retour de
  `GET /users` et `PATCH /users/{user_id}`, donc changé la spec OpenAPI. Spec
  et types régénérés (classe d'oubli la plus récurrente du dépôt).

**Puis deux défauts du chemin de release lui-même**, invisibles jusqu'à ce
qu'on tague pour de vrai — un premier tag `v0.1.0` a échoué et a été supprimé
sans avoir publié aucun artefact :
- `release.yml` démarrait Postgres **sans** `wal_level=logical`, que le job
  `core` de `ci.yml` lui donne : les deux tests `@pytest.mark.postgis` du
  consommateur CDC (SP-11) ne pouvaient pas y passer. CI verte, release rouge.
  Dérive structurellement invisible — la dernière release taguée
  (`v0.1.0-rc1`, 2026-07-15) précède ces tests. **9ᵉ règle** ajoutée,
  `test_release_gate_starts_postgres_like_ci`, qui compare les flags des deux
  workflows plutôt que d'attendre le prochain tag ;
- `pip-audit --strict` s'audite lui-même : l'avis PYSEC-2026-3721 sur `pip`
  26.1.2 (transitif via `pip-api`, dépendance de `pip-audit`) a été publié
  entre deux exécutions du même job, vert vingt minutes plus tôt. `pip>=26.2`
  contraint dans le groupe `dev` plutôt qu'un `--ignore-vuln`.

**Résultat, vérifié au registre et non sur le vert du workflow** : les huit
images existent en `v0.1.0` **et sont anonymement téléchargeables** — jeton
anonyme `ghcr.io/token` puis `GET /v2/…/manifests/v0.1.0` → HTTP 200, sans
aucune credential ghcr dans le `~/.docker/config.json` local. La supposition de
la revue « visibilité privée au premier push, à basculer à la main » ne vaut
donc pas pour ce dépôt (paquets poussés par le `GITHUB_TOKEN` du dépôt, qui est
public) : rien à faire à la main.

Conséquence directe : **I3 est fermé pour de bon**. `.env.example` passe de
`GEOSTUDIO_VERSION=latest` à `v0.1.0`, ce qui n'était pas possible avant qu'une
release existe (`scripts/install.sh` aurait échoué au `pull`). Mesuré sur le
compose de production résolu avec le défaut du gabarit : `grep -c ":latest"`
→ **0**, contre 6 avant.

**Constaté, non corrigé** (fichier non commité d'une autre session) : les deux
hooks `bash -c` de `.pre-commit-config.yaml` (`eslint`, `prettier`) ne
reçoivent jamais les fichiers — pre-commit les passe en arguments du `bash -c`,
où ils deviennent `$0`/`$1`. `prettier` échoue en « No parser and no file path
given » et bloque tout commit touchant `shell/src/**` ; `eslint` « passe » en
lintant tout le projet au lieu des fichiers indexés. Il manque un `"$@"` aux
deux (et un `--` côté entry).

- **SP-22** — Filet qualité statique (vague 2 du plan d'action
  `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` ; vague 0 = SP-20
  clôture, vague 1 = SP-21). 7 chantiers de garde-fous statiques/CI, exécutés
  en subagent-driven-development (9 tâches d'implémentation + tâche 10 de
  clôture), review par tâche systématique.
  - **Ruff (Task 1)** — le `select` prescrit par le brief laissait 342
    violations non auto-fixables sous `core/app` seul (dont 269 `B008` faux
    positif FastAPI `Depends`, 45 `B904`, 7 `B905` à effet comportemental
    réel) : **décision Tanguy — remédiation complète, pas de rétrécissement**.
    `extend-immutable-calls` pour B008 (zéro changement de code), `B904`
    chaîné site par site (`from err`/`from None` réfléchi — ex.
    `app/secrets/routes.py` en `from None` pour ne pas fuiter du ciphertext
    via `IntegrityError.params`), `B905 strict=True` vérifié sur les 9 sites,
    périmètre élargi à tout `core/` (app+tests+alembic+scripts). 2 vrais bugs
    trouvés au passage : une comparaison `assert_egress_allowed(...) is None`
    qui n'était pas un `assert` (expression nue, jamais vérifiée) dans 2
    fichiers de test, et un `pytest.raises(Exception)` trop large resserré
    aux 2 vraies exceptions attendues. `ruff check`/`format --check` verts et
    câblés en CI sur tout `core/`.
  - **Contrat de couches complété (Task 2)** — `app.cdc`/`app.instance`/
    `app.search`/`app.analytics` insérés au contrat import-linter (30 entrées
    au total) aux positions exactes déjà en vigueur dans le code ;
    `lint-imports` : `Contracts: 1 kept, 0 broken.`
  - **ESLint + Prettier (Task 3)** — `tseslint.configs.recommendedTypeChecked`
    prescrit par le brief amenait 845 violations (89% hors périmètre, 26
    règles de sûreté de type sur 202 fichiers) : **décision Tanguy —
    resserrer** (pas de remédiation complète, contrairement à Task 1) à
    `tseslint.configs.recommended` + `no-floating-promises`/
    `no-misused-promises` ajoutées explicitement, plus un `no-explicit-any:
    "off"` scopé aux seuls fichiers `*.test.{ts,tsx}` (28 sites, 4 fichiers
    de mocks MSW/DataTransfer). 2 vrais bugs trouvés en triant
    `no-floating-promises` : `PipelineRunPanel.loadRuns()` et
    `VisualQueryWizardPage.poll()` sans aucun `try/catch`, corrigés en miroir
    du patron déjà établi par `ReportRunPanel.tsx` (SP-17b). Premier passage
    Prettier réel sur tout `shell/` (jamais configuré avant cette tâche) →
    308 fichiers reformatés. `dangerouslySetInnerHTML` interdit hors
    `richSection.tsx` par une règle `no-restricted-syntax` dédiée (renvoi
    vers `sanitizeMarkdown()`), avec un bloc d'exception de fichier pour
    `richSection.tsx` lui-même. `npx eslint .`/`prettier --check .` verts,
    `npm run test` 152/1235 inchangé, `npm run build` passe, câblé en CI.
  - **mypy --strict (Task 4)** — 98 erreurs mesurées initialement sur les 4
    modules nommés (`app.auth`/`app.secrets`/`app.analytics`/`app.copilot`),
    dont 13 provenant de 8 fichiers hors périmètre importés transitivement
    (`--strict` type-vérifie par défaut tout module atteint par import, pas
    seulement les 4 ciblés) : `follow_imports = "silent"` ajouté à
    `[tool.mypy]`, vérifié comme un mécanisme standard qui supprime le
    rapport d'erreur sur les fichiers importés sans affaiblir la vérification
    des 4 modules eux-mêmes ni la passe large informative. 85 erreurs réelles
    corrigées (annotations, `TableInfo`/`duckdb.DuckDBPyConnection` au lieu
    d'`Any`, 3 `assert` de narrowing) → 0 erreur. 1 vrai bug trouvé et
    signalé explicitement : `app/auth/dependency.py` réutilisait le nom
    `claims` pour deux types incompatibles selon la branche, renommé
    `oidc_claims` (comportement inchangé, branches mutuellement exclusives).
    core pytest inchangé. CI : passe stricte bloquante sur les 4 modules +
    passe large `mypy app/` `|| true` non bloquante, après `ruff format
    --check`.
  - **Couverture à seuil non régressif (Task 5)** — `check_coverage.py`/
    `check-coverage.mjs` (TDD RED→GREEN, 3/3), seuils versionnés dans
    `core/.coverage-threshold` (**85**) et `shell/.coverage-threshold`
    (**88**), câblés en CI juste après chaque suite de tests (une seule
    exécution par job, pas de doublon). Mesure shell brute anormale (51,78%)
    investiguée plutôt que devinée : artefacts de build locaux `dist/`/
    `dist-export/` gitignorés comptés comme source non couverte —
    `coverage.exclude` du brief **remplace** `coverageConfigDefaults.exclude`
    par spread peu profond (vérifié sur la source `vitest@3.2.7`) au lieu de
    le compléter, donc `dist/**` en sortait. Nettoyage local seul (aucune
    config touchée), remesuré à 88,15% → seuil 88. core 85,09% → seuil 85.
  - **pre-commit + commitlint (Task 6)** — reprise d'une implémentation
    partielle laissée par une session précédente. **Trois entrées de hook
    étaient cassées** : les `entry: bash -c 'cd shell && npx eslint --fix'`/
    `prettier --write` ne recevaient jamais les fichiers stagés (pre-commit
    les passe en arguments du `bash -c`, où ils deviennent `$0`/`$1` —
    `prettier` échouait en « No parser and no file path given » et bloquait
    tout commit touchant `shell/src/**`, `eslint` « passait » en lintant tout
    le projet) ; et `lint-imports`, non documenté jusque-là, échouait aussi
    depuis la racine (`uv run --project core` ne change pas de cwd). Forme
    retenue : `bash -c 'cd shell && npx eslint --fix "${@#shell/}"' --`
    (après qu'une première tentative gardant la racine comme cwd se soit
    révélée elle-même cassée — les globs `files:` d'une flat config ESLint
    et `.prettierignore` résolvent relativement au cwd). `commitlint.config.js`
    pointe `./shell/node_modules/@commitlint/config-conventional` (le nom de
    paquet nu ne résout pas depuis la racine), donc `## Commandes` a dû être
    réordonné (`npm ci` avant `pre-commit install`, sinon tout commit d'un
    clone frais entre les deux étapes échoue au hook `commit-msg`).
    `uvx pre-commit run --all-files` vert (5/5).
  - **Sécurité de chaîne d'outils (Tasks 7-9)** — CodeQL (`codeql.yml`,
    report-only, `github/codeql-action/init@v4`+`analyze@v4`) + gitleaks
    (`gitleaks.yml`, bloquant, `gitleaks/gitleaks-action@v3`,
    `GITLEAKS_VERSION: "8.30.1"` épinglé) sur push/PR ; Trivy + SBOM
    (`release.yml`, `aquasecurity/trivy-action@v0.36.0` +
    `anchore/sbom-action@v0.24.0`, `upload-sarif@v4`) par image publiée au
    tag `v*` ; Dependabot (`uv` sur `/core`, `npm` sur `/shell`,
    `github-actions` sur `/`, hebdomadaire). `.gitleaks.toml` : `[extend]
    useDefault = true` indispensable (sans lui une config personnalisée
    remplace tout le jeu de règles) + 3 exclusions justifiées par écrit (clé
    AES-GCM de test, placeholder Superset, `admin:admin` Grafana d'un
    runbook, cette dernière resserrée à `targetRules = ["curl-auth-user"]`
    dans son propre bloc pour ne pas exempter tout le fichier de toutes les
    règles).
  - **Écarts assumés avec la spec** : fichier/bloc d'exception
    `dangerouslySetInnerHTML` (ci-dessus, Task 3) ; mypy `--strict` invoqué
    par ligne de commande sur les 4 modules plutôt que par `[[tool.mypy.
    overrides]]` (Task 4) ; Trivy/CodeQL en report-only —
    `continue-on-error: true` explicitement posé sur Trivy/SBOM (décision
    Tanguy, Task 8) après qu'il soit apparu que Trivy scanne l'image
    **depuis ghcr** juste après l'avoir poussée (`push: true` sans
    `load: true`), donc un re-pull complet (11,1 Go pour `qgis-worker`,
    risque de saturation disque/timeout), et que `exit-code: "0"` seul ne
    couvre pas un échec d'infra de l'étape elle-même ; SBOM publié comme
    artefact de run par le comportement par défaut de `sbom-action`, sans
    étape supplémentaire ; gitleaks **bloquant** (seule porte non
    report-only des trois) et scannant les commits du push/PR — pas l'arbre
    de travail —, `GITLEAKS_NO_GIT` n'existant pas côté action (déviation
    assumée de la décision de planification n°6, sans conséquence pratique,
    `origin/dev` n'étant qu'à 1 commit de `main`) ; ESLint resserré à
    `recommended` + les deux règles de promesses plutôt que
    `recommendedTypeChecked` (Task 3, ci-dessus) ; `groups` retiré de
    l'entrée Dependabot `uv` (`dependency-type` non documenté pour cet
    écosystème — une config invalide y est silencieusement ignorée par
    GitHub plutôt que rejetée, piège vérifié indépendamment par
    l'implémenteur et le reviewer).
  - **Leçon récurrente de ce plan, la plus transférable** : le texte
    littéral du plan/brief était faux à de nombreux endroits sur des
    interfaces tierces, chaque fois trouvé en vérifiant contre la source
    réelle — jamais contre la doc ou la mémoire : quatre knobs de
    `gitleaks-action` (`GITLEAKS_NO_GIT` inexistant, `GITLEAKS_CONFIG` fixé
    inconditionnellement aurait cassé tout push tant que `.gitleaks.toml`
    n'existe pas, `GITHUB_TOKEN` obligatoire sur `pull_request`,
    `gitleaks-action@v2` hors support) ; la version de CLI gitleaks
    installée par défaut par l'action (8.24.3, antérieure au format
    `[[allowlists]]` introduit en 8.25.0 qu'exige `.gitleaks.toml` — la
    porte bloquante aurait échoué sur du contenu explicitement validé comme
    fixture, l'allowlist de Task 7 n'aurait jamais servi en CI) ; trois
    références d'action non épinglées ou périmées
    (`aquasecurity/trivy-action@master`, `codeql-action/upload-sarif@v3`→v4,
    `anchore/sbom-action@v0`) ; l'option `dependency-type` non supportée pour
    `uv` (Task 9, ci-dessus) ; trois entrées de hook pre-commit qui ne
    transmettaient pas les fichiers (Task 6, ci-dessus) ; et trois messages
    de commit d'affilée, dictés mot pour mot par le brief lui-même (Tasks
    8/9), rejetés par le commitlint que la Task 6 du même plan venait
    d'installer (`subject-case`).
  - **Reste non vérifiable avant un déclenchement réel** : Trivy/SBOM
    seulement au prochain tag `v*` ; Dependabot seulement à son premier
    passage planifié (hebdomadaire) ; CodeQL/gitleaks seulement au prochain
    push/PR sur ce dépôt — aucun des trois n'a pu être observé vert en
    conditions réelles pendant cette session, même précédent que les tests
    `@pytest.mark.qgis` de SP-15d.
  - **Clôture (Task 10, 2026-08-21)** — suite complète rejouée des deux
    côtés : core `uv run pytest` → **1653 passed, 153 skipped, 0 failed**
    (aucune baisse par rapport aux 1649/153/0 mesurés au début de Task 1, ni
    aux 1652 passed mesurés par Task 5 après ses propres ajouts — le delta
    restant vient de commits SP-21 concurrents, pas d'une régression SP-22),
    `ruff check`/`format --check`/`mypy --strict` (4 modules)/`lint-imports`
    verts ; shell `npm run lint`/`format:check`/`test` (**152 fichiers /
    1235 tests, chiffre identique à la référence**)/`build` verts.
    `uvx pre-commit run --all-files` : 5/5 hooks verts — **la config en
    porte 6** (`ruff-check`, `ruff-format`, `lint-imports`, `eslint`,
    `prettier`, `commitlint`) ; `--all-files` n'exerce que les 5 hooks de
    l'étage `pre-commit`, jamais `commitlint` (posé sur l'étage
    `commit-msg`, qui n'existe que lors d'un vrai commit) — ne pas lire
    cette commande comme couvrant le filet en entier.
  - **Revue finale de branche (2026-08-21)** — 1 Critical + 5 Important
    trouvés, 0 non résolu au merge. **C1** — `release.yml` posait
    `continue-on-error: true` sur les étapes Trivy et SBOM mais pas sur
    l'étape intermédiaire `Upload Trivy results`
    (`codeql-action/upload-sarif@v4`) : quand Trivy échoue (re-pull ghcr,
    cf. `### Suivis non bloquants ouverts`), le SARIF n'existe pas et cette
    étape échouait dur, contredisant le commentaire du fichier lui-même —
    même `continue-on-error: true` posé sur les trois étapes désormais.
    **I1** — la seule porte bloquante du filet sous-scannait en silence :
    `gitleaks/gitleaks-action@v3` dérive sa plage de scan de l'API GitHub
    (commits d'une PR sans pagination, 30/page ; tableau `commits` d'un
    push, plafonné à 20 par GitHub) plutôt que d'un vrai scan de fichiers —
    mesuré sur ce dépôt : PR #75 (59 commits), #74 (30), #69 (33), donc
    environ la moitié des commits de la dernière PR de release jamais
    scannée, job vert quand même. Remplacé par un appel direct au CLI
    gitleaks en conteneur (`docker run zricethezav/gitleaks:v8.30.1 dir .
    --redact --exit-code 1`) — scan de l'arbre de travail du checkout, ce
    que la décision de planification n°6 demandait dès l'origine ;
    `fetch-depth: 0` retiré (plus nécessaire, aucun `git log` impliqué).
    Vérifié dans les deux sens contre un clone propre de ce dépôt : exit 0
    sur le contenu réel (`.gitleaks.toml` toujours efficace), exit 1 sur un
    faux AWS access key injecté puis retiré. **I2** — les hooks
    eslint/prettier de `.pre-commit-config.yaml` (`files: ^shell/src/.*\.
    (ts|tsx)$`) ne couvraient qu'une fraction de ce que la CI vérifie
    (`eslint .`/`prettier --check .` depuis `shell/`, donc aussi `e2e/**`,
    `scripts/*.mjs`, `playwright.config.ts`, tout `.json`/`.css`/`.md` du
    dossier) — un fichier `shell/e2e/*.spec.ts` modifié passait le hook et
    cassait la CI. Passés en `pass_filenames: false` + `files: ^shell/.*$`,
    lançant `--fix .`/`--write .` sur tout `shell/` à chaque déclenchement
    (même périmètre que la CI par construction, plutôt qu'une regex à
    tenir manuellement synchronisée) — prouvé en stageant un fichier
    `e2e/` factice, jamais touché par l'ancien pattern, désormais reformaté
    par le hook. **I3** — `dependabot.yml` n'avait pas de `target-branch`,
    donc aurait ouvert ses PR hebdomadaires directement sur `main` alors
    que `dev` est la branche de travail (CLAUDE.md) — `target-branch:
    "dev"` ajouté aux trois entrées. **I4/I5** — cf. corrections de
    `## Commandes` ci-dessus (chiffres de test réels + `uv tool install
    pre-commit`). **M1** — `default_install_hook_types: [pre-commit,
    commit-msg]` ajouté (un `pre-commit install` nu ne posait avant que le
    hook `pre-commit`, laissant tomber `commitlint`). **M2** —
    `force-exclude = true` ajouté à `[tool.ruff]` : sans lui,
    `extend-exclude` ne protégeait `tests/test_deployability.py` que de la
    découverte par répertoire, pas d'un chemin passé explicitement — or
    c'est exactement ce que font les hooks pre-commit ; vérifié avant/après
    (`ruff check core/tests/test_deployability.py` l'analysait, puis ne
    trouve plus de fichier Python à ce chemin). **M4** — `minVersion =
    "8.25.0"` ajouté à `.gitleaks.toml`, co-localisant la contrainte de
    version réelle (format `[[allowlists]]`) avec le fichier qui la porte ;
    vérifié qu'il ne s'agit que d'un log de niveau debug, jamais un
    avertissement bloquant. **M3/M5** — cf. corrections ci-dessus et dans
    `### Suivis non bloquants ouverts`.
- **SP-23** — « Les quatre bouchons à coût faible » (étape 4 du séquencement
  du plan d'action `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
  §6, chantiers 4.18/4.6/4.15/4.16 de la vague 4) : dans les quatre cas le
  cœur savait déjà faire la chose, seule la surface exposée au shell
  manquait ou était incomplète.
  - **4.15, agrégats manquants** : quatre agrégats de plus sur
    `AggregateRequestBody`/`AggregateMeasure`
    (`countDistinct`/`median`/`percentile`/`stddev`) et un paramètre `p`
    (centile en **pourcentage**, `0 < p < 100`, jamais en fraction —
    converti en fraction seulement dans `_agg_expr`/`metricExpr`) plutôt
    que trois agrégats fixes `p50`/`p90`/`p95` (décision de spec).
    Contrat de valeur vide tranché explicitement : `countDistinct` → `0`,
    `median`/`percentile`/`stddev` → `null`, jamais `0` (une médiane
    d'ensemble vide ou un écart-type d'une ligne unique n'existent pas —
    l'indicateur (`indicator.tsx`) affiche désormais `—`, `chartOption.ts`'s
    `num()` continue de convertir `null` en `0` pour tous les types de
    graphique ECharts qu'il traite — `chartType` est un `string` libre, il
    n'y a pas de liste fermée à compter —, limite acceptée en suivi non
    bloquant). Le nouveau `resolveFlatValue` d'`indicator.tsx` ne fait pas
    que rendre « — » : il **change la valeur affichée** par l'indicateur
    pour toute source `type: "statistics"` — il lit désormais l'agrégat
    calculé par le serveur (`properties.value` de la première ligne) au lieu
    de compter les lignes de la réponse, ce qui n'avait pas de sens sur une
    réponse déjà agrégée — et rend « — » dès que la source porte des
    `measures` explicites, dont les libellés personnalisés ne garantissent
    aucune clé `value` (tiret honnête plutôt qu'une valeur devinée). Le
    comptage/somme côté client ne subsiste que pour les sources
    `features`/`static`, dont chaque ligne est une feature brute. `stddev`
    ajouté au chemin ArcGIS (`_STAT_TYPES`, `live_query.py`, natif via
    `statisticType`), les trois autres refusés proprement
    (`ArcgisQueryError`) plutôt que mal-évalués en silence — précédent
    SP-16b. **Élargissement de périmètre assumé en session** (spec §2/§4) :
    4.15 couvre les **deux** surfaces d'agrégat, pas seulement le chemin
    analytique — l'assistant de requête visuelle SP-14o compile ses
    métriques vers du SQL brut par un chemin entièrement distinct
    (`compilePipeline.ts`'s `metricExpr`/`decompileMetrics`, réciproques au
    caractère près sur les neuf fonctions) ; ce seul élargissement fait
    sortir 4.15 du calibre « S » d'origine.
  - **4.16, grains temporels manquants** : `AggregateRequestBody.bucket`
    passe de trois à six valeurs (`hour`/`day`/`week`/`month`/`quarter`/
    `year` — `DATE_TRUNC` les acceptait déjà toutes), sélecteur de grain
    ajouté à `DataSourcePanel` (désactivé sans `groupBy` à un seul champ,
    reflet direct de la garde serveur), `chartOption.ts`'s `offsetLabel`
    étiquette les six unités de la fenêtre de comparaison.
    `comparisonWindow.ts`'s `bucketFor()` **non touché** (décision de
    spec explicite) : c'est une heuristique de fenêtre de comparaison, pas
    un choix d'auteur, et l'élargir changerait le rendu de widgets déjà
    livrés.
  - **4.6, le catalogue voit les 12 types** : `resourceTypes.ts` (nouveau,
    `Record<ResourceType, string>` exhaustif, source unique pour
    `CatalogPage` et `ItemCard`) remplace le `<select>` Type à 3 options ;
    les types `alert` et `external` — jusqu'ici sans destination au clic —
    routés vers leur vraie destination réelle (`openItemAsync`, déjà câblé
    pour 5 types spéciaux, complété pour ces deux-là).
  - **4.18, historique de versions atteignable** : `GET
    /configs/{id}/revisions` et `POST /configs/{id}/rollback` existaient
    depuis SP-0, audités, mais `ItemClient` n'avait aucune des deux
    méthodes et aucune page du shell ne les appelait. `ConfigHistoryPanel`
    (nouveau, générique) monté sur les **cinq** éditeurs adossés à une
    config (app/dashboard/site, carte, dataset, pipeline, rapport) —
    décision de spec explicite, pas seulement le builder d'app : la route
    est générique, un composant unique évite quatre panneaux divergents
    plus tard. Confirmation bloquante avant restauration (pas de
    prévisualisation, pas de `Ctrl+Z` sur une restauration — deux notions
    d'annulation qui divergeraient, écarté en session) ;
    `useUndoableDraft` gagne `resetDraft` (remplace le brouillon **et**
    vide toute la pile undo — le stack ne peut pas défaire une écriture
    serveur, contrairement à `setDraft` qu'utilisent les quatre autres
    éditeurs sur un `useState` simple). **Élargissement de périmètre
    assumé en session** (spec §2/§4) : 4.18 corrige au passage un trou de
    validation que le chantier rend atteignable pour la première fois —
    `rollback_config` ne repassait par aucun validateur de payload
    (restaurer une vieille version de pipeline ou d'alerte pouvait
    ressusciter une référence vers une collection supprimée depuis, ou
    réactiver une capacité éteinte). Corrigé par
    `repo.get_revision_config` (lecture seule) + la même séquence de dix
    appels qu'`update_config` (huit `_validate_*` plus les deux
    `_require_*_enabled`, `core/app/configs/routes.py:237-246`), appelée
    **avant** l'écriture (422 si invalide, aucune version écrite). Sans
    `actor_id` sur `config_revisions` (relève du chantier 4.20, hors
    périmètre assumé). Aucune migration sur les quatre chantiers.
  - Exécution en subagent-driven-development, 19 tâches, revue par tâche
    systématique — 0 Critical/Important non résolu au merge sur
    l'ensemble. Trois trouvailles notables, aucune anticipée par le texte
    littéral du plan :
    1. **Tâche 13** — le brief demandait de revalider `rollback_config`
       avec la même séquence qu'`update_config`, ce qui inversait de fait
       une décision SP-8c délibérée (« rollback restaure une révision
       même si elle violerait désormais un scope d'extension resserré,
       comportement volontaire faute d'appelant réel ») — un test
       existant de `test_configs_extension_permissions.py` en encodait
       encore l'ancien contrat (200, pas de revalidation). Corrigé (renommé,
       422 attendu) après vérification indépendante contre la spec SP-23
       (qui nomme explicitement « portée d'extension » parmi les
       validateurs) et contre le code réel d'`update_config` — pas une
       régression, un renversement de décision assumé par la spec du jour
       même.
    2. **Tâche 15** — le brief exigeait explicitement que les nouveaux
       tests de `resetDraft` tournent sous `<StrictMode>` (précédent
       SP-19/C1 : tout le bookkeeping de refs doit se faire dans le corps
       de la fonction, jamais dans un updater passé à `setDraftState`,
       sous peine de double-exécution). Trouvé en revue de tâche
       (Important) : les deux nouveaux tests utilisaient un `renderHook`
       nu, et l'auto-revue de l'implémenteur affirmait à tort le
       contraire. Fixé en un commit séparé, re-revue clean — l'
       implémentation elle-même (jamais de fonction passée à
       `setDraftState`) était correcte depuis le début, seule la preuve
       par test manquait.
    3. **Tâche 18** — en faisant tourner la suite e2e complète pour la
       **première fois depuis les tâches 11/12** (les tâches précédentes
       ne lançaient que leurs specs ciblées), une régression préexistante
       est apparue : le `<select>` Type du catalogue rend en permanence
       un `<option value="external">Externe</option>`, cassant
       `getByText("Externe")` sans désambiguïsation dans **six** specs de
       moissonnage déjà existantes (harvest-arcgis/ckan/csw/ogc-records/
       stac/wms — violation du mode strict Playwright, 2 éléments
       correspondants). Corrigé par `.last()` (l'`<option>` précède
       toujours le badge de carte dans l'ordre du DOM), vérifié
       indépendamment correct sur les six specs par le reviewer. Commit
       séparé du livrable de la tâche (`fix(shell)` distinct de
       `test(shell)`), pour garder l'historique lisible.
       **Incident de session, distinct de la trouvaille elle-même** : le
       premier subagent implémenteur dispatché sur cette tâche a fini
       dans un état confus — son travail (`catalog.spec.ts`/`mocks.ts`/
       nouveau `config-history.spec.ts`) s'est retrouvé `git stash`é au
       lieu d'être committé, et son rapport final portait le contenu
       d'une tâche sans rapport avec celle-ci (SP-17b) — contamination
       vraisemblable d'un fichier de rapport scratch
       (`.superpowers/sdd/task-18-report.md`) réutilisé sans être vidé
       entre deux sessions de travail distinctes. Le contrôleur a
       récupéré le stash, vérifié son contenu ligne à ligne contre le
       brief (conforme) avant de le committer, plutôt que de redispatcher
       un agent sur un état déjà suspect.
  - **Preuves de sortie finales** (tâche 19) : core `uv run pytest` →
    **1673 passed, 153 skipped, 0 failed** ; `ruff check`/`ruff format
    --check`/`mypy --strict` (4 modules)/`lint-imports` verts ; couverture
    core **85,17 %** (seuil 85). Shell `npm run lint`/`format:check` verts,
    `npm run test` → **155 fichiers / 1300 tests** ; `npm run build` vert ;
    `npm run e2e` → **105 passed, 4 skipped, 0 failed** ; couverture shell
    **88,96 %** (seuil 88, mesurée après nettoyage de `dist/`/`dist-export/`
    — même piège documenté par SP-22 tâche 5, artefacts de build locaux
    gitignorés comptés comme source non couverte par la config `vitest`
    de ce dépôt). `uvx pre-commit run --all-files` : 5/5 hooks verts.
    OpenAPI/types TS confirmés synchronisés — la commande littérale du
    brief (`uv run python scripts/export_openapi.py`) échoue seule
    (`ModuleNotFoundError: app`, le script n'insère pas le cwd sur
    `sys.path` en exécution directe, et `app` n'est pas installé en mode
    editable) et nécessite l'incantation réelle de `ci.yml`
    (`PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY` de test) — écart entre le
    texte du brief et le job CI réel, non documenté avant cette tâche.
  - **Revue finale de branche (2026-08-22)** — 0 Critical, 4 Important, 14
    Minor ; les quatre Important sont tous des **croisements entre les quatre
    chantiers**, structurellement invisibles à une revue par tâche, et aucun
    n'était une régression d'une tâche isolée. **I1** — `_measure_label` ne
    connaissait pas `p` : deux mesures `percentile` sur le même champ (P50 +
    P90 côte à côte, le cas d'usage canonique du centile, et exactement ce que
    le nouveau `DataSourcePanel` invite à construire) dérivaient le même
    libellé, le SQL calculait bien les deux et **le pivot en perdait une en
    silence** (mesuré) — `p` entre désormais dans le libellé dérivé
    (`percentile50_amount`), aux trois sites qui dupliquaient cette dérivation,
    ramenés à une seule définition partagée. **I2** — le garde-fou de saisie du
    centile (`PercentileInput`) avait été écrit par la tâche 10 en réaction à ce
    défaut exact sur la surface de l'assistant de requête visuelle, et jamais
    reporté sur les deux champs centile de `DataSourcePanel` : vider le champ y
    laissait `agg: "percentile"` sans `p`, donc une config **enregistrable et
    publiable** que le cœur refuse en 422 pour tous ses lecteurs (la tâche 5
    était déjà committée quand la tâche 10 a trouvé le problème — aucune revue
    par tâche ne pouvait recroiser les deux) ; le composant est désormais
    partagé par les deux surfaces. **I3** — `rollbackConfig` n'invalidait pas la
    clé react-query de sa config, là où les quatre `useSaveX` du dépôt le font
    tous : sur les trois éditeurs à seed inconditionnel, le premier refetch
    après restauration (un simple alt-tab, `refetchOnWindowFocus` étant à son
    défaut) ramenait un contenu différent du cache et **écrasait le brouillon**
    sans rien dire ; l'invalidation est désormais portée par la restauration
    elle-même, dans le panneau, pas dupliquée sur les cinq pages. **I4** —
    l'élargissement du jeu d'agrégats a ouvert deux trous jumeaux dans
    `AlertRule` : `p` n'était pas validé à la sauvegarde (une règle
    `percentile` sans `p` passait le 422 puis échouait **à chaque tick de son
    cron, pour toujours** — le mode d'échec que le validateur voisin
    `_require_valid_message_template` existe précisément pour supprimer), et
    `float(None)` sur un agrégat légitimement `NULL` (`stddev` sur une ligne
    unique, `median` sur une colonne texte — deux cas mesurés, impossibles
    avant SP-23 où les cinq agrégats étaient tous `COALESCE(…, 0)`) sortait en
    « erreur interne » opaque au lieu d'un `AlertEvaluationError` explicite,
    contre la règle établie par SP-16b. Une seule passe de correction (6
    commits, I1→I4 + trois corrections d'affirmations fausses de cette entrée
    CLAUDE.md elle-même : le compte des validateurs de rollback, le nombre de
    types de graphique, et le silence sur le fait que le nouveau
    `resolveFlatValue` d'`indicator.tsx` **change la valeur affichée** de toute
    source `statistics` et ne fait pas que rendre « — »), puis **re-revue
    complète : 0 Critical, 0 Important, 5 Minor** — les huit points fermés,
    vérifiés un par un contre le code plutôt que sur parole (OpenAPI/TS
    régénérés et `diff` vide, mesuré ; site d'appel SP-14o du composant partagé
    inchangé et ses tests pré-existants verts ; surplus du prédicat
    d'invalidation audité clé par clé).
  - **Test instable de CI corrigé au passage** (hors périmètre SP-23, mais il
    bloquait le merge) : `test_copilot_routes.py::test_synchronous_provider_call_does_not_block_the_event_loop`
    (SP-20) bornait la durée du bloc concurrent à 1,8 × le délai du faux
    fournisseur, ce qui **mesure la vitesse de la machine** et non la propriété
    visée. Rouge deux fois de suite en CI (0,87 s puis 0,79 s contre un seuil de
    0,72 s), vert sur les runs précédents. L'arithmétique tranche : une vraie
    sérialisation coûterait au moins 2 × 0,4 s = 0,8 s, donc les appels se
    recouvraient bel et bien — ce qui échouait, c'était la marge face au surcoût
    CPU sérialisé des trois requêtes sous instrumentation de couverture sur un
    runner partagé. Le faux fournisseur enregistre désormais l'intervalle
    monotone de chaque appel abouti et le test assère leur **recouvrement** :
    assertion strictement plus forte et insensible à la charge, vérifiée dans
    les deux sens (une attente remplacée par un `time.sleep` bloquant la fait
    échouer). **Leçon transférable** : une assertion de durée totale ne prouve
    jamais une propriété de concurrence, elle mesure la machine ; mesurer le
    recouvrement des intervalles, lui, la prouve.
  - **Preuves de sortie après correction** (2026-08-22, contrôleur) : core
    `uv run pytest` → **1675 passed, 154 skipped, 0 failed**, couverture
    **85,16 %** (seuil 85) ; `ruff check`/`ruff format --check`/`mypy --strict`
    (4 modules)/`lint-imports` verts. Shell `npm run test` → **155 fichiers /
    1302 tests**, couverture **89,24 %** (seuil 88) ; `npm run lint`/
    `format:check`/`build` verts ; `npm run e2e` → **105 passed, 4 skipped, 0
    failed**. `uvx pre-commit run --all-files` : 5/5 hooks verts.
- **SP-24** — Carte interrogeable (chantier **4.1** du plan d'action
  `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` §6, vague 4 ;
  constats **D1** — aucun popup, nulle part — et **D2** — interactivité et
  passage à l'échelle mutuellement exclusifs — de la spec §7) : un lecteur
  peut cliquer une entité sur une carte publiée et voir ses attributs, y
  compris quand le jeu de données est assez gros pour être tuilé. **Deux
  élargissements de périmètre assumés et tranchés en session** (spec §2/§4) :
  (1) les tuiles vectorielles passent désormais par le cœur
  (`GET /collections/{id}/tiles/{z}/{x}/{y}.mvt`, `ST_AsMVT` sous
  `rls_scope`+`can()`) plutôt que par Martin — pas un détour : c'est ce qui
  donne à une couche tuilée un `collectionId`, donc un schéma de champs pour
  le popup, une porte d'autorisation, et le socle dont SP-25 (symbologie)
  aura besoin ; (2) **changement cassant assumé** : la route publique Martin
  (labels Traefik `/tiles`) est retirée dans ce SP même, pas en suivi —
  Martin se connecte en propriétaire des tables (donc hors RLS) et n'a
  aucune notion de collection ni de `can()`, le trou se ferme dans le même
  chantier que la capacité qui le rendait tentant.
  - **Cœur** : `core/app/features/tiles.py` (helpers purs de validation
    z/x/y + construction du SQL MVT, route montée inconditionnellement,
    **aucune entrée `audit_log` par tuile** — décision de spec assumée, une
    vue de carte produit des centaines de tuiles) ; index GiST idempotent
    dans `apply_collection_ddl` + migration **0028** (rattrapage des
    collections déjà enregistrées — downgrade vérifié non destructif par le
    contrôleur sur une base jetable à 500 lignes réelles, précisément le
    mode d'échec que la migration 0024/SP-17b avait laissé passer faute
    d'être testée sur base non vide) ; `PopupConfig`/`PopupField` sur
    `MapLayer`, des deux côtés du fil ; OpenAPI/types TS régénérés.
  - **Shell** : `popupTemplate.ts` (module pur, interpolation `${expression}`
    CEL dans un gabarit markdown — seconde syntaxe d'expression du dépôt,
    divergence assumée par la spec — scanner de `}` fermante conscient des
    guillemets CEL, sans quoi une expression telle que `${ "}" }` referme le
    placeholder trop tôt et laisse fuiter le reste littéralement) ;
    `popupContent.ts` (résout `PopupConfig`+propriétés → titre/lignes,
    distingue `fields: []` — l'auteur a tout retiré — de l'absence de
    `fields` — montrer tout : un défaut trouvé en revue, `PopupEditor`
    produisant justement `fields: []` en décochant le dernier champ,
    exposait sinon toutes les propriétés y compris internes) ; `MapPopup.tsx`
    (composant présentationnel) branché dans `MapView` (clic sur couche
    `vector`/`feature`, jeton de session sur `transformRequest` pour toute
    requête `/collections/`) ; `PopupEditor.tsx`, éditeur d'auteur **partagé
    par les deux surfaces** — `LayersPanel` de l'éditeur de cartes ET
    `PropsPanel` du widget carte des apps/dashboards/sites — le partage
    referme explicitement l'écart I2 de la revue finale SP-23, où un
    garde-fou écrit pour une surface n'avait jamais été reporté sur sa
    jumelle ; son scanner de gabarit réutilise `closingBrace` exporté de
    `popupTemplate.ts` plutôt que de le redupliquer (même classe de bug que
    la trouvaille I2 ci-dessus, fermée avant même d'exister sur cette
    seconde surface). `configSchema`/`WidgetPropDescriptor` délibérément non
    touchés : le copilote SP-20 ne peut pas écrire `popup` sur le widget
    carte (`applyClientOp` filtre par schéma, aucune forme n'existe pour un
    objet imbriqué) — décision assumée de la tâche 13.
  - **Sélecteur de couches** : Martin totalement retiré de
    `listLayerSources`/`LayerPicker` (`fetchMartinSources` supprimé, une
    seule entrée tuilée `service: "core"` par collection, portant
    `collectionId`/`geometryKind`/`pkColumn`) ; route publique et
    `VITE_MARTIN_URL`/`martinUrl` retirés du compose de prod et du shell
    (garde-fou de déployabilité SP-21 resté vert, 31/31).
  - **Preuve de sortie E2E réelle, pas simulée** : `core/scripts/
    dump_mvt_fixture.py` exécuté une fois contre PostGIS réel produit une
    fixture MVT binaire committée (`shell/e2e/fixtures/world-tile.mvt`),
    `map-popup.spec.ts` clique un vrai canvas MapLibre WebGL (patron déjà
    prouvé par `analytics-context.spec.ts`) et vérifie popup renseigné +
    jeton de session sur la requête de tuile — précédent SP-15d (5 tests
    qgis jamais exécutés pour de vrai) explicitement non rejoué.
  - **2 défauts réels cross-tâches trouvés et corrigés par la preuve E2E**
    (tâche 16), tous deux invisibles à une revue par tâche : le chemin de
    LECTURE d'une carte enregistrée (`toFrontLayer`/`RawMapLayer` dans
    `itemClient.ts`) ne relisait jamais `popup`/`collectionId`/
    `geometryKind`/`pkColumn` — toute carte rechargée avec un popup
    configuré ne pouvait jamais l'afficher (le cœur round-trippe déjà ces
    champs correctement ; bug de lecture seul côté shell, corrigé + 2 tests
    de régression) ; le mock E2E `**/collections*` renvoyait `[]` par défaut,
    périmé depuis le retrait du repli catalogue Martin (tâche 15, commit
    57fc36c) sans mise à jour du mock ni E2E complet lancé à l'époque —
    cassait une spec pré-existante (`map-editor.spec.ts`), corrigé pour
    miroiter le vrai comportement serveur.
  - Exécution en subagent-driven-development, 17 tâches, revue par tâche
    systématique. Défauts Important trouvés et corrigés en cours de route
    (aucun Critical sur l'ensemble des 17 tâches) : I2-T8 (`stringify` non
    total sur une valeur circulaire) et I2-T8bis (scanner d'accolade non
    conscient des guillemets CEL, cf. ci-dessus) ; I1-T9 (fields:[] vs
    absence, exposition d'information — cf. ci-dessus) ; I1-T10 (cast
    `AddLayerObject` inerte retiré, typage affiné par branche, restauration
    prouvée sur les 3 branches par injection d'un champ bidon) ; I1-T11 (un
    popup figé au lieu de fermé quand une couche perd sa config popup —
    fermé par anticipation du scénario que la tâche 12 allait rendre
    atteignable) ; un Important étiqueté **plan-mandated** en tâche 13 (2
    tests du widget carte asseraient sur un état posé par un composant
    chargé en `lazy()` sans l'attendre — ne passaient que par dépendance à
    l'ordre d'exécution dans le fichier, rouges en isolation ; texte du
    brief lui-même, corrigé sans repasser par l'utilisateur, cohérent avec
    le précédent établi tout du long de ce SP de corriger sans re-demander
    une trouvaille contre le texte du plan).
  - Preuves de sortie (2026-08-22) : core `uv run pytest` (PostGIS réel,
    conteneur `postgis-test`) → **1863 passed, 5 skipped** — les 5 skips
    sont tous le marqueur `qgis` (`CORE_TEST_QGIS_WORKER_URL` non défini),
    **aucun skip `postgis`** : les preuves des tâches 3/4/5 ont bien tourné
    pour de vrai, précédent SP-15d non rejoué ; `ruff check`/`ruff format
    --check`/`mypy --strict` (4 modules)/`lint-imports` verts ; couverture
    **92,77 %** (seuil 85). Shell `npm run lint`/`format:check` verts,
    `npm run test` → **159 fichiers / 1377 tests**, couverture **89,53 %**
    (seuil 88) ; `npm run build` vert ; `npm run e2e` → **107 passed, 4
    skipped, 0 failed**. `uvx pre-commit run --all-files` : 5/5 hooks
    verts. OpenAPI/types TS confirmés synchronisés (`git status
    --porcelain` vide sur les deux).
  - **Revue finale de branche (2026-08-23)** : 0 Critical, 5 Important, tous
    invisibles à une revue par tâche, tous corrigés — **C1** `isHostedCoreUrl`
    ne comparait pas le chemin de base de `VITE_CORE_URL` : l'overlay prod
    (`docker-compose.prod.yml`) le pose à `https://hôte/api`, donc une vraie
    URL de tuile y est `/api/collections/…`, jamais `/collections/…` — le
    jeton de session ne s'attachait **jamais** en production, invisible en
    test où toutes les URL de cœur étaient sans chemin. Comparaison étendue
    au chemin de base. **I1** géométrie inconnue/mixte (`geometryKind`
    absent — colonne PostGIS non typée, cas courant d'une ingestion mêlant
    Point/MultiPoint ou LineString/MultiLineString) posait un unique layer
    "fill" : une couche de points ou de lignes ne rendait **rien**,
    silencieusement, sans erreur. Pose désormais trois sous-couches typées
    (`{id}__point/line/polygon`), chacune filtrée par
    `["geometry-type"]`, paint scindé par préfixe (`circle-`/`line-`/
    `fill-`), popup toujours résolu par l'id de la COUCHE de la config (pas
    de la sous-couche), rollback des sous-couches restantes si l'une échoue
    à l'ajout. **I3** aucun plafond de coût sur la route tuiles, atteignable
    anonymement sur une collection publique et sans aucune trace d'audit
    (décision de spec §3.1) : un seul GET sur une collection dense scannait
    et agrégeait toute la table en mémoire. `LIMIT :max_features` (5000,
    posé DANS la sous-requête MVT — c'est le nombre de lignes lues qu'il
    faut borner, pas la sortie de l'agrégat, toujours une seule ligne) +
    `statement_timeout` transaction-local (10s, `set_config(..., true)`,
    même patron que `rls_scope`), même classe de garde que le sandbox SQL
    analyste transposée à Postgres. **I4** la prop `exprContext` de
    `MapView` (Task 8/9) n'avait aucun site de montage réel capable de la
    remplir (ni variables ni contexte d'app dans `MapEditorPage`, ni
    ExprContext de l'ActionBus exposé par `mapWidget`/`ExplorerDrawer`) —
    une capacité annoncée et vide à l'exécution. Retirée ; `resolvePopupContent`
    ne prend plus de contexte externe, construit `{vars: {}, user: {name:
    ""}}` en interne — le seul vocabulaire d'un gabarit de popup est
    `record.*`. **I5** chaque frappe dans `PopupEditor` produisait un
    nouveau tableau `config.layers` qui détruisait/recréait TOUTES les
    sources/couches MapLibre (scintillement, re-requêtes de tuiles, refetch
    GeoJSON complet pour une couche `feature`) pour un simple edit de
    popup, qui n'affecte que le rendu React d'un clic déjà survenu. `layersKey`
    mémoïsé (projection excluant `popup`) découple désormais l'effet
    d'application des couches des edits popup-only. Session interrompue en
    cours de correction (fix déjà écrit mais laissant le build shell cassé —
    signature de `resolvePopupContent` non alignée avec son site d'appel) ;
    reprise par une session suivante, qui a complété le fix et ajouté la
    couverture de test manquante pour les 5 comportements ci-dessus, avec
    vérification RED→GREEN réelle (`git stash` du fichier de production pour
    confirmer l'échec contre le code d'avant fix, pas seulement des tests
    écrits après coup contre du code déjà correct). Preuves de sortie
    post-correction : core `uv run pytest` (PostGIS réel) → **1868 passed, 5
    skipped**, couverture **92,77 %** (seuil 85) ; shell `npx vitest run` →
    **159 fichiers / 1387 tests** (+10 vs Task 17), couverture **89,56 %**
    (seuil 88) ; `npm run build`/`tsc --noEmit`/lint verts ; OpenAPI/types TS
    inchangés (fix interne, aucune surface API modifiée) ; `uvx pre-commit
    run --all-files` 5/5 verts. **SP-24 clos pour de bon.**
- **SP-25** — Symbologie dans l'éditeur de cartes (chantiers **4.2**
  « Symbologie » et **4.3** « Classes et palettes » du plan d'action
  `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` §6, vague 4, lot
  Carte, suite directe de SP-24 dont le `collectionId`/`geometryKind` posé
  sur chaque couche tuilée est ce qui permet ici de calculer des bornes de
  classes sans charger les features) : une couche carte (`LayersPanel` de
  l'éditeur standalone **et** le widget carte des apps/dashboards/sites)
  gagne une symbologie déclarative — couleur catégorielle/continue/classée
  (quantile, intervalle égal, seuils naturels Jenks, 2 à 9 classes) et
  taille continue —, compilée en paint MapLibre à l'affichage au lieu d'un
  `paint` brut écrit à la main, avec palettes curatées + une palette dérivée
  du thème (`theme-primary`, widget carte uniquement). **Élargissement de
  périmètre assumé dès la spec** (§2, décision de session) : unification
  des deux surfaces sur un seul type `LayerSymbology` et un seul composant
  d'édition partagé plutôt que deux mécanismes parallèles — précédent
  explicitement invoqué, l'écart I2 de la revue finale SP-23 (garde-fou
  écrit sur une surface, jamais reporté sur sa jumelle).
  - **Cœur** : capacité `sample` sur `AggregateRequestBody`/
    `run_collection_aggregate` (`USING SAMPLE n ROWS`, 1-2000, exclusive de
    `groupBy`/`bins`) — seule addition serveur nécessaire, le quantile et
    l'intervalle égal se calculent avec les primitives déjà existantes ;
    `MapLayer.symbology: dict | None` sur `configs/schemas.py`, même
    précédent que `paint`/`popup` (SP-24).
  - **Shell** : `builder/widgets/palette.ts` (palettes curatées + rampe
    séquentielle dérivée du thème, lerp RGB maison) ; `ItemClient.
    sampleCollectionField` ; `mapSymbology.ts` étendu (classification
    quantile/intervalle égal côté client, Jenks par programmation dynamique
    de Fisher, extension de `buildMapPaint`/`buildLegend` pour le cas
    classé — expression MapLibre `step`) ; `MapSymbologyEditor.tsx`
    (composant d'édition partagé, host-agnostic, même précédent que
    `PopupEditor.tsx` SP-24) monté à la fois dans `LayersPanel.tsx`
    (éditeur de carte standalone) et `mapWidget.tsx` (widget carte des
    apps/dashboards, `PropsPanel`). **Changement cassant assumé** (spec §7,
    même précédent que le retrait de Martin en SP-24) : `mapWidget.tsx`
    abandonne `props.encodings`/`useNumericDomain`/ses deux `useQuery` de
    domaine calculés à chaque rendu au profit du même champ `symbology`
    figé à l'enregistrement — toute app déjà publiée avec une symbologie de
    widget carte perd cette configuration au prochain chargement. Domaines
    et bornes calculés une fois et figés dans la config à l'enregistrement,
    jamais recalculés au rendu (y compris pour une carte publique anonyme,
    cohérent avec la garde de coût I3/SP-24). Threading de `Theme` à travers
    `WidgetDefinition["PropsPanel"]` (`AppBuilderPage` → `PropsPanel.tsx` →
    `def.PropsPanel`), changement additif par typage structurel vérifié sur
    les ~22 autres widgets (aucun ne déstructure `theme`, tous continuent de
    compiler sans y toucher).
  - **Déviation assumée vs. le texte littéral de la spec (§3.7)** : la
    spec demandait « un bloc symbologie par couche vector/feature » dans
    `LayersPanel` ; en pratique `LayerSymbologyEditor` retourne `null` sans
    `collectionId` (`shell/src/map/LayersPanel.tsx:57`), qui n'existe que
    pour les couches `kind: "vector"` — une couche `feature` (tuiles
    externes, GeoJSON brut) n'a donc **aucun** éditeur de symbologie
    fonctionnel dans l'éditeur standalone, contrairement au bloc popup
    voisin qui, lui, fonctionne sans collection (saisie manuelle des noms
    de champs). Documenté par le code lui-même comme une limite de
    périmètre, pas une régression — nécessite une décision produit non
    couverte par les Global Constraints du plan.
  - **Déviation assumée sur le widget carte (Task 11)** : Jenks y est
    proposé dans la spec au même titre que dans l'éditeur standalone, mais
    `mapWidget.tsx`'s `sampleField` ne résout aucun `collectionId` réel pour
    ce host (chemin distinct et non unifié avec `LayersPanel`, spec §1) —
    l'option « Seuils naturels (Jenks) » y est donc masquée
    (`jenksAvailable={false}` sur `MapSymbologyEditor`, plutôt que de
    l'offrir puis échouer à l'usage). Trouvé et corrigé en revue finale de
    branche (I5, cf. ci-dessous), pas anticipé par le texte littéral de la
    spec.
  - Exécution en subagent-driven-development, 11 tâches d'implémentation
    (Tasks 1-11) + Task 12 (E2E) + revue finale de branche, revue par tâche
    systématique (0 Critical/Important non résolu sur les 12 tâches).
    **Task 12 a trouvé et corrigé 2 bugs réels hors de son propre
    périmètre**, invisibles à
    toute revue par tâche antérieure puisqu'elle est le premier point du
    plan à faire tourner la suite E2E complète : (1) `toFrontLayer()`
    (chemin de lecture `GET /configs/{id}` d'`itemClient.ts`) ne
    round-trippait jamais `MapLayer.symbology` vers le front — même classe
    de bug que le fix `popup` de SP-24 — corrigé en miroir exact du même
    patron de spread conditionnel ; (2) régression préexistante dans
    `analytics-context.spec.ts` (3 tests SP-14h) jamais rejoué contre le
    changement cassant de la Task 11 (`props.encodings`→`props.symbology`,
    domaine catégoriel `{values:[]}` sans clic explicite « Recalculer les
    classes » → expression MapLibre dégénérée → couche silencieusement
    absente) — corrigé en ajoutant les clics de recalcul manquants aux 3
    tests (code de production intouché, séquence d'interaction E2E mise à
    jour pour la nouvelle UX intentionnelle). Suite E2E complète restaurée
    à 108 passed / 4 skipped / 0 failed (référence SP-24 107 + cette
    nouvelle spec = 108).
  - **Revue finale de branche** (opus) : 1 Critical (C1) + 6 Important
    (I1-I6) + 11 Minor. **C1** — un domaine de symbologie jamais recalculé
    ou dégénéré (catégoriel vide, champ vidé avec un domaine périmé, bornes
    dupliquées issues de données à égalité/constantes) faisait émettre à
    `buildMapPaint` une expression MapLibre invalide, qui lève à
    `map.addLayer` — silencieusement avalée par le `try/catch` existant de
    `MapView` : la couche entière disparaît, aucun signal utilisateur.
    I1 — `quantileBreaksFromRow`/`jenksBreaks` produisaient des bornes
    `NaN`/`undefined` sur une collection vide/trop petite, sérialisées en
    silence en `null`. I2 — l'id du `datalist` de `MapSymbologyEditor` était
    une constante globale, cassant l'autocomplétion de champ dès 2 couches
    stylées (même classe que I2/SP-23 — un garde-fou écrit sur une surface,
    jamais reporté sur sa jumelle, `PopupEditor` avait déjà `useId()`). I3 —
    `recomputeSize` n'avait aucun `catch` (contrairement à `recomputeColor`).
    I4 — `effectivePaint` calculait un seul objet paint par couche pour un
    `geometryKind` deviné, donc une couche tuilée à géométrie mixte
    (découpage 3 sous-couches de SP-24/I1) n'obtenait jamais que du paint
    `fill-*` — les sous-couches `circle-`/`line-` restaient silencieusement
    non stylées. I5 — `mapWidget`'s `runStatistics` codait en dur
    `layer: ""` et n'avait aucun repli sans `datasetId` (source adossée à
    une simple collection), plus Jenks proposé là où il ne peut pas
    fonctionner (limite de périmètre sanctionnée par le plan, mais l'option
    aurait dû être masquée — cf. déviation ci-dessus). I6 — un
    `MapEditorPage.test.tsx` flaky à ~25 % (sans rapport avec SP-25,
    préexistant, mais porte rouge sur le merge de cette branche).
  - **Fix round 1** (commit `014bd04`) : C1+I1-I6 corrigés en une seule
    passe TDD. `normalizeDomain` (nouvelle fonction pure, porte partagée
    appelée par `buildMapPaint` **et** `buildLegend`) rejette un domaine
    catégoriel vide, des bornes non finies, ou des bornes qui, après
    dédoublonnage des égalités adjacentes, comptent moins de 2 valeurs
    distinctes ou ne sont pas strictement croissantes — dégradation
    gracieuse (moins de classes utilisables) plutôt que rejet total sur une
    égalité partielle. 161 fichiers / 1454 tests (+27), E2E 108/4/0
    (référence inchangée), preuve RED→GREEN pour C1 via `git stash` ciblé
    (17 échecs avant fix → 0 après), I6 rejoué 10/10 vert en boucle.
  - **Re-revue** (opus) : 6/7 fermés correctement (I1-I6). **C1 partiellement
    fermé** — trou de bord trouvé dans le dédoublonnage du round 1 lui-même :
    un domaine qui se réduit à exactement 2 bornes distinctes (1 classe)
    passait encore la garde (seul « < 2 bornes » était rejeté, pas « < 3 »),
    et `buildMapPaint` en tirait une expression `step` à 2 arguments — le
    minimum MapLibre en exige 4 — reproduit empiriquement par le
    re-reviewer contre le vrai parseur `@maplibre/maplibre-gl-style-spec`,
    même symptôme original que C1 via son propre déclencheur n°3 (données à
    égalité/constantes), atteignable par n'importe quelle colonne de
    comptage/note avec assez de valeurs au minimum. 2 nouveaux Minor
    signalés (N2, N3, cf. ci-dessous), non corrigés, même disposition que
    la liste Minor de la première passe.
  - **Fix round 2** (commit `cacddb9`, C-new seul) : seuil de dédoublonnage
    de `normalizeDomain` relevé de `< 2` à `< 3` bornes distinctes (Option
    A — la porte partagée déjà appelée par `buildMapPaint` et `buildLegend`,
    donc le fix reste symétrique par construction sans toucher `buildLegend`
    séparément). 161 fichiers / 1461 tests (+7), nouveaux tests validant
    l'expression `step` produite/rejetée contre le vrai
    `@maplibre/maplibre-gl-style-spec` (`createExpression`), pas seulement
    une assertion de forme. E2E non rejoué pour ce fix pur de fonction
    (aucune surface visible au DOM touchée), explicitement noté comme tel.
    **0 Critical/Important ouvert à ce stade.**
  - **Preuves de sortie finales** (Task 13, 2026-08-23) : core
    `uv run pytest` (PostGIS réel) → **1878 passed, 5 skipped, 0 failed**
    (référence exacte de fin de Task 3, 0 régression), couverture **93 %**
    (seuil 85) ; `ruff check`/`ruff format --check`/`mypy --strict` (4
    modules)/`lint-imports` verts. Shell `npx vitest run` → **161 fichiers /
    1461 tests**, couverture **89,64 %** (seuil 88, mesurée après
    nettoyage de `dist/`/`dist-export/`, piège documenté SP-22/23/24) ;
    `npm run lint`/`format:check`/`build` verts ; `npm run e2e` → **108
    passed, 4 skipped, 0 failed** (référence SP-24 107 + spec
    `map-symbology.spec.ts` = 108, match exact). Garde-fou de déployabilité
    (`test_deployability.py`) → **31/31 verts**, sans fix — ce plan n'ajoute
    aucune variable d'env/service/bucket. `uvx pre-commit run --all-files` :
    5/5 hooks verts. OpenAPI/types TS confirmés synchronisés (`git status
    --porcelain` vide sur les deux, régénérés dès Task 3, rien n'a dérivé
    depuis). **Liste Minor reportée en suivi non bloquant** (M1-M11 du
    round 1 + N2/N3 de la re-revue) : cf. `### Suivis non bloquants ouverts`.
    **SP-25 clos.**
- **SP-26** — Durcissement avant v0.1 publique (vague 3 du plan d'action
  `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` §6) : ferme les 7
  chantiers restants de cette vague (3.2, clé maître au démarrage, déjà
  fait avant SP-26, non retouché) — renumérotés par la spec en 3.1, 3.3,
  3.4, 3.5a/3.5b/3.5c (3.5 bundlait 3 mécanismes indépendants), 3.6, 3.7,
  3.8.
  - **3.6, conteneurs non-root** : 7 des 8 images (core, export-worker,
    appexport-standalone, appexport-runtime-builder, qgis-worker, backup,
    shell) passées en utilisateur non-root, `HOME` pinné avant les étapes
    de build DuckDB/GRASS/Playwright partout où nécessaire (même
    précédent que SP-15d/SP-17a pour la survie du cache local) ;
    `postgis` vérifié déjà non-root au niveau process serveur (`gosu` de
    l'entrypoint officiel), non modifié. 2 bugs réels trouvés et corrigés
    en tâche, invisibles au texte littéral du plan : `shell` (nginx)
    plantait au démarrage (`/run/nginx.pid` permission denied) ;
    `backup`'s vrai point de montage runtime `/backup/archives` était
    root-owned et non inscriptible.
  - **3.1, mode mock interdit hors dev** : `CORE_AUTH_MODE=mock` (qui
    donnait `bootstrap_admin=True` à tout Bearer non vide sans aucune
    vérification d'environnement, C6 de la revue de projet 2026-08-20)
    refuse désormais de démarrer sans `CORE_ENV=development` explicite —
    garde fail-fast au boot, même emplacement/patron que
    `load_master_key()`.
  - **3.5a, format d'erreur RFC 7807 unique** : `application/problem+json`
    sur toute l'API via 3 handlers d'exception globaux
    (`ValidationHTTPException`/`HTTPException`/`Exception` bare), nouveau
    module `core/app/errors.py` hors contrat de couches (précédent
    `app.db`/`app.observability`). Erreurs de validation structurées
    migrées vers un membre d'extension `errors` au premier niveau — plus
    jamais imbriquées sous `detail`, qui reste une chaîne partout
    (changement cassant scopé à 2 sites shell). Diff OpenAPI/TS **vide**,
    vérifié correct et non un oubli : aucune route de ce dépôt ne déclare
    `responses=` explicite, donc aucun handler d'exception global ne peut
    apparaître dans le schéma documenté.
  - **3.4, rate limiting différencié** : middleware ASGI en mémoire par
    process, clé = en-tête `Authorization` brut (pas d'identité vérifiée
    — tourne avant l'injection de dépendances FastAPI, et `/mcp` est un
    mount ASGI brut sans DI du tout), 4 groupes de budget (sql=10/llm=20/
    jobs=15/harvest, initialement toutes routes puis resserré en revue
    finale aux seules routes d'écriture — cf. ci-dessous), fenêtre
    glissante 60s. Referme le suivi non bloquant SP-20 sur l'absence de
    rate limiting applicatif sur `/copilot/turn` (désormais dans le
    groupe `llm`, avec `/mcp`).
  - **3.5b, arrêt propre `cdc-worker`** : `stream_changes()` acceptait
    déjà un paramètre `should_stop`, jamais branché — SIGTERM positionne
    un flag vérifié à chaque itération, puis un flush final avant sortie
    pour ne pas perdre les lignes bufferisées non encore dues à l'âge
    (I11, revue de projet 2026-08-20).
  - **3.5c, `ErrorBoundary` applicatif** : nouveau boundary racine
    (`shell/src/AppErrorBoundary.tsx`), distinct du `WidgetErrorBoundary`
    scopé par widget (`WidgetHost.tsx`, non touché) — toute exception de
    rendu ailleurs (chrome builder, pages, panneaux) produisait un écran
    blanc (I12, revue de projet 2026-08-20). Posé autour
    d'`AuthProvider`/`QueryClientProvider`, pas à l'intérieur, pour
    attraper aussi un crash d'initialisation des providers eux-mêmes.
  - **3.3, CSP/Permissions-Policy/compression** : étend le middleware
    `security-headers` Traefik existant (pas un nouveau) +
    `shell/nginx.conf` (sert aussi les exports statiques/autoportés hors
    Traefik). **CSP livrée en Report-Only, jamais basculée en
    enforcing** — repli explicitement sanctionné par le plan : aucun
    binaire Chromium disponible dans cet environnement pour la
    vérification empirique préalable requise (Playwright et
    chrome-devtools-mcp ont échoué au lancement). 1 bug YAML réel corrigé
    dans le texte littéral du brief (guillemets manquants sur la valeur
    CSP, `data: blob:` casse le parse YAML). 4 bloqueurs concrets déjà
    identifiés pour la bascule enforcing, documentés en commentaire
    (`docker-compose.prod.yml` + renvoi depuis `shell/nginx.conf`) plutôt
    que laissés à redécouvrir : tuiles WMS/WMTS et terrain externes
    bloquées par `img-src`, tileset 3D externe bloqué par `connect-src`,
    widgets d'extension tiers bloqués par `script-src 'self'`,
    `nginx.conf`'s `connect-src 'self'` faux hors overlay prod (shell/core
    sur des origines différentes sur le compose de base).
  - **3.7, notification des alertes SLO** : point de contact webhook +
    politique de routage (dossier SLO), Step 1 du brief empiriquement
    vérifié contre l'image réelle (`grafana/otel-lgtm:0.11.4`, Grafana
    12.0.1) — expansion `${VAR}` native confirmée. **Déviation réelle et
    vérifiée par rapport au texte littéral du brief** : le défaut
    `${GRAFANA_ALERT_WEBHOOK_URL:-}` (chaîne vide) proposé fait planter
    tout le conteneur au démarrage (Grafana exige une URL non vide même
    pour un contact point censé rester inerte) — corrigé par un défaut
    syntaxiquement valide mais délibérément inatteignable
    (`http://127.0.0.1:1/grafana-alert-webhook-not-configured`).
    **Preuve de bout en bout réellement observée** : POST réel reçu par
    un listener HTTP local via `host.docker.internal` après dépause
    temporaire de la règle `test-alert-do-not-keep-in-prod` déjà présente
    dans `rules.yaml` pour cet usage, alerte passée `active` dans l'API
    Alertmanager puis arrêtée après repause, `git diff` sur `rules.yaml`
    confirmé vide.
  - **3.8, E2E sur OIDC réel** : nouvelle suite `shell/e2e-oidc/` contre
    une vraie stack (postgis+keycloak+core en `CORE_AUTH_MODE=oidc`+shell,
    nouveau job CI dédié) — **preuve de bout en bout réellement obtenue**,
    pas seulement affirmée : 2 specs (login+logout) passées 4 fois de
    suite en local, 0 échec. Referme le suivi non bloquant SP-20 sur
    l'absence de preuve bout-en-bout navigateur+iframe+Keycloak, et le
    précédent SP-15d/SP-17a-Task-6 (un test jamais réellement exécuté).
    **Bug produit réel trouvé et corrigé en cours de route** : la
    déconnexion Keycloak laissait l'utilisateur sur la page nue « vous
    êtes déconnecté » faute de `post_logout_redirect_uri`
    (`AuthProvider.tsx` + `deploy/keycloak/geostudio-realm.json`,
    propagation prod vérifiée via le mécanisme de `sed` déjà existant de
    `docker-compose.prod.yml`). **Régression découverte, sans rapport
    avec OIDC** : le changement cassant RFC 7807 de 3.5a avait laissé un
    mock E2E (`shell/e2e/sql-lab.spec.ts`) sur l'ancienne forme imbriquée
    — première exécution de la suite E2E complète depuis ce commit,
    précédent SP-23 Task 18/SP-25 Task 12 (régression cross-tâche
    invisible tant que personne ne relance la suite complète) — corrigée
    dans un commit séparé, baseline E2E restaurée à 108/4/0.
  - **Décision de scope actée, précédent très établi de ce dépôt (au
    moins 5 occurrences antérieures documentées)** : le bug préexistant
    `core/Dockerfile`/résolution `mcp==2.0.0` cassant `fastmcp` (CLAUDE.md
    SP-21, confirmé toujours présent par 3.8) N'A PAS été corrigé dans
    SP-26 — hors périmètre. Conséquence directe à surveiller : le nouveau
    job CI `shell-e2e-oidc` est le premier job de ce dépôt à faire
    `docker compose build core` (les jobs `core`/`shell`/`api-types-drift`
    existants utilisent `uv sync`, respectent `uv.lock`, ne buildent
    jamais l'image Docker) — **attendu rouge de façon déterministe à son
    premier run GitHub Actions réel**, tant que ce bug n'est pas corrigé
    séparément.
  - **Revue finale de branche (opus, 2026-08-27)** : 1 Critical + 6
    Important, tous invisibles à une revue par tâche. **C1** — `/scratch`
    jamais créé/chowné dans `core/Dockerfile` (le service `worker` partage
    la même image core non-root et monte `etl-scratch:/scratch` pour les
    jobs pipeline/terrain3d) **plus** un uid mismatch entre `app` (core) et
    `qgis` (qgis-worker) — deux images de base différentes, chacune
    `useradd --system` sans uid explicite — cassant la remise de fichier
    pipeline→sidecar QGIS à travers ce même répertoire partagé. Corrigé
    par uid/gid 1001 fixé identique dans les deux Dockerfiles (vérifié
    libre dans les deux images de base) + création/chown de `/scratch`
    dans `core/Dockerfile`, **écriture croisée réelle prouvée dans les
    deux ordres de démarrage possibles du volume nommé** (pas seulement
    égalité d'uid — précédent explicitement suivi). **I1** — budget
    rate-limit harvest (10/min, `_HARVEST_RE` couvrant alors TOUTES les
    routes `/harvest/*`) tuait silencieusement les couches externes du
    sélecteur de couches (recherche sans debounce dans `LayerPicker.tsx`,
    échecs avalés par `Promise.allSettled`) — corrigé en resserrant le
    groupe harvest aux seules routes d'écriture (4 sur 8, les 4 lectures
    exemptées). **I2** — défaut compose
    `CORE_ENV: ${CORE_ENV:-development}` désarmait la garde mock-mode de
    3.1 exactement dans le scénario qu'elle visait (compose de base sans
    `.env`) — corrigé (défaut vidé), flux `.env.example`→
    `bootstrap-env.sh` non affecté. **I3** — 403 démo lecture-seule encore
    en JSON plat, angle mort de 3.5a (middleware, pas exception handler)
    — aligné sur les 3 autres sites RFC 7807. **I4** — `RateLimiter._hits`
    clé sur le JWT brut (rotation OIDC toutes les quelques minutes)
    croissait sans borne, docstring affirmant à tort une croissance
    négligeable — balayage périodique (toutes les 50 requêtes) retirant
    réellement les entrées vides du dict, docstring corrigé. **I5/I6** —
    documentation seule (checklist CSP avant enforcing, runbook de
    migration non-root). Une passe de fix (7/7) puis **re-revue** (opus) :
    6/7 fermés correctement et vérifiés indépendamment ; **I6
    partiellement fermé** — 2 Important supplémentaires trouvés : le
    runbook contenait une commande `chown backup:backup` qui échoue
    réellement (le nom `backup` n'existe pas dans l'image `alpine`
    générique utilisée pour la commande, et l'uid de
    `deploy/backup/Dockerfile` n'était de toute façon pas fixé), et
    omettait un 3e volume nommé cassé par le même changement non-root
    (`appexport-runtime`, `deploy/appexport-runtime-builder/Dockerfile`).
    **2e passe de fix** : `backup`/`builder` fixés eux aussi à uid/gid
    1001 (vérifié libre dans leurs images de base respectives — sans
    contrainte de convergence avec `app`/`qgis`, aucun volume partagé
    avec eux), runbook corrigé (chown numérique, pas par nom) et complété,
    vérifié empiriquement dans les deux sens (ancienne commande échoue
    réellement, nouvelle réussit). Plus 2 des 4 Minor de la re-revue
    fermés au passage (tests I2/C1 renforcés — valeur résolue plutôt que
    seulement la syntaxe de défaut ; `qgis-worker` couvert en plus de
    `core`) et 1 pointeur documentaire ajouté (`shell/nginx.conf` renvoie
    vers la checklist CSP de `docker-compose.prod.yml`). **0
    Critical/Important non résolu au merge.**
  - **Preuves de sortie finales** (2026-08-27) : core `uv run pytest`
    (PostGIS réel) → **1896 passed, 5 skipped, 1 failed** — l'échec est
    `tests/test_features_rls.py::test_scope_preserves_original_sql_error`,
    confirmé **préexistant et sans rapport avec SP-26** (reproduit à
    l'identique dans un worktree jetable au commit juste avant le début de
    ce plan, indépendamment 3 fois au cours de cette exécution — dérive
    psycopg2/gestion de transaction non encore diagnostiquée, hors
    périmètre) ; couverture **92,96 %** (seuil 85) ; `ruff check`/`ruff
    format --check`/`mypy --strict` (4 modules)/`lint-imports` verts.
    Garde-fou de déployabilité (`test_deployability.py`) → **35/35**
    (31 d'origine + 4 nouveaux : C1×2, I2×1, puis les renforcements de la
    re-revue). Shell `npx vitest run` → **162 fichiers / 1463 tests**
    (mesurée après nettoyage `dist/`/`dist-export/`, même piège documenté
    SP-22-25), couverture **89,57 %** (seuil 88) ; `npm run lint`/
    `format:check`/`build` verts ; `npm run e2e` → **108 passed, 4
    skipped, 0 failed**. `uvx pre-commit run --all-files` : 5/5 hooks
    verts. **SP-26 clos.**

### À venir

- **SP-14** — clos (jalon M11 atteint, cf. SP-14o dans `### Fait`).
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
- Reste de la vision post-v0.1, 3D — rendu et hébergement de tilesets
  uploadés livrés (cf. `### Fait`) ; restent non planifiés : terrain servi
  par notre propre TiTiler depuis un DEM COG hébergé chez nous, encodage
  terrain `mapbox` en plus de `terrarium`, conversion 3D (py3dtiles,
  nuages de points).
- **SP-18** — clos, jalon M15 atteint (cf. `### Fait`).
- **SP-19** — clos (cf. `### Fait`).
- **SP-20** — clos, **jalon M16 atteint** (cf. `### Fait`). **Vague 0 du
  plan d'action 2026-08-20 close le 2026-08-20** : ses quatre chantiers
  (0.1 jeton MCP lié à l'appelant, 0.2 appel LLM hors boucle d'événements
  + budget global, 0.3 `CORE_INTERNAL_BASE_URL`, 0.4 entrée bornée et
  neutralisée) sont livrés et testés. Le résidu de 0.2 a été fermé à part :
  `LLMProvider.chat` est **asynchrone par contrat** (`httpx.AsyncClient`,
  plus de `anyio.to_thread`), donc l'échéance du tour **annule** l'appel LLM
  au lieu de l'abandonner dans un thread du pool (40 jetons partagés par
  tout le process) jusqu'à son propre timeout de 30 s. Note pour les
  sessions suivantes : la version antérieure de ce paragraphe affirmait que
  `asyncio.wait_for` ne pouvait pas interrompre l'appel synchrone et que le
  504 arrivait donc en retard — **c'est faux, mesuré** (504 rendu à
  l'échéance à 0,01 s près ; l'annulation asyncio traverse
  `anyio.to_thread.run_sync` malgré `abandon_on_cancel=False`). Le défaut
  réel était le thread abandonné, pas la latence de réponse. **Fermé par
  SP-26/3.4** : rate limiting applicatif sur `/copilot/turn` (groupe
  `llm`, avec `/mcp`, 20/min — clé sur l'en-tête `Authorization` brut,
  pas une identité vérifiée par utilisateur/tenant, cf. SP-26). Reste hors
  périmètre livré, non planifié : garde d'egress sur l'appel LLM sortant
  (4e surface, les trois autres en ont une — vague 6.2).
- **SP-24** — clos, chantier **4.1** du plan d'action fermé (cf. `### Fait`).
- **SP-25** — clos, chantiers **4.2/4.3** du plan d'action fermés (cf.
  `### Fait`). Le lot Carte du plan d'action §6 vague 4 s'arrête là :
  **4.4** (mesure) et **4.5** (croquis) restent hors périmètre de SP-24/
  SP-25, non planifiés, non numérotés au-delà de leur identifiant de plan
  d'action. Reste ouvert dans le périmètre déjà livré, non planifié : un
  éditeur de symbologie fonctionnel pour les couches `kind: "feature"`
  dans `LayersPanel` (aujourd'hui `null` faute de `collectionId` — décision
  produit non tranchée, cf. `### Suivis non bloquants ouverts`) ; Jenks sur
  le widget carte des apps/dashboards (masqué faute de résolution
  `collectionId` sur ce host, chemin distinct de `LayersPanel` par choix de
  spec §1).
- **SP-26** — clos, vague 3 du plan d'action (durcissement avant v0.1
  publique) fermée (cf. `### Fait`) : les 7 chantiers restants (3.1, 3.3,
  3.4, 3.5a/3.5b/3.5c, 3.6, 3.7, 3.8) sont livrés. Le nouveau job CI
  `shell-e2e-oidc` (3.8) est attendu rouge à son premier run réel tant que
  le bug préexistant `core/Dockerfile`/`mcp==2.0.0` (documenté SP-21,
  toujours présent) n'est pas corrigé — hors périmètre de SP-26 par
  décision de scope explicite, cf. `### Suivis non bloquants ouverts`.

### Suivis non bloquants ouverts

- SP-20, suivis non bloquants (revue finale de branche + clôture) : le
  chemin OIDC **réel** de `useMcpToken` (`signinSilent({scope,
  forceIframeAuth: true})`) n'est vérifié que statiquement et
  unitairement — aucun bout-en-bout navigateur+iframe+Keycloak n'a pu être
  produit dans cet environnement, à faire avant mise en production (même
  précédent que les tests `@pytest.mark.qgis` de SP-15d) ; ce
  `signinSilent` remplace l'utilisateur OIDC stocké de toute la session
  shell (inoffensif sur ce realm, dont le mapper d'audience
  `geostudio-core` est au niveau client, fragile sur un autre) ;
  `CORE_LLM_PROVIDER` non vide mais **invalide** active le panneau et le
  routeur sans échec au démarrage (échoue seulement en 500 à l'usage —
  contraste avec `CORE_SECRETS_MASTER_KEY`, fail-fast au boot) ;
  `configSchema` n'a pas de validation par valeurs autorisées (enum), donc
  le copilote peut écrire une valeur qu'aucun `<select>` de l'UI manuelle
  ne produirait (ex. `chartType` invalide) ; un nom d'outil client qui
  entrerait en collision avec l'allowlist MCP s'exécuterait côté serveur
  au lieu de repartir en `clientOp` (non exploitable aujourd'hui, les 5
  noms client ne recoupent jamais les 6 noms MCP — à surveiller si le
  vocabulaire client devient dynamique). Fermé : `anyio` n'est plus
  importé nulle part dans `core/app/` (le passage du fournisseur LLM en
  asynchrone a supprimé le seul usage), donc plus de dépendance
  transitive non déclarée.
- `deploy/postgis/Dockerfile` + `deploy/postgis/pg_hba.conf` (non
  commités, apparus pendant SP-20 pour faire tourner un vrai Keycloak) :
  **inertes**, vérifié empiriquement — Postgres lit
  `$PGDATA/pg_hba.conf`, jamais `/etc/postgresql/pg_hba.conf`, faute d'un
  `-c hba_file=…` dans le `command:` du service ; et l'image se termine
  déjà par `host all all all scram-sha-256`, que le fichier proposé
  affaiblirait en `md5` s'il était câblé un jour. Le vrai problème de
  démarrage de la stack par défaut reste le volume `pg-data` cassé
  (bullet ci-dessous).
- Connecteur ArcGIS v0 = services publics seulement (pas de token/OAuth distant) ;
  résiduel DNS-rebinding TOCTOU sur la garde egress (pinning-IP différé).
- Tags d'images Docker `pgbouncer`/`martin`/`titiler` à repinner si dérive ;
  documenter dans `.env.example`.
- Volume `pg-data` du projet compose par défaut cassé (`alembic_version` jamais
  stampée) — réparation non destructive hors périmètre. **Croisement SP-21** :
  `shell` a désormais `depends_on: core: condition: service_healthy` (décision
  Tanguy, gardé tel que le plan SP-21 le spécifiait) — si `core` ne devient
  jamais `healthy` (par exemple à cause de ce volume cassé), `shell` ne démarre
  plus du tout, là où avant il démarrait quand même et affichait une page
  d'erreur. `docker compose ps` le dit désormais explicitement (`shell` reste
  `Created`), ce qui est un diagnostic plus net qu'une page muette, mais change
  le symptôme observé par quiconque tombe sur ce volume cassé sans connaître ce
  changement.
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
- SP-14o, suivi non bloquant (trouvé en revue finale d'intégration) : le
  mode replace (writer.collection/writer.dataset) fait grossir le journal
  CDC d'environ 2x par run (tombstones + inserts, jamais purgés —
  `app/cdc/compaction.py` est explicitement append-only en sortie) ; une
  requête visuelle planifiée quotidiennement accumule un journal non borné
  sur une donnée de sortie qui, elle, reste de taille constante — dégrade
  progressivement la latence de `_dedup_cte`. Combinaison SP-15h
  (planification) × SP-14o (mode replace) qui n'apparaît nulle part dans le
  plan/la spec d'origine ; append seul aurait eu le même problème en pire
  (données fausses en plus). Pas de fix de code décidé pour l'instant — à
  surveiller si l'usage réel de requêtes visuelles planifiées se généralise.
- SP-18a, suivis non bloquants : widgets de filtre interactifs
  (`filter`/`selectFilter`/`dateRangeFilter`/`sliderFilter`) silencieusement
  inertes sur une source `"static"` gelée — `freeze_config` ignore
  `DataSource.query`, aucun risque de fuite de données mais expérience
  trompeuse (décision produit à trancher : honorer `query` à la congélation
  vs. étendre l'avertissement d'export existant). `reclaim_stuck_jobs`
  d'`app.appexport.repository` est du code mort (aucune tâche périodique ne
  l'appelle, contrairement à `app.export`/`app.reports` — un job dont le
  worker meurt en cours de route reste `running` indéfiniment ; nécessite
  une vraie tâche procrastinate périodique pour être branché, pas un fix
  d'une ligne). `bundler.py` copie `assets/` en non récursif (un sous-dossier
  généré par un futur changement Vite disparaîtrait silencieusement du
  bundle). `POST /app-exports` ne valide pas le `kind` de l'item (un item
  `map`/`dataset`/`pipeline` produit un job "done" avec un bundle
  inexploitable, plutôt qu'un 422 immédiat — même classe que le suivi
  SP-17a déjà noté, mais ici en échec silencieusement "réussi"). Fenêtre de
  quelques secondes où un widget Formulaire affiche encore "Enregistrer"
  dans un export avant que le `QueryClient` par défaut (3 retries,
  backoff exponentiel) ne marque la requête de permission en erreur —
  `retry: false` sur `entry.tsx`'s `QueryClient` réglerait ça proprement.
- SP-21, suivis non bloquants : la restauration n'a **jamais été rejouée
  de bout en bout** (chantier 1.4, renvoyé en vague 2) — le périmètre de
  sauvegarde est vérifié mécaniquement (quels buckets, quelles tables),
  mais personne n'a observé une restauration réussie, en particulier pour
  un item `tileset3d`. Le garde-fou **lit des YAML** : il ne démarre rien,
  ne prouve pas qu'un tag existe réellement au registre (seul `docker
  manifest inspect`, exécuté à la main en tâche 5, le fait), et ne prouve
  pas qu'un `docker compose pull && up` de l'overlay complet fonctionne
  bout en bout. La sonde `worker` (`procrastinate healthchecks`) ne
  détecte pas un worker coincé sur une tâche qui ne rend jamais la main —
  seule la liveness du process, pas la progression du travail. Le pinning
  au patch est une dette d'entretien assumée : aucun outil de mise à jour
  automatique (Renovate/Dependabot ou équivalent) n'est en place, quatre
  images de plus à surveiller manuellement pour les CVE. Le
  `depends_on: core: service_healthy` d'`export-worker` reste vérifié
  **par lecture seulement** — la stack n'a pas pu être montée jusque là
  dans cette
  session (cf. panne pré-existante ci-dessous), donc jamais observé en
  conteneur réel. Décision Tanguy sur `shell` → `core:
  condition: service_healthy` (gardé) et son interaction avec le volume
  `pg-data` cassé : documentée dans le bullet `pg-data` ci-dessus, pas
  répétée ici.
  **Panne de packaging pré-existante, distincte de SP-21**, rencontrée en
  sondant la stack réelle et à ne pas confondre avec un défaut introduit
  par cette tâche : GUC invalide `output_plugin_libraries` dans le
  `command:` de `postgis` ; les images `core`/`worker` ignorent `uv.lock`
  au build et récupèrent `mcp==2.0.0`, qui casse l'import `fastmcp` ; un
  `libexpat.so.1` manquant pour `defusedxml`. Ces trois pannes ont empêché
  `shell` et `export-worker` d'atteindre « started » dans les
  vérifications Docker réelles de cette session — non corrigées, hors
  périmètre du garde-fou de déployabilité (qui teste la forme du compose,
  pas la buildabilité des images).
  **Licences** : notice + labels OCI embarqués toujours **manquants** pour
  `geostudio-postgis` — bloqué, son `Dockerfile` porte des lignes non
  commitées d'un autre travail en cours dans cet arbre, et le stager
  emporterait ce travail. La question d'une notice LGPL embarquée pour
  `geostudio-core`/`geostudio-export-worker` (`psycopg`, LGPL-3.0-only,
  utilisé non modifié) n'est **pas tranchée** — traitement documenté mais
  pas validé par Tanguy. La licence de Chromium/FFmpeg embarqués dans
  `geostudio-export-worker` reste délibérément « non tranchée » (précédent
  SP-17a). Le binaire `mc` de `geostudio-backup` est téléchargé depuis une
  URL non pinnée en version (`release/linux-amd64/mc`) : l'offre de source
  AGPL ne peut donc pas nommer la version exacte redistribuée dans une
  image donnée, seulement pointer vers le dépôt amont.
  **Résolveur AST des variables d'environnement** — angles morts connus,
  documentés mais non couverts : un nom dont la valeur est calculée (pas
  une constante littérale), une f-string, une indirection par `getattr`.
  `_module_string_constants` ignore les affectations chaînées
  (`A = B = "X"`) et les `AnnAssign` (`A: str = "X"`).
  **Minors résiduels à garder en tête** (les trois autres sont fermés par
  la passe de correctif de la revue finale : raison d'être du fichier de
  garde-fou complétée, `.env.example` « documenté mais non substitué »
  désormais outillé par la 8ᵉ règle, test tautologique
  `test_slot_name_matches_the_consumer` supprimé — il relisait `SLOT_NAME`
  par la même chaîne d'import pour l'affirmer égal à lui-même) : la sonde
  `pgbouncer` traverse le pool jusqu'à Postgres (`select 1`), donc
  `pgbouncer` passe `unhealthy` si `postgis` est dégradé — sans cascade
  réelle aujourd'hui, vérifié : les cinq consommateurs de `pgbouncer` sont
  tous en `service_started`, jamais `service_healthy` ; le runbook de
  restauration nomme désormais les **trois** endroits à changer pour ajouter
  un bucket au périmètre (un seul est outillé), là où il en promettait un.
- SP-22, suivis non bloquants : le re-pull ghcr d'une image de 11,1 Go
  (`qgis-worker`) à chaque publication de tag `v*` — **deux fois, pas une**
  (corrigé ici : l'étape Trivy et l'étape `sbom-action` prennent chacune
  `image: ghcr.io/...` et re-pullent donc chacune l'image complète depuis
  ghcr, jamais seulement Trivy) — alternative `load: true` + scan local
  envisagée, non retenue (coût propre non mesurable dans cette session).
  Deux mécaniques supplémentaires trouvées en revue finale, documentées
  plutôt que corrigées : (a) ajouter `schedule:`/`workflow_dispatch:` à
  `gitleaks.yml` réouvrirait la tentation d'un scan d'historique complet
  (sous-commande `git` plutôt que `dir`), qui buterait sur la vraie clé
  privée `age` de test au commit `0b4733a` — cf. commentaire dédié dans le
  fichier ; (b) `sbom-action` garde `upload-release-assets` à son défaut
  `true` alors que le commentaire du fichier dit lui-même qu'il n'existe
  aucune GitHub Release à laquelle attacher quoi que ce soit — inoffensif
  sous `continue-on-error: true` (l'étape échoue silencieusement à
  l'upload, le SBOM part quand même en artefact de run par son autre
  comportement par défaut) mais contradictoire, à nettoyer si `sbom-action`
  est un jour reconfiguré. Asymétrie assumée entre Dependabot `/core` (PR
  non groupées, `uv` ne supporte pas `groups.*.dependency-type`) et
  `/shell` (dev/prod groupés, `npm` le supporte) — **ne pas « rétablir la
  parité »** en réintroduisant `dependency-type` sur l'entrée `uv` dans une
  session future, l'option y est silencieusement ignorée par GitHub, pas
  rejetée. `package-ecosystem: "docker"` absent de `dependabot.yml` alors
  qu'il couvrirait la dette d'épinglage des 8 images de base relevée par
  SP-21 (décision du propriétaire, non ajouté) — et Dependabot ne couvre de
  toute façon que des mises à jour de version : `secret_scanning`,
  `secret_scanning_push_protection` et `dependabot_security_updates` sont
  **désactivés** sur ce dépôt public (vérifié via `gh api repos/.../
  security_and_analysis` — les trois `status: "disabled"`), donc aucune
  alerte de sécurité GitHub native n'est active en plus de gitleaks/
  CodeQL/Trivy ; ne pas lire `dependabot.yml` comme couvrant ce terrain.
  Les 2 exclusions par regex de `.gitleaks.toml` (clé AES-GCM de test,
  placeholder Superset) portent sur tout le dépôt et non sur les seuls
  fichiers nommés dans leur commentaire — jugé acceptable en Task 7, pas
  resserré. Les hooks eslint/prettier de `.pre-commit-config.yaml`
  tournent désormais sur tout `shell/` à chaque déclenchement
  (`pass_filenames: false`, cf. revue finale I2 ci-dessus) plutôt que sur
  les seuls fichiers stagés — le point Minor Task 6 sur les noms de
  fichier contenant une espace ne s'applique donc plus (plus de
  découpage d'arguments). Nouveaux points Minor notés en revue finale : ni
  `codeql.yml` ni `gitleaks.yml` n'ont de bloc `concurrency:` et tous deux
  tournent deux fois sur les mêmes commits (`push` + `pull_request`) —
  même lacune que `ci.yml`, une convention à trancher plutôt qu'une
  régression ; épinglage hétérogène entre workflows (exact pour
  `trivy-action`/`sbom-action`/l'image Docker gitleaks, majeur flottant
  pour `actions/checkout@v4`/`codeql-action@v4`). **Constat de sécurité**
  trouvé en Task 7, hors périmètre de cette vague : une vraie clé privée
  `age` de test subsiste dans l'historique public du dépôt (commit
  `0b4733a`), redactée depuis par `fac2606` et absente de `HEAD` — jetable
  d'après le rapport d'origine, mais à confirmer ou rotationner ; l'audit
  de l'historique complet reste hors périmètre de cette vague (décision de
  planification n°6).
- SP-23, suivis non bloquants : `chartOption.ts`'s `num()` convertit
  toujours `null` en `0` pour les séries ECharts — un agrégat indéfini
  (écart-type d'un groupe d'une seule ligne) s'affiche « 0 » dans un
  graphique, alors que l'indicateur (`indicator.tsx`) affiche « — ».
  Limite acceptée en SP-23 : changer `num()` toucherait toutes les branches
  de rendu de `chartOption.ts` (au moins quatorze types nommés, et
  `chartType` est un `string` libre — pas de liste fermée), dont
  boxplot/radar/sankey qui n'acceptent pas `null`. La
  parité `STDDEV_SAMP`/`statisticType: "stddev"` d'ArcGIS est affirmée
  d'après la documentation du service, jamais mesurée contre un service
  réel. `GET /configs/{id}/revisions` n'est pas paginée : une config
  éditée des centaines de fois renverrait toutes ses révisions d'un seul
  coup. L'auteur d'une révision reste absent (`config_revisions` n'a pas
  d'`actor_id`) — relève du chantier 4.20 (journal d'audit consultable),
  hors périmètre assumé de SP-23.
  **Ajouts de la revue finale de branche** (triés non bloquants, hors les
  quatre Important corrigés) : `ConfigHistoryPanel` n'a **pas d'état de
  chargement** (un historique en cours de chargement est visuellement
  indiscernable d'un historique vide — l'état d'erreur, lui, est traité et
  testé) et pas de bouton « Réessayer » ; `ItemCard` a perdu son repli
  `?? item.resourceType`, donc un 13ᵉ `kind` livré côté cœur avant le shell
  rendrait une pastille **vide** au lieu de la valeur brute ; le chemin
  ArcGIS **accepte et ignore** un `p` posé sur un `stddev` là où le chemin
  DuckDB le refuse en 400 (incohérence déclarative, aucune donnée exposée ni
  faussée) ; le `throw` de `metricExpr` remonte un message développeur
  **anglais** à l'utilisateur (`VisualQueryWizardPage` fait
  `setError(e.message)`), et dans la branche création il survient après
  `createEmptyCollection`/`createDatasetItem`, laissant collection et item
  orphelins (classe pré-existante, nouvelle façon de l'atteindre) ; les
  champs centile portent `min={1} max={99}` sans `step` là où le serveur
  accepte tout réel de `]0, 100[` ; `resolveFlatValue` rend « — » dès qu'une
  source porte des `measures`, y compris pour une mesure unique dont le
  `label` est justement `value` (un indicateur lisible affiche « — ») ; le
  round-trip du centile n'est réciproque **qu'à 4 décimales**
  (`decompileMetrics` arrondit à 1e-4, atteignable par MCP, pas par l'UI) —
  l'affirmation « réciproques au caractère près » est donc légèrement
  surévaluée ; la spec §6 demandait un test de rollback par famille
  sensible, **`pipeline` n'en a pas** (seul `alert` et la portée d'extension
  sont couverts ; code partagé, risque résiduel faible, mais la preuve
  demandée manque) ; le grain `hour` étiquette ses catégories en `datetime`
  brut (`2026-05-17 13:00:00`, pré-existant mais visible pour la première
  fois sur un axe dense) ; et le grain choisi par l'auteur est **ignoré en
  mode comparaison** (`chart.tsx`/`indicator.tsx` recalculent `bucketFor()`,
  trois valeurs, donc une série en « Année » se compare en mois) —
  conséquence directe et documentée de la décision de ne pas toucher
  `bucketFor()`, mais c'est l'incohérence que le prochain rapport de bug
  utilisateur nommera.
  **Ajouts de la re-revue de la passe de correction** : le format de libellé
  `f"{agg}{p:g}_{field}"` retenu pour fermer I1 tronque à 6 chiffres
  significatifs, donc la collision revient à l'identique pour
  `p=33.333333333` vs `p=33.33333`, et `p=99.9999999` produit un
  `percentile100_…` qui annonce une valeur que le serveur refuse (non
  atteignable par l'UI, atteignable par MCP — l'option de repli « refuser
  deux mesures dont le libellé collisionne » aurait fermé le cas
  entièrement) ; la garde `Number.isFinite` du site d'appel jumeau
  (`QuerySummaryBuilder`, avec le commentaire qui explique que `??` ne
  remplace pas `NaN`) n'a pas été reportée dans `DataSourcePanel`, où
  `DataSource.query` est un `Record<string, unknown>` — un `p` non numérique
  y est type-légal et rend le champ vide (aucun commit invalide possible,
  la garde du composant tient) ; pour une source écrite hors UI en
  `{agg: "percentile"}` sans `p`, le champ **affiche « 50 » sans jamais le
  committer**, là où il était vide avant le correctif (l'absence était au
  moins signalée) ; la docstring du test copilote affirme encore que
  `provider.chat` est synchrone, faux depuis la clôture de la vague 0 de
  SP-20 ; et l'un des quatre cas invalides du nouveau test de
  `DataSourcePanel` est un doublon silencieux (jsdom normalise `"abc"` en
  `""` dans un `input type="number"`, donc la branche `Number.isFinite` de
  `PercentileInput` n'est en réalité exercée par aucun test).
- SP-24, suivis non bloquants : **D2 reste vrai dans le widget carte d'app**
  — il reste sur une couche `kind: "feature"` alimentée par sa `DataSource`
  (son filtrage/cross-filter côté client en dépendent), avec son plafond
  silencieux de 100 entités (`core/app/features/routes.py:181`) ; le widget
  gagne le popup, pas le tuilage — décision de spec assumée, pas un oubli.
  Aucune entrée `audit_log` par tuile (décision de spec §3.1), donc aucune
  trace d'une lecture massive par le chemin tuilé. Une valeur de propriété
  est interprétée comme du markdown dans un popup à gabarit — surface
  DOMPurify-assainie, mais à garder en tête si un futur besoin de
  désactiver le rendu markdown émerge. La seconde syntaxe d'expression
  (`${…}`) coexiste avec le binding JSON `{ $expr }` existant — divergence
  assumée par la spec, seule la forme gabarit donne une mise en forme
  libre. Le copilote SP-20 ne peut pas écrire `popup` sur le widget carte
  (`WidgetPropDescriptor.type` n'a pas de forme pour un objet imbriqué, et
  `applyClientOp` filtre par `configSchema`) — décision assumée de la
  tâche 13. Une table PostGIS ajoutée à la main hors registre de
  collections n'a plus aucun chemin de service depuis le retrait de la
  route publique `/tiles` de Martin — un besoin qui existait, même informel,
  perd son chemin de contournement. Aucune mesure de latence par tuile n'a
  été produite (pas de comparatif avant/après Martin→cœur). Ajout de la
  revue par tâche 12 : aucun test direct de `templateError` sur un cas
  guillemet CEL à travers `PopupEditor` (couverture transitive seulement
  via `popupTemplate.test.ts`). Ajout de la revue par tâche 16 : les 2
  défauts cross-tâches corrigés par la preuve E2E ont été committés dans le
  même commit que la preuve elle-même plutôt qu'en `fix(shell)` séparé —
  contraire au précédent explicitement consigné par SP-23 tâche 18, sans
  conséquence fonctionnelle.
- SP-25, suivis non bloquants : **M7** — une couche `feature` (tuiles
  externes, GeoJSON brut) n'a aucun éditeur de symbologie fonctionnel dans
  `LayersPanel` (`LayerSymbologyEditor` retourne `null` sans
  `collectionId`, qui n'existe que pour `kind: "vector"`) — déviation
  réelle vis-à-vis du texte littéral de la spec §3.7 (« un bloc symbologie
  par couche vector/feature »), nécessite une décision produit non couverte
  par les Global Constraints du plan (le bloc popup voisin, lui, fonctionne
  sans collection par saisie manuelle des noms de champs — rien n'empêche
  en principe le même repli pour la symbologie, mais Jenks/quantile/
  intervalle égal ont tous besoin d'un échantillon serveur qu'une couche
  sans collection ne peut pas fournir). **M1** — la preuve E2E
  (`map-symbology.spec.ts`) asserte le texte du panneau éditeur, pas le
  paint MapLibre compilé — preuve plus faible que ce que son propre
  docstring donne à penser, bien que `MapView.test.tsx` couvre séparément
  le chemin de paint compilé au niveau unitaire. **M2** — aucune légende de
  symbologie dans l'éditeur de carte standalone, seulement dans le widget
  carte (asymétrie assumée, pas un défaut du plan). **M3** — aucun signal
  de péremption quand champ/mode/méthode changent sans recalcul explicite :
  domaine et métadonnées de classification peuvent silencieusement diverger
  jusqu'au prochain clic « Recalculer ». **M4** — le type de retour de
  `resolvePalette` promet un non-null mais retourne `undefined` pour un id
  de palette inconnu — atteignable car `MapLayer.symbology` est un dict non
  typé côté cœur. **M5** — le travail de `sample` est non borné bien que sa
  sortie soit plafonnée à 2000 lignes — même forme adjacente-DoS que les
  chemins préexistants `min`/`max`/`percentile` sur la même route (pas une
  régression, une surface élargie). **M6** — `sample` combiné à
  `split`/`measures` est silencieusement ignoré plutôt que rejeté, hérite
  du laxisme déjà existant de `bins`. **M8** — `CHANGELOG.md` non mis à
  jour malgré la demande de spec §7 de noter le changement cassant
  `props.encodings`→`props.symbology` — habitude du dépôt entier, pas
  spécifique à SP-25. **M9** — le copilote SP-20/`configSchema` n'a jamais
  été étendu pour `symbology`, même résultat que l'omission délibérée de
  `popup` en SP-24, mais ici par omission plutôt que décision explicite.
  **M10** — `shell/src/api/types.ts` porte désormais un import type-only
  depuis `builder/widgets/mapSymbology` — un module de contrat d'API qui
  pointe vers un module de widget ; aucun cycle à l'exécution, mais à
  nettoyer un jour. **M11** — `toFixed(1)` utilisé sans condition pour les
  libellés de bornes/légende — peu lisible pour des valeurs très grandes ou
  très petites. **N2** (re-revue) — un recalcul qui réussit mais produit un
  résultat inutilisable (ex. échantillon Jenks trop court) efface quand
  même l'indice « pas encore calculé », sans aucun autre signal à l'auteur.
  **N3** (re-revue) — les domaines numériques continus, contrairement aux
  domaines classés, contournent entièrement `normalizeDomain` : un min/max
  `NaN` issu d'une collection vide produit une expression `interpolate`
  **acceptée** par MapLibre qui se sérialise pourtant en `null` via
  `JSON.stringify` — même classe de corruption silencieuse que I1, sur un
  chemin de code différent, non corrigé.
- SP-26, suivis non bloquants : le bug préexistant
  `core/Dockerfile`/résolution `mcp==2.0.0` cassant `fastmcp` (documenté
  SP-21, confirmé toujours présent par 3.8) laisse le nouveau job CI
  `shell-e2e-oidc` attendu rouge à son premier run réel — c'est le premier
  job de ce dépôt à faire `docker compose build core` (les jobs
  `core`/`shell`/`api-types-drift` existants utilisent `uv sync`, respectent
  `uv.lock`, ne buildent jamais l'image Docker) — décision de scope
  explicite de ne pas le corriger dans SP-26 (précédent très établi de ce
  dépôt, cf. `### Fait`). CSP toujours en Report-Only (3.3), jamais
  vérifiée en conditions réelles (aucun Chromium disponible dans cet
  environnement) — 4 bloqueurs concrets déjà identifiés et documentés en
  commentaire pour la bascule enforcing (cf. `### Fait`), pas encore
  résolus. Rate limiter (3.4) clé sur le JWT brut, donc le budget d'un
  appelant se réinitialise à chaque rafraîchissement de jeton OIDC (toutes
  les quelques minutes) — limite du choix de conception documenté (clé sur
  l'en-tête brut, pas une identité vérifiée), pas un bug, mais un budget
  « par jeton » plutôt que réellement « par minute » sous OIDC réel.
  Minor non corrigés de la revue finale de branche (~8 + 2 résiduels de la
  re-revue) : `HTTPStatus(...).phrase` lève `ValueError` sur un code non
  standard dans un handler d'exception (aucun site actuel n'utilise un code
  non standard, piège latent) ; `import logging` en corps de handler plutôt
  qu'en tête de module ; un 500 est désormais loggé deux fois (une fois par
  le handler, une fois par `ServerErrorMiddleware` de Starlette) ; le tag
  `docker build -t geostudio-postgis-ci` du nouveau job CI OIDC n'est
  consommé par aucune étape suivante (buildé deux fois, coût CI gaspillé
  seulement) ; `docker-compose.prod.yml` n'affiche pas `CORE_ENV: production`
  explicitement (inerte aujourd'hui, `CORE_AUTH_MODE: oidc` y est déjà en
  dur) ; `AppErrorBoundary` ne couvre pas un crash de `loadConfig()` en
  portée module (avant tout rendu React) ni ne se réinitialise au
  changement de route ; la politique Grafana racine route TOUTES les
  alertes vers le webhook, pas seulement celles du dossier SLO (le
  commentaire `.env.example` sous-estime la portée réelle) ; `cdc-worker`
  gère SIGTERM mais pas SIGINT (`docker stop` envoie SIGTERM, donc le
  chemin de production est couvert ; un `Ctrl-C` local reste un arrêt dur
  avec lignes bufferisées non flushées) ; classification I1 par « pas GET »
  plutôt que « est une écriture » (un `OPTIONS`/`HEAD` sur `/harvest/*`
  tomberait techniquement dans le budget harvest, inatteignable aujourd'hui
  — aucun CORS preflight n'est répondu sur ce chemin).
- **SP-27** (20 tâches, chantiers 4.4/4.5) — symbologie avancée de la carte :
  contour data-driven (fixe puis classé, `FieldClassificationPicker` extrait
  et partagé avec la couleur), opacité, icônes catégorielles (catalogue
  Lucide curaté de 140 icônes générées à la build + bibliothèque d'icônes
  personnalisées tenant-scoped, `app/mapicons/` au cœur), étiquettes CEL
  multi-champs (`${record.champ}`, source GeoJSON dédiée car `feature-state`
  est rejeté par le validateur style-spec), et un outil de mesure/croquis
  éphémère (distance/aire, tracé libre/rectangle/cercle/polygone/texte),
  câblés à la fois dans l'éditeur de carte **et** le widget carte (D2,
  périmètre élargi — le widget ne compilait jamais `symbology`, seul
  `paint`, donc rien de SP-27 n'atteignait une app/dashboard réelle avant
  Task 19). E2E complet passé de 108/4/0 à **111/4/0**.
  Trois passes de révision du plan (16 bloquants + 27 important trouvés par
  trois audits parallèles disjoints avant exécution), 20 tâches toutes en
  subagent-driven-development avec revue indépendante par tâche, plus une
  revue finale de branche sur opus.
  **Assainisseur SVG (`app/mapicons/svg.py`, D4/D6/D7) — le point le plus
  sensible du plan** : upload multipart (jamais présigné, D7 — un second
  `PUT` sur une URL présignée aurait restauré un SVG hostile après
  assainissement, invariant de D4 faux tel que rédigé initialement),
  assainissement à l'écriture par allowlist XML (`defusedxml`,
  re-sérialisation depuis l'arbre parsé, jamais un filtre regex), octets
  assainis seuls stockés sous une clé choisie par le cœur. **Trois tours de
  revue/correctif sur ce seul fichier** : (1) un contournement par
  échappement CSS (`fill="\75 rl(http://evil.test/x)"`) défaisait le filtre
  `url()` **et** les listes noires `javascript:`/`data:`, fermé en
  remplaçant la liste noire par une liste blanche de forme (mot-clé
  purement alphabétique + notation fonctionnelle ancrée, aucune ne pouvant
  former un jeton `url()` ni un schéma) plutôt qu'en patchant le payload
  précis ; (2) cette liste blanche s'est révélée trop étroite et supprimait
  silencieusement des couleurs nommées/`rgb()`/`hsl()` légitimes (icône
  stockée mais rendue avec la mauvaise couleur, aucune erreur à l'upload),
  élargie sans réintroduire de liste noire.
  **Piège central de Task 14 (étiquettes)** : un `setData` inconditionnel
  sur `idle` s'auto-entretient indéfiniment (`setData` → événement
  `content` → `SourceCache.reload()` → repaint → nouvel `idle`, ~6 Hz,
  gel d'onglet potentiel) — fermé par une mémoïsation par charge postée,
  **par instance de `MapView`** (un `Important` de revue de tâche a
  d'abord trouvé le cache à portée module, partagé entre `MapView`
  co-montées affichant la même couche — corrigé en `useRef`).
  **Revue finale de branche (807f7c8..dfaf6a7, 33 commits) : 0 Critique,
  4 Important, 13 Mineur, tous les 16 déviations documentées du plan
  vérifiées individuellement contre le code, aucun écart non documenté** —
  la relectrice a elle-même rejoué les portes de qualité (tsc, ruff,
  lint-imports, `test_deployability` 35/35, `test_mapicons_*` 88/88,
  arithmétique E2E) plutôt que de se fier au rapport. Les 4 Important sont
  tous des défauts d'interaction croisée entre tâches, invisibles à une
  revue par tâche seule (piège n°4 de `CLAUDE.md`) : `loadIconImages`
  (Task 8) était un 3e consommateur de `symbology.icon` jamais symétrisé
  avec la garde de géométrie/le filtre de domaine de Task 7 — fermé en
  consommant `MapPaintResult.iconImages` déjà calculé par `effectivePaint`
  au lieu de re-dériver ; un contour classé se rendait correctement mais ne
  pouvait jamais apparaître dans la légende (`LegendSpec.stroke` resté
  catégoriel-seul quand Task 5 a rendu le sélecteur de contour symétrique à
  la couleur) — légende élargie à l'union à trois variantes de la couleur ;
  suppression d'icône personnalisée sans `.catch()` (son jumeau, l'upload,
  en a un) ni nettoyage de référence — `.catch()` ajouté + confirmation
  nommant la conséquence (le référencement pendant lui-même reste un suivi,
  corriger côté cœur est hors périmètre) ; `iconField` (état local de
  `MapSymbologyEditor`) ne se resynchronisait jamais avec
  `value.icon.field`, désynchronisé par un undo/redo SP-19 — corrigé par un
  effet dépendant du seul champ committé (`[icon?.field]`, pas `[icon]`
  ni `[value]`, pour ne jamais écraser une saisie en cours). Fix wave
  vérifiée par une re-revue indépendante de la même relectrice : les quatre
  Important fermés pour de vrai (payloads d'attaque et scénarios rejoués en
  direct, pas seulement le rapport cru sur parole), aucun n'en a rouvert
  un autre. **Verdict final : Ready to merge — Yes.**
  Suivis non bloquants ouverts par la revue finale (aucun n'est un
  correctif requis avant la clôture) : icônes personnalisées absentes des
  exports statiques (`StaticItemClient.fetchMapIconBlob` renvoie
  `unsupported()`, prescrit par le plan mais jamais consigné en suivi) ;
  référencement pendant après suppression d'icône (le référencement lui-même
  n'est jamais nettoyé côté cœur, seule une confirmation en avertit
  l'auteur) ; le rationnel du suivi `ImageManager` (jamais purgé,
  « borné par le catalogue, 140×16 Ko ») est devenu faux depuis que Task 12
  a rendu la bibliothèque téléversable par tenant — borne réelle
  désormais la taille de la bibliothèque du tenant, pas une constante ;
  `_has_graphics` de l'assainisseur SVG ignore le texte porté par
  `tspan` (rejette un icône Illustrator texte-seul légitime, pas une
  faille de sécurité) ; aucun quota/rate-limit sur `POST /map-icons`
  (cohérent avec la posture existante du dépôt sur `thumbnail`/
  `ingestion`, mais `/map-icons` est le seul des trois à créer un nombre
  non borné de lignes+objets S3) ; le bucket d'icônes reçoit une politique
  CORS `AllowedOrigins: ["*"]` à chaque upload, héritée de la présignation
  que D7 retire pourtant de cette surface (hygiène, pas une brèche) ;
  `computedAt` (invariant SP-25 « domaines figés ») n'est jamais remis à
  zéro quand `field`/`mode` change sans recalcul explicite — le résumé de
  classification affiche alors la date/les classes de l'**ancien** champ
  jusqu'au prochain clic « Recalculer » (hérité de SP-25, désormais
  dupliqué sur le contour par D5) ; le mode tracé libre du croquis peut
  encore être laissé bloqué (relâchement de souris hors canevas) même si
  « Effacer tout » le corrige maintenant (recovery existe, la cause racine
  reste atteignable) ; la source `__sketch__` peut se retrouver sous une
  couche de données après un `applyLayers` ultérieur (ex. changement de
  source de données par un cross-filter) — cosmétique, pas fonctionnel.
- **SP-28** (4 tâches, symbologie des couches `feature` — URL GeoJSON) —
  résout l'item resté ouvert par SP-27 : l'éditeur de symbologie pour les
  couches `kind: "feature"` dans `LayersPanel` (auparavant `null` faute de
  `collectionId`). Nouveau module pur `shell/src/map/geojsonIntrospect.ts`
  (fetch client-side, jamais via `ItemClient` — URL tierce arbitraire, pas
  le catalogue du cœur) implémentant les contrats `StatQueryFn`/
  `SampleFieldFn` calculés en mémoire sur les entités déjà chargées ;
  `LayersPanel.tsx` branche `LayerPopupEditor`/`LayerSymbologyEditor` sur
  présence/absence de `collectionId` via un hook react-query partagé
  (`useFeatureLayerGeoJson`, clé `["feature-geojson", url]`) ; `LayerPicker.tsx`
  gagne un formulaire « ajouter par URL GeoJSON », détecte `renderAs`
  depuis la géométrie de la première entité et amorce ce même cache.
  `jenksAvailable` reste vrai ici (contrairement au widget carte
  `mapWidget.tsx`, adossé à un `DataSource` distant sans valeurs brutes) —
  seul lot du plan, resté explicitement hors périmètre. E2E complet passé
  de 111/4/0 à **112/4/0**. 4 tâches en subagent-driven-development, revue
  indépendante par tâche (0 Critique/Important sur chacune), plus une
  revue finale de branche sur opus.
  **1 Critique trouvé par la revue finale, invisible à la revue par
  tâche** (le défaut traverse Task 3, qui écrit `renderAs`, et deux
  fichiers qu'elle n'ouvre jamais) : `renderAs` — premier champ persisté
  jamais écrit par cette branche — ne survivait pas à un
  enregistrement+rechargement. Absent du modèle Pydantic `MapLayer`
  (`core/app/configs/schemas.py`, `extra="ignore"` le supprimait
  silencieusement au `model_dump()`) et jamais lu par `toFrontLayer()`
  (`shell/src/api/itemClient.ts`) — 3e occurrence du piège CLAUDE.md n°5
  (« chemin de lecture oublié »), après `popup` et `symbology`.
  Conséquence utilisateur réelle : une couche de points stylée en `circle`
  redevenait invisible après rechargement (repli sur le défaut `fill` de
  `MapView.tsx`) — défaisait exactement ce que la spec vise à empêcher.
  Invalidait aussi la contrainte globale du plan (« pas de changement
  cœur/pas de régénération OpenAPI »), vraie pour `symbology`/`popup`
  (préexistants dans le schéma) mais devenue fausse dès que Task 3 a
  commencé à émettre `renderAs`. Fixé (champ + régénération OpenAPI/TS
  réelle, diff non vide cette fois — piège n°1 s'appliquait pour de vrai
  — + spread côté shell + 2 tests de round-trip), re-revue indépendante :
  fix vérifié. **2e occurrence du même défaut trouvée en vérification de
  clôture, hors du filet des deux revues précédentes** : relancer la suite
  pytest complète du cœur après le fix (jamais faite par le fix lui-même,
  qui n'avait exécuté que la suite ciblée) a révélé qu'un test préexistant
  sans rapport (`test_routes.py::test_map_config_round_trips_tiles3d_layer_terrain_and_camera`,
  couche `tiles3d`) fait une égalité de dict **exacte** et n'incluait pas
  la nouvelle clé `renderAs: None` — root-cause confirmée par bisection
  manuelle sur worktree jetable (fichier par fichier : seul `schemas.py`
  cause l'échec, car il change la sérialisation de *toute* couche, pas
  seulement `feature`) ; corrigé directement par le contrôleur (1 ligne).
  1 Important documenté en suivi non bloquant, pas corrigé dans cette
  branche (décision actée, pattern établi de ce dépôt) : bug UI réel et
  vérifié, **préexistant et partagé avec les couches `kind: "vector"`**
  (pas introduit par SP-28) — le `<span>` de titre dans `LayersPanel.tsx`
  peut avoir une largeur de layout nulle (interaction flex
  `flex-1 truncate` + sibling `basis-full` toujours déployé pour
  `vector`/`feature`), trouvé et documenté par la tâche E2E (contournée
  par un sélecteur différent, `getByRole("button", { name: "Retirer …" })`).
  5 Minor documentés, non corrigés : cache-priming de Task 3 n'élimine pas
  réellement le refetch qu'il prétend éviter (`staleTime: 0` par défaut) ;
  `retry: 3` par défaut triple les requêtes CORS échouées en production ;
  la suppression du garde `if (!collectionId) return null` a aussi ouvert
  l'éditeur pour une couche `vector` sans `collectionId` (cas non
  atteignable depuis le picker actuel) ; chaque couche feature est
  refetchée à l'ouverture de n'importe quel panneau de symbologie, pas
  seulement la couche stylée (risque accepté par la spec, plus large que
  son libellé) ; `setFeatureBusy(false)` pas dans un `finally`.
  Contamination trouvée et corrigée en cours de session (piège n°9) :
  `.superpowers/sdd/task-{1,2,3,4}-{brief,report}.md` étaient
  force-trackés en git depuis une session antérieure malgré le
  `.gitignore` `*` du dossier — restaurés (`git checkout --`) avant toute
  clôture, aucune perte (contenu dupliqué dans le ledger `sp28-progress.md`
  et les fichiers `sp28-task-*`). **Verdict final : Ready to merge — Yes**,
  mergé dans `main` (`075b6ae`) et `dev`/`main` poussés sur `origin`.

- **SP-29b** (31 tâches, exécution complète en subagent-driven-development
  sur une seule session) — kit de ~40 primitives UI headless (Radix UI +
  tokens GeoStudio) sous `shell/src/ui/kit/`, additif à côté des fichiers
  `shell/src/ui/*` existants (jamais touchés, vérifié à plusieurs reprises
  y compris en revue finale), plus une galerie interne réservée aux
  administrateurs (`/internal/kit-gallery`). 18 paquets Radix + lucide-react
  installés à des versions exactes, `--gs-shadow-*` ajouté au contrat de
  tokens. Chaque tâche a eu sa revue indépendante (spec + qualité), la
  plupart avec 0 défaut ; plusieurs défauts réels ont quand même été
  trouvés et corrigés en cours de route, tous documentés en détail dans le
  ledger de session (`sp29b-progress.md`, non commité — scratch) :

  - **Task 2** : `npm install pkg@version` sans `--save-exact` avait écrit
    des ranges caret dans `package.json` au lieu des 18 versions exactes
    exigées par le brief — corrigé.
  - **Task 5 (Checkbox, gabarit des 15 tâches Radix suivantes)** : la revue
    a insisté sur ce fichier précisément parce qu'il sert de patron —
    trouvé et corrigé un trou de couverture (`disabled` bloque le clic
    mais n'était pas testé au clavier) avant qu'il ne se propage.
  - **Task 6 (Radio)** : le wrapper Radix trivial du plan échoue
    réellement le test de navigation clavier sous jsdom (confirmé
    indépendamment par le contrôleur en le rejouant tel quel) — Radix gère
    la sélection au clavier via des écouteurs `document`-level posés par
    item (hors React), pas via un `onKeyDown` sur `Root`/`Item`. L'implé-
    menteur a contourné avec un `onKeyDown` custom + registre de refs par
    Context, mais sans `stopPropagation()` — analyse du code source Radix
    installé a montré un risque réel de double appel à `onValueChange` en
    répétition clavier (touche maintenue), invisible en test, latent tant
    que `Radio` n'est câblé sur aucun écran. Corrigé (`stopPropagation()`),
    re-vérifié.
  - **Task 8 (Slider)** : un polyfill `ResizeObserver` posé GLOBALEMENT
    dans `shell/src/test/setup.ts` (nécessaire pour Radix Slider) a cassé
    2 tests préexistants et sans rapport dans `AppRenderer.test.tsx`, qui
    dépendaient de `typeof ResizeObserver === "undefined"` pour un
    comportement de repli délibéré en environnement de test. Corrigé en
    stub local au fichier de test concerné (patron réutilisé sur toutes
    les tâches Radix suivantes qui en avaient besoin : Select/Combobox/
    Tooltip/galerie, jamais `setup.ts`).
  - **Tasks 10/11/17** : trois bugs réels du texte littéral du plan
    lui-même trouvés par les tests écrits verbatim eux-mêmes : ColorField
    ne resynchronisait pas le champ texte sur un changement externe de
    `value` (le plan promettait pourtant « synchronisé dans les deux
    sens ») ; NumberField perdait la saisie multi-chiffres si lié
    directement à `value` sans state local (le test du plan lui-même
    l'aurait révélé) ; deux clés i18n `kit.numberField.*`/`kit.breadcrumb.
    label` violaient la convention `<domaine>.<intention>` documentée en
    tête de `catalog.fr.ts` — la correction de Task 11 (retirer `kit.`) et
    celle de Task 17 (garder `kit.` mais fusionner l'intention) divergeaient
    entre elles, incohérence trouvée et corrigée en Task 17.
  - **Task 13 (Combobox, dispatché sur modèle standard, composant le plus
    élaboré du plan)** : trois défauts vérifiés empiriquement par le
    contrôleur avec falsification (remise du texte littéral du brief pour
    confirmer l'échec, puis restauration) — `activeIndex` initial à `0`
    (brief) au lieu de `-1` (le brief contredisait mathématiquement son
    propre test) ; `avoidCollisions={false}` posé en PRODUCTION sur
    `Combobox.tsx` (pas seulement en test) pour contourner un vrai coût
    CPU mesuré (`shift`/`flip` de `@floating-ui/react-dom` qui ne converge
    jamais sous jsdom, ×6.7 mesuré) — dégrade un comportement réel de
    production (le menu ne se repliera jamais au bord de la fenêtre, même
    dans un vrai navigateur), jugé acceptable (levier public documenté de
    la lib, aucune alternative test-only crédible) et retenu comme
    précédent pour Popover/Menu/Tooltip (Tasks 20/21/22), qui l'ont chacun
    mesuré puis réutilisé à l'identique. En marge de cette tâche, une
    vraie erreur `tsc`/`npm run build` a été trouvée dans `Segmented.tsx`
    (Task 9, déjà « approuvée 0 défaut ») — invisible parce qu'aucune
    revue de tâche jusque-là ne lançait `tsc --noEmit`, seulement Vitest ;
    corrigée hors numérotation de tâche, toutes les revues suivantes
    incluent désormais systématiquement `tsc --noEmit`.
  - **Task 19 (Splitter)** : jsdom n'implémente pas du tout `PointerEvent`
    — `fireEvent.pointerDown(el, { clientX })` (texte littéral du brief)
    retombe sur un `Event` générique sans `clientX`, diagnostiqué par le
    contrôleur (pas juste accepté du rapport de l'implémenteur qui avait
    signalé DONE_WITH_CONCERNS), corrigé par un polyfill `PointerEvent`
    local au fichier de test.
  - **Task 23 (Dialog)** : un test en échec avait été attribué à tort par
    l'implémenteur au même problème Popper que Combobox — le contrôleur a
    vérifié indépendamment que `@radix-ui/react-dialog` n'utilise pas
    `@radix-ui/react-popper` et a diagnostiqué la vraie cause : Radix
    Dialog auto-focus déjà le premier élément focusable IMMÉDIATEMENT à
    l'ouverture (confirmé empiriquement), donc le `userEvent.tab()` du
    texte littéral du brief déplaçait le focus EN AVANT avant l'assertion
    — encore un bug du texte du plan, pas de l'environnement.
  - **Tâches 22/26 (Tooltip, Toast)** : deux seules tâches du plan à
    toucher `shell/src/App.tsx` (Providers Radix globaux) — vérifiées
    sûres (props de contexte pur pour Tooltip, positionnement `fixed`
    pour le Viewport de Toast qui rend un vrai `<ol>`), `App.test.tsx`
    revérifié 0 régression aux deux passages.
  - **Task 30 (galerie)** : trois déviations du texte littéral, toutes
    vérifiées — `Table` ajouté (sans lui, seule des 40 primitives jamais
    réellement rendue, recoupé un à un contre l'auto-revue du plan) ;
    Providers Radix posés localement dans le composant de PAGE plutôt que
    dans le test (divergence du précédent Task 26, jugée sans danger par
    lecture du code source Radix — contexte scopé par Provider le plus
    proche — mais justification en commentaire légèrement trompeuse,
    Minor) ; stub `ResizeObserver` attribué à 4 primitives, vérifié exact
    (elles importent toutes `useSize` inconditionnellement au rendu,
    contrairement aux composants popper-based).
  - **Collision de session concurrente** découverte pendant la revue de
    Task 6 : une autre session travaillait au même moment sur ce même
    arbre (plan différent, intitulés historiques de SP-26) et écrasait en
    un seul batch les fichiers génériques `.superpowers/sdd/task-N-brief.md`
    du script `task-brief` — heureusement sans conséquence car le reviewer
    de Task 6 avait revu contre le texte réel du plan plutôt que contre le
    brief corrompu, mais tous les fichiers de cette session ont été
    immédiatement renommés `sp29b-*` pour la suite (piège n°9, encore).

  **Revue finale de branche** (modèle le plus capable) : 0 Critique,
  **3 Important, tous re-vérifiés par falsification empirique après
  coup, pas seulement par « les tests passent »** — leçon la plus
  coûteuse de cette clôture. Le premier passage de correctif sur
  l'Important 1 (`expectTokenizedClasses()` inspectait `container`, vide
  pour les 7 primitives qui portalisent leur contenu stylé vers
  `document.body` : Popover/Menu/Tooltip/Dialog/Drawer/Select/Combobox —
  falsifié par injection de `bg-red-500`, un test « corrigé » ne bronchait
  toujours pas) a été accepté sur la foi de « tous les tests passent » —
  et le contrôleur, en re-falsifiant lui-même chaque fichier un par un
  après le fix, a trouvé que 3 des 7 ne vérifiaient toujours rien :
  `Popover.test.tsx` (un `container: root` explicite fait pointer
  `baseElement` sur ce même `root`, pas `document.body` — comportement
  réel de `@testing-library/react` vérifié dans le paquet installé),
  `Select.test.tsx` (le test qui appelait la vérification n'ouvrait
  jamais le menu déroulant) et `Menu.test.tsx` (la vérification était
  placée APRÈS le clic qui ferme le menu et démonte son contenu portalisé).
  Trois commits de correctif successifs, chacun re-vérifié par
  falsification réelle avant d'être accepté. Les deux autres Important :
  4 chaînes françaises hors `t()` (ConfirmDialog, Combobox, et deux
  `aria-label`) et 2 `aria-label` interpolant un `React.ReactNode`
  arbitraire dans un template literal (`Chip`, `DataTable` — bug latent
  produisant `"[object Object]"` pour tout appelant SP-30 passant un
  élément React plutôt qu'une string), corrigés par des props optionnelles
  explicites avec repli via `t()`. 6 Minor documentés comme suivis non
  bloquants pour SP-30 (détail dans l'entrée `### Livré` de CLAUDE.md).

  Portes de qualité (Task 31) : `npm run test -- --coverage` échouait de
  façon reproductible (v8 ajoute un surcoût CPU qui s'additionne au coût
  de mesure Popper déjà connu, poussant 6-7 tests au-delà de leur
  `OPEN_TIMEOUT` déjà à 15000) — diagnostiqué par le contrôleur
  (`--maxWorkers` réduit seul insuffisant, même en exécution totalement
  séquentielle ; `--testTimeout` CLI sans effet, le 3e argument de
  `test()` prime) et corrigé en portant `OPEN_TIMEOUT` à 45000 dans les 4
  fichiers concernés, stable sur 2 exécutions consécutives. Suite
  complète finale : 215 fichiers / 1775 tests, e2e 113/4/0 inchangé,
  couverture 90,75 % (seuil 88), `tsc`/lint/format/pre-commit tous
  propres. **Verdict final : Ready to merge — Yes.**

  **Après clôture, sur demande explicite** : PR #102 (dev→main, avec
  SP-29a) a révélé 2 échecs CI pré-existants, non liés au contenu de
  SP-29b — `core` : `test_deployability.py::
  test_every_compose_substitution_is_documented` échouait sur
  `VITE_AUTH_MODE` absent de `.env.example` malgré sa substitution dans
  `docker-compose.yml`, documenté comme suivi non bloquant depuis SP-29a
  et jamais corrigé jusqu'ici — corrigé (une ligne + commentaire). `scan`
  (gitleaks, arbre de travail) : 2 leaks réels, dont une découverte plus
  large que prévu — **104 fichiers** sous `.superpowers/sdd/` (scratch de
  sessions SP-17a/SP-17b et antérieures, briefs/rapports/diffs) étaient
  force-trackés en git depuis longtemps malgré le `.gitignore`
  `.superpowers/` — récidive du piège n°9 jamais nettoyée en profondeur
  malgré des mentions ponctuelles dans SP-14m/SP-28. Retirés du suivi
  (`git rm --cached`, conservés sur disque) ; le second leak (exemple
  curl `admin:admin` dans un plan SP-26) allowlisté sur le même patron
  déjà établi pour SP-10b. Les deux corrections vérifiées par clone
  propre + rejeu local avant push ; CI repassée intégralement au vert
  (20/20 checks) après ce second passage.

---

## Versé depuis CLAUDE.md par SP-42 (Tâche 17, 2026-09-05)

Contenu ci-dessous **repris verbatim** de `CLAUDE.md` avant dégonflement —
`### Livré` (SP-1 à SP-41 dans leur version détaillée d'origine,
y compris les entrées SP-30a→SP-30l, SP-31 à SP-41 non encore archivées),
`### Conventions tranchées (2026-09-01)` et `### À venir` (listes de
suivis Minor hérités SP-29b→SP-30k). Le contenu factuel encore pertinent
a été versé dans `docs/revue/2026-09-04-backlog.md` (entrées `REV-nnn`) ;
ce qui suit est l'historique complet, non trié, pour qui veut le détail
brut d'une revue finale ou d'une déviation de plan.

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
  `LayersPanel` à largeur nulle — cf. `### Livré`/SP-36 et SP-37) : ce test
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
- **SP-36 — LayersPanel, titre de couche à largeur nulle** (3 tâches +
  vérification finale, spec
  `docs/superpowers/specs/2026-09-03-sp36-layerspanel-titre-flex-wrap-design.md`,
  plan
  `docs/superpowers/plans/2026-09-03-sp36-layerspanel-titre-flex-wrap.md`
  — referme la partie « titre à largeur nulle » du lot **Carte** ouvert
  depuis SP-28) : `flex-wrap` ajouté au `<li>` de `LayersPanel.tsx:164` —
  sans lui, le bloc `basis-full` (édition inline, couches
  `vector`/`feature`) ne pouvait jamais passer à la ligne, et écrasait à
  la place le `<span>` de titre — seul sibling à min-width automatique
  réduite à 0 via `flex-1 truncate`/`overflow: hidden` — à une largeur de
  layout nulle. Deux specs E2E mises à jour :
  `map-feature-layer-symbology.spec.ts` (remplace le contournement par
  sélecteur « Retirer … » par une assertion directe de visibilité du
  titre) et `map-symbology.spec.ts` (ajoute la toute première assertion
  de titre pour le cas `vector`, sur la couche « Communes »). Correctif
  falsifié avant d'être fait confiance : revert temporaire, les deux
  specs confirmées en échec réel, restauré. `triptych-narrow.spec.ts`
  (Task 3, re-mesure empirique de l'écran Cartes, pas supposée) : « le
  `<span>` de titre d'une couche vector/feature à largeur de layout
  nulle (mécanisme (b), `flex-1 truncate` + sibling `basis-full` toujours
  déployé) est corrigé — `flex-wrap` ajouté à la ligne (`LayersPanel.tsx`).
  Ré-mesuré empiriquement (pas supposé) : plus aucun offenseur sur
  l'onglet "Couches" à 390px avec la vérification de clip désormais
  active. Seul le mécanisme (a) — la colonne browse (~249px de large à
  900px) trop étroite pour le contenu de LayersPanel — persiste, et
  seulement dans la grille desktop (900px) : offenseur unique mesuré
  `DIV.overflow-y-auto.border-r.border-rule` (scrollWidth 290 >
  clientWidth 249), sans rapport avec la famine de colonne centrale
  corrigée par SP-33. À 390px (layout mobile en onglets, la colonne
  "Couches" occupe toute la largeur disponible) ce mécanisme ne
  reproduit pas. » — `wideBoundaryKnownIssue` reformulé en conséquence :
  « Cartes : 1 offenseur pré-existant (colonne browse trop étroite pour
  le contenu de LayersPanel) — sans rapport avec la famine de colonne
  centrale corrigée par SP-33 ; le titre de couche à largeur nulle est
  corrigé par SP-36. Tracké CLAUDE.md/lot "Carte". » Aucun changement
  sous `core/` (`git diff --stat main...HEAD -- core/` vide). E2E 143
  tests/138 passed/5 skipped/0 failed → **inchangé** vs la référence
  SP-33/SP-34 (aucun test ajouté ni retiré par ce plan — l'onglet
  "Couches" à 390px passe désormais pour de vraies raisons plutôt que
  d'être écarté par `skipClipCheckForTabs`, sans changer le compte).
  Vitest shell **inchangé** (221 fichiers/1848 tests — un premier run
  complet a montré 1 échec isolé sur `MapEditorPage.test.tsx` [« affiche
  le panneau d'historique »], confirmé flaky et sans rapport avec ce plan
  par ré-exécution ciblée puis complète, 0 échec les deux fois : la
  dépendance d'ordre sur le stub `matchMedia` de ce fichier, sans
  `vi.unstubAllGlobals()`, était déjà documentée comme risque latent —
  cf. entrée SP-30l). **Ready to merge.**
- **SP-37 — LayersPanel, colonne browse à 900px** (4 tâches + vérification
  finale, spec
  `docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md`,
  plan
  `docs/superpowers/plans/2026-09-04-sp37-layerspanel-colonne-browse.md` —
  ferme le dernier mécanisme ouvert du lot **Carte** : la colonne `browse`
  de `TriptychLayout.tsx` qui clippait le contenu de `LayersPanel` à
  900px, tracké depuis SP-28, mesuré par SP-36/Task 3) : deux offenseurs
  réels trouvés et corrigés, dont un dont l'hypothèse initiale de la spec
  s'est révélée fausse — vérifiée avant d'être écrite dans le plan, pas
  après coup. Le premier offenseur, `PopupEditor.tsx:160` (la ligne
  d'ajout de champ), corrigé par `flex-wrap` — même mécanisme que SP-36.
  Pour le second, l'hypothèse initiale de la spec visait
  `MapSymbologyEditor.tsx:575` (la ligne valeur d'icône `span`+`button`) :
  testée pendant l'écriture de la spec, elle ne reproduisait pas (son
  texte passe à la ligne, ne force aucune largeur). Le vrai second
  offenseur, trouvé à sa place : `MapSymbologyEditor.tsx:695`, un
  `<input type="file">` d'upload d'icône sans aucune classe de largeur —
  mécanisme distinct, pas un défaut de flex-wrap mais un plancher de
  largeur de contrôle natif ; `min-w-0` seul testé et jugé insuffisant,
  `w-full` requis. Fix intégré au passage, à la demande de Tanguy : les
  deux `border-t` restants non tokenisés de `LayerPicker.tsx` (dette
  extraite de SP-30c/SP-34) s'écrivent désormais `border-t border-rule`.
  `triptych-narrow.spec.ts` (Task 4, écran Cartes) porte désormais le
  commentaire suivant, mot pour mot :
  « SP-36 a fermé le mécanisme (b) (titre de couche à largeur nulle).
  SP-37 (docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md)
  ferme le mécanisme (a) restant (colonne browse trop étroite pour le
  contenu de LayersPanel) : deux offenseurs distincts trouvés et
  corrigés — la ligne d'ajout de champ de PopupEditor.tsx (flex-wrap
  manquant) et le champ de fichier d'upload d'icône de
  MapSymbologyEditor.tsx (aucune classe de largeur). Ré-mesuré
  empiriquement après les deux correctifs : plus aucun offenseur, ni à
  390px ni à 900px. Le lot "Carte" est clos (CLAUDE.md). » Aucun
  changement sous `core/` (`git diff --stat` scopé aux commits de ce
  plan vide ; le seul diff `core/` relevé par la commande littérale du
  plan sur `main...HEAD` est un commit `core/uv.lock` antérieur à
  l'ouverture de ce plan, sans rapport). E2E 143 tests/138 passed/5
  skipped/0 failed → **144 tests/140 passed/4 skipped/0 failed** (le
  skip Cartes à 900px retiré par Task 4, plus le nouveau test permanent
  de Task 2 — exactement l'arithmétique prédite par le plan, confirmée
  et non simplement recopiée). Vitest shell **inchangé** (221
  fichiers/1848 tests — un premier run complet a de nouveau montré le
  même échec isolé et déjà documenté sur `MapEditorPage.test.tsx`,
  reconfirmé flaky par ré-exécution isolée puis complète, 0 échec les
  deux fois). Couverture shell **90,51 %** (seuil 88) — identique à la
  référence SP-33, aucune régression. Défaut de texte de plan trouvé et
  corrigé, pas un échec : la Step 4 du texte de Task 4 prédisait que le
  run complet montrerait « tous les tests passent sauf le skip Catalogue
  pré-existant » — prédiction périmée, le skip Catalogue avait déjà été
  fermé par SP-33 ; le seul skip réel du fichier avant Task 4 était
  Cartes lui-même (celui que cette tâche retire) — le résultat
  réellement observé était donc 0 skip, strictement meilleur que la
  prédiction du plan, pas un échec. **Ready to merge.**
- **SP-38 — page d'administration des utilisateurs** (4 tâches + vérification
  finale, spec `docs/superpowers/specs/2026-09-04-sp38-admin-utilisateurs-design.md`,
  plan `docs/superpowers/plans/2026-09-04-sp38-admin-utilisateurs.md` — ferme
  le chantier 4.21 de la vague 4
  (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`) : le cœur avait
  déjà `GET`/`PATCH /users` (livrés et testés par SP-31, sans que son entrée
  CLAUDE.md le documente comme tel) ; seule l'UI manquait. Unique ajout côté
  cœur : le paramètre de recherche `q` sur `GET /users`/`list_users()`,
  nécessaire pour que la recherche fonctionne à n'importe quelle échelle de
  tenant — un filtrage côté client sur une seule page de résultats paginés
  n'aurait cherché que dans la page déjà chargée. Côté shell :
  `UserSummary`/`client.listUsers`/`client.updateUserRole` sur `ItemClient`
  (+ `useUsers`/`useUpdateUserRole`), puis `UsersAdminPage` (`/admin/users`,
  `RequirePrivilege privilege="admin.users.manage"`) — sélecteur de rôle
  natif inline par ligne (erreur générique par ligne sur échec, `rowError`),
  recherche, pagination Précédent/Suivant, panneau d'aide anti-lockout
  statique, patron `TriptychLayout` identique à `RolesAdminPage` — découverte
  depuis `AdminExtensionsPage`. Aucun nouveau spec E2E (chantier UI de faible
  risque, déjà couvert par les tests d'intégration cœur en `TestClient` et
  les tests shell mockés MSW). Suite cœur **2093 passed / 5 skipped / 0
  failed** (`CORE_TEST_DATABASE_URL` pointé vers le conteneur `postgis-test`
  local, port 5433 — sans lui, 168 tests postgis/qgis skippent silencieusement
  au lieu des 5 skips qgis réels ; le chiffre de baseline du plan, 1899
  passed/3 skipped, s'est révélé lui-même périmé/inexact à la vérification —
  le diff réel depuis le commit d'ouverture du plan ne touche que
  `core/app/auth/routes.py`, `core/app/users/repository.py`,
  `core/openapi.json` et un seul fichier de test [+26 lignes, Task 1] :
  aucune régression, aucune activité concurrente détectée). Vitest shell
  **222 fichiers/1858 tests, 0 échec**, couverture 90,51 % (seuil 88,
  identique à la référence SP-33/34/36/37). `npm run build` propre. E2E
  **144 tests/140 passed/4 skipped/0 failed** — inchangé vs la référence
  SP-37, confirmé via `test-results/.last-run.json` (`status: "passed"`,
  `failedTests: []`), pas la seule fin de la sortie du reporter `list`.
  Contrôle manuel de bout en bout (Step 5, recommandé non bloquant) **non
  exécuté** : aucune stack `docker compose up -d` disponible dans cet
  environnement, non démarrée spécialement pour ce plan (décision actée par
  le brief lui-même). **Ready to merge.**
  **Revue finale de branche (opus) : 2 Important + 1 lot de Minor groupés,
  tous fermés et re-vérifiés.** (1) La route `/admin/users` n'admet que le
  privilège `admin.users.manage`, mais `UsersAdminPage` dépend aussi de
  `GET /roles` (gardé côté cœur par le privilège **distinct**
  `admin.roles.manage`) pour peupler chaque sélecteur de rôle — un rôle sur
  mesure porteur du premier privilège sans le second obtenait un
  `usersQuery` en succès et un `rolesQuery` en 403 silencieux : le garde de
  rendu `{usersQuery.data && rolesQuery.data && (<table>…)}` ne produisait
  alors ni table ni message, une page blanche sans explication. Corrigé par
  une alerte dédiée (`role="alert"`, même style que celle de
  `usersQuery.isError`) qui nomme explicitement les deux privilèges en jeu.
  (2) `useUpdateUserRole` n'invalidait que `["users"]` ; rien n'empêche un
  admin de changer son propre rôle depuis cette page (seule garde serveur :
  anti-lockout sur le dernier titulaire des privilèges sensibles, pas une
  interdiction de l'auto-rétrogradation), auquel cas `useMe()` (`["me"]`)
  continuait de servir l'ancien jeu de privilèges en cache — nav, domaines
  et `RequirePrivilege` restaient faux dans tout le shell jusqu'à un
  rechargement complet. Corrigé par l'ajout d'une seconde invalidation
  `["me"]` dans le même `onSuccess`. Lot de Minor groupé, à la recommandation
  du reviewer : `rowError` était effacé sans condition en tête de
  `handleRoleChange`, donc changer le rôle de la ligne B faisait disparaître
  un message d'erreur encore valide sur la ligne A — scopé pour ne
  s'effacer que si l'erreur affichée appartient à la ligne en cours de
  modification ; l'indicateur `pending`/`disabled` par ligne dépendait de
  `updateUserRole.isPending`/`variables?.id`, un seul objet de mutation
  partagé dont `variables` ne survit que pour le dernier appel invoqué —
  remplacé par un état local `pendingUserId`, posé avant `mutateAsync` et
  effacé en `finally` — correct pour un changement à la fois ; avec deux
  lignes en vol simultanément, le dernier posé gagne (état scalaire, limite
  assumée, non testée) ; `rowError`
  survivait un changement de page ou de recherche sans lien visible avec ce
  qui s'affichait — effacé désormais aux trois points d'entrée (recherche,
  Précédent, Suivant). Deux nouveaux tests ajoutés à
  `UsersAdminPage.test.tsx` pour les deux branches d'erreur (échec `/users`,
  échec `/roles` — la seconde vérifie explicitement l'absence de
  `<table>`) : suite passée de 7 à **9 tests, tous verts**
  (`npx vitest run src/pages/UsersAdminPage.test.tsx`). `npx tsc --noEmit`
  propre. Suite shell complète relancée (piège n°6) : **222 fichiers/1860
  tests, 0 échec** — aucune régression sur `hooks.test.ts` ni aucun autre
  consommateur de `useUpdateUserRole`. Suivis non bloquants documentés,
  non corrigés dans cette passe : pas d'état vide explicite sur une
  recherche à zéro résultat ; le lien de découverte depuis
  `AdminExtensionsPage` est gardé sur `admin.extensions.manage`, pas sur
  `admin.users.manage` lui-même — un rôle sur mesure porteur du seul
  privilège que cette page nomme dans sa propre garde de route ne peut pas
  la découvrir depuis le hub, la même classe de défaut « livré mais
  inatteignable » que ce SP existe pour combler, à reprendre dans une
  future session ; recherche sans anti-rebond à chaque frappe, dette de
  famille partagée avec le patron déjà existant de `CatalogPage`, pas
  nouvelle ici ; collision possible d'`aria-label` si deux utilisateurs
  partagent le même nom d'utilisateur. **Ready to merge.**

- **SP-39 — notifications in-app** (12 tâches, spec
  `docs/superpowers/specs/2026-09-04-sp39-notifications-in-app-design.md`,
  plan `docs/superpowers/plans/2026-09-04-sp39-notifications-in-app.md` —
  ferme le chantier 4.19 de la vague 4
  (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, document non
  modifié — même règle que SP-38 §2.7/§3.3) : un run de pipeline (ou tout
  autre job des 4 autres familles) en échec est désormais signalé dans une
  cloche persistante du shell même si l'utilisateur a quitté le panneau de
  suivi. Nouveau domaine `core/app/notifications/` (modèle, migration 0031,
  dépôt, 6 routes self-service `/notifications*` **inconditionnelles**, sans
  flag de capacité — vérifié genuinely unconditional contre le fichier réel,
  pas seulement le diff) écrit en best-effort par les **5** tâches
  procrastinate existantes (ingestion, pipeline, export, export d'app,
  rapport), chacune dans un bloc `try/except` séparé de celui qui committe
  le statut du job (`app/db.py::request_scoped_session` fait rollback de
  tout le bloc `with` sur exception — violer cette séparation aurait
  silencieusement annulé un statut de job déjà écrit). Garde
  anti-double-notification sur `export/jobs.py` : aucune notification
  `kind="export"` quand `job.page_id is not None` (rendu interne au sweep
  de rapports, notifié `kind="report"` à sa place). Côté shell :
  `NotificationBell` dans `TopBar` (badge masqué à zéro, popover, sélecteur
  de préférence `all`/`failures_only`/`none` persisté par utilisateur,
  clic sur une notification avec item → `useOpenItem` + marquage lu ; sans
  item → non cliquable), sondage `refetchInterval: 45_000` via React Query
  (pas le patron de boucle manuelle plafonnée des jobs individuels — forme
  de problème différente, sondage indéfini monté une fois pour toute la
  session). E2E 144/4/0 → **inchangé** (aucun nouveau spec E2E, décision
  explicite de la spec §5.3). Vitest shell 222→**223 fichiers, 1865
  tests**, 0 échec, couverture 90,32 % (seuil 88). Suite cœur
  **2120 passed / 5 skipped / 0 failed** (mesuré avec un conteneur
  `postgis-test` réel, driver `+psycopg` — pas `+psycopg2`, dont l'usage a
  fait échouer à tort `test_cdc_consumer_postgis.py` lors d'un premier run
  de cette clôture, corrigé en cours de vérification, sans rapport avec ce
  plan) ; l'échec intermittent préexistant
  `test_features_rls.py::test_scope_preserves_original_sql_error`
  (documenté depuis SP-29a) ne s'est pas reproduit sur ce run. Migration
  0031 testée dans les deux sens sur une base Postgres réellement non vide
  (piège n°8) : `postgis-test` s'est révélé être un schéma construit par
  `Base.metadata.create_all()` (aucune table `alembic_version`), donc
  **pas** sûr d'y lancer Alembic directement — un tenant/rôles/utilisateur/
  notification réels ont été insérés dans une base Postgres temporaire
  séparée (`sp39_migration_test`, même conteneur, détruite après coup) pour
  vérifier `upgrade head` → `downgrade -1` → `upgrade head` sans toucher au
  schéma de test partagé par les autres tâches.
  **Deux bugs `UnboundLocalError` réels trouvés sur la classe de défaut
  « variable référencée par l'appel `_notify` de la branche d'échec,
  jamais garantie liée si l'échec survient avant son affectation
  normale »** — le bloc `try/except` séparé garantit le statut du job,
  mais pas, par lui-même, que l'appel de notification ne plante pas avant
  d'atteindre son propre `try/except` : (1) `app/ingestion/tasks.py`,
  trouvé par la revue finale de la Tâche 4 (texte littéral du plan
  fautif, pas une déviation de l'implémenteur), corrigé en initialisant
  `created_by`/`collection_title` à `None` et en gardant l'appel sur
  `created_by is not None` — fermé et re-vérifié par falsification
  indépendante (retrait du correctif → crash reproduit) ; (2)
  `app/pipelines/jobs.py`, cette fois trouvé et corrigé **proactivement**
  par l'implémenteur de la Tâche 5 avant même la revue (même mécanisme,
  `item_id`), la revue ayant ensuite retracé tout le flux de contrôle pour
  confirmer qu'aucun chemin non lié ne subsiste. Les trois autres sites
  d'écriture (export, export d'app, rapport) ont chacun leurs variables
  affectées **avant** le `try` qu'elles gardent — vérifié explicitement,
  pas supposé, aucun correctif nécessaire là. **1 Important accepté comme
  dette non bloquante, non corrigé** (Tâche 8, plan-mandaté) : les deux
  sites d'écriture du sweep de rapports (`_notify_pending_reports`/
  `_record_trigger_failure`) partagent la même session/transaction que les
  lignes run+audit qu'ils ne doivent pas affecter — à la différence du
  patron `app/pipelines/jobs.py::_notify` (session isolée) — texte du plan
  explicite (« malgré le commit partagé »), risque étroit et de faible
  probabilité sous Postgres réel, mirroring un patron déjà présent
  ailleurs dans ce même fichier ; candidat à un futur correctif transverse
  sur les 5 sites d'écriture, pas traité ici. **Un vrai écart spec/schéma
  trouvé et correctement contourné** (Tâche 8) : la spec SP-39 affirme que
  `payload.channels` « peut être vide », mais
  `ReportSchedulePayload._require_at_least_one_channel` l'interdit
  réellement (contrainte délibérément testée) — le scénario littéral du
  brief était donc irréalisable via l'API de persistance réelle ;
  contourné par un test qui monkeypatche `get_config_by_item` pour prouver
  l'invariant de code sans toucher à la validation produit (changer le
  validateur serait une vraie décision produit, hors périmètre de cette
  tâche). Revues par tâche systématiques (11 tâches de code, 1 tâche
  mécanique de régénération OpenAPI/TS faite directement) : **0 Critique
  sur l'ensemble du plan**, 2 Important trouvés et fermés (les deux
  `UnboundLocalError` ci-dessus), 1 Important accepté comme dette
  documentée (session partagée du sweep de rapports), une vingtaine de
  Minor documentés par tâche (recette de contrôle non uniformisée entre
  tâches sœurs, `aria-label` partagé entre 3 éléments du popover de
  notifications une fois ouvert — à corriger dans une future tâche —,
  tests de limite de pagination absents, etc.). Revue finale de branche
  **non lancée séparément** dans ce plan : la vérification finale (Tâche
  12, ci-dessus) a servi de filet de clôture, conformément à la
  granularité déjà pratiquée sur SP-38 pour un chantier de risque
  comparable. **Ready to merge.**

- **SP-40 — pièces jointes sur une entité** (20 tâches — 18 planifiées + 2
  ajoutées en cours d'exécution, spec
  `docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md`, plan
  `docs/superpowers/plans/2026-09-04-sp40-pieces-jointes.md` — ferme le
  chantier 4.12) : une photo (ou tout autre fichier) attachée à une entité
  depuis le widget Formulaire est visible d'un lecteur autorisé et
  invisible des autres, consultable dans le popup de la carte (éditeur
  **et** widget carte de l'App Builder/`/sites/{slug}`, anonyme inclus sur
  une collection publique) et via l'outil MCP en lecture `list_attachments`.
  Nouveau domaine `core/app/attachments/` (modèle `Attachment`, dépôt,
  routes self-scoped presign/confirm/liste/lecture/suppression) inséré
  entre `app.features` et `app.collections` dans le contrat de couches ;
  upload S3 présigné (patron A6) ; lecture en proxy authentifié
  (`Depends(get_current_user_optional)`, `tenant_id` toujours résolu via
  `col.tenant_id`, jamais `user.tenant_id`) ; `Collection.attachment_fields`
  (JSON, déclaré via `PATCH /collections/{id}`) fusionné comme pseudo-champ
  `type: "attachment"` dans `GET /collections/{id}/schema` ; cascade de
  suppression depuis `remove_feature` ; `MAX_ATTACHMENT_BYTES` 25 Mo.
  Côté shell : nouveau type de champ `attachment` dans le widget
  Formulaire (upload/liste/suppression), éditeur de liste dans
  `EditCollectionPanel`, sélecteur « Pièces jointes » dans `PopupEditor`
  (câblé éditeur de carte **et** widget carte), `MapView`/`MapPopup`
  affichent la section, `/sites/{slug}` la dérive automatiquement du
  schéma. Suite core **1896→2159 passed** / 5 skipped / 0 failed (mesurée
  sur un conteneur `postgis-test` réel, rafraîchi en Tâche 18 — schéma
  périmé depuis la Tâche 7, `ALTER TABLE collections ADD COLUMN
  attachment_fields` appliqué directement, container non tracké par
  Alembic). Suite shell **222→224 fichiers / 1858→1889 tests**, couverture
  90,17 % (seuil 88). E2E **144→143 tests** (2 nouveaux specs pièces
  jointes, 1 skip Catalogue pré-existant sans rapport devenu obsolète en
  cours de route — décompte net stable).
  **Deux tâches ajoutées en cours d'exécution, hors plan initial, sur
  décision de Tanguy après escalade** — le texte du plan lui-même
  s'avérant insuffisant pour livrer la promesse de sa propre spec :
  - **Tâche 19** : le widget carte de l'App Builder (consommé aussi par
    `/sites/{slug}`) construit TOUJOURS des couches `kind: "feature"`
    (URL GeoJSON résolue), jamais `kind: "vector"` — seul l'éditeur de
    carte en produit. `MapView` (Tâche 14) ne récupérait pourtant les
    pièces jointes que pour `kind: "vector"` : la plomberie de la Tâche 15
    était donc réelle mais inerte sur `/sites/{slug}`, contrairement à la
    spec §3.4. Décision actée avec Tanguy (approche la plus sûre parmi
    deux proposées, pas de bascule de `kind` — trop invasif, aurait
    touché le pipeline de rendu/symbologie partagé de toutes les Apps
    existantes) : champs `collectionId?`/`pkColumn?` purement additifs
    sur la variante `feature` de `MapLayer`, résolution dans
    `DataContext.tsx` pour une source `type: "features", service: "core"`
    sans `datasetId` (cas `previewConfig`, sans dataset enregistré),
    câblage depuis le widget carte, garde `MapView` élargie. Un 3e site
    gardé en dur sur `"vector"` trouvé au passage (`attachmentFileUrl` de
    `MapPopup` — sans lui, la liste se serait affichée avec des liens de
    téléchargement cassés).
  - **Tâche 20** : sur une vraie collection à PK **entière** (le cas le
    plus courant), `ST_AsMVT(..., feature_id_name)`
    (`core/app/features/tiles.py`) retire la colonne PK des attributs MVT
    et la place uniquement dans `feature.id` top-level, jamais dans
    `properties` — `handlePopup` (Tâche 14) ne lisait le fid que depuis
    `properties[layer.pkColumn]`, donc le popup de carte ne remontait
    JAMAIS les pièces jointes pour ce cas, plus sérieux que le gap
    `/sites/{slug}` (touche le tout premier des 4 usages de l'objectif du
    plan). Trouvé par l'implémenteur de la Tâche 17 en tentant un
    `pkColumn` entier réaliste pour son E2E (contourné à l'origine avec
    `pkColumn: "population"`, non entière — masquant plutôt que prouvant
    le cas courant). Fix : plombe l'id déjà résolu par
    `makeFeatureClickHandler` (`f.id ?? properties[pkColumn]`, déjà
    correct pour `onFeatureClick`/cross-filter) jusqu'à `onPopup`/
    `handlePopup`. A revélé que **3 des 4 tests d'attachements déjà
    approuvés** (Tâches 14/19) avaient des fixtures combinant un `id`
    top-level arbitraire avec une valeur `properties[pkColumn]`
    différente — combinaison structurellement impossible en production
    (vérifié contre `tiles.py`/`repository.py`) — corrigées vers des
    scénarios réalistes. Le spec E2E de la Tâche 17 a ensuite pu abandonner
    son contournement (`pkColumn: "population"` → `"id"`, cas réel) après
    décodage direct du fixture binaire `world-tile.mvt` confirmant un
    `feature_id` exploitable.
  **Revue finale de branche (Tâche 18) : 1 régression réelle trouvée par
  la suite E2E complète et corrigée, indépendamment revue et vérifiée par
  falsification** : `admin-collections.spec.ts` (spec antérieure à SP-40,
  jamais mise à jour) faisait planter `EditCollectionPanel` —
  `useState(collection.attachmentFields)` sans repli, alors qu'aucun de
  ses 3 mocks de réponse collection n'inclut ce nouveau champ désormais
  requis. Confirmée régression réelle (pas pré-existante) via
  `git show d243fdff:...EditCollectionPanel.tsx`. Corrigée
  (`?? []`) et vérifiée par falsification (revert → même timeout exact
  reproduit → restauré). Suivi Minor non bloquant : les 3 mocks de ce
  spec restent incohérents avec le vrai contrat API (un vrai
  `POST /collections` renvoie toujours `attachmentFields: []`, jamais
  absent) — le correctif protège contre l'absence sans corriger les mocks
  à la source. Chaque tâche individuellement review-approuvée (spec +
  qualité), plusieurs défauts réels du texte littéral des briefs trouvés
  et corrigés en cours de route (piège n°3, détail dans le ledger de
  session).
  **Revue finale de branche transverse (Tâche 18, opus, paquet des 25
  commits) : 1 Critical (C1) + 6 Important (I2-I7), tous fermés et
  indépendamment re-revus — Ready to merge après ce lot.** Le cœur et
  les deux points les plus sensibles désignés par le plan (contrat
  `tenant_id`, ordre des hooks de `MapView.tsx` après ses 3 modifications
  cumulées) tenaient déjà ; les défauts trouvés sont tous des angles
  morts transverses qu'aucune revue par tâche ne pouvait voir seule :
  - **C1 (Critical)** : les liens de téléchargement de pièce jointe
    (`<a href>` nu, widget Formulaire ET popup carte) ne portaient aucun
    en-tête `Authorization` — 404 pour toute collection non publique,
    même pour un utilisateur autorisé ; seul le cas anonyme/collection
    publique (`/sites/{slug}`) fonctionnait. Racine dans la spec
    elle-même (exigeait un `href=` direct tout en imposant un proxy
    authentifié). Corrigé : `client.downloadAttachment` (fetch
    authentifié + `URL.createObjectURL`, patron déjà établi
    `ExplorerMenu.handleExport`) remplace les deux liens par un bouton.
    E2E renforcés pour suivre un vrai `200` sur la requête déclenchée,
    pas seulement la visibilité du lien — referme le trou par lequel C1
    était passé.
  - **I2** : `filename`/`content_type` client jamais assainis →
    `UnicodeEncodeError` (500) sur tout nom/type non-ASCII, guillemet
    permettant l'injection d'en-tête. Patron `_SAFE_FILENAME` de
    mapicons appliqué, liste noire d'extensions dangereuses posée. 2
    passes de revue supplémentaires ont trouvé et fermé : `content_type`
    encore non validé (même crash, en-tête différent) ; la première
    passe avait mutilé le nom STOCKÉ, régression sur les noms accentués
    français jamais cassés avant — corrigé par l'encodage RFC 6266/5987
    standard (ASCII de repli + valeur UTF-8 exacte), le nom brut n'étant
    plus jamais altéré en base ; contournement résiduel sur un `\n`
    final (`.match()` → `.fullmatch()`).
  - **I3** : `GET /collections/{id}/schema` fusionne les champs
    `attachment` (chantier 4.12) comme pseudo-champs sans colonne SQL —
    5 consommateurs shell les traitaient encore comme des colonnes
    réelles (symbologie de carte, lien de cross-filter, requête visuelle
    ×3, dataset édité, export CSV) — tous exclus.
  - **I4** : un champ attachment marqué « Requis » rendait le formulaire
    définitivement non soumettable (le composant ne passe jamais par
    `values`/`onChange`) — corrigé y compris pour une config déjà
    enregistrée avant ce correctif.
  - **I5** : hooks `useAttachments`/`useDeleteAttachment` sans aucun
    consommateur — supprimés.
  - **I6** : le widget carte de l'App Builder ne pouvait JAMAIS
    configurer `PopupConfig.attachmentField` (codé en dur à `[]`) —
    seule la dérivation automatique de `/sites/{slug}` l'atteignait.
    Résout maintenant le schéma de la collection liée (patron
    `FormPropsPanel`).
  - **I7** : le test de migration existant ne couvrait que
    `Base.metadata.create_all()`, jamais `alembic upgrade` ni une base
    non vide (piège n°8). Nouveau test sur une base Postgres jetable,
    vérifié par falsification. **A lui-même trouvé un vrai bug en cours
    d'écriture** : `Config("alembic.ini")` déclenche `fileConfig()` dans
    `env.py`, qui désactive par défaut tous les loggers du process non
    listés dans ce fichier — polluait 3 tests `caplog` sans rapport
    ailleurs dans la même session pytest, reproduit et corrigé
    (`Config()` sans fichier ini + `script_location` posé à la main).

  Suite finale : cœur 2170 passed/5 skipped/0 failed (Postgres réel) ;
  shell 224 fichiers/~1900 tests, `tsc`/eslint/prettier propres ; E2E 143
  passed/4 skipped/0 failed. **Ready to merge.**

- **SP-41 — métadonnées éditables et licence par jeu** (9 tâches + 1 lot de
  correctifs de revue finale, spec
  `docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md`,
  plan `docs/superpowers/plans/2026-09-04-sp41-metadonnees-licence.md` —
  ferme le chantier 4.9) : une collection peut déclarer une licence
  (résolue en URI DCAT-AP réelle et en identifiant SPDX pour STAC), un
  producteur, un contact, une fréquence de mise à jour, une généalogie,
  une langue, une version et une emprise temporelle ; un item quelconque
  (map/app/dashboard/…) peut déclarer une licence et une langue ; **un bug
  qui effaçait les mots-clés existants d'un item à chaque ouverture du
  panneau Éditer est corrigé** (`ItemDetailPage.tsx` passait
  `keywords: []` en dur au lieu de `item.keywords ?? []`). Nouveau module
  cœur `app/catalog/` (catalogues curatés licences/fréquences/langues,
  zéro dépendance, route `GET /metadata-catalog`) ; migration Alembic
  0033 (10 colonnes `Collection` + 2 colonnes `Item`, convention
  `str, default=""` sauf `language` `default="fr"`, testée upgrade/
  downgrade/upgrade sur une base Postgres jetable réellement non vide) ;
  câblage `PATCH`/`GET` sur les deux domaines ; export DCAT-AP et export
  STAC reflètent les champs déclarés, avec omission des champs non
  déclarés (sauf licence/langue, toujours présents — exception
  documentée). Côté shell : `EditCollectionPanel` passe sur des onglets
  (`ui/kit/Tabs`, Général/Métadonnées ouvertes/Pièces jointes) ;
  `MetadataForm` (consommé par `ItemDetailPage` **et** `DatasetEditPage`,
  ce dernier non listé par le brief, trouvé en cours de route) gagne
  licence + langue.
  **Défauts réels trouvés et corrigés en cours d'exécution** (piège n°3,
  pas des déviations improvisées) : Task 1 a dû repositionner
  `app.catalog` dans le contrat de couches (le brief demandait de
  l'ajouter tout en bas, mais son propre code de route importe
  `app.auth` — combinaison impossible) ; Task 3 a trouvé et corrigé un
  crash `write_audit` (`date` non JSON-serializable, `model_dump(...,
  mode="json")`) ; Task 5 a trouvé et corrigé un bug `dct:temporal` qui
  perdait tout repli `dcat:startDate` quand seule `temporal_end` était
  déclarée ; Task 7 a régénéré OpenAPI/TS et découvert que rendre
  `license`/`language`/les 10 champs `Collection` obligatoires côté TS
  cassait le typecheck de **14 fichiers de test** (le brief n'en
  anticipait que 1-3) — les 13 non réclamés par aucune tâche corrigés
  mécaniquement en suivi immédiat plutôt que différés ; Task 8 a trouvé
  un test qui ne testait pas ce qu'il prétendait (conversion `UNSET→""`
  jamais exercée) et un test cassé pré-existant de Task 7
  (`itemClient.test.ts::createBookmarkItem`, fixture `toEqual` non mise
  à jour) ; Task 10 (vérification finale) a trouvé et corrigé deux
  défauts réels dans la suite cœur, non prévus par le brief :
  `test_public_items_list.py` (allowlist non mise à jour pour
  `license`/`language`, exposition publique jugée intentionnelle — but
  même du chantier) et `test_pipeline_node_validation.py` (15 erreurs de
  fixture, `INSERT` SQL brut non mis à jour pour 8 nouvelles colonnes
  `NOT NULL`).
  **Revue finale de branche (opus, diff scopé `core/`+`shell/` depuis
  avant Task 1, 57 fichiers) : 1 Critical + 3 Important, tous fermés et
  re-vérifiés indépendamment** — le Critical et deux des trois Important
  n'étaient visibles qu'au niveau de la branche entière, aucune revue par
  tâche ne pouvait les voir seule :
  - **C1 (Critical)** : `extent.temporal` de l'export STAC émettait une
    date nue (`"2020-01-01"`) au lieu d'un instant RFC 3339 dès qu'une
    emprise temporelle était déclarée — un client STAC conforme (validé
    empiriquement avec `Collection.model_validate(doc)`, le même
    validateur que tout le reste du fichier de test) rejette alors le
    document Collection **entier**, pas seulement le champ. Passé
    inaperçu parce que les 5 nouveaux tests de Task 5/6 avaient
    justement perdu cette validation que leurs voisins utilisent tous.
    Corrigé (`T00:00:00Z`/`T23:59:59Z`), les 5 tests retrouvent leur
    `model_validate`.
  - **I2** : une emprise temporelle déclarée ne pouvait **jamais** être
    effacée par `PATCH` — `temporalStart`/`temporalEnd` n'ont pas de
    représentation « vide » non-`None` (contrairement aux 8 champs
    texte), donc « champ omis » et « champ explicitement mis à `null` »
    valaient tous deux `None` côté Python, exactement le payload envoyé
    par `EditCollectionPanel` à chaque enregistrement. Corrigé via
    `body.model_fields_set` (présence de la clé dans le JSON, même à
    `null`) plutôt que `is not None`.
  - **I3** : tous les producteurs déclarés collisionnent sur la **même**
    IRI `dct:publisher` dans `GET /dcat/catalog` — un consommateur JSON-LD
    qui fusionne le document en graphe RDF voit un seul `foaf:Agent` avec
    N `foaf:name` incohérents. Corrigé par une IRI scoping par
    `collection_id` (pas par le texte du producteur, pour éviter une
    nouvelle collision entre producteurs au nom similaire) quand un
    producteur est déclaré ; IRI partagée à l'échelle du tenant inchangée
    sinon (non-régression).
  - **I4** : les 12 nouvelles colonnes n'ont qu'un défaut Python-side
    (`default=`), pas de `server_default=` — dérive de schéma entre
    `Base.metadata.create_all()` (utilisé par toutes les suites SQLite)
    et `alembic upgrade head` (déploiement réel), déjà payée une fois
    dans ce même plan (`test_pipeline_node_validation.py`, Task 10) et
    latente sur ~4 autres fichiers de test à `INSERT` SQL brut. Corrigé
    en ajoutant `server_default` à l'identique de la migration 0033.
  6 Minor documentés en suivi non bloquant : `EditCollectionPanel` sans
  garde `??`/défaut sur les 10 nouveaux champs (même classe que le
  correctif SP-40 sur `attachmentFields`, latent tant qu'aucun E2E
  n'ouvre l'onglet Métadonnées ouvertes) ; sentinelle `UNSET`/libellé
  dupliqués sans source commune entre `EditCollectionPanel` et
  `MetadataForm` ; `resolve_language()` lève `KeyError` sans garde sur un
  id de langue absent du catalogue (inatteignable via l'API aujourd'hui,
  mais un futur rétrécissement du catalogue ou une écriture DB directe le
  rendrait exploitable) ; `licenseUri` survit à un changement de licence
  loin de `"other"` (sans conséquence, non documenté) ; les 3
  consommateurs de `useMetadataCatalog()` ne gèrent pas `isError`
  (contrôle silencieusement vide, pas de perte de données) ; le texte de
  la spec §4 n'a pas été mis à jour pour refléter le repli
  `dcat:startDate`/`created_at` quand seule `temporal_end` est déclarée
  (comportement délibéré et testé, contradiction purement documentaire).
  **Incident piège n°9 (session concurrente, sans conséquence sur le
  contenu)** : une session concurrente (« SP-42 revue globale », même
  arbre `dev`, pas de worktree) a absorbé le commit de Task 9 dans le
  sien par une course `git add`/`git commit` — contenu vérifié
  intégralement correct (`git show HEAD:<fichier>`, re-vérifié
  indépendamment par la revue via diff scopé par pathspec), aucune
  réécriture d'historique tentée. Le sous-agent du lot de correctifs de
  revue finale a lui-même heurté une limite de session (HTTP 429) juste
  après avoir commité les 4 correctifs, avant d'écrire son rapport — les
  commits étaient intacts, la vérification finale (suite complète,
  portes qualité, diff OpenAPI) et le rapport ont été complétés
  directement par le contrôleur, puis re-revus indépendamment (0
  Critical/Important/Minor).
  Suite finale : cœur **2051 passed/178 skipped/0 failed** ; shell 224
  fichiers/1906+ tests, `tsc`/lint/format propres ; E2E 142 passed/4
  skipped/0 failed (référence stable depuis SP-38/39/40, pas de
  régression). Diff OpenAPI confirmé vide sur les correctifs de revue
  finale (routes STAC/DCAT sans `response_model`). **Ready to merge.**

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
  `shell/e2e/triptych-narrow.spec.ts` à 900px sur les 6 écrans qui rendent
  réellement la grille et la font passer — Cartes incluse depuis SP-37, qui
  a retiré son `test.skip()` (les deux mécanismes du lot « Carte » sont
  clos : (b) par SP-36, (a) par SP-37) —, Tâches/Paramètres ne rendent
  aucune grille à vérifier (`<EmptyState>` seul), cf. `### Livré`/SP-33,
  SP-36 et SP-37). Reste, par
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
- Questions produit ouvertes (comparatif §8) : **Q2** (premiers utilisateurs
  réels — la seule qui puisse réordonner le phasage), Q10 (temps réel), Q11
  (offline).


---

### Suivis de stack (versions pré-SP-42, corrigées depuis dans CLAUDE.md)

Trois faits ci-dessous ont été corrigés ou requalifiés par SP-42 (Tâche 17) :
l'analyse « otel-lgtm sans `ports: !reset []` en prod » (notée dans l'entrée
SP-32 ci-dessus) est fermée depuis le commit `6eb709bd` ; le diagnostic
« `.env` plus ancien » ci-dessous s'est révélé faux, la vraie cause étant
que `scripts/bootstrap-env.sh` ne générait jamais `CORE_SECRETS_MASTER_KEY`
(corrigé par le commit `87201679`) ; la restauration de sauvegarde, décrite
ci-dessous comme « jamais rejouée », a en réalité été rejouée une fois avec
succès partiel (cf. `docs/revue/2026-09-04-backlog.md`, `REV-164`).

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
