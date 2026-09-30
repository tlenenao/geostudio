# Audit GeoStudio 2026-09-29 — plan consolidé (k01, révisé après la passe « flags allumés »)

Consolidation des 447 findings dédoublonnés (`merged.jsonl`, sortie de
`audit_findings.py dedup`), des verdicts de rejeu de `v01/findings.jsonl` et de
la passe complémentaire « flags allumés » (dossiers `j05b`, `j06b`, `j08b`,
`j09b`, `j10b`, `t01b`, `t03b`, 2026-09-30).
Ce document **ne corrige rien** : il ordonne ce qu'il faut corriger, combler ou
ajouter, par cause racine : **chaque finding devient une tâche individuelle**
(ou un petit groupe indissociable), et les tâches sont regroupées en **36
paquets d'implémentation** ordonnés par niveaux de dépendance (§6). Les
versions précédentes (30 tâches en 6 phases de 5, puis 36 en 6 × 6) sont
remplacées ; toutes les sévérités sont désormais affectées.

## 0. Chiffres et méthode

| | S1 | S2 | S3 | S4 | Total |
|---|---|---|---|---|---|
| Findings dédoublonnés, premier passage | 7 | 92 | 211 | 65 | 375 |
| **Findings dédoublonnés, après passe flags** | **13** | **114** | **249** | **71** | **447** |

- **127 S1/S2** : 80 rejoués par v01 sur une stack réinitialisée
  (**79 confirmés**, **1 non reproduit** : j01-004, artefact de l'outillage
  `stack-reset.sh`, corrigé depuis : `scripts/audit/stack-reset.sh:89` pose
  désormais `GRANT USAGE ON SCHEMA public TO PUBLIC`) ; **30 `verified` par la
  passe flags** (chaque test `bug(...)` échoue pour la raison du finding avec
  `AUDIT_VERIFY=1`), non rejoués par v01 ; **17 `probable`** non rejoués
  (lecture de code), à confirmer par le test d'acceptation de leur tâche.
- Apport de la passe : **6 S1** (j05b-002, j05b-005, j06b-001, j06b-005,
  j10b-010, j10b-011) et **24 S2** nouveaux ; deux S2 du premier passage sont
  absorbés par un finding de la passe (c09-010 → t03b-001, j06-004 → j06b-010),
  cinq sont élargis (j02-002 ← j10b-002, j08-001 ← j08b-004, j10-007 ← j10b-006,
  c02-005 ← j06b-013 + j09b-009, c02-007 ← j06b-006).
- Par nature : 159 bug, 76 improvement, 51 gap, 44 a11y, 42 security, 31 debt,
  27 perf, 16 test-gap, 1 feature.
- Méthode : regroupement par **cause racine** (§2) avant découpage en tâches ;
  chaque cause racine a été relue dans le code (pas dans les rapports d'agents,
  piège n°12) : au commit `19a536f7` pour le premier passage, au commit
  `22f61a37` pour les fichiers et lignes nouvellement cités (seuls
  `docker-compose.yml` et les scripts d'audit ont changé entre les deux, sur le
  port Grafana et `run-suite.sh`). Toutes les `locations` des 447 findings
  (856 emplacements) ont été vérifiées mécaniquement (fichier présent, lignes
  dans le fichier : 0 écart). Les `depends_on` ont été contrôlés (§2, dernière
  sous-section). La table de traçabilité (§7) est vérifiée par script (ids
  S1/S2 de `merged.jsonl` ⊆ ids du plan).
- Convention : `fichier:début-fin` = lignes relues ; « acceptation » = le test
  d'audit correspondant passe une fois `bug(` remplacé par `test(` (§8), plus
  un test pérenne dans la suite du dépôt (`core/tests/` ou `shell/e2e/`), car
  les specs `shell/e2e/journeys/` ne tournent pas en CI.

## 1. Le constat en une phrase

La suite E2E du dépôt est verte (166/0) **parce qu'elle tourne en auth mock sur
un cœur mocké** (`shell/e2e/*.spec.ts`, `mocks.ts`) : les quatre défauts qui
cassent le plus de parcours sur la stack réelle — `.defer()` hors App
procrastinate ouverte, CORS MinIO non implémenté, worker MapLibre servi en
`octet-stream`, secret HMAC de lien de partage vide — ne sont visibles **que**
sur une stack composée réelle, que ni la CI ni les E2E n'exercent. La vague de tête (P01–P06)
les traite ; P27 ajoute le filet qui les aurait attrapés.

**Ce que la passe flags ajoute** : chaque capacité allumée pour la première
fois retombe sur les **mêmes classes** — `AppNotOpen` (export PNG/PDF, runs de
pipeline, exports d'app), `PutBucketCors` (exports d'app, tilesets, terrain),
`geom`/`geometry` (pipelines, requête visuelle, mode autoporté), « livré ≠
câblé » (le `worker` n'a ni `CORE_SECRETS_MASTER_KEY` ni `CORE_EXPORT_ENABLED`)
— plus six causes que le premier passage ne pouvait pas voir (export-worker en
boucle de redémarrage, mode autoporté hors `/v1`, quotas contournables, liens
présignés sur l'hôte interne, Grafana anonyme Admin, canevas de pipeline
inutilisable au clavier). Aucune capacité allumée n'a pu être exercée de bout
en bout sans contournement (§5.2).

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
- **Passe flags** — trois capacités allumées confirment la même racine, chaque
  fois avec une ligne de job **commitée avant** le `defer` qui lève :
  `core/app/export/routes.py:90-92` (`session.commit()` puis `defer_task`) →
  **j05b-005 (S1)** ; `core/app/pipelines/routes.py:93-101` →
  `core/app/pipelines/service.py:71-75` → **j06b-001 (S1)** ;
  `core/app/appexport/routes.py:54-59`, `:86-87` → j10b-001. Conséquences :
  l'assistant de requête visuelle recrée tout au second clic (j05b-001) et les
  lignes `pending` ne sont jamais reprises (j09b-010, cf. RC-1 bis dans P01).
- Effet de bord sur l'audit : import, moissonnage, évaluation d'alerte et
  indexation sémantique n'ont jamais tourné de bout en bout ; plusieurs agents
  ont semé leurs données en SQL direct (j02, j07, j09, j10, j11) et la passe
  flags a **rejoué les tâches à la main depuis le conteneur `worker`**
  (j05b, j06b, j10b, t03b) — voir §5.

### RC-2 — Files, tâches **et variables d'environnement** non câblées au worker
- `docker-compose.yml:439-440` : `-q ingestion,search,cdc,etl,tileset3d,terrain3d,appexport`
  — pas de `harvest` ; pas de `--concurrency` (défaut 1).
- `core/app/jobs/__init__.py:66-80` : `import_paths` sans `app.compliance.jobs`.
- Findings : **c02-003 (S1)** (+j07-001), c02-004, c09-001, c09-002 (S3).
- **Passe flags** : le bloc `environment:` du `worker`
  (`docker-compose.yml:441-470`, relu) ne reçoit ni `CORE_SECRETS_MASTER_KEY`
  (présent pour `core`, `:321`), ni `CORE_EXPORT_ENABLED` (`core` `:322`,
  `export-worker` `:582`), ni `CORE_READ_ONLY_MODE` (`core` `:274`) ; et
  `CORE_PIPELINE_FILE_IO_ENABLED`, lu par `core/app/pipelines/runtime.py:484`
  et `:1069`, n'apparaît dans **aucun** service du compose. Conséquences :
  tout run de connecteur à secret, tout e-mail d'alerte et tout rapport
  planifié échouent dans le worker alors que l'aperçu (exécuté dans `core`)
  fonctionne → **j06b-005 (S1)** (+j09b-001, j09b-002 fusionnés), j09b-012
  (S3), volet câblage de j06-001. Concurrence 1 mesurée : un run de 50k lignes
  retient un export lancé 4 s après (t03b-002, même cause que c09-001).
- Classe : piège n°2 (« livré ≠ câblé ») — `test_deployability.py` ne compare
  ni les files déclarées aux `-q` des services, ni les variables lues par les
  tâches aux `environment:` du service qui les exécute.

### RC-3 — Stack de référence : défauts de config qui cassent une capacité
- MinIO reconstruit : `core/app/ingestion/storage.py:39-45` appelle
  `put_bucket_cors` sans rattraper `NotImplemented` → **j02-002 (S1)** (+j03-002).
  **Passe flags** : le même appel casse les exports d'app dans le worker
  (j10b-002, fusionné dans j02-002) et les envois de tilesets et de terrains
  (`core/app/tileset3d/routes.py:113`, `core/app/terrain3d/routes.py:72` →
  j10b-012) : c'est la racine qui bloque le plus de capacités allumées.
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
  À rejouer après P04 (§5). La passe flags n'a pas levé ce contournement
  (t01b et t03b le citent encore).

### RC-5 — Nom de colonne géométrie du lac (`geometry` vs `geom`)
- `core/app/cdc/parquet_writer.py:72` écrit le GeoDataFrame avec la colonne
  `geometry` ; `core/app/analytics/sql_sandbox.py:90-108` et
  `core/app/analytics/aggregate.py:230-266` sélectionnent/filtrent
  `table_info.geometry_column` (`geom` pour une collection importée).
- Findings : **j05-001 (S1)**, j05-002 (+j05-003, j05-018 fusionnés), et en
  aval j05-012/j05-024 (S3, `depends_on: j05-003` → fusionné dans j05-002).
- **Passe flags** — deux lecteurs de plus : `core/app/pipelines/runtime.py:196-209`
  sélectionne `"{geom_col}" AS geometry` depuis un Parquet qui n'a que
  `geometry` → j06b-002 (+j06b-008, colonne ajoutée après l'écriture du
  Parquet) et j05b-004 (requête visuelle sur une collection importée) ;
  `core/app/appexport/miniserver/items.py:52-57` (`_select_list`,
  `ST_AsGeoJSON("{info.geometry_column}")`) → **j10b-011 (S1)**. Le correctif
  doit être **un seul helper** partagé par les cinq lecteurs, sinon la classe
  revient au sixième.

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
- **Passe flags** : `core/app/alerts/notify.py:55-65` résout le secret SMTP
  **par son nom dans le tenant** (`secrets_repo.get_secret_payload(…,
  name=channel.smtpSecretName)`), sans contrôle de propriété → j09b-006
  (+j09b-005, STARTTLS sans contexte SSL) : même classe que c01-003 (coffre
  sans ACL), traitée dans la même paquet (P16).
- **Anti-lockout** : `core/app/roles/repository.py:160-170`
  (`count_users_with_privileges`) compte tous les utilisateurs du rôle sans
  filtrer `erased_at`, et `core/app/compliance/service.py:64-72` laisse son
  rôle à un compte anonymisé → le dernier administrateur actif peut être
  anonymisé (j08b-004, fusionné dans j08-001). Le même compteur garde le
  changement de rôle (`core/app/auth/routes.py:168`).

### RC-8 — Masquage GAP-22 non reporté sur les chemins d'écriture et d'export
`core/app/appexport/freeze.py:24-66`, `core/app/appexport/snapshot.py:56-88`
(lecture non masquée), `core/app/features/routes.py:632-665` (PUT = remplacement
intégral, efface les colonnes masquées) → c01-001, c01-004, j10-007, j07-015 (S3).
**Passe flags** : j10-007 est désormais **confirmé par un vrai job** (j10b-006,
fusionné) : le zip statique et le GeoParquet autoporté contiennent la valeur
masquée en lecture anonyme.

### RC-9 — Pas de version de base à l'enregistrement d'une config
`core/app/configs/routes.py:397-434`, `core/app/configs/repository.py:211-225` :
dernier écrivain gagne → j04-008 (+c03-006, t02-002), t02-003.

### RC-10 — export-worker instable et aveugle (nouvelle, passe flags)
- `docker-compose.yml:565-605` : `export-worker` lance
  `procrastinate … worker -q export` **sans** l'étape
  `python -m scripts.ensure_procrastinate_schema` que le `worker` exécute
  (`:439-440`), via `pgbouncer:6432` en pool transaction. Les journaux
  (« prepared statement "_pg3_0" already exists », « cached plan must not
  change result type ») désignent une connexion qui ne reçoit pas
  `prepare_threshold=None` (`core/app/jobs/__init__.py:51`,
  `CONNECTION_KWARGS`) — hypothèse du finding, **à confirmer** avant correctif :
  le code ne montre pas quelle connexion procrastinate échappe au réglage.
- `SHELL_BASE_URL` pointe `shell:8300` (`:584`) mais le bundle du shell embarque
  `VITE_CORE_URL=http://localhost:8200`, injoignable depuis le conteneur :
  aucune page ne devient « prête » (j05b-006, S3).
- Findings : j05b-008 (RestartCount 46 en 70 min), j05b-006. Conséquence : ni
  PDF `printLayout` ni `ReportSchedule` n'ont pu aboutir pendant la passe (§5.3).

### RC-11 — Mode d'export autoporté : contrat d'URL et colonne géométrie (nouvelle)
- `core/app/appexport/miniserver/main.py:72-160` : toutes les routes sont
  montées sans préfixe (`@app.get("/collections")`…), alors que le runtime
  shell appelle `${coreUrl}/v1` (`shell/src/api/base.ts:252`) — oubli de
  SP-57b → **j10b-010 (S1)**.
- Plus RC-5 dans le mini-serveur → **j10b-011 (S1)**.
- Le test d'intégration (`core/tests/test_appexport_standalone_e2e.py`) n'utilise
  qu'une collection sans géométrie et des chemins sans `/v1` (j10b-013, S3) ;
  l'image `geostudio-appexport-standalone:latest` suit le cœur sans version
  (j10b-009, S3).

### RC-12 — Quotas appliqués à un sous-ensemble des créations (nouvelle)
- Contrôle d'items/collections présent seulement dans
  `core/app/configs/service.py:110` et `core/app/collections/routes.py:356-357`
  (`/collections/empty`) ; absent de `register_collection`
  (`core/app/collections/routes.py:270`) → j08b-001 ; absent des créations
  faites par les jobs : `run_import` (`core/app/ingestion/importer.py:240`,
  `:285`), `_write_dataset` (`core/app/pipelines/runtime.py:901`),
  `finalize_tileset3d_task` (`core/app/tileset3d/jobs.py:79`) → j08b-010.
- Stockage : `check_storage_quota_or_raise` (`core/app/quotas/service.py:191-210`)
  est appelé **après** le téléversement par les 4 sites de confirmation, puis
  ajoute encore `additional_bytes` → double comptage (j08b-003) ;
  `usage_for_tenant` ne compte que 4 buckets
  (`core/app/quotas/service.py:99-104`) — ni exports, ni CDC, ni PostGIS
  (t03b-006, j08b-012).
- Findings : j08b-001, j08b-003, j08b-010, t03b-006 (S2) ; j08b-002, j08b-011,
  j08b-012, j08b-007, j08b-008 (S3/S4).

### RC-13 — Sorties S3 : liens et clés (nouvelle)
- `generate_presigned_get_url` (`core/app/ingestion/storage.py:63`) signe sur
  `S3_ENDPOINT_URL` (`http://minio:9000`) ; aucun point de terminaison public
  n'existe dans le code ni le compose. Consommateurs relus :
  `core/app/reports/jobs.py:298-308` (lien envoyé par webhook/e-mail →
  j09b-011), `core/app/appexport/routes.py:103-106` (`resultUrl` → j10b-008),
  `core/app/reports/routes.py:90`.
- `writer.export` (`core/app/pipelines/runtime.py:1036-1059`) fait
  `put_object(Key=p.key)` sans créer le bucket (j06b-003) ni préfixer la clé
  par le tenant (j06b-004, un Créateur écrase `renders/…`).

### RC-14 — Passerelle d'administration et observabilité (nouvelle)
- `otel-lgtm` (`docker-compose.yml:648-690`) ne pose aucune variable
  `GF_AUTH_*` : Grafana reste en accès anonyme **Admin** derrière le cookie de
  passerelle ; création d'une source de données vers `http://minio:9000`
  acceptée (j09b-007). Le routeur Traefik applique `csp-dynamic@file` à Grafana
  (`:686`), incompatible avec ses scripts en ligne (j09b-008, S3).
- Titiler : 500 `unhashable type: 'dict'` sur sa page racine, aussi en accès
  direct (`deploy/titiler/Dockerfile`, j08b-005, S3) ; URL de lancement
  construite sur `CORE_BASE_URL` (`core/app/admin_tools/routes.py:49`,
  j08b-006, S3).

### Autres rattachements de la passe flags (sans nouvelle racine)
- **Requête visuelle n'écrit pas sa sortie** (j05b-002, S1) : même cause que
  j02-003 — `core/app/features/validation.py:71-73` exige `tenant_id` comme
  colonne requise alors que le writer (`core/app/pipelines/runtime.py:826-899`)
  retire cette colonne réservée → P10.04.
- **Écriture ligne à ligne** de `writer.collection` (t03b-001, absorbe
  c09-010) : 2 050 lignes/s, `core/app/pipelines/runtime.py:826-899` → P18.
- **Alertes perdues en silence** (j09b-004) : `core/app/alerts/jobs.py:230-283`
  consomme la transition même quand la livraison échoue → P20.
- **Canevas de pipeline** (t01b-001, t01b-008) : `shell/src/builder/pipeline/PipelineCanvas.tsx:385-398`
  (`handleEdgesChange` ignore les changements `select`) et `:478-487` (connexion
  achevée seulement par `onNodeClick`) ; contraste en sombre (t01b-007) :
  `:58-60` sans `text-ink`, même base que t01-005 → P32 et P33.

### Contrôle des `depends_on` (S1/S2)
Tous les `depends_on` des S1/S2 pointent vers un id présent dans `merged.jsonl`,
sauf **t02-003 → t02-002**, fusionné dans **j04-008** (même paquet P09) ;
j05-012/j05-024 (S3) → j05-003, fusionné dans **j05-002** (P05). j08-002 (S2)
dépend de j08-006 (S3), traité dans la même paquet (P12). Passe flags :
**j10b-010, j10b-011 → j10b-013** (S3, même paquet P11) ; **j10b-012 → j10b-002**,
fusionné dans **j02-002** (même paquet P03) ; **t03b-002 (P02) → t03b-001
(P18)** : dépendance de constat, pas d'ordre — t03b-002 passe dès qu'un run
`etl` ne bloque plus la file `export`, quel que soit le débit d'écriture.
Chaque dépendance est reprise dans l'ordre des tâches (§6, colonne « Dépend de »).

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
| j05 Analyste | 1 | 2 | 14 | 1 | **bloqué** (SQL Lab sur import) | RC-5, injection de formule CSV/XLSX (j05-009) ; requête visuelle et export async : voir j05b |
| j06 Data engineer | 0 | 4 | 7 | 4 | voir j06b | `CORE_ETL_ENABLED=false` au premier passage (j06-001) ; lecture de code : topologie non validée, DSN sans garde d'egress |
| j07 Data steward | 1 | 5 | 12 | 2 | **bloqué** (moissonnage) | RC-2 file `harvest`, RC-1, source en erreur martelée (j07-006), `/stac/search` 500 sur table cassée |
| j08 Admin de tenant | 0 | 2 | 13 | 3 | dégradé | anonymisation annulée au prochain login (j08-001), page conformité inaccessible à l'Administrateur (j08-002) ; quotas : voir j08b |
| j09 Ops / instance | 0 | 3 | 10 | 2 | bloqué (alertes manuelles) | RC-1, échec de livraison invisible (j09-003), dataset vide → erreur (j09-013) ; passerelle : voir j09b |
| j10 Sites / export | 0 | 3 | 7 | 1 | dégradé | config publique de tout kind (j10-001), export non masqué (j10-007) ; exports : voir j10b |
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

**Passe « flags allumés »** (stack OIDC, ETL/export/appexport/admin tools/
quotas/tileset3d/terrain3d allumés, LLM éteint) :

| Parcours | S1 | S2 | S3 | S4 | État | Causes dominantes |
|---|---|---|---|---|---|---|
| j05b Requête visuelle, exports async | 2 | 3 | 4 | 0 | **bloqué** | RC-1 (run et `POST /v1/export` en 500), sortie jamais écrite (j05b-002 = j02-003), RC-5 sur base géométrique, RC-10 export-worker |
| j06b Pipelines exécutés | 2 | 5 | 7 | 1 | **bloqué** | RC-1 (run en 500), RC-2 (worker sans clé maître), RC-5 (reader.collection), RC-13 (bucket, clé), DSN sans egress (j06b-010) |
| j08b Quotas, passerelle, anti-lockout | 0 | 4 | 7 | 1 | dégradé | RC-12 (quotas contournables, double comptage), RC-7 anti-lockout, RC-14 Titiler 500 |
| j09b Livraison d'alertes, rapports, reprise | 1 | 6 | 4 | 0 | **bloqué** (rapports, e-mail) | RC-2 (worker sans `CORE_EXPORT_ENABLED` ni clé maître), alerte perdue sur 5xx, SMTP d'autrui, liens internes, `pending` jamais repris, Grafana Admin anonyme |
| j10b Export d'apps, 3D | 3 | 4 | 6 | 0 | **bloqué** | RC-1, RC-3 (CORS : export d'app et envois 3D), RC-11 autoporté (`/v1`, `geom`), RC-8 confirmé, RC-13 lien de bundle |
| t01b Accessibilité des surfaces allumées | 0 | 3 | 8 | 4 | dégradé | canevas DAG non utilisable au clavier (connexion, arêtes), nœuds illisibles en sombre |
| t03b Performance ETL / quotas | 0 | 3 | 6 | 0 | dégradé | écriture ligne à ligne (4 min pour 500k), worker unique à concurrence 1, usage de stockage sous-estimé ; moteur DuckDB sain (< 3 s pour 500k) |

## 4. Matrice de couverture des tests

Colonnes : **U** = tests unitaires/intégration cœur (`core/tests`, 365
fichiers) ; **E2E-mock** = `shell/e2e/*.spec.ts` (cœur mocké, CI) ;
**E2E-OIDC** = `shell/e2e-oidc/` (un seul fichier : `auth-oidc.spec.ts`) ;
**Audit** = tests Playwright écrits pendant l'audit contre la stack réelle
(premier passage : 620 tests dans 69 fichiers ; **après la passe flags :
~770 tests dans 96 fichiers**, cf. `REJEU.md`, hors CI) ; **Réel** = le
parcours a-t-il pu être exercé de bout en bout sur la stack composée.

| Domaine | U | E2E-mock | E2E-OIDC | Audit (tests) | Réel | Trou principal |
|---|---|---|---|---|---|---|
| Catalogue public / SEO / embed | oui | `catalog`, `embed` | non | j01 : 34 | partiel | aucun catalogue anonyme ; embed nominal non exercé (j13-001) |
| Lecture, fiche, bookmarks, notifications | oui | `bookmarks`, `item-detail-panels` | non | j02 : 30 | partiel | pièces jointes (RC-3) ; deep-link (RC-6) |
| Import → carte | oui | `ingestion*`, `map-*` | non | j03 : 40 | **non** | RC-1 + RC-3 : aucun import réel ; rendu carte (RC-4) |
| App builder | oui | `app-builder*`, `actions`, `variables` | non | j04 : 40 | oui | rechargement après enregistrement (ids perdus) jamais testé |
| SQL Lab / agrégats / exports | oui | `sql-lab`, `chart`, `export` | non | j05 : 35 + j05b : 25 | partiel | RC-5 ; requête visuelle et `POST /v1/export` exécutés seulement par défèrement manuel ; rendu PNG/PDF jamais abouti |
| Pipelines / connecteurs | oui | `pipeline-builder` | non | j06 : 57 + j06b : 25 | partiel (runs déférés à la main) | RC-1, RC-2 ; aucun run avec secret réussi ; connecteurs externes et `reader.file` non exercés |
| Moissonnage / STAC / DCAT | oui | `harvest-*` (6) | non | j07 : 59 | **non** | file `harvest` non consommée ; aucun serveur distant joignable |
| Admin tenant / RGPD / quotas | oui | `compliance-admin`, `quota-guard` | non | j08 : 35 + j08b : 25 | partiel | quotas testés sur un second cœur `:8201` (limites basses) ; UI de dépassement jamais rendue |
| Ops, alertes, rapports, passerelle | oui | `alert-rule`, `report-schedule`, `tasks` | non | j09 : 25 + j09b : 25 | partiel | livraisons exécutées dans un conteneur jetable (egress) ; rendu de rapport simulé en base ; métriques OTel absentes |
| Sites, story, export d'apps | oui | `sites-portal-*`, `static-export`, `connected-export` | non | j10 : 30 + j10b : 25 | partiel | exports d'app rejoués dans le worker avec `ensure_uploads_bucket` neutralisé ; autoporté sur code monté |
| Copilote / MCP | oui (fournisseur fake) | `copilot*` (jeton mock) | **non** | j11 : 24 | **non** | LLM éteint (volontaire) ; chemin OIDC du jeton MCP (j11-015) |
| Mobile / tactile | non | `map-touch`, `responsive`, `triptych-narrow` | non | j12 : 30 | partiel | RC-4 : carte jamais rendue |
| Partage / permissions | oui | `item-permissions`, `publication` | non | j13 : 34 | partiel | liens (RC-3) |
| Accessibilité | — | `a11y-audit` (9 pages) | non | t01 : 40 + t01b : 24 | partiel | thème sombre non audité en CI ; canevas DAG et tiroir tileset : états « en cours » vus par interception |
| Résilience | — | — | non | t02 : 37 | oui | arrêt worker non signalé ; 401 |
| Performance | perf import (temps mur, c05-003) | `check-bundle-size` | non | t03 : 34 + t03b : 25 | partiel | mesures carte sur contournement RC-4 ; ETL mesuré sur collections sans géométrie (RC-5) |
| Cohérence UI / i18n | lint i18n | `theme` | non | t04 : 30 | oui | — |
| Déploiement / compose | `test_deployability.py` | — | — | — | — | files vs `-q`, **variables core vs worker**, secrets vides, MIME, images/versions non contrôlés |

Conséquence pour le plan : chaque tâche des paquets P01–P06 livre, en plus du correctif,
une **règle de déployabilité** ou un test sur stack composée (P27), faute de
quoi la même classe revient à la prochaine capacité.

## 5. Angles morts et passe complémentaire

### 5.1 Premier passage : capacités éteintes

Capacités **éteintes** pendant le premier passage (stack non modifiable par
les agents) ; leurs zones n'étaient **pas saines**, elles étaient **non
auditées** :

| Capacité | Valeur pendant l'audit | Zones non exercées | Findings qui le signalent |
|---|---|---|---|
| `CORE_ETL_ENABLED` (+ `CORE_PIPELINE_FILE_IO_ENABLED`) | `false` (`docker-compose.yml:285`, `:459`) | builder de pipeline (palette 57 op, aperçu, runs, cron, webhook), connecteurs, exécution de la requête visuelle, outils MCP de pipeline, a11y du canvas DAG | j06-001, j06-009, j06-012, j06-013 ; resume j05/j06/j11/t01/t04 |
| `CORE_EXPORT_ENABLED` / `CORE_APPEXPORT_ENABLED` | `false` (`:322`, `:582`) | export asynchrone `/v1/export`, PDF `printLayout`, `ReportSchedule`, les 3 modes d'export d'app | j10-011, t03-008 ; resume j05/j09/j10/j11 |
| `CORE_ADMIN_TOOLS_ENABLED` | `false` (`:335`) | passerelle `/admin/martin\|titiler\|grafana`, jeton de lancement, cookie `gs_admin_session`, forwardAuth | j09-016 ; resume j08/j09 |
| `CORE_QUOTAS_ENABLED` | `false` (`:343`) | blocage par quota à l'import, au terrain 3D, à la création ; affichage des quotas | j08-017, t02-014 |
| `CORE_LLM_PROVIDER` | vide (`:264`) | tour de copilote réel, loopback `/mcp`, génération SQL/requête visuelle, historique | j11-001, j11-006 ; resume j05/j11 |
| `CORE_TILESET3D_ENABLED` | `false` (`:328`) | hébergement de tilesets 3D (upload, proxy) | aucun finding (angle mort muet) |
| Embeddings | fournisseur `fake` | pertinence de la recherche sémantique | j02-012 (S3, probable) |
| Profil `observability` | non démarré | Grafana, SLO, OTel | resume j09 |
| Egress de moissonnage | allowlist vide | moissonnage réel ArcGIS/WMS/WFS/WMTS/CSW/CKAN, livraison réelle webhook/SMTP | resume j07/j09 |
| Traefik / CSP enforcing | shell servi en direct sur :8300 | CSP réelle, compression, routage `seo-bots`, `sitemap.xml` racine | resume j10/t03 |

Autres angles morts du premier passage : données semées en SQL direct à cause
de RC-1/RC-3/j02-003 (le chemin d'import réel n'a donc jamais produit les
données testées) ; lecteur d'écran réel non utilisé (t01) ; appareils mobiles
réels (j12) ; `purge_tenant` jamais déclenché (consigne) ; mesures de rendu
carte sur contournement (RC-4).

### 5.2 Couvert par la passe « flags allumés » (2026-09-30)

Flags posés par `scripts/audit/enable-flags.sh` (cf. `REJEU.md`), profils
`export`, `appexport`, `observability`. Couvert, **avec les contournements
indiqués** (un parcours couvert par contournement n'est pas un parcours sain) :

| Capacité | Couvert | Contournement utilisé | Agents |
|---|---|---|---|
| Pipelines (`CORE_ETL_ENABLED`) | API complète, validation, aperçu, runs réels par le worker (reader.collection → filter/derive → writer.export), changement de schéma, erreurs, webhook entrant, cron (`*/5`), builder (palette, glisser-déposer, undo/redo, zones, réouverture) ; volumes 50k/500k ; a11y du canevas | runs déférés depuis le conteneur `worker` (RC-1) ; jeux de données sans géométrie (RC-5) | j06b, t01b, t03b |
| Requête visuelle | filtre, jointures, résumé (9 métriques), relance idempotente, round-trip « Modifier », lecture de la sortie par agrégat et SQL Lab | run déféré à la main + `ALTER TABLE … SET DEFAULT` sur la sortie (j05b-002) | j05b |
| Export async `/v1/export`, plafonds d'export | 422/404/droits, 500 `AppNotOpen`, plafond 10 000 (CSV/GeoJSON/GPKG/XLSX), contenu réel du GPKG | job déféré à la main ; rendu jamais abouti (RC-10) | j05b, t03b |
| Export d'apps (3 modes) | gel, garde des widgets, instantané GeoParquet, contenu des zips, ouverture des bundles (Statique, Connecté, Autoporté), CORS étroit, champs sensibles | tâche rejouée dans le worker avec `ensure_uploads_bucket` neutralisé (RC-3) ; zip récupéré par `docker cp` ; autoporté sur le code `core/app` monté (image locale périmée, j10b-009) | j10b, t01b |
| Tilesets 3D (`CORE_TILESET3D_ENABLED`) | proxy de lecture d'un tileset finalisé (200, 404, traversée, droits), droits d'envoi, tiroir d'envoi (a11y) | tileset créé par `finalize_tileset3d_task` rejouée ; envoi réel bloqué (j10b-012) | j10b, t01b |
| Quotas (`CORE_QUOTAS_ENABLED`) | items, collections, stockage (409 RFC 7807, concurrence de 8 créations), contournements, usage de stockage | **second cœur `:8201`** à limites basses (les limites de la stack sont inatteignables), `run_import` appelé au niveau fonction | j08b, t03b |
| Passerelle d'administration (`CORE_ADMIN_TOOLS_ENABLED`) | lancement (droits par rôle), cookie, jeton falsifié ou d'un autre outil, forwardAuth, révocation, page Infrastructure ; Grafana sous sous-chemin, dashboards et sources provisionnés | — | j08b, j09b |
| Alertes et rapports planifiés | livraison webhook réelle (payload, transition, 169.254.169.254 bloqué, cible muette), e-mail réel (auth, STARTTLS), balayages réels du worker, reprise de jobs périmés | évaluation exécutée dans un conteneur jetable à l'env du cœur (egress + RC-2) ; SMTP jetable ; rendu de rapport simulé en base | j09b |
| Anti-lockout du dernier administrateur | contournement par compte anonymisé | tenant jetable (`lockout_sim.py`) avec les services réels | j08b |
| Contexte analytique global | plage temporelle depuis `?ctx=` | — | j05b |

Première passe **confirmée ou réfutée** par la passe : j06-004 → j06b-010
(confirmé), j06-015 → j06b-006 (confirmé), j10-007/008/009/010 → j10b-006/004/
003/005 (de « probable » à « verified »), j08-015/016 → j08b-002/011
(confirmés), j08-017 levé mais périmètre du quota plus étroit que supposé
(RC-12), j05-024 confirmé (j05b-007), j05-023 nuancé (j05b-003), j06-010
réfuté (« Automatisation » n'est plus un `<span aria-disabled>`).

### 5.3 Ce qui reste non couvert

| Zone | Pourquoi | À faire pour la couvrir |
|---|---|---|
| Copilote LLM, génération SQL / requête visuelle en langage naturel, loopback `/mcp` réel (j11 entier) | `CORE_LLM_PROVIDER` **volontairement éteint** pendant toute la passe | passe dédiée avec `CORE_LLM_PROVIDER=fake`, après P07 (RC-6) |
| Observabilité : métriques, traces et journaux du cœur dans Grafana, SLO | seule la **passerelle** a été vérifiée ; `OTEL_EXPORTER_OTLP_ENDPOINT` vide sur la stack | poser l'endpoint, vérifier les séries du cœur et du worker ; revérifier après P17 |
| `reader.file` / `writer.file` | `CORE_PIPELINE_FILE_IO_ENABLED` **n'est câblé dans aucun service** du compose (RC-2) ; seul l'échec flag éteint est testé | P02 câble la variable (défaut `false`), puis un run réel flag allumé |
| Connecteurs Snowflake, BigQuery, MSSQL, Oracle, blob | aucun service externe disponible | conteneurs de test (MSSQL, Oracle XE, MinIO pour blob) ; Snowflake/BigQuery par contrat (fixtures dlt) |
| Run de connecteur **avec secret** réussi, plafonds et délais des connecteurs, outil MCP `run_pipeline` | bloqués par j06b-005 ; pas de serveur lent | après P02, P16 |
| Impression PDF `printLayout` et `ReportSchedule` de bout en bout | **bloqués par export-worker** (boucle de redémarrage, cœur injoignable, RC-10) et `POST /v1/export` en 500 (RC-1) ; rendu simulé en base | après P01 + P06 |
| Conversion terrain 3D (COG via Titiler) et tuiles terrain ; envoi réel d'un tileset | envoi bloqué par j10b-012 (RC-3) | après P03 |
| Moissonnage réel, import réel, pièces jointes réelles (j03, j07, j02 sans semis SQL) | RC-1/RC-2/RC-3 ; la passe ne les a pas relancés | après P01–P03 |
| Webhook livré **par le worker réel** | la garde d'egress bloque toute cible privée ; évaluation exécutée dans un conteneur jetable | cible de test sur réseau autorisé par l'allowlist d'egress |
| Jobs procrastinate orphelins en `doing` (worker tué en vol) | tuer le worker était interdit | test d'intégration cœur, pas de stack |
| UI de dépassement de quota | limites du shell inatteignables sans modifier la stack (P26 rend les limites réglables) | après P26 |
| Rendu carte (500k, terrain 3D, tileset hébergé), a11y carte | contournement `stubMap`/`fixWorkerMime` toujours en place (RC-4) | après P04 |
| Contexte d'emprise et cross-filter inter-datasets ; zoom 200-400 %, lecteur d'écran réel ; compression Traefik ; `purge_tenant` | hors budget ou consigne | inchangé |
| v01 sur les 30 nouveaux S1/S2 | non lancé | rejouer v01 (colonne V = « A » en §7) |


## 6. Plan : 386 tâches individuelles regroupées en 36 paquets

**Changement de structure.** Le découpage « 30 tâches en 6 phases de 5 » (puis
36 en 6 × 6) est abandonné : chaque finding de `merged.jsonl` devient une
**tâche** — une correction, ou un petit groupe indissociable quand une seule
modification ferme plusieurs findings (ex. ouvrir l'App procrastinate ferme
sept `AppNotOpen`) — et les tâches sont regroupées en **36 paquets
d'implémentation** cohérents : même cause racine, mêmes modules, même équipe de
revue, dépendances respectées. **Toutes** les sévérités sont affectées :
429 findings dans 386 tâches (13 S1, 110 S2,
236 S3, 70 S4), 18 rejets motivés (§6.4), soit
447/447 ids couverts — vérifié par script.

Lecture des tables : **Cible** = comportement attendu (champ `expected` du
finding, première phrase) ; **Fichiers** = `locations` des findings (toutes
vérifiées mécaniquement, §0) ; **Effort** = le plus fort des findings de la
tâche (XS < ½ j, S ≈ 1 j, M ≈ 2–3 j, L ≈ 1 sem, XL > 1 sem) ; **Dépend de** =
`depends_on` des findings et dépendances relevées pendant la consolidation
(§2) ; **Acceptation** = les tests `bug(` du parcours passent et sont basculés
en `test(` (§8), sinon le `repro` du finding (script ou sonde, inversé).
Chaque tâche livre en plus un test pérenne dans `core/tests/` ou `shell/e2e/`
(les specs `shell/e2e/journeys/` ne tournent pas en CI).

### 6.1 Ordre d'exécution et parallélisme

Le **niveau** d'un paquet = 1 + le niveau le plus haut des paquets dont une de
ses tâches dépend (calculé depuis la colonne « Dépend de », sans cycle). Tous
les paquets d'un même niveau peuvent être menés **en parallèle** ; un paquet
peut démarrer ses tâches sans dépendance externe avant la fin des niveaux
précédents (la dépendance est par tâche, pas par paquet).

| Niveau | Paquets (en parallèle) | Attend |
|---|---|---|
| 1 | P01 Jobs procrastinate, P02 Câblage du worker, P04 Shell servi, P05 Colonne géométrie du lac, P07 Session OIDC et stockage local par compte, P08 Installation, release et secrets de déploiement, P09 Intégrité des écritures et versions de config, P10 Builder d'app, formulaires et écriture d'entités, P12 Rôles, privilèges, RGPD et anti-lockout, P13 Fuites de lecture et surfaces publiques, P17 Passerelle d'administration et observabilité, P21 Contrats d'API du cœur, P27 CI, tests et filets d'infrastructure, P33 Accessibilité transverse, P34 Cohérence UI et i18n, P36 Documentation | — |
| 2 | P03 Stockage S3, P06 export-worker, rendu PNG/PDF et rapports planifiés, P14 Partage, groupes et liens, P15 Masquage GAP-22 sur tous les chemins, P16 Coffre de secrets, connecteurs et egress, P18 Pipelines, P19 Moissonnage, STAC et DCAT, P20 Alertes et notifications, P22 Client shell, P23 MCP et copilote, P24 Index et balayages SQL, P25 DuckDB, lakehouse et SQL Lab, P28 Import de fichiers, P29 Données complètes et troncatures annoncées, P31 Mise en page mobile et carte tactile, P32 Canevas de pipeline | P01, P02, P04, P05, P07, P08, P09, P10, P12, P21, P33, P34 |
| 3 | P11 Export d'apps, P26 Quotas appliqués à toute création, P30 Carte, P35 Catalogue public, SEO et parcours lecteur | P01, P03, P04, P05, P07, P12, P22, P24 |

Ordre recommandé : au niveau 1, **P01, P02, P04, P05 d'abord** (elles
débloquent la stack réelle et invalident des mesures, §2 RC-1, RC-2, RC-4,
RC-5), en parallèle de P07, P08 et P09 ; au niveau 2, **P03 puis P06** (la
tâche P03.01 n'attend rien et peut partir dès le début ; seules P03.02–P03.03
attendent P01.01). Les paquets shell (P33, P34) et la documentation (P36) n'ont
aucune dépendance et peuvent être confiés à une autre équipe dès le départ.
Après P01–P03 : relancer j03, j07, j02 sans semis SQL et j05b/j06b/j10b sans
contournement (§5.3) ; après P07 : la passe LLM fake.

| Paquet | Titre | Revue | Tâches | S1/S2 | S3/S4 | Niveau | Dépend de (paquets) |
|---|---|---|---|---|---|---|---|
| P01 | Jobs procrastinate : ouverture dans l'API et reprise des jobs (RC-1) | cœur — jobs/infra | 8 | 12 | 5 | 1 | — |
| P02 | Câblage du worker : files, variables, concurrence (RC-2) | cœur — jobs/infra + déploiement | 6 | 6 | 2 | 1 | — |
| P03 | Stockage S3 : CORS MinIO, buckets, liens présignés (RC-3, RC-13) | cœur — stockage | 7 | 6 | 3 | 2 | P01, P09 |
| P04 | Shell servi : nginx, MIME, cache, bundle (RC-4) | shell — build/nginx | 7 | 2 | 6 | 1 | — |
| P05 | Colonne géométrie du lac (RC-5) | cœur — analytique/lakehouse | 2 | 4 | 1 | 1 | — |
| P06 | export-worker, rendu PNG/PDF et rapports planifiés (RC-10) | cœur — jobs/infra | 4 | 1 | 3 | 2 | P01 |
| P07 | Session OIDC et stockage local par compte (RC-6) | shell — auth | 8 | 5 | 3 | 1 | — |
| P08 | Installation, release et secrets de déploiement | déploiement | 8 | 4 | 4 | 1 | — |
| P09 | Intégrité des écritures et versions de config (RC-9) | cœur — configs/migrations | 10 | 6 | 4 | 1 | — |
| P10 | Builder d'app, formulaires et écriture d'entités | shell — builder | 16 | 5 | 12 | 1 | — |
| P11 | Export d'apps : mode autoporté, garde et gel (RC-11) | cœur — appexport | 7 | 2 | 7 | 3 | P01, P03, P05 |
| P12 | Rôles, privilèges, RGPD et anti-lockout (RC-7) | cœur — authz | 16 | 4 | 14 | 1 | — |
| P13 | Fuites de lecture et surfaces publiques (RC-7) | cœur — authz | 11 | 4 | 7 | 1 | — |
| P14 | Partage, groupes et liens (RC-7) | cœur — authz + shell | 14 | 4 | 11 | 2 | P08, P12 |
| P15 | Masquage GAP-22 sur tous les chemins (RC-8) | cœur — authz | 5 | 3 | 2 | 2 | P10 |
| P16 | Coffre de secrets, connecteurs et egress | cœur — sécurité | 8 | 4 | 5 | 2 | P02 |
| P17 | Passerelle d'administration et observabilité (RC-14) | déploiement + sécurité | 8 | 1 | 7 | 1 | — |
| P18 | Pipelines : exécution, planification, écriture | cœur — pipelines | 12 | 3 | 9 | 2 | P01 |
| P19 | Moissonnage, STAC et DCAT | cœur — fédération | 16 | 4 | 12 | 2 | P01, P02 |
| P20 | Alertes et notifications | cœur — alertes + shell | 15 | 3 | 13 | 2 | P01, P02 |
| P21 | Contrats d'API du cœur : validation stricte et RFC 7807 | cœur — API | 9 | 3 | 6 | 1 | — |
| P22 | Client shell : `base.request`, erreurs et connectivité | shell — API/client | 11 | 0 | 11 | 2 | P21, P34 |
| P23 | MCP et copilote | cœur — MCP/copilote | 16 | 2 | 14 | 2 | P07 |
| P24 | Index et balayages SQL | cœur — perf/migrations | 9 | 5 | 5 | 2 | P09 |
| P25 | DuckDB, lakehouse et SQL Lab : bornes et exactitude | cœur — analytique | 16 | 2 | 16 | 2 | P05 |
| P26 | Quotas appliqués à toute création (RC-12) | cœur — quotas | 9 | 4 | 8 | 3 | P01, P03 |
| P27 | CI, tests et filets d'infrastructure | CI/déploiement | 14 | 4 | 10 | 1 | — |
| P28 | Import de fichiers | cœur — ingestion + shell | 10 | 0 | 11 | 2 | P01 |
| P29 | Données complètes et troncatures annoncées | cœur — features + shell | 9 | 5 | 7 | 2 | P01 |
| P30 | Carte : `MapView` et éditeur de carte | shell — carte | 5 | 1 | 5 | 3 | P04, P22 |
| P31 | Mise en page mobile et carte tactile | shell — mise en page | 15 | 5 | 10 | 2 | P04 |
| P32 | Canevas de pipeline | shell — pipelines + a11y | 10 | 3 | 7 | 2 | P33 |
| P33 | Accessibilité transverse | shell — a11y | 27 | 4 | 23 | 1 | — |
| P34 | Cohérence UI et i18n | shell — UI | 24 | 0 | 24 | 1 | — |
| P35 | Catalogue public, SEO et parcours lecteur | shell + cœur public | 12 | 2 | 10 | 3 | P07, P12, P24 |
| P36 | Documentation | doc | 2 | 0 | 9 | 1 | — |

### 6.2 Paquets et tâches

#### P01 — Jobs procrastinate : ouverture dans l'API et reprise des jobs (RC-1)

- Portée : RC-1. Tous les `.defer()` synchrones du process API lèvent `AppNotOpen` ; les lignes de job commitées avant le `defer` restent `pending`/`queued` à jamais.
- Revue : cœur — jobs/infra ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : nouveau test d'intégration cœur **sans deferrer mocké** (`POST /v1/uploads` → ligne `procrastinate_jobs`) ; l'image `core` et la CI résolvent la même version de procrastinate ; retirer de `REJEU.md` le contournement « `.defer()` rejoué à la main depuis le worker ».

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P01.01 | **j03-001** (S1), **j07-002** (S2), **j09-001** (S2), **t02-004** (S2), **j05b-005** (S1), **j06b-001** (S1), **j10b-001** (S2) | Ouvrir `app.jobs.app` dans le `lifespan` du cœur (ou `defer_async`) : débloque import, moissonnage, alertes, runs de pipeline, export PNG/PDF, export d'app | `core/app/ingestion/routes.py:66-70`, `core/app/harvest/routes.py:116-120`, `core/app/harvest/routes.py:303-326`, `core/app/alerts/service.py:73` (+10) | S | P01.02 | `bug(`→`test(` : j03-001, j07-002, j09-001, j09-002, j11-003, t02-004, j05b-005, j06b-001, j10b-001 — `j03/import-api.spec.ts`, `j05b/exports.spec.ts`, `j06b/run-api.spec.ts`, `j06b/ui-builder.spec.ts`, `j07/harvest-api.spec.ts`, `j09/alerts-api.spec.ts`, `j10b/export-pipeline.spec.ts`, `j11/mcp-api.spec.ts`, `t02/api-errors.spec.ts` |
| P01.02 | **j03-018** (S2) | Image reproductible, dépendances figées par le lockfile. | `core/Dockerfile:48` | S | — | repro inversé : `cd core && grep -n 'uv pip install' Dockerfile` |
| P01.03 | **c02-005** (S2) | La réclamation marque l'ancien run failed (avec une requête conditionnelle sur son statut) et ne relance que si le run est réellement mort (heartbeat… | `core/app/pipelines/repository.py:180-197`, `core/app/pipelines/jobs.py:271-290` | M | P01.01 | `bug(`→`test(` : j06b-013, j09b-009 — `j06b/webhook-cron-api.spec.ts`, `j09b/recovery.spec.ts` |
| P01.04 | **j03-003** (S2), c02-007 (S3), **j09b-010** (S2) | « Commit puis defer » : reprendre aussi les jobs `pending`/`queued` trop anciens (re-defer ou erreur « jamais pris en charge ») | `core/app/ingestion/repository.py:89-119`, `core/app/ingestion/tasks.py:173-205`, `core/app/pipelines/service.py:104-109`, `core/app/ingestion/routes.py:213-221` (+3) | M | P01.01, P01.03 | `bug(`→`test(` : j03-003, j06b-006, j09b-010 — `j03/import-api.spec.ts`, `j06b/run-api.spec.ts`, `j09b/recovery.spec.ts` |
| P01.05 | c02-006 (S3) | Chaque transition est un UPDATE conditionnel sur le statut attendu (WHERE status='running') dont le rowcount décide de la suite, et une tâche longue… | `core/app/ingestion/repository.py:70-122`, `core/app/export/repository.py:69-120`, `core/app/appexport/repository.py:58-100` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-09-29/c02/repro/test_c02_repro.py -p tests.conftest -p no:cacheprovider --ba…` |
| P01.06 | c02-013 (S3) | Un Engine unique par process worker, créé paresseusement et réutilisé par toutes les tâches. | `core/app/jobs/common.py:40-46`, `core/app/harvest/jobs.py:20-22`, `core/app/items/jobs.py:25-28`, `core/app/tileset3d/jobs.py:32-34` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/engine_per_job.py $SCRATCH` |
| P01.07 | t02-013 (S3), j09-014 (S3) | Santé de file exposée par `/health` et `/v1/instance` (worker arrêté visible) | `core/app/main.py:392-394`, `core/app/instance/routes.py:19-31`, `docker-compose.yml:383` | M | P01.01 | `bug(`→`test(` : t02-013 — `t02/services-down.spec.ts` |
| P01.08 | **j05b-001** (S2) | Un échec de lancement est rattrapable sans créer d'objets orphelins ni de doublons (réutiliser les objets déjà créés, relancer seulement le run, ou n… | `shell/src/pages/VisualQueryWizardPage.tsx:250-326` | M | P01.01 | `bug(`→`test(` : j05b-001 — `j05b/wizard-exec.spec.ts` |

#### P02 — Câblage du worker : files, variables, concurrence (RC-2)

- Portée : RC-2 (« livré ≠ câblé », piège n°2). Files non consommées, modules de tâches non importés, variables lues par les tâches absentes de l'`environment:` du `worker`, concurrence 1.
- Revue : cœur — jobs/infra + déploiement ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : les nouvelles règles de `test_deployability.py` échouent si l'on retire `harvest` du `-q` ou `CORE_SECRETS_MASTER_KEY` du `worker` (falsification, piège n°10) ; compose prod et `deploy/ansible/` alignés.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P02.01 | **c02-003** (S1) | Toute file déclarée par une tâche est consommée par au moins un worker déployé, et un test de déployabilité le vérifie. | `docker-compose.yml:440`, `core/app/harvest/jobs.py:25-51` | XS | — | `bug(`→`test(` : j07-001 — `j07/harvest-api.spec.ts` |
| P02.02 | **c02-004** (S2) | Toute tâche déférable est enregistrée dans le worker (import_paths complet) et un test compare les tâches connues du process API à celles du worker. | `core/app/jobs/__init__.py:64-80`, `core/app/compliance/jobs.py:28-40`, `core/app/compliance/routes.py:76-85` | XS | — | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/queues_vs_workers.py` |
| P02.03 | **c09-001** (S2), **t03b-002** (S2) | Concurrence du worker : `-c N` ou service `-q etl` dédié | `docker-compose.yml:439-440`, `core/app/pipelines/jobs.py:189-190` | M | — | `bug(`→`test(` : t03b-002 — `t03b/pipeline-volume.spec.ts` |
| P02.04 | **j06b-005** (S1), j09b-012 (S3) | Parité d'environnement `core`/`worker` (`CORE_SECRETS_MASTER_KEY`, `CORE_EXPORT_ENABLED`, `CORE_READ_ONLY_MODE`, `CORE_PIPELINE_FILE_IO_ENABLED`) + règle de déployabilité | `docker-compose.yml:431-446`, `docker-compose.yml:321`, `core/tests/test_deployability.py:1-40` | S | — | `bug(`→`test(` : j06b-005, j09b-001, j09b-002 — `j06b/run-api.spec.ts`, `j09b/alerts-delivery.spec.ts`, `j09b/reports.spec.ts` |
| P02.05 | c09-002 (S3) | Un tick de balayage/compaction déjà en attente ne doit pas être re-déféré (queueing_lock) ; | `core/app/pipelines/jobs.py:271-273`, `core/app/alerts/jobs.py:469-471`, `core/app/reports/jobs.py:449-451`, `core/app/cdc/jobs.py:19-21` | S | P02.03 | repro inversé : `grep -rn 'queueing_lock' core/app ; grep -rn '@app.periodic' -A1 core/app` |
| P02.06 | **j06-001** (S2) | Au moins une passe d'audit/E2E tourne sur une stack avec ETL activé (worker etl + file), sinon toute la surface pipeline reste non testée de bout en… | `core/app/main.py:301-302` | M | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06/etl-disabled-api › "les routes pipelines ne sont pas mont…` |

#### P03 — Stockage S3 : CORS MinIO, buckets, liens présignés (RC-3, RC-13)

- Portée : RC-3 (`put_bucket_cors` → `NotImplemented` sur le MinIO reconstruit) et RC-13 (liens signés sur `http://minio:9000`, bucket d'export non créé, clé non préfixée).
- Revue : cœur — stockage ; niveau 2 ; dépend de : P01, P09.
- Critères de clôture du paquet, en plus des tâches : test contre le MinIO réel ; retirer du rejeu j10b la neutralisation de `ensure_uploads_bucket` ; règle de déployabilité : point de terminaison public posé dès qu'un export est allumé.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P03.01 | **j02-002** (S1), **j10b-012** (S2) | Rattraper `NotImplemented` sur `put_bucket_cors`, CORS via `MINIO_API_CORS_ALLOW_ORIGIN` : débloque pièces jointes, import, export d'app, tilesets, terrain | `core/app/ingestion/storage.py:39-45`, `core/app/attachments/routes.py:169-190`, `core/app/ingestion/routes.py:73-84`, `core/app/tileset3d/routes.py:113` (+1) | S | — | `bug(`→`test(` : j02-002, j03-002, j10b-002, j10b-012 — `j02/reader-data.spec.ts`, `j03/import-api.spec.ts`, `j03/map-ui.spec.ts`, `j10b/export-pipeline.spec.ts`, `j10b/tiles3d.spec.ts` |
| P03.02 | **j06b-003** (S2) | writer.export crée le bucket s'il manque (ou le compose/init le crée). | `core/app/pipelines/runtime.py:1040-1059` | XS | P01.01 | `bug(`→`test(` : j06b-003 — `j06b/a-export-bucket.spec.ts` |
| P03.03 | **j06b-004** (S2) | Clé forcée sous un préfixe tenant/pipeline, sans chemin absolu ni remontée. | `core/app/pipelines/runtime.py:1058-1059` | S | P01.01 | `bug(`→`test(` : j06b-004 — `j06b/run-api.spec.ts` |
| P03.04 | **j09b-011** (S2), **j10b-008** (S2) | Signer les liens de téléchargement sur un point public (ou route cœur qui redirige) | `core/app/reports/jobs.py:298-308`, `core/app/appexport/routes.py:103-106` | S | P03.01 | `bug(`→`test(` : j09b-011, j10b-008 — `j09b/reports.spec.ts`, `j10b/bundle-ui.spec.ts` |
| P03.05 | c09-016 (S3) | Plafond de taille par fichier (head_object avant lecture) et lecture partielle pour l'inspection. | `core/app/ingestion/routes.py:87-105`, `core/app/ingestion/tasks.py:105-125`, `core/app/ingestion/storage.py:71-73` | S | — | repro inversé : `grep -rn 'MAX_UPLOAD\\|max_upload' core/app --include=*.py` |
| P03.06 | c01-012 (S4) | Un job ne devrait être lisible que par son initiateur (ou un admin), comme dans core/app/ingestion/routes.py. | `core/app/tileset3d/routes.py:240-249`, `core/app/terrain3d/routes.py:142-150`, `core/app/export/routes.py:96-111` | XS | — | critère de la cible (lecture de code) |
| P03.07 | c02-011 (S3) | La suppression S3 n'a lieu qu'après le commit de la suppression en base (ou via une file de purge d'objets orphelins). | `core/app/attachments/repository.py:82-118`, `core/app/features/routes.py:667-695` | S | P09.01 | critère de la cible (lecture de code) |

#### P04 — Shell servi : nginx, MIME, cache, bundle (RC-4)

- Portée : RC-4. `shell/nginx.conf:20-22` sans type `mjs` : worker MapLibre jamais démarré ; pas de cache ni de 404 d'asset.
- Revue : shell — build/nginx ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : `GET /assets/maplibre-gl-worker.mjs` → `text/javascript` sur l'image construite ; retirer `stubMap`/`fixWorkerMime` ; puis rejouer j03-017, les mesures carte de t03 et l'a11y carte de t01.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P04.01 | **j12-001** (S1), t03-002 (S3) | Servir `.mjs` en `text/javascript` (et gzip) : worker MapLibre | `shell/nginx.conf:20-22`, `shell/vite.copyMaplibreWorker.ts:29-35`, `shell/src/map/maplibreWorkerSetup.ts:21`, `shell/nginx.conf:6-8` | XS | — | `bug(`→`test(` : j12-001, t03-002 — `j12/map-touch.spec.ts`, `t03/bundle.spec.ts` |
| P04.02 | t03-001 (S3) | Assets hachés servis en 'Cache-Control: public, max-age=31536000, immutable', index.html en 'no-cache'. | `shell/nginx.conf:20-22` | XS | — | `bug(`→`test(` : t03-001 — `t03/bundle.spec.ts` |
| P04.03 | t03-003 (S3) | Les requêtes /assets/* absentes répondent 404 ; | `shell/nginx.conf:20-22` | XS | — | `bug(`→`test(` : t03-003 — `t03/bundle.spec.ts` |
| P04.04 | t03-004 (S4) | Ni manifeste ni fixtures de test dans l'image de production. | `shell/Dockerfile:19`, `shell/public/fixtures/gauge-extension-widget.js:1-57` | XS | — | `bug(`→`test(` : t03-004 — `t03/bundle.spec.ts` |
| P04.05 | t03-006 (S3) | Seuil avec une marge (~5 %) ou budget en gzip, et un index.js (462 Ko bruts) allégé. | `shell/.bundle-size-threshold:1`, `shell/scripts/check-bundle-size.mjs:26-44` | XS | — | `bug(`→`test(` : t03-006 — `t03/bundle.spec.ts` |
| P04.06 | **t03-005** (S2) | Le catalogue atteint un LCP < 2,5 s sur profil mobile ; | `shell/src/pages/CatalogSpatialFilter.tsx:50-166`, `shell/src/pages/CatalogPage.tsx:240-246`, `shell/vite.config.ts:30-50` | M | — | `bug(`→`test(` : t03-005 — `t03/bundle.spec.ts`, `t03/vitals.spec.ts` |
| P04.07 | j03-017 (S3) | Un filet E2E vérifie le rendu canvas (style local, fond tuilé hors-ligne). | `shell/e2e/journeys/j03/map-ui.spec.ts:105-111` | L | — | repro inversé : `Non rejouable en test : limite d'environnement documentée dans resume.md` |

#### P05 — Colonne géométrie du lac (RC-5)

- Portée : RC-5. Le GeoParquet porte `geometry`, les lecteurs cherchent `table_info.geometry_column` (`geom`).
- Revue : cœur — analytique/lakehouse ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : un **helper unique** fixe le nom canonique, réutilisé par P11 (mini-serveur autoporté) ; test cœur sur une collection **importée**.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P05.01 | **j05-001** (S1), **j05-002** (S2), **j05b-004** (S2), **j06b-002** (S2) | Helper unique de nom de colonne géométrie pour SQL Lab, agrégats, `reader.collection`, requête visuelle | `core/app/analytics/sql_sandbox.py:90-108`, `core/app/cdc/parquet_writer.py:72`, `core/app/analytics/aggregate.py:230-266`, `core/app/pipelines/runtime.py:196-215` (+2) | M | — | `bug(`→`test(` : j05-001, j05-002, j05-003, j05-018, j05b-004, j06b-002, j06b-008 — `j05/aggregate-api.spec.ts`, `j05/sql-api.spec.ts`, `j05b/wizard-misc.spec.ts`, `j06b/run-api.spec.ts` |
| P05.02 | j05-012 (S3) | Une colonne timestamptz reste un TIMESTAMP dans la table matérialisée. | `core/app/analytics/sql_sandbox.py:115-125` | S | P05.01 | `bug(`→`test(` : j05-012 — `j05/sql-api.spec.ts` |

#### P06 — export-worker, rendu PNG/PDF et rapports planifiés (RC-10)

- Portée : RC-10. export-worker en boucle de redémarrage (statements préparés via pgbouncer, pas de `ensure_procrastinate_schema`) et incapable de joindre le cœur depuis la page rendue.
- Revue : cœur — jobs/infra ; niveau 2 ; dépend de : P01.
- Critères de clôture du paquet, en plus des tâches : `RestartCount` stable sur 30 min avec exports en file ; un `POST /v1/export` PDF aboutit à `done` ; débloque la couverture PDF/`ReportSchedule` (§5.3).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P06.01 | **j05b-008** (S2) | export-worker tourne sans redémarrage derrière PgBouncer en pool transaction, comme le worker. | `core/app/jobs/__init__.py:40-55`, `docker-compose.yml:565-600` | M | P01.01 | repro inversé : `docker inspect geostudio-export-worker-1 --format '{{.RestartCount}}' && docker logs geostudio-export-worker-1 2>&1 \| grep -B2 'Database er…` |
| P06.02 | j05b-006 (S3) | Une configuration qui rend l'export impossible est détectée (sonde au démarrage ou erreur du job explicite : le cœur n'est pas joignable depuis expor… | `core/app/export/jobs.py:95-120`, `docker-compose.yml:565-600` | S | — | `bug(`→`test(` : j05b-006 — `j05b/exports.spec.ts` |
| P06.03 | j09b-013 (S3) | Premier déclenchement calé sur le prochain tick cron après la création. | `core/app/reports/repository.py:127-152` | S | P06.01 | `bug(`→`test(` : j09b-013 — `j09b/reports.spec.ts` |
| P06.04 | c01-014 (S3) | Modifier destinataires/canaux devrait exiger que l'éditeur puisse lire lui-même toutes les données rendues, ou l'exécution devrait se faire avec les… | `core/app/reports/jobs.py:183-217`, `core/app/alerts/jobs.py:98-113`, `core/app/configs/report_validation.py:17-26` | M | P06.01 | critère de la cible (lecture de code) |

#### P07 — Session OIDC et stockage local par compte (RC-6)

- Portée : RC-6. `signinSilent()` à chaque tour de copilote démonte le shell ; `returnTo` perdu ; historiques `localStorage` partagés entre comptes.
- Revue : shell — auth ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : nouveau `shell/e2e-oidc/copilot-oidc.spec.ts` (LLM fake) : brouillon et pile d'annulation intacts après 3 tours ; 25 tours sans 422.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P07.01 | **j11-007** (S1) | Le tour de copilote s'applique au brouillon courant sans remonter l'application ni perdre l'état d'édition. | `shell/src/builder/copilot/useMcpToken.ts:52-86`, `shell/src/auth/RequireAuth.tsx:28-33` | M | — | `bug(`→`test(` : j11-007 — `j11/copilot-ui.spec.ts` |
| P07.02 | **j02-004** (S2) | Le retour Keycloak restaure la route demandée (état de redirection conservé) et nettoie code/state de l'URL. | `shell/src/auth/AuthProvider.tsx:38-58`, `shell/src/auth/RequireAuth.tsx:13-17` | S | — | `bug(`→`test(` : j02-004 — `j02/reader-ui.spec.ts` |
| P07.03 | **j02-010** (S2) | Sans jeton, la route usage redirige vers la connexion (ou attend l'auth), puis affiche l'app ; | `shell/src/shell/routes.tsx:361`, `shell/src/pages/AppRuntimePage.tsx:28-30`, `shell/src/pages/AppRuntimePage.tsx:140-150` | S | P07.02 | `bug(`→`test(` : j02-010 — `j02/reader-ui.spec.ts` |
| P07.04 | **j11-009** (S2) | Le shell tronque l'historique (fenêtre glissante <= 40 messages) et borne la saisie (maxLength 4000). | `shell/src/builder/copilot/CopilotChat.tsx:60-67`, `core/app/copilot/routes.py:31-52` | XS | P07.01 | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j11/copilot-server.spec.ts -g 'motifs de refus' (preuve serve…` |
| P07.05 | **j11-015** (S2) | Au moins un scénario e2e-oidc : tour de copilote avec brouillon conservé et jeton d'audience geostudio-mcp. | `shell/src/builder/copilot/useMcpToken.ts:52-63` | M | P07.01 | repro inversé : `ls shell/e2e-oidc ; grep -ril 'copilot\\|mcp' shell/e2e-oidc` |
| P07.06 | t02-008 (S3) | Sur 401, le shell tente un renouvellement silencieux puis, à défaut, invite à se reconnecter (ou redirige vers la connexion). | `shell/src/api/base.ts:255-285`, `shell/src/api/base.ts:57-76` | M | — | `bug(`→`test(` : t02-008 — `t02/connectivity.spec.ts` |
| P07.07 | j05-016 (S3) | L'historique est cloisonné par utilisateur (clé suffixée de l'id) et purgé à la déconnexion. | `shell/src/lib/sqlLabHistory.ts:10-20` | XS | — | `bug(`→`test(` : j05-016 — `j05/sqllab-ui.spec.ts` |
| P07.08 | j11-008 (S3) | L'historique est relisible dans le panneau (et scopé par utilisateur/item), ou la persistance est retirée. | `shell/src/lib/copilotHistory.ts:13-22`, `shell/src/builder/copilot/CopilotChat.tsx:90-93` | S | — | repro inversé : `grep -rn readCopilotHistory shell/src --include=*.tsx` |

#### P08 — Installation, release et secrets de déploiement

- Portée : Images non publiées pour la branche, `sed` de l'installeur, secrets HMAC vides par défaut (RC-3), surfaces Keycloak/Traefik exposées.
- Revue : déploiement ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : installation à blanc depuis le tag publié (aucun `manifest unknown`) ; règle de déployabilité : aucun `*_SECRET` requis par une route active n'a de défaut vide sans être généré par `bootstrap-env.sh`.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P08.01 | **c06-004** (S1) | Le tag d'images et la révision du dépôt déployé sont solidaires : la release bumpe GEOSTUDIO_VERSION et le playbook checkout le même tag. | `.env.example:347`, `deploy/ansible/playbook.yml:27-32`, `docker-compose.prod.yml:30` | XS | — | critère de la cible (lecture de code) |
| P08.02 | **c06-001** (S2) | Toute valeur (secret S3, TS_AUTHKEY) est écrite littéralement dans .env quel que soit son contenu. | `scripts/install.sh:170-185` | XS | — | repro inversé : `bash -c 'cd $(mktemp -d); printf "K=\n" > .env; v="ab&cd/ef"; sed -i.bak "s\|^K=.*\|K=${v}\|" .env; cat .env'` |
| P08.03 | **c06-005** (S2) | Le mot de passe temporaire (ou un lien de reset) est communiqué à l'opérateur exactement une fois, quelle que soit la passe. | `deploy/ansible/playbook.yml:34-72`, `scripts/install.sh:413-420` | S | — | critère de la cible (lecture de code) |
| P08.04 | c06-013 (S4) | Le secret passe par stdin ou variable d'environnement du conteneur. | `scripts/install.sh:354-356` | XS | — | critère de la cible (lecture de code) |
| P08.05 | c06-010 (S3) | Le tag n'est publiable que depuis un commit de main dont ci.yml est vert ; | `.github/workflows/release.yml:3-6`, `.github/workflows/release.yml:9-79` | S | — | repro inversé : `gh api repos/tlenenao/geostudio/branches/main/protection` |
| P08.06 | **j13-001** (S2) | Une installation standard génère le secret (ou le cœur refuse de démarrer / désactive proprement la fonction avec un 503 explicite) et la création d'… | `scripts/bootstrap-env.sh:17-28`, `docker-compose.yml:327`, `core/app/sharing/share_links.py:34-52`, `.env.example:230` | XS | — | `bug(`→`test(` : j13-001 — `j13/sharing-api.spec.ts`, `j13/sharing-ui.spec.ts` |
| P08.07 | c06-008 (S3) | Le découvreur de labels passe par un proxy de socket en lecture seule limité aux endpoints containers/events. | `docker-compose.prod.yml:293-300` | XS | — | critère de la cible (lecture de code) |
| P08.08 | j11-016 (S3) | DCR volontaire et cadré (Trusted Hosts, jeton d'enregistrement initial) ou désactivé hors besoin, et documenté comme surface d'onboarding MCP. | `deploy/keycloak/geostudio-realm.json:1458-1470` | S | — | repro inversé : `curl -s -X POST http://localhost:8180/realms/geostudio/clients-registrations/openid-connect -H 'content-type: application/json' -d '{"clien…` |

#### P09 — Intégrité des écritures et versions de config (RC-9)

- Portée : Commit après réponse, références inverses non gardées, FK sans `ON DELETE`, dernier écrivain gagne, downgrades destructeurs.
- Revue : cœur — configs/migrations ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : migrations testées **sur base non vide** dans les deux sens (piège n°8) ; OpenAPI + types TS régénérés (piège n°1).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P09.01 | **c02-001** (S2) | Une écriture n'est annoncée comme réussie qu'après un commit effectif ; | `core/app/db.py:180-195`, `core/app/main.py:262-266` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-09-29/c02/repro/test_c02_repro.py -p tests.conftest -p no:cacheprovider --ba…` |
| P09.02 | **c02-002** (S2) | Les trois routes de suppression d'une config/item appliquent la même garde _require_no_reverse_references et refusent en 409. | `core/app/configs/routes.py:311-352`, `core/app/configs/routes.py:66-76` | XS | — | `bug(`→`test(` : j13-003 — `j13/sharing-api.spec.ts` |
| P09.03 | **c03-001** (S2) | Supprimer un pipeline, une alerte, un rapport, une carte exportée, une app exportée ou un item moissonné réussit (historique purgé ou détaché) ou ren… | `core/app/configs/routes.py:79-89`, `core/alembic/versions/0018_pipeline_runs.py:24`, `core/alembic/versions/0036_pipeline_webhook_tokens.py:26`, `core/alembic/versions/0020_alert_evaluations.py:24` (+4) | S | — | repro inversé : `cd core && CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= CORE_ENV=development PYTHONPATH=. uv run pytest ../docs/rev…` |
| P09.04 | **j04-008** (S2) | PUT refuse (409/412) une sauvegarde issue d'une version périmée, ou l'UI détecte le conflit. | `core/app/configs/repository.py:211-225`, `core/app/configs/routes.py:397-433` | M | P09.01 | `bug(`→`test(` : j04-008, t02-002 — `j04/rights-history.spec.ts`, `t02/api-errors.spec.ts` |
| P09.05 | **t02-003** (S2) | L'écriture porte la version lue (If-Match / champ baseVersion) ; | `core/app/configs/routes.py:397-434`, `shell/src/pages/AppBuilderPage.tsx:585-591`, `shell/src/api/domains/apps.ts:89-93` | M | P09.04 | `bug(`→`test(` : t02-003 — `t02/api-errors.spec.ts`, `t02/connectivity.spec.ts` |
| P09.06 | **j04-003** (S2) | Un événement beforeunload prévient d'une perte de modifications non enregistrées. | `shell/src/lib/useDirtyGuard.tsx:12-25` | S | — | `bug(`→`test(` : j04-003 — `j04/builder-ui.spec.ts` |
| P09.07 | t02-001 (S3) | Un plafond de corps (413) est appliqué à l'API JSON, pour qu'un créateur ne puisse pas saturer la base, la mémoire d'uvicorn et l'historique de versi… | `core/app/configs/routes.py:137-166` | S | — | `bug(`→`test(` : t02-001 — `t02/api-errors.spec.ts` |
| P09.08 | j03-015 (S3) | La nouvelle version est listée comme courante aussitôt après l'enregistrement. | `shell/src/builder/ConfigHistoryPanel.tsx:56-58`, `shell/src/pages/MapEditorPage.tsx:189-190` | S | — | `bug(`→`test(` : j03-015 — `j03/map-ui.spec.ts` |
| P09.09 | c03-008 (S3) | Même tolérance documentée que 0042.downgrade (savepoint par instruction) sur la jumelle gis_rls. | `core/alembic/versions/0008_collections_admin.py:68-72` | XS | — | critère de la cible (lecture de code) |
| P09.10 | c03-009 (S3) | Un downgrade qui détruit des preuves d'effacement ou un marquage de champs sensibles échoue si des lignes existent, ou exporte l'état avant de le sup… | `core/alembic/versions/0039_erasure.py:43-45`, `core/alembic/versions/0042_sensitive_fields.py:45-65`, `core/alembic/versions/0042_sensitive_fields.py:68-118` | S | — | critère de la cible (lecture de code) |

#### P10 — Builder d'app, formulaires et écriture d'entités

- Portée : Round-trip des ids d'actions, écriture refusée (`tenant_id` exigé), états de widgets et de pages.
- Revue : shell — builder ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : test cœur `POST /collections/empty` puis `POST …/items` → 201 ; test d'intégration assistant de requête visuelle → run → lignes de sortie ; retirer le contournement `ALTER TABLE … SET DEFAULT` de `REJEU.md`.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P10.01 | **j04-001** (S2) | Les actions gardent leur id à l'aller-retour et se retirent/éditent individuellement. | `core/app/configs/schemas.py:46-54`, `shell/src/builder/ActionsPanel.tsx:66-68` | XS | — | `bug(`→`test(` : j04-001, j10-006 — `j04/wiring-ui.spec.ts`, `j10/builder-ui.spec.ts` |
| P10.02 | **j04-010** (S2) | Toute erreur non rattachable à un champ visible déclenche le message générique (role=alert). | `shell/src/builder/widgets/form.tsx:660-676` | S | — | `bug(`→`test(` : j04-010 — `j04/form-map.spec.ts` |
| P10.03 | **j04-011** (S2) | Les raccourcis de suppression ne s'activent que si le focus est sur le canevas/body. | `shell/src/pages/AppBuilderPage.tsx:143-156` | XS | — | `bug(`→`test(` : j04-011, j04-012 — `j04/keyboard.spec.ts` |
| P10.04 | **j02-003** (S2), **j05b-002** (S1) | Ne pas exiger la colonne réservée `tenant_id` dans `validate_feature` (formulaires et `writer.collection`) | `core/app/features/validation.py:71-73`, `core/app/collections/provisioning.py:44-58`, `core/app/pipelines/runtime.py:826-899`, `shell/src/pages/VisualQueryWizardPage.tsx:284-289` | S | — | `bug(`→`test(` : j02-003, j05b-002 — `j02/reader-data.spec.ts`, `j05b/wizard-ops.spec.ts` |
| P10.05 | t01-014 (S3) | Les touches Suppr/Retour arrière ne suppriment un widget que lorsque le focus est sur le canevas, pas sur un contrôle de formulaire. | `shell/src/pages/AppBuilderPage.tsx:144-156` | XS | — | `bug(`→`test(` : t01-014 — `t01/dialogs.spec.ts` |
| P10.06 | j04-002 (S3) | Seuls des widgets de production figurent dans la palette (exemples derrière un flag dev). | `shell/src/pages/AppBuilderPage.tsx:51-52` | XS | — | `bug(`→`test(` : j04-002 — `j04/builder-ui.spec.ts` |
| P10.07 | j04-004 (S3) | La suppression d'une page purge les messages orphelins (pruneMessagesForIds sur les ids de ses widgets) et demande confirmation. | `shell/src/builder/PageManager.tsx:25-30`, `shell/src/pages/AppBuilderPage.tsx:367-368` | S | — | `bug(`→`test(` : j04-004 — `j04/wiring-ui.spec.ts` |
| P10.08 | j04-005 (S3) | Le champ reflète l'état du brouillon après undo/redo. | `shell/src/builder/VariablesPanel.tsx:66-69` | XS | — | `bug(`→`test(` : j04-005 — `j04/wiring-ui.spec.ts` |
| P10.09 | j04-006 (S3) | Un état explicite (source introuvable) est affiché ; | `shell/src/builder/widgets/data.tsx:108-109`, `shell/src/builder/widgets/data.tsx:284-285` | XS | — | `bug(`→`test(` : j04-006 — `j04/data-runtime.spec.ts` |
| P10.10 | j04-009 (S3) | Le créateur peut ajuster largeur/hauteur (poignée ou champs) et dupliquer un widget. | `shell/src/builder/GridCanvas.tsx:95-130` | L | — | `bug(`→`test(` : j04-009 — `j04/rights-history.spec.ts` |
| P10.11 | j04-014 (S3) | Nom non vide, unique et identifiant valide ; | `shell/src/builder/VariablesPanel.tsx:44-50`, `shell/src/builder/VariablesContext.tsx:20-24` | S | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j04/wiring-ui -g 'deux variables de même nom'` |
| P10.12 | j04-015 (S4) | Un identifiant de page inconnu affiche un état explicite ou redirige vers la première page. | `shell/src/builder/pages.ts:13-15` | XS | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j04/wiring-ui -g 'identifiant de page inconnu'` |
| P10.13 | j04-016 (S4) | Le libellé affiche le titre lisible de la collection/dataset. | `shell/src/builder/DataSourcePanel.tsx:130-150` | XS | — | repro inversé : `Voir libellé des options après ajout d'une source dans e2e/journeys/j04/form-map.spec.ts (test 'formulaire : charger les champs')` |
| P10.14 | t02-009 (S3) | Le message du cœur (detail, ou « Réessayez dans N s » sur 429) est affiché, comme à la création d'un élément. | `shell/src/pages/AppBuilderPage.tsx:604-609`, `shell/src/api/domains/apps.hooks.ts:17-27` | S | — | `bug(`→`test(` : t02-009 — `t02/connectivity.spec.ts` |
| P10.15 | j10-002 (S4) | Un identifiant de chapitre inconnu retombe explicitement sur le premier chapitre (libellé « Chapitre 1 / 3 ») ou affiche une page introuvable. | `shell/src/builder/AppRenderer.tsx:142-190`, `shell/src/builder/pages.ts:13-15` | XS | — | `bug(`→`test(` : j10-002 — `j10/story-ui.spec.ts` |
| P10.16 | j12-012 (S3) | Sans layouts.sm explicite, les widgets s'empilent pleine largeur en sm (ou l'éditeur propose « empiler sur mobile »). | `shell/src/builder/AppRenderer.tsx:110-125`, `shell/src/builder/grid.ts:16-20` | M | — | `bug(`→`test(` : j12-012 — `j12/builder-touch.spec.ts` |

#### P11 — Export d'apps : mode autoporté, garde et gel (RC-11)

- Portée : RC-11. Mini-serveur autoporté hors `/v1` et sur la mauvaise colonne géométrie ; garde et gel incomplets.
- Revue : cœur — appexport ; niveau 3 ; dépend de : P01, P03, P05.
- Critères de clôture du paquet, en plus des tâches : rejeu j10b sur l'image construite (et non le code monté) ; le test e2e autoporté échoue si l'on retire `/v1` (falsification).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P11.01 | **j10b-010** (S1) | Le conteneur autoporté répond sous /v1 et l'app exportée affiche ses données. | `core/app/appexport/miniserver/main.py:72-160`, `shell/src/api/base.ts:252` | S | P01.01, P03.01, P11.02 | `bug(`→`test(` : j10b-010 — `j10b/bundle-ui.spec.ts` |
| P11.02 | **j10b-011** (S1), j10b-013 (S3) | Mini-serveur : colonne géométrie du GeoParquet + test e2e avec géométrie et chemins `/v1` | `core/app/appexport/miniserver/items.py:52-57`, `core/app/cdc/parquet_writer.py:82-85`, `core/tests/test_appexport_standalone_e2e.py:121-122`, `core/tests/test_appexport_standalone_e2e.py:206` | S | P05.01, P11.01 | `bug(`→`test(` : j10b-011 — `j10b/bundle-ui.spec.ts` |
| P11.03 | j10b-009 (S3) | L'image du bundle est épinglée à la version du cœur qui l'a produit, et le manifeste porte un numéro de version vérifié au démarrage avec un message… | `core/app/appexport/bundler.py:49-53`, `core/app/appexport/manifest.py:64` | S | — | repro inversé : `Exporter un bundle standalone (cf. export-pipeline.spec.ts « standalone »), dézipper, puis docker run -d -p 8393:8000 -v <dir>/data:/data:r…` |
| P11.04 | j10b-003 (S3) | Tout widget intégré du registre du shell est accepté ; | `core/app/appexport/guard.py:32-57` | XS | — | `bug(`→`test(` : j10b-003 — `j10b/export-pipeline.spec.ts` |
| P11.05 | j10b-004 (S3) | La garde parcourt récursivement les widgets imbriqués (tabs, modal, drawer) avant d'accepter le bundle. | `core/app/appexport/guard.py:68-78` | S | — | `bug(`→`test(` : j10b-004 — `j10b/export-pipeline.spec.ts` |
| P11.06 | j10b-005 (S3), j10-010 (S3) | Signaler la troncature à 50 000 enregistrements | `core/app/appexport/freeze.py:64`, `core/app/appexport/snapshot.py:88` | S | — | `bug(`→`test(` : j10b-005 — `j10b/export-pipeline.spec.ts` |
| P11.07 | j10b-007 (S3) | Seuls les items de kind app/dashboard sont exportables ; | `core/app/appexport/routes.py:44-47`, `core/app/appexport/jobs.py:126-134` | XS | — | `bug(`→`test(` : j10b-007 — `j10b/export-pipeline.spec.ts` |

#### P12 — Rôles, privilèges, RGPD et anti-lockout (RC-7)

- Portée : RC-7 côté rôles : pas de plafond « ≤ mes privilèges », anonymisation annulée au login, dernier administrateur anonymisable, routes shell non gardées.
- Revue : cœur — authz ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : PoC `c01/poc/test_c01_authz_poc.py` inversé ; test de migration 0030 sur base avec un Lecteur.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P12.01 | **c01-002** (S2), j08-007 (S3) | Plafond « ≤ mes privilèges » à l'attribution de rôle et à l'édition de son propre rôle | `core/app/auth/routes.py:140-198`, `core/app/roles/routes.py:81-138`, `core/app/roles/routes.py:55-80` | M | — | `bug(`→`test(` : j08-007 — `j08/users-roles-api.spec.ts` |
| P12.02 | **c03-002** (S2) | Un aller-retour downgrade/upgrade de 0030 ne doit jamais élever les privilèges d'un compte ; | `core/alembic/versions/0030_roles.py:98-114`, `core/alembic/versions/0030_roles.py:76-95` | S | — | repro inversé : `cd core && CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= CORE_ENV=development PYTHONPATH=. uv run pytest ../docs/rev…` |
| P12.03 | **j08-001** (S2) | Un compte anonymisé ne doit pas pouvoir être recréé avec ses données personnelles ; | `core/app/compliance/service.py:79-83`, `core/app/users/repository.py:13-45` | M | — | `bug(`→`test(` : j08-001, j08b-004 — `j08/compliance-usage-api.spec.ts`, `j08b/admin-tools-api.spec.ts` |
| P12.04 | **j08-002** (S2) | L'anonymisation (réversible dans son effet, admin.users.manage) doit être atteignable par l'admin ; | `shell/src/shell/chrome/SettingsNav.tsx:36-40`, `shell/src/shell/routes.tsx:327-337`, `core/app/roles/privileges.py:74-79`, `core/app/compliance/routes.py:32-60` | S | P12.06 | `bug(`→`test(` : j08-002 — `j08/admin-ui.spec.ts` |
| P12.05 | j08-005 (S3) | Nom non vide, borné, unique (insensible à la casse) dans le tenant et distinct des rôles prédéfinis ; | `core/app/roles/schemas.py:13-20`, `core/app/roles/routes.py:55-80`, `core/app/roles/repository.py:108-120` | S | — | `bug(`→`test(` : j08-005 — `j08/users-roles-api.spec.ts` |
| P12.06 | j08-006 (S3) | Action d'anonymisation par ligne de la liste des utilisateurs avec confirmation, et messages distincts (introuvable, déjà anonymisé, dernier titulair… | `shell/src/pages/ComplianceAdminPage.tsx:19-70`, `shell/src/pages/UsersAdminPage.tsx:15-60` | M | P12.04 | `bug(`→`test(` : j08-006 — `j08/admin-ui.spec.ts` |
| P12.07 | j08-013 (S4) | Indicateur erased dans la liste, sélecteur de rôle désactivé, exclusion de userCount. | `core/app/auth/routes.py:107-115`, `core/app/quotas/service.py:42-47` | XS | — | `bug(`→`test(` : j08-013 — `j08/compliance-usage-api.spec.ts` |
| P12.08 | j08-018 (S3) | Colonnes e-mail/nom/dernière connexion, désactivation de compte, tri et filtre par rôle côté serveur. | `core/app/auth/routes.py:139-186`, `core/app/users/repository.py:13-50` | M | — | repro inversé : `curl -H "Authorization: Bearer $ADMIN" http://localhost:8200/v1/users (jeton audit-admin) ; ouvrir /admin/users : deux colonnes.` |
| P12.09 | c01-010 (S3) | Un privilège catalogué devrait être appliqué côté serveur, ou être documenté explicitement comme purement navigationnel. | `core/app/roles/privileges.py:8-13`, `shell/src/auth/capabilities.ts:59` | M | — | critère de la cible (lecture de code) |
| P12.10 | j02-015 (S3) | Décision produit explicite : soit le Lecteur peut créer ses propres vues (privilège dédié ou analytics.view), soit le manque est documenté dans le ca… | `core/app/roles/privileges.py:85-97` | S | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j02 -g 'toutes les écritures'` |
| P12.11 | j05b-009 (S3) | Soit l'Analyste peut produire des datasets dérivés (privilège dédié), soit l'assistant lui est masqué/désactivé avec une explication. | `core/app/roles/privileges.py:11-14`, `shell/src/shell/routes.tsx:260` | M | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j05b/wizard-misc -g "Analyste"` |
| P12.12 | j05-022 (S3), j06-013 (S3) | Routes shell pipelines / requête visuelle sous `RequirePrivilege` | `shell/src/shell/routes.tsx:260`, `shell/src/shell/routes.tsx:258-264`, `shell/src/pages/PipelineBuilderPage.tsx:101` | S | — | `bug(`→`test(` : j05-022 — `j05/visualquery-ui.spec.ts` |
| P12.13 | j08-011 (S3) | Message explicite du nombre d'utilisateurs bloquant la suppression. | `shell/src/pages/RolesAdminPage.tsx:47-56`, `shell/src/i18n/catalog.fr.ts:201` | XS | — | `bug(`→`test(` : j08-011 — `j08/admin-ui.spec.ts` |
| P12.14 | j08-012 (S3) | Titre adapté (« Tâches du tenant ») et colonne/filtre par utilisateur quand tasks.view_all. | `shell/src/pages/UsagePage.tsx:42-175`, `shell/src/pages/UsagePage.tsx:103` | S | — | `bug(`→`test(` : j08-012 — `j08/admin-ui.spec.ts` |
| P12.15 | j08-014 (S4) | Les caractères % et _ recherchés littéralement (échappement). | `core/app/users/repository.py:107-113` | XS | — | repro inversé : `curl ci-dessus avec le jeton de audit-admin.` |
| P12.16 | j08-009 (S3) | Formulaire d'enregistrement, suppression (avec confirmation), état vide explicite. | `shell/src/pages/AdminExtensionsPage.tsx:8-75`, `core/app/extensions/routes.py:97-109` | M | — | `bug(`→`test(` : j08-009 — `j08/admin-ui.spec.ts` |

#### P13 — Fuites de lecture et surfaces publiques (RC-7)

- Portée : RC-7 côté lecture : `scope` non typé, config publique de tout kind, tables système registrables, formules CSV, routes sans authentification.
- Revue : cœur — authz ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : tests cœur de non-régression pour chaque fuite (valeur de `scope` inconnue → 422).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P13.01 | **j02-001** (S2) | Une valeur de scope hors all\|mine\|shared\|public est rejetée (422) ou retombe sur le filtre le plus restrictif ; | `core/app/items/repository.py:335-349`, `core/app/items/routes.py:62-72`, `core/app/items/routes.py:97-118` | XS | — | `bug(`→`test(` : j02-001 — `j02/reader-api.spec.ts` |
| P13.02 | **j10-001** (S2) | La route publique ne sert que les kinds destinés au public (site, app, dashboard, map, dataset) ; | `core/app/public/routes.py:117-124`, `core/app/items/routes.py:129-180` | S | — | `bug(`→`test(` : j10-001 — `j10/site-api.spec.ts` |
| P13.03 | **t02-005** (S2) | Seules les tables métier sont candidates : les tables du cœur, de Keycloak et de la file de jobs sont exclues (liste d'exclusion étendue ou schéma dé… | `core/app/collections/routes.py:430-466`, `core/app/db.py:114` | S | — | `bug(`→`test(` : t02-005 — `t02/api-errors.spec.ts` |
| P13.04 | **j05-009** (S2) | Ces cellules sont neutralisées (préfixe apostrophe/typage texte) dans les deux formats. | `core/app/analytics/export.py:45`, `core/app/analytics/export.py:69-90` | S | — | `bug(`→`test(` : j05-009 — `j05/export-api.spec.ts` |
| P13.05 | j10-004 (S3) | La liste publique et la galerie ne présentent que des kinds destinés au public. | `core/app/public/routes.py:51-70`, `shell/src/builder/widgets/gallery.tsx:71-80` | XS | P13.02 | `bug(`→`test(` : j10-004 — `j10/site-api.spec.ts` |
| P13.06 | c01-007 (S3) | Une réponse dont le contenu dépend de l'identité (non masquée ou authentifiée) devrait être private (ou porter Vary: Authorization). | `core/app/features/tiles.py:129-190` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_tiles_cache_poc.py::tes…` |
| P13.07 | j06b-009 (S3) | 401 sans session. | `core/app/pipelines/routes.py:72-74` | XS | — | `bug(`→`test(` : j06b-009 — `j06b/preview-authz-api.spec.ts` |
| P13.08 | j08-008 (S3) | moduleUrl restreint à https (ou à une allowlist d'origines), tag conforme à la grammaire des custom elements, tailles > 0, chaînes non vides sur PATC… | `core/app/extensions/schemas.py:23-44`, `core/app/extensions/routes.py:32-66`, `shell/src/builder/extensions/moduleCache.ts:1-10` | S | — | repro inversé : `Reproduire les 3 curl ci-dessus avec le jeton de audit-admin (POST /v1/extensions, PATCH /v1/extensions/aud-j08-ext).` |
| P13.09 | c01-013 (S4) | La configuration de partage ne devrait être lisible qu'avec l'action share. | `core/app/items/service.py:36-45` | XS | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_authz_poc.py::test_any_…` |
| P13.10 | j02-005 (S4) | La liste des groupes et l'ACL d'un item ne sont visibles que de qui peut partager l'item/gérer le catalogue. | `core/app/sharing/routes.py:30-45`, `core/app/items/service.py:36-45` | S | — | `bug(`→`test(` : j02-005 — `j02/reader-api.spec.ts` |
| P13.11 | j03-007 (S3) | Le présigné est réservé à data.manage. | `core/app/ingestion/routes.py:74-80` | XS | — | `bug(`→`test(` : j03-007 — `j03/import-api.spec.ts` |

#### P14 — Partage, groupes et liens (RC-7)

- Portée : RC-7 côté partage : publication par un Lecteur, groupes sans CRUD, données liées non partagées, liens de partage.
- Revue : cœur — authz + shell ; niveau 2 ; dépend de : P08, P12.
- Critères de clôture du paquet, en plus des tâches : outil MCP `set_sharing` soumis à la même garde (test de parité) ; méthodes `ItemClient` + types régénérés.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P14.01 | **j13-002** (S2) | Publier, rendre public, re-partager ou créer un lien exigent, en plus du rôle de partage editor, le privilège du kind (ou un privilège dédié de publi… | `core/app/items/routes.py:130-160`, `core/app/items/service.py:48-74`, `core/app/items/routes.py:246-255`, `core/app/sharing/authorization.py:84-85` | S | P12.01 | `bug(`→`test(` : j13-002 — `j13/sharing-api.spec.ts` |
| P14.02 | **j13-004** (S2) | Le créateur d'un groupe (et un administrateur) liste les membres, en retire, renomme et supprime le groupe ; | `core/app/sharing/routes.py:30-98`, `core/app/sharing/repository.py:94-109` | M | — | `bug(`→`test(` : j13-004 — `j13/sharing-api.spec.ts` |
| P14.03 | **j13-008** (S2) | Au partage d'une carte/app, le panneau signale les sources non partagées et propose de les partager avec le même groupe (ou le propriétaire dispose d… | `core/app/sharing/authorization.py:74-86`, `shell/src/shell/routes.tsx:290-299`, `shell/src/shell/ShareForm.tsx:248-266` | M | — | `bug(`→`test(` : j13-008, j13-009 — `j13/sharing-api.spec.ts` |
| P14.04 | **j03-012** (S2) | Avertissement à la publication ou proposition de publier les collections référencées. | `shell/src/shell/ItemActions.tsx:26-40` | M | P14.01 | `bug(`→`test(` : j03-012 — `j03/map-api.spec.ts` |
| P14.05 | j13-010 (S3) | Le cœur combine rôle de partage et privilège de kind dans permissions, et le shell n'affiche pas une commande vouée au 403. | `core/app/items/repository.py:81-95`, `shell/src/shell/ItemActions.tsx:118-125` | S | P14.01 | `bug(`→`test(` : j13-010 — `j13/sharing-ui.spec.ts` |
| P14.06 | c01-006 (S3), c08-001 (S3) | Révocation d'un lien : vérifier que le lien appartient à l'item | `core/app/items/routes.py:318-339`, `core/app/sharing/repository.py:165-173`, `core/app/sharing/repository.py:165-172` | XS | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_authz_poc.py::test_shar…` |
| P14.07 | j13-005 (S3) | Ajout de membre par recherche de nom/e-mail (annuaire restreint aux utilisateurs du tenant) ou, a minima, identifiant visible et copiable dans Paramè… | `shell/src/shell/ShareForm.tsx:196-246`, `shell/src/pages/SettingsPage.tsx:20-35`, `core/app/auth/routes.py:117-126` | S | — | `bug(`→`test(` : j13-005 — `j13/sharing-ui.spec.ts` |
| P14.08 | j13-006 (S3) | « Créer le groupe » n'est affiché qu'avec catalog.manage et « Ajouter un membre » que sur les groupes dont l'utilisateur est créateur (GET /groups do… | `shell/src/shell/ShareForm.tsx:319-380`, `core/app/sharing/routes.py:47-58`, `core/app/sharing/repository.py:100-101` | XS | — | `bug(`→`test(` : j13-006 — `j13/sharing-ui.spec.ts` |
| P14.09 | j13-007 (S3) | Libellé explicite (« Visible par tous les membres de l'organisation ») et rappel dans le panneau de l'état de publication anonyme, avec lien vers l'a… | `shell/src/i18n/catalog.fr.ts:611`, `core/app/items/repository.py:338-346` | XS | — | `bug(`→`test(` : j13-007 — `j13/sharing-ui.spec.ts` |
| P14.10 | j13-011 (S3) | Le lien partageable pointe vers une page du shell (/embed/{jeton} ou /shared/{jeton}) sur l'origine publique de l'instance. | `core/app/items/routes.py:291-299`, `shell/src/shell/ShareForm.tsx:143-161` | S | P08.06 | critère de la cible (lecture de code) |
| P14.11 | j13-012 (S4) | Libellé lisible (date localisée, créateur, créé le), liens inactifs repliés. | `shell/src/shell/ShareForm.tsx:81-113`, `shell/src/i18n/catalog.fr.ts:638` | XS | P08.06 | critère de la cible (lecture de code) |
| P14.12 | j13-013 (S3) | Distinguer « peut modifier » de « peut gérer le partage » (rôle manager ou option du propriétaire), comme les rôles contributeur/gestionnaire des cat… | `core/app/sharing/authorization.py:84-85` | M | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j13/sharing-api.spec.ts -g 'co-propriétaire'` |
| P14.13 | c01-005 (S3) | Un lien de partage devrait cesser de fonctionner dès que son créateur ne peut plus lire (ou partager) l'item racine. | `core/app/configs/routes.py:353-395`, `core/app/items/routes.py:342-381`, `core/app/configs/guest_access.py:67-112` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_authz_poc.py::test_shar…` |
| P14.14 | j01-010 (S3) | Un parcours d'audit authentifié (creator) qui crée un lien de partage à échéance courte puis le rejoue en anonyme (nominal, expiré, révoqué). | `shell/src/pages/EmbedPage.tsx:75-100` | M | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j01 -g 'embed'` |

#### P15 — Masquage GAP-22 sur tous les chemins (RC-8)

- Portée : RC-8. Masquage absent des chemins d'écriture (PUT intégral), d'export d'app et de schéma.
- Revue : cœur — authz ; niveau 2 ; dépend de : P10.
- Critères de clôture du paquet, en plus des tâches : édition par formulaire d'un utilisateur masqué ne met aucune colonne sensible à NULL.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P15.01 | **c01-001** (S2) | Modifier sensitiveFields devrait exiger data.view_sensitive (ou admin.collections.manage), faute de quoi un éditeur non habilité peut démasquer les c… | `core/app/collections/routes.py:599-686` | S | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_authz_poc.py::test_coll…` |
| P15.02 | **c01-004** (S2) | L'édition d'une entité ne devrait jamais écraser les colonnes que l'utilisateur n'a ni vues ni envoyées (masquées ou non gérées par le formulaire). | `core/app/features/routes.py:632-665`, `core/app/features/repository.py:217-243`, `shell/src/builder/widgets/form.tsx:522-527`, `shell/src/builder/widgets/form.tsx:644-648` | M | P10.04 | critère de la cible (lecture de code) |
| P15.03 | **j10-007** (S2) | Un export ne contient que ce qu'un lecteur anonyme (ou l'exportateur sans data.view_sensitive) peut lire : champs sensibles masqués. | `core/app/appexport/freeze.py:24-66`, `core/app/appexport/snapshot.py:56-88`, `core/app/features/rls.py:32-40` | M | P10.04 | `bug(`→`test(` : j10-007, j10b-006 — `j10/export-core.spec.ts`, `j10b/export-pipeline.spec.ts` |
| P15.04 | j07-015 (S3) | Schéma et fiche collection ne révèlent pas les champs masqués à qui n'a pas data.view_sensitive. | `core/app/collections/routes.py:154-172`, `core/app/collections/routes.py:519-537` | S | — | `bug(`→`test(` : j07-015 — `j07/metadata-masking-api.spec.ts` |
| P15.05 | j07-016 (S3) | Le propriétaire (ou éditeur) d'une collection peut lire ses champs sensibles, ou l'exclusion est documentée dans l'éditeur. | `core/app/features/routes.py:119-127`, `core/app/roles/privileges.py:25` | M | — | `bug(`→`test(` : j07-016 — `j07/metadata-masking-api.spec.ts` |

#### P16 — Coffre de secrets, connecteurs et egress

- Portée : Secrets résolus sans ACL (connecteurs, SMTP d'alerte), DSN sans garde d'egress, plafonds de connecteurs.
- Revue : cœur — sécurité ; niveau 2 ; dépend de : P02.
- Critères de clôture du paquet, en plus des tâches : timeouts `connect_timeout`/`statement_timeout`/RESTClient prouvés par un serveur lent.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P16.01 | **c01-003** (S2), j06-005 (S3) | ACL du coffre : un Créateur ne liste ni n'utilise le secret d'autrui | `core/app/pipelines/connector_runtime.py:90-111`, `core/app/pipelines/connector_runtime.py:283-300`, `core/app/secrets/repository.py:77-84`, `core/app/secrets/routes.py:1-4` (+2) | M | — | `bug(`→`test(` : j06-005 — `j06/secrets-api.spec.ts` |
| P16.02 | **j06b-010** (S2) | Hôte du DSN soumis à la garde d'egress (réseau interne refusé). | `core/app/pipelines/connector_runtime.py:309-345` | M | P02.04 | `bug(`→`test(` : j06b-010, j06-004 — `j06/secrets-api.spec.ts`, `j06b/preview-authz-api.spec.ts` |
| P16.03 | **j06-014** (S2) | Chaque lecture externe a timeout, plafond de lignes/octets et nombre de pages max, DuckDB est borné en mémoire/disque, l'aperçu est borné en durée. | `core/app/pipelines/connector_runtime.py:283-306`, `core/app/pipelines/connector_runtime.py:334-346`, `core/app/pipelines/runtime.py:525-541`, `core/app/pipelines/routes.py:135-158` | M | P02.06 | critère de la cible (lecture de code) |
| P16.04 | j06-003 (S3) | Toute adresse non globale (ip.is_global faux) est bloquée pour reader.connector.rest et le moissonnage. | `core/app/pipelines/egress.py:35-43`, `core/app/harvest/egress.py:50-58` | XS | — | `bug(`→`test(` : j06-003 — `j06/graph-and-egress.spec.ts` |
| P16.05 | j06-006 (S3) | Mise à jour de la valeur en place et refus (ou avertissement) de suppression d'un secret encore référencé, avec liste des usages. | `core/app/secrets/routes.py:106-131` | M | — | `bug(`→`test(` : j06-006 — `j06/secrets-api.spec.ts` |
| P16.06 | j06-007 (S4) | Les erreurs de validation du coffre ne réfléchissent jamais les valeurs de payload. | `core/app/secrets/routes.py:42-49` | XS | — | `bug(`→`test(` : j06-007 — `j06/secrets-api.spec.ts` |
| P16.07 | j06-008 (S4) | Les champs obligatoires des payloads ont min_length=1 (422 sinon). | `core/app/secrets/schemas.py:23-25`, `core/app/secrets/schemas.py:13-20` | XS | — | `bug(`→`test(` : j06-008 — `j06/secrets-api.spec.ts` |
| P16.08 | **j09b-006** (S2) | L'usage d'un secret par une alerte exige le droit d'usage sur ce secret (propriétaire ou privilège). | `core/app/alerts/notify.py:55-70`, `core/app/secrets/repository.py:1-5` | S | P02.04, P16.01 | `bug(`→`test(` : j09b-006, j09b-005 — `j09b/alerts-delivery.spec.ts` |

#### P17 — Passerelle d'administration et observabilité (RC-14)

- Portée : RC-14. Grafana anonyme Admin derrière le cookie, CSP inadaptée, Titiler 500, URL de lancement et lien MinIO.
- Revue : déploiement + sécurité ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : règle de déployabilité : aucun service derrière `admin-auth@docker` n'expose un rôle anonyme Admin.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P17.01 | **j09b-007** (S2) | Le porteur de la passerelle ne peut pas créer de source de données vers le réseau interne (403 ou lecture seule). | `docker-compose.yml:649-672`, `core/app/admin_tools/tokens.py:1-10` | S | — | `bug(`→`test(` : j09b-007 — `j09b/gateway-grafana.spec.ts` |
| P17.02 | j08b-005 (S3) | La racine de l'outil Titiler ouverte par le bouton « Titiler » de la page Infrastructure s'affiche (landing ou documentation). | `docker-compose.yml:188-216` | S | — | `bug(`→`test(` : j08b-005 — `j08b/admin-tools-api.spec.ts` |
| P17.03 | j08b-006 (S3) | Le lancement redirige vers l'origine de la passerelle (PUBLIC_BASE_URL) ou un chemin absolu qui atteint Traefik, en dev comme en production. | `core/app/admin_tools/routes.py:44-70`, `docker-compose.yml:160-161` | S | — | `bug(`→`test(` : j08b-006 — `j08b/admin-tools-api.spec.ts` |
| P17.04 | j08b-009 (S3) | La console MinIO est ouverte via la passerelle /admin-tools ou le lien est masqué quand le port n'est pas publié. | `shell/src/pages/AdminInfrastructurePage.tsx:15-17`, `docker-compose.prod.yml:29-33` | XS | — | `bug(`→`test(` : j08b-009 — `j08b/admin-tools-ui.spec.ts` |
| P17.05 | j09b-008 (S3) | Grafana se charge sans violation : CSP dédiée ou non appliquée sur le routeur grafana. | `core/app/security/traefik_render.py:21-50` | S | — | `bug(`→`test(` : j09b-008 — `j09b/gateway-grafana.spec.ts` |
| P17.06 | t01b-011 (S4) | Nom ou description indiquant « (s'ouvre dans un nouvel onglet) ». | `shell/src/pages/AdminInfrastructurePage.tsx:70-75`, `shell/src/pages/AdminInfrastructurePage.tsx:58` | XS | — | `bug(`→`test(` : t01b-011 — `t01b/admin-flags.spec.ts` |
| P17.07 | j09-009 (S3) | Une vue d'état d'instance (santé Postgres/S3/worker/CDC, files et jobs bloqués) accessible à l'administrateur. | `shell/src/pages/AdminInfrastructurePage.tsx:26-110`, `core/app/instance/routes.py:18-31` | L | — | `bug(`→`test(` : j09-009 — `j09/ops-ui.spec.ts` |
| P17.08 | j09-016 (S3) | Un test E2E avec CORE_ADMIN_TOOLS_ENABLED=true derrière Traefik vérifie lancement, cookie, accès à Martin et révocation du privilège. | `core/app/admin_tools/routes.py:37-102`, `core/app/instance/routes.py:18-31` | M | — | repro inversé : `curl -s localhost:8200/v1/instance ; grep -rln 'admin-tools' shell/e2e core/tests` |

#### P18 — Pipelines : exécution, planification, écriture

- Portée : Topologie non validée, topologie non validée, écriture ligne à ligne, planification, erreurs brutes.
- Revue : cœur — pipelines ; niveau 2 ; dépend de : P01.
- Critères de clôture du paquet, en plus des tâches : un run planifié écrit `pipeline.run` dans `audit_log` ; 50 000 lignes par `writer.collection` en lots (compteur de requêtes, piège n°7) ; **j06b rejoué sans défèrement manuel**.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P18.01 | **c03-003** (S2) | Toute écriture de données, y compris par un run planifié, laisse une trace audit_log (tenant_id, acteur = propriétaire résolu, actor_kind='schedule',… | `core/app/pipelines/jobs.py:271-290`, `core/app/pipelines/runtime.py:862-898` | S | — | critère de la cible (lecture de code) |
| P18.02 | **j06-002** (S2) | Ces graphes sont rejetés en 422 à l'enregistrement avec un message actionnable (nœud X sans entrée), côté cœur (API/MCP/copilote) et côté éditeur. | `core/app/configs/pipeline_validation.py:29-48`, `core/app/configs/schemas.py:272-287`, `core/app/pipelines/runtime.py:686-687`, `core/app/pipelines/runtime.py:1137-1138` (+1) | S | — | `bug(`→`test(` : j06-002 — `j06/graph-and-egress.spec.ts` |
| P18.03 | **t03b-001** (S2) | Une écriture en masse (COPY ou insertions groupées, validation par lot) tient 500 000 lignes en moins d'une minute. | `core/app/pipelines/runtime.py:826-899` | M | P01.01 | `bug(`→`test(` : t03b-001 — `t03b/pipeline-volume.spec.ts` |
| P18.04 | t03b-008 (S3) | Écriture en flux (COPY DuckDB vers S3/fichier temporaire, fetchmany) à mémoire bornée, ou plafond explicite avec message. | `core/app/pipelines/runtime.py:1019-1058`, `core/app/pipelines/runtime.py:826-848` | M | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t03b/pipeline-volume.spec.ts -g "writer.export GeoJSON"` |
| P18.05 | t03b-009 (S3) | Annulation d'un run (POST /pipelines/{id}/runs/{rid}/cancel) et progression par lot visibles dans le panneau d'exécution. | `core/app/pipelines/routes.py:93-134` | M | P18.03 | critère de la cible (lecture de code) |
| P18.06 | j06b-007 (S3) | Message métier indiquant le nœud et la cause, sans SQL interne. | `core/app/pipelines/jobs.py:245-255`, `core/app/pipelines/jobs.py:262-268` | S | — | `bug(`→`test(` : j06b-007 — `j06b/run-api.spec.ts` |
| P18.07 | j06b-011 (S3) | Limite par IP/pipeline pour la route trigger, indépendante du jeton présenté. | `core/app/ratelimit/limiter.py:63-70`, `core/app/ratelimit/limiter.py:47-57` | S | — | `bug(`→`test(` : j06b-011 — `j06b/webhook-cron-api.spec.ts` |
| P18.08 | j06b-012 (S3) | 422 pour tout cron qui n'a pas exactement 5 champs. | `core/app/configs/schemas.py:255-263` | XS | — | `bug(`→`test(` : j06b-012 — `j06b/webhook-cron-api.spec.ts` |
| P18.09 | j06b-015 (S3) | La valeur affichée est la valeur enregistrée (défaut posé à l'ajout ou option vide visible). | `shell/src/builder/pipeline/PipelineNodeInspector.tsx:175-190` | XS | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06b/ui-builder.spec.ts -g "j06b-015"` |
| P18.10 | j06b-016 (S3) | URL réelle du cœur avec /v1/pipelines/{id}/trigger. | `shell/src/i18n/catalog.fr.ts:1211-1212`, `shell/src/builder/pipeline/PipelineWebhookTrigger.tsx:62-65` | XS | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06b/ui-builder.spec.ts -g "j06b-016"` |
| P18.11 | j06-011 (S4) | La palette respecte l'état locked de la barre de domaines. | `shell/src/ui/kit/CommandPalette.tsx:55-62` | XS | — | `bug(`→`test(` : j06-011 — `j06/etl-disabled-ui.spec.ts` |
| P18.12 | j06-012 (S3) | Même garde en tête de page que PipelineBuilderPage (état d'indisponibilité, pas de formulaire). | `shell/src/pages/VisualQueryWizardPage.tsx:530-558` | S | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06/etl-disabled-ui › "requête visuelle : formulaire affiché…` |

#### P19 — Moissonnage, STAC et DCAT

- Portée : Source en erreur martelée, retours UI, collections cassées, validation des sources et des paramètres STAC.
- Revue : cœur — fédération ; niveau 2 ; dépend de : P01, P02.
- Critères de clôture du paquet, en plus des tâches : test cœur : une source en erreur n'est plus « due » avant son intervalle.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P19.01 | **j07-003** (S2) | Un message confirme la mise en file ou signale l'échec (role=status/alert), comme pour la suppression. | `shell/src/pages/HarvestSourcesAdminPage.tsx:165-171` | XS | P01.01, P02.01 | `bug(`→`test(` : j07-003 — `j07/harvest-ui.spec.ts` |
| P19.02 | **j07-006** (S2) | Le passage en erreur date la tentative (last_attempt_at) afin de respecter l'intervalle, avec éventuellement un backoff. | `core/app/harvest/service.py:66-73`, `core/app/harvest/repository.py:206-239` | S | P02.01 | `bug(`→`test(` : j07-006 — `j07/harvest-api.spec.ts` |
| P19.03 | **j07-008** (S2) | La collection cassée est ignorée (journalisée) et la recherche répond 200 avec les autres collections, comme /stac/collections et /dcat/catalog. | `core/app/stac/routes.py:344-399`, `core/app/stac/routes.py:381` | S | P02.01 | `bug(`→`test(` : j07-008 — `j07/stac-dcat-api.spec.ts` |
| P19.04 | **j07-017** (S2) | La raison de l'échec et la date de dernier passage sont visibles (colonne, infobulle ou panneau de détail). | `shell/src/pages/HarvestSourcesAdminPage.tsx:155-158` | XS | P02.01 | `bug(`→`test(` : j07-017 — `j07/harvest-ui.spec.ts` |
| P19.05 | j07-004 (S3) | Une URL non http(s) est refusée à la création (422) ; | `core/app/harvest/schemas.py:7-12` | S | — | `bug(`→`test(` : j07-004 — `j07/harvest-api.spec.ts` |
| P19.06 | j07-005 (S3) | Une source de même (tenant, type, URL) est refusée (409). | `core/app/harvest/routes.py:123-151`, `core/app/harvest/models.py:1-60` | S | — | `bug(`→`test(` : j07-005 — `j07/harvest-api.spec.ts` |
| P19.07 | j07-007 (S3) | La suppression retire (ou propose de retirer) les items créés par la source, ou les marque explicitement orphelins. | `core/app/harvest/repository.py:71-73`, `core/app/harvest/routes.py:280-300` | M | — | `bug(`→`test(` : j07-007 — `j07/harvest-api.spec.ts` |
| P19.08 | j07-009 (S3) | Erreur explicite et stable (404/409/503 avec detail) ou dégradation gracieuse cohérente entre surfaces. | `core/app/stac/routes.py:165-200`, `core/app/stac/routes.py:215-264`, `core/app/features/routes.py:200-244` | S | — | `bug(`→`test(` : j07-009 — `j07/stac-dcat-api.spec.ts` |
| P19.09 | j07-010 (S3) | Un datetime invalide répond 400 avec un detail RFC 3339 attendu. | `core/app/stac/routes.py:326-341`, `core/app/stac/routes.py:330-341` | XS | — | `bug(`→`test(` : j07-010 — `j07/stac-dcat-api.spec.ts` |
| P19.10 | j07-011 (S3) | Le filtrage et la propriété datetime des items sont cohérents avec temporalStart/temporalEnd de la collection (ou avec un champ date de la donnée). | `core/app/stac/routes.py:246-249`, `core/app/stac/routes.py:330-341` | M | — | `bug(`→`test(` : j07-011 — `j07/stac-dcat-api.spec.ts` |
| P19.11 | j07-012 (S3) | license vaut proprietary/various et un lien {rel:'license', href: licenseUri} est présent quand l'URI est renseignée. | `core/app/stac/serializers.py:70-77` | S | — | `bug(`→`test(` : j07-012 — `j07/stac-dcat-api.spec.ts` |
| P19.12 | j07-013 (S4) | Un jeton invalide répond 400. | `core/app/stac/routes.py:316-323`, `core/app/stac/routes.py:367-368` | XS | — | `bug(`→`test(` : j07-013 — `j07/stac-dcat-api.spec.ts` |
| P19.13 | j07-014 (S3) | Bornes temporelles ordonnées ; | `core/app/collections/schemas.py:66-115` | S | — | `bug(`→`test(` : j07-014 — `j07/metadata-masking-api.spec.ts` |
| P19.14 | j07-018 (S3) | Un intervalle vide envoie intervalMinutes:null et retire la planification. | `shell/src/shell/EditHarvestSourcePanel.tsx:21-33` | XS | — | `bug(`→`test(` : j07-018 — `j07/harvest-ui.spec.ts` |
| P19.15 | j07-019 (S4) | licenseUri est vidée quand la licence n'est plus « other ». | `shell/src/shell/EditCollectionPanel.tsx:44`, `shell/src/shell/EditCollectionPanel.tsx:84` | XS | — | `bug(`→`test(` : j07-019 — `j07/collections-ui.spec.ts` |
| P19.16 | j07-020 (S3) | Chaque source expose le nombre d'enregistrements moissonnés, leurs états (ok/stale) et un lien vers les items créés. | `core/app/harvest/routes.py:92-103` | M | — | repro inversé : `curl -s -H "authorization: Bearer $T" localhost:8200/v1/harvest/sources/{id}/records # 404, route absente ; GET /v1/harvest/sources/{id} ne…` |

#### P20 — Alertes et notifications

- Portée : Échecs de livraison invisibles et non rejoués, premier état compté comme transition, MCP hors mode lecture seule, cloche de notifications.
- Revue : cœur — alertes + shell ; niveau 2 ; dépend de : P01, P02.
- Critères de clôture du paquet, en plus des tâches : migration du statut de livraison testée sur base non vide.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P20.01 | **j09-003** (S2) | L'auteur de la règle voit, dans l'historique d'évaluation, que la notification n'a pas été livrée et pourquoi. | `core/app/alerts/jobs.py:230-275`, `core/app/alerts/routes.py:26-32`, `shell/src/builder/AlertRuleEditor.tsx:27-50` | M | P01.01 | `bug(`→`test(` : j09-003 — `j09/alerts-api.spec.ts` |
| P20.02 | **j09-013** (S2) | count sur zéro ligne vaut 0 ; | `core/app/alerts/jobs.py:188-192` | S | P01.01 | `bug(`→`test(` : j09-013 — `j09/alerts-api.spec.ts` |
| P20.03 | **j09b-004** (S2) | Une notification échouée est retentée (ou signalée comme non livrée et rejouable) à l'évaluation suivante. | `core/app/alerts/jobs.py:230-283`, `core/app/alerts/repository.py:138-167` | M | P01.01, P02.04 | `bug(`→`test(` : j09b-004 — `j09b/alerts-delivery.spec.ts` |
| P20.04 | j09b-003 (S3) | Un en-tête de signature vérifiable (HMAC d'un secret par canal) accompagne chaque livraison. | `core/app/alerts/notify.py:37-52` | S | — | `bug(`→`test(` : j09b-003 — `j09b/alerts-delivery.spec.ts` |
| P20.05 | j09-004 (S3) | Seule une transition vers firing (ou firing -> ok) notifie ; | `core/app/alerts/jobs.py:332`, `core/app/alerts/jobs.py:428` | S | — | `bug(`→`test(` : j09-004 — `j09/alerts-api.spec.ts` |
| P20.06 | j09-008 (S3) | Le journal « Mes tâches » inclut les évaluations/notifications des règles dont l'utilisateur est propriétaire. | `core/app/alerts/jobs.py:341-347`, `core/app/alerts/jobs.py:266-275`, `core/app/usage/service.py:54-55`, `core/app/usage/routes.py:39-44` | S | — | `bug(`→`test(` : j09-008 — `j09/ops-api.spec.ts` |
| P20.07 | j09-011 (S3) | Une erreur de déclenchement est annoncée (role=alert) et un succès rafraîchit l'état. | `shell/src/builder/AlertRuleEditor.tsx:28-46` | XS | P01.01 | `bug(`→`test(` : j09-011 — `j09/alerts-ui.spec.ts` |
| P20.08 | j09-012 (S4) | Libellés français (« Déclenchée », « Normale », « En attente », « Erreur ») avec valeur, date et message d'erreur de la dernière évaluation. | `shell/src/builder/AlertRuleEditor.tsx:36-38`, `shell/src/lib/jobStatusLabel.ts:19-32` | S | — | `bug(`→`test(` : j09-012 — `j09/alerts-ui.spec.ts` |
| P20.09 | c01-008 (S3), c02-008 (S3) | `run_alert_rule` MCP soumis au mode lecture seule et à `@write_tool` | `core/app/mcp/tools/alerts.py:41-117`, `core/app/mcp/tools/alerts.py:99-117`, `core/app/mcp/tools/alerts.py:41-42` | XS | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_mcp_poc.py::test_run_al…` |
| P20.10 | j09-006 (S3) | Le sélecteur porte un nom propre (ex. | `shell/src/shell/chrome/NotificationBell.tsx:96`, `shell/src/shell/chrome/NotificationBell.tsx:108-111` | XS | — | `bug(`→`test(` : j09-006 — `j09/notifications.spec.ts` |
| P20.11 | j09-007 (S3) | Toutes les notifications sont atteignables (pagination/scroll infini) ou un lien mène à une page d'historique. | `shell/src/shell/chrome/NotificationBell.tsx:86` | S | — | `bug(`→`test(` : j09-007 — `j09/notifications.spec.ts` |
| P20.12 | j09-015 (S3) | Les jobs longs ou critiques (moissonnage, 3D, alerte firing/échec de canal) notifient leur propriétaire in-app. | `shell/src/shell/chrome/NotificationBell.tsx:17-23`, `core/app/harvest/jobs.py:25-40`, `core/app/alerts/jobs.py:230-275` | M | — | repro inversé : `cd core && grep -rn 'notify_best_effort(' app --include=*.py \| grep -v 'def '` |
| P20.13 | j02-013 (S4) | Le déclencheur s'appelle « Notifications », le sélecteur « Préférence de notification » ; | `shell/src/shell/chrome/NotificationBell.tsx:94-112` | XS | — | `bug(`→`test(` : j02-013 — `j02/reader-notifications.spec.ts` |
| P20.14 | j02-014 (S4) | Les non lues sont mises en évidence (gras/pastille, aria) et la liste permet d'aller au-delà de 20. | `shell/src/shell/chrome/NotificationBell.tsx:32-83`, `shell/src/shell/chrome/NotificationBell.tsx:84-90` | XS | — | `bug(`→`test(` : j02-014 — `j02/reader-notifications.spec.ts` |
| P20.15 | c03-010 (S4) | Règle 'audit_log sur toute écriture' appliquée, au minimum sur la préférence (choix utilisateur persistant). | `core/app/notifications/routes.py:79-125` | XS | — | critère de la cible (lecture de code) |

#### P21 — Contrats d'API du cœur : validation stricte et RFC 7807

- Portée : Schémas de config permissifs, erreurs hors `application/problem+json`, bornes de pagination absentes (OFFSET/LIMIT négatifs → 500).
- Revue : cœur — API ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : `c08/probes/probe_7807.py` : 404/422 en `application/problem+json` ; OpenAPI + types régénérés ; suite E2E complète verte.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P21.01 | **c08-002** (S2) | Un document declaratif schematise (regle d'architecture 2) rejette ce qu'il ne comprend pas, surtout pour l'ecriture par agent MCP/IA : cle inconnue,… | `core/app/configs/schemas.py:431-433`, `core/app/configs/schemas.py:14-25`, `core/app/configs/schemas.py:28-37`, `core/app/configs/schemas.py:96-117` | M | — | repro inversé : `cd core && CORE_ENV=development CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= PYTHONPATH=. uv run pytest -c pyprojec…` |
| P21.02 | **c08-004** (S2) | Toute erreur HTTP du coeur est application/problem+json (SP-26) et le shell affiche le detail de validation (champ, message) issu du coeur. | `core/app/main.py:144-169`, `shell/src/api/base.ts:58-75` | S | — | repro inversé : `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= uv run python ../docs/revue/audit-2026-09-29/c…` |
| P21.03 | **j03-011** (S2) | Rejet 422 des valeurs hors bornes. | `core/app/configs/schemas.py:71-131` | M | — | `bug(`→`test(` : j03-011 — `j03/map-api.spec.ts` |
| P21.04 | j04-013 (S3) | Une validation serveur partagée refuse ou signale ces configs. | `core/app/configs/schemas.py:28-44`, `core/app/configs/routes.py:137-166` | M | — | `bug(`→`test(` : j04-013 — `j04/core-validation.spec.ts` |
| P21.05 | j01-005 (S4) | Un handler RequestValidationError uniforme renvoyant un problème RFC 7807. | `core/app/main.py:144-169` | S | — | `bug(`→`test(` : j01-005 — `j01/anonymous.spec.ts` |
| P21.06 | j08-003 (S3) | Paramètres validés (Query(ge=1, le=200)) avec réponse 422. | `core/app/auth/routes.py:117-131`, `core/app/users/repository.py:107-119`, `core/app/usage/routes.py:28-45`, `core/app/usage/service.py:42-66` | XS | — | `bug(`→`test(` : j08-003 — `j08/users-roles-api.spec.ts` |
| P21.07 | j08-004 (S3) | 422 sur date illisible ou limit hors bornes, 400 si since > until. | `core/app/usage/routes.py:69-80`, `core/app/usage/service.py:88-105` | XS | — | `bug(`→`test(` : j08-004 — `j08/compliance-usage-api.spec.ts` |
| P21.08 | j08-010 (S4) | pageSize renvoyé = pageSize appliqué ; | `core/app/usage/routes.py:28-62` | XS | P21.06 | repro inversé : `curl ci-dessus (jeton audit-admin) ; comparer pageSize renvoyé à la limite de 200 de list_usage_tasks.` |
| P21.09 | j09-005 (S3) | Paramètres validés (Query(ge=1), plafond) : 422 pour une pagination invalide. | `core/app/notifications/routes.py:45-49`, `core/app/notifications/repository.py:61-66`, `core/app/usage/routes.py:29-33`, `core/app/usage/service.py:58-61` | XS | — | `bug(`→`test(` : j09-005 — `j09/notifications.spec.ts` |

#### P22 — Client shell : `base.request`, erreurs et connectivité

- Portée : `fetch` nus hors `base.request`, types écrits à la main, bannière de connectivité, états d'erreur des pages.
- Revue : shell — API/client ; niveau 2 ; dépend de : P21, P34.
- Critères de clôture du paquet, en plus des tâches : suite E2E complète verte ; aucun `fetch(` hors `shell/src/api/base.ts` (lint).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P22.01 | c04-001 (S3) | Tout appel cœur du sas ItemClient passe par fetchWithTimeout/request, comme le garantit le commentaire SP-B7 de base.ts. | `shell/src/api/domains/layers.ts:145-148`, `shell/src/api/domains/features.ts:14-30`, `shell/src/api/domains/extensionsAdminTools.ts:33-36`, `shell/src/api/domains/extensionsAdminTools.ts:65-68` (+3) | S | — | repro inversé : `grep -n 'fetch(' shell/src/api/domains/*.ts` |
| P22.02 | c04-003 (S3) | Un champ présent dans le MapLayer du cœur (core/app/configs/schemas.py:96) survit au round-trip, ou est explicitement rejeté à l'écriture. | `shell/src/api/base.ts:102-152`, `shell/src/api/types.ts:257-300` | S | — | repro inversé : `sed -n 96,118p core/app/configs/schemas.py; sed -n 102,152p shell/src/api/base.ts` |
| P22.03 | c04-005 (S4) | Un helper unique (ex. | `shell/src/App.tsx:21-26`, `shell/src/pages/EmbedPage.tsx:26-31` | XS | — | repro inversé : `grep -n __GEOSTUDIO_ENV__ shell/src/App.tsx shell/src/pages/EmbedPage.tsx` |
| P22.04 | c08-005 (S3) | Toute erreur HTTP du coeur passe par parseErrorResponse (ApiError) pour que l'UI affiche detail et delai de reessai (SP-B5). | `shell/src/api/base.ts:346`, `shell/src/api/base.ts:367`, `shell/src/api/base.ts:417`, `shell/src/api/base.ts:435` (+5) | S | P21.02 | repro inversé : `grep -rn "new Error('Request failed" shell/src/api --include=*.ts \| grep -v test` |
| P22.05 | c08-009 (S3) | Regle decidee 'types generes depuis l'OpenAPI du coeur' : une seule source de verite pour AppConfig/MapConfig, ou au minimum un test de parite de com… | `shell/src/api/types.ts:1014-1025`, `shell/src/api/types.ts:312-318`, `shell/src/api/meSchemaParity.types.ts:1-39` | M | P21.01 | repro inversé : `cd shell && npx tsc -p ../docs/revue/audit-2026-09-29/c08/probes/tsconfig.json` |
| P22.06 | t02-006 (S3) | Tant que la bannière est affichée, un sondage périodique (refetchInterval ou ping) relance les requêtes en erreur et la lève dès le retour du cœur. | `shell/src/shell/ConnectivityBanner.tsx:12-35`, `shell/src/App.tsx:36`, `shell/src/i18n/catalog.fr.ts:1850` | S | — | `bug(`→`test(` : t02-006 — `t02/connectivity.spec.ts` |
| P22.07 | t02-007 (S3) | Un état hors ligne est signalé (bannière « vous êtes hors ligne ») et distingué d'une liste réellement vide. | `shell/src/shell/ConnectivityBanner.tsx:6-11`, `shell/src/App.tsx:36` | S | P22.06 | `bug(`→`test(` : t02-007 — `t02/connectivity.spec.ts` |
| P22.08 | t02-012 (S4) | La bannière ne se lève que lorsque les requêtes qui avaient échoué par injoignabilité réussissent à nouveau. | `shell/src/shell/ConnectivityBanner.tsx:18-31` | XS | P22.06 | `bug(`→`test(` : t02-012 — `t02/connectivity.spec.ts` |
| P22.09 | t04-010 (S3) | Distinguer 404/403 (« introuvable / accès refusé ») d'une erreur de chargement (« Erreur de chargement » + Réessayer). | `shell/src/pages/ItemDetailPage.tsx:49-53`, `shell/src/pages/DatasetEditPage.tsx:64-68`, `shell/src/pages/AppBuilderPage.tsx:213-225`, `shell/src/pages/MapEditorPage.tsx:106-111` | S | P22.10 | `bug(`→`test(` : t04-010 — `t04/states.spec.ts` |
| P22.10 | t04-011 (S3) | Un composant d'erreur unique (message, style Banner danger, bouton Réessayer). | `shell/src/pages/CatalogPage.tsx:262-270`, `shell/src/pages/RolesAdminPage.tsx:84-90`, `shell/src/pages/DatasetPage.tsx:76-82` | S | P34.19 | `bug(`→`test(` : t04-011 — `t04/states.spec.ts` |
| P22.11 | t04-012 (S3) | Un message d'erreur avec Réessayer dans chaque section qui échoue. | `shell/src/pages/SettingsPage.tsx:54-79`, `shell/src/pages/SettingsPage.tsx:13-36` | XS | P22.10 | `bug(`→`test(` : t04-012 — `t04/states.spec.ts` |

#### P23 — MCP et copilote

- Portée : Outils MCP bloquant la boucle asyncio, parité REST/MCP, erreurs du fournisseur LLM, budget et historique du copilote.
- Revue : cœur — MCP/copilote ; niveau 2 ; dépend de : P07.
- Critères de clôture du paquet, en plus des tâches : `c02/repro/mcp_blocks_event_loop.py` : `/health` répond pendant un outil lent (recouvrement d'intervalles, piège n°7) ; la vérification réelle attend une passe LLM fake (§5.3).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P23.01 | **c02-009** (S2) | Les tools qui font des I/O bloquantes s'exécutent hors de la boucle (anyio.to_thread.run_sync ou fonctions def synchrones que FastMCP exécute en thre… | `core/app/mcp/tools/catalog.py:55-79`, `core/app/mcp/tools/analytics.py:82-166`, `core/app/mcp/tools/configs.py:152-200` | M | — | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/mcp_blocks_event_loop.py $SCRATCH` |
| P23.02 | c02-010 (S3) | Aucun appel réseau/DB synchrone dans une coroutine servie par la boucle principale. | `core/app/mcp/auth.py:24-36`, `core/app/copilot/routes.py:240-253`, `core/app/mapicons/routes.py:101-163` | S | P23.01 | critère de la cible (lecture de code) |
| P23.03 | c08-003 (S3) | Memes validations que le REST equivalent : erreur d'outil explicite sur page/pageSize/limit/offset hors bornes. | `core/app/mcp/tools/catalog.py:56-79`, `core/app/mcp/tools/catalog.py:110-133`, `core/app/mcp/tools/catalog.py:135-198` | XS | — | repro inversé : `cd core && CORE_ENV=development CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= PYTHONPATH=. uv run pytest -c pyprojec…` |
| P23.04 | c08-006 (S3) | L'erreur d'outil MCP porte le statut et le detail structure (par exemple structuredContent ou prefixe code) equivalents au problem+json du REST. | `core/app/mcp/tools/identity.py:95-101`, `core/app/mcp/tools/analytics.py:95-140` | S | — | repro inversé : `sed -n 95,101p core/app/mcp/tools/identity.py ; grep -n 'UnknownAggregateField' core/app/mcp/tools/analytics.py core/app/features/routes.py` |
| P23.05 | c08-007 (S3) | Une decision de parite explicite : chaque capacite ItemClient a soit un outil MCP soit une exclusion documentee (par exemple secrets) et verifiee par… | `core/app/mcp/tools/__init__.py:36-58`, `core/app/mcp/tools/identity.py:27-37` | L | — | repro inversé : `cd core && grep -rhn -A2 '@server.tool' app/mcp/tools \| grep 'def ' ; python3 -c "import json;print(sorted(json.load(open('openapi.json'))[…` |
| P23.06 | c08-008 (S4) | Les outils de catalogue relaient les memes filtres que la route REST, ou un seul outil est expose. | `core/app/mcp/tools/catalog.py:56-108`, `core/app/items/routes.py:62-94` | S | P23.05 | repro inversé : `sed -n 56,108p core/app/mcp/tools/catalog.py` |
| P23.07 | c01-009 (S3) | Chaque appel d'outil MCP (au minimum ceux qui lisent des données métier) devrait laisser une trace audit_log (acteur, outil, cible). | `core/app/mcp/tools/catalog.py:135-199`, `core/app/mcp/tools/analytics.py:82-167` | M | — | repro inversé : `cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . ../docs/revue/audit-2026-09-29/c01/poc/test_c01_mcp_poc.py::test_mcp_re…` |
| P23.08 | j11-002 (S3) | Erreur d'outil explicite de validation (comme le 422 REST), sans SQL ni nom de table interne. | `core/app/mcp/tools/catalog.py:136-198`, `core/app/mcp/tools/catalog.py:56-79` | XS | — | `bug(`→`test(` : j11-002 — `j11/mcp-api.spec.ts` |
| P23.09 | j11-001 (S3) | Un message d'indisponibilité lisible (« fournisseur LLM non configuré »), ou des outils non exposés quand la capacité est éteinte ; | `core/app/copilot/llm_provider.py:112-122`, `core/app/auth/dependency.py:96-110` | XS | — | `bug(`→`test(` : j11-001 — `j11/mcp-api.spec.ts` |
| P23.10 | j11-004 (S3) | Environ 6 tours par minute ne devraient pas épuiser le budget ; | `core/app/ratelimit/limiter.py:16`, `core/app/ratelimit/limiter.py:49-57`, `core/app/copilot/mcp_loopback.py:88-124` | S | — | `bug(`→`test(` : j11-004 — `j11/mcp-api.spec.ts` |
| P23.11 | **j11-005** (S2) | 502/504 avec un detail exploitable pour toute panne du fournisseur LLM (comme pour la garde d'egress). | `core/app/copilot/routes.py:157-190` | S | — | `bug(`→`test(` : j11-005 — `j11/copilot-server.spec.ts` |
| P23.12 | j11-006 (S3) | Un message d'indisponibilité (avec la marche à suivre pour un administrateur) là où le copilote apparaîtrait. | `shell/src/pages/AppBuilderPage.tsx:571-584`, `shell/src/pages/SqlLabPage.tsx:285-297`, `shell/src/pages/VisualQueryWizardPage.tsx:503-515` | S | — | `bug(`→`test(` : j11-006 — `j11/copilot-ui.spec.ts` |
| P23.13 | j11-010 (S4) | Le copilote d'édition est masqué ou désactivé quand l'utilisateur n'a pas la permission d'écriture. | `shell/src/pages/AppBuilderPage.tsx:571-583`, `shell/src/builder/copilot/CopilotPanel.tsx:34-71` | XS | — | `bug(`→`test(` : j11-010 — `j11/copilot-ui.spec.ts` |
| P23.14 | j11-011 (S3) | Distinguer copilote et agent externe dans audit_log (actor_kind ou payload.origin) et tracer chaque tour (hash du message, outils appelés). | `core/app/copilot/routes.py:241-269`, `core/app/mcp/tools/configs.py:232-262` | M | — | repro inversé : `sed -n 241,269p core/app/copilot/routes.py ; grep -n write_audit core/app/copilot/*.py` |
| P23.15 | j11-012 (S3) | Un contenu de catalogue malveillant ne peut pas déclencher une écriture : résultats d'outils bornés/fencés, confirmation humaine avant tout outil d'é… | `core/app/copilot/routes.py:211-232` | M | — | repro inversé : `sed -n 205,235p core/app/copilot/routes.py` |
| P23.16 | j11-013 (S3) | Contexte compacté (page active, résumé des widgets) ou plafond relevé, et message explicite sur cette limite. | `core/app/copilot/routes.py:34`, `shell/src/builder/copilot/CopilotChat.tsx:56-71` | M | P07.01 | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j11/copilot-server.spec.ts -g 'motifs de refus' (preuve serve…` |

#### P24 — Index et balayages SQL

- Portée : Index manquants (`audit_log`, `configs`, `config_revisions`, `report_runs`), lectures publiques non paginées en SQL, balayages N+1.
- Revue : cœur — perf/migrations ; niveau 2 ; dépend de : P09.
- Critères de clôture du paquet, en plus des tâches : `c03/probes/index_plans.py` sans `SCAN` ; comparateur modèle/Alembic vert ; compteur de requêtes (pas de temps mur, piège n°7).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P24.01 | **c03-004** (S2), c09-005 (S3) | Index sur `audit_log` | `core/alembic/versions/0004_audit_log.py:18-30`, `core/app/usage/service.py:88-100`, `core/app/usage/service.py:42-60`, `core/app/audit/models.py:15-26` (+2) | S | — | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c03/probes/index_plans.py` |
| P24.02 | **c03-005** (S2) | Index (ou contrainte unique) sur configs.item_id et index (config_id, version) sur config_revisions. | `core/alembic/versions/0001_baseline.py:18-35`, `core/app/configs/repository.py:41-47`, `core/app/configs/repository.py:87-88` | XS | P09.01 | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c03/probes/index_plans.py` |
| P24.03 | **c09-004** (S2) | Index composite (config_id, version DESC) et index sur configs(item_id) et (kind, tenant_id). | `core/app/configs/models.py:15-34`, `core/alembic/versions/0001_baseline.py:1-40` | XS | — | repro inversé : `cd core && grep -rn 'config_revisions\\|configs' alembic/versions/*.py \| grep -i index ; grep -n 'Index' app/configs/models.py` |
| P24.04 | c03-007 (S3) | Index (report_item_id, tenant_id, created_at) comme ix_pipeline_runs_pipeline. | `core/app/reports/models.py:21`, `core/app/reports/repository.py:77-107` | XS | — | repro inversé : `cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c03/probes/index_plans.py` |
| P24.05 | **c09-006** (S2) | Pagination LIMIT/OFFSET en SQL, colonnes strictement nécessaires (defer(embedding)), route anonyme bornée. | `core/app/items/repository.py:531-560`, `core/app/public/routes.py:22-32`, `core/app/public/routes.py:87-95` | S | P24.01 | repro inversé : `cd core && PYTHONPATH=. uv run python -c "from sqlalchemy import select; from sqlalchemy.dialects import postgresql; from app.items.models…` |
| P24.06 | **c09-003** (S2) | Sélectionner en une requête (jointure Config/ConfigRevision courante ou colonne refresh_enabled/next_run_at indexée) uniquement les configs planifiée… | `core/app/configs/repository.py:97-126`, `core/app/configs/repository.py:41-46`, `core/app/pipelines/repository.py:151-168`, `core/app/alerts/repository.py:138-148` (+1) | M | — | repro inversé : `sed -n 97,126p core/app/configs/repository.py` |
| P24.07 | c09-007 (S3) | Agrégation SQL (JSONB keywords, GROUP BY) ou chargement des seules colonnes owner/keywords ; | `core/app/items/repository.py:440-460`, `core/app/items/repository.py:483-528` | S | P24.05 | repro inversé : `sed -n 440,460p core/app/items/repository.py; sed -n 505,528p core/app/items/repository.py` |
| P24.08 | c09-011 (S3) | Cache court (TTL/invalidation sur DDL) du TableInfo par table ; | `core/app/collections/introspection_pg.py:74-140`, `core/app/features/tiles.py:140-160` | S | — | repro inversé : `grep -c 'session.execute' core/app/collections/introspection_pg.py ; grep -n 'cache\\|lru' core/app/collections/introspection_pg.py` |
| P24.09 | c09-012 (S3) | count optionnel/estimé (numberMatched facultatif OGC) et pagination keyset sur la PK. | `core/app/features/repository.py:140-162` | S | — | repro inversé : `sed -n 146,162p core/app/features/repository.py` |

#### P25 — DuckDB, lakehouse et SQL Lab : bornes et exactitude

- Portée : DuckDB sans limite mémoire ni délai, compaction et change-log non réduits, résultats d'agrégat inexacts, SQL Lab.
- Revue : cœur — analytique ; niveau 2 ; dépend de : P05.
- Critères de clôture du paquet, en plus des tâches : `current_setting('memory_limit')` borné sur toute connexion `open_connection` ; un agrégat pathologique est interrompu.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P25.01 | **c09-008** (S2) | Même garde que sql_sandbox (memory_limit, threads, timer interrupt, plafond de lignes de groupes) sur toute connexion DuckDB servant une requête HTTP. | `core/app/features/routes.py:249-262`, `core/app/analytics/duckdb_conn.py:21-38`, `core/app/features/routes.py:268-306` | M | P05.01 | repro inversé : `cd core && PYTHONPATH=. uv run python -c "import duckdb;print(duckdb.connect(':memory:').execute(\"select current_setting('memory_limit'),c…` |
| P25.02 | **c09-009** (S2) | Limites mémoire/threads et budget de temps sur l'aperçu ; | `core/app/pipelines/routes.py:134-158`, `core/app/pipelines/runtime.py:765-830`, `core/app/alerts/jobs.py:158-163`, `core/app/alerts/jobs.py:303-308` | M | P25.01 | repro inversé : `sed -n 765,800p core/app/pipelines/runtime.py` |
| P25.03 | c09-014 (S3) | Fusion par niveaux (ne pas réécrire un fichier proche du seuil), plafond mémoire par fusion, listage limité aux partitions récentes (dt=). | `core/app/cdc/compaction.py:53-56`, `core/app/cdc/compaction.py:66-83`, `core/app/cdc/compaction.py:86-100` | M | — | repro inversé : `cd core && PYTHONPATH=. uv run python -c "from app.cdc.compaction import select_files_to_merge as s;M=1<<20;print([f['key'] for f in s([{'k…` |
| P25.04 | c09-015 (S3) | Snapshot/état courant périodique (base + delta) ou matérialisation mise en cache par LSN. | `core/app/analytics/aggregate.py:401-432`, `core/app/analytics/sql_sandbox.py:90-108` | L | — | repro inversé : `sed -n 401,432p core/app/analytics/aggregate.py` |
| P25.05 | j05-004 (S3) | Les buckets d'un grain temporel sont triés chronologiquement. | `core/app/analytics/aggregate.py:546-563` | XS | — | `bug(`→`test(` : j05-004, j05-007 — `j05/aggregate-api.spec.ts` |
| P25.06 | j05-005 (S3) | Un groupe NULL est rendu null. | `core/app/analytics/aggregate.py:270-297` | XS | — | `bug(`→`test(` : j05-005 — `j05/aggregate-api.spec.ts` |
| P25.07 | j05-006 (S3) | Réponse 400 explicite sur une valeur de filtre invalide. | `core/app/features/routes.py:268-308` | XS | — | `bug(`→`test(` : j05-006 — `j05/aggregate-api.spec.ts` |
| P25.08 | j05-008 (S3) | Le résultat est rendu (null ou texte) ou une erreur 400 propre, jamais un 500. | `core/app/features/routes.py:464-533` | XS | — | `bug(`→`test(` : j05-008 — `j05/sql-api.spec.ts` |
| P25.09 | j05-010 (S3) | Le fichier contient au moins la ligne d'en-tête. | `core/app/features/routes.py:310-372`, `core/app/analytics/export.py:69-80` | XS | — | `bug(`→`test(` : j05-010 — `j05/export-api.spec.ts` |
| P25.10 | j05-020 (S3) | La réponse signale que le lac n'est pas à jour (champ pending/asOf) ou reflète la base. | `core/app/features/routes.py:268-308` | M | — | `bug(`→`test(` : j05-020 — `j05/sql-api.spec.ts` |
| P25.11 | t03b-004 (S3) | La réponse indique l'âge/la complétude des données (en-tête ou champ asOf), ou l'agrégat comble le retard depuis Postgres. | `core/app/cdc/buffer.py:16-35` | S | — | `bug(`→`test(` : t03b-004 — `t03b/analytics-volume.spec.ts` |
| P25.12 | j05-024 (S3), j05b-007 (S3) | Contexte temporel global : comparaison typée des dates | `shell/src/lib/analyticsPatch.ts:21-25`, `shell/src/lib/analyticsPatch.ts:22-25`, `core/app/analytics/aggregate.py:230-268` | S | P05.01 | `bug(`→`test(` : j05b-007 — `j05b/context.spec.ts` |
| P25.13 | j05-023 (S3), j05b-003 (S3) | Opérateur « contient » : insensible à la casse, jokers échappés | `shell/src/builder/visualQuery/compileFilter.ts:22`, `shell/src/builder/visualQuery/compileFilter.ts:33-36` | S | — | `bug(`→`test(` : j05b-003 — `j05b/wizard-ops.spec.ts` |
| P25.14 | j05-013 (S3) | Les collections interrogeables sont listées avec titre et proposées à la saisie. | `shell/src/pages/SqlLabPage.tsx:50-60`, `shell/src/pages/SqlLabPage.tsx:175-190` | M | — | `bug(`→`test(` : j05-013 — `j05/sqllab-ui.spec.ts` |
| P25.15 | j05-015 (S4) | NULL est rendu distinctement (ex. | `shell/src/pages/SqlLabPage.tsx:241` | XS | — | `bug(`→`test(` : j05-015 — `j05/sqllab-ui.spec.ts` |
| P25.16 | j05-027 (S3) | Entrée insère une nouvelle ligne ; | `shell/src/pages/SqlLabPage.tsx:184` | XS | — | `bug(`→`test(` : j05-027 — `j05/sqllab-ui.spec.ts` |

#### P26 — Quotas appliqués à toute création (RC-12)

- Portée : RC-12. Contrôle d'items/collections absent de `register_collection` et des jobs ; stockage contrôlé après téléversement (double comptage) et sous-estimé.
- Revue : cœur — quotas ; niveau 3 ; dépend de : P01, P03.
- Critères de clôture du paquet, en plus des tâches : rejeu j08b **sans le second cœur `:8201`** (retiré de `REJEU.md`, limites réglables) ; test unitaire à +1 octet de la limite.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P26.01 | **j08b-001** (S2) | Toute création de collection, par quelque route que ce soit, vérifie check_quota_or_raise(kind='collections'). | `core/app/collections/routes.py:270-322`, `core/app/collections/routes.py:356-357` | XS | P01.01 | `bug(`→`test(` : j08b-001 — `j08b/quotas-api.spec.ts` |
| P26.02 | **j08b-003** (S2) | Le refus n'intervient que si usage réel + 0 (objet déjà compté) dépasse la limite, ou si l'objet est exclu de l'usage avant d'ajouter sa taille. | `core/app/quotas/service.py:191-210`, `core/app/ingestion/routes.py:186-191`, `core/app/attachments/routes.py:236-250`, `core/app/terrain3d/routes.py:112-118` (+1) | S | P03.01 | `bug(`→`test(` : j08b-003 — `j08b/quotas-api.spec.ts` |
| P26.03 | **j08b-010** (S2), c02-014 (S3) | Contrôle d'items/collections au point unique de création (routes et jobs) | `core/app/ingestion/importer.py:240-295`, `core/app/ingestion/tasks.py:95-120`, `core/app/pipelines/runtime.py:975-990`, `core/app/tileset3d/jobs.py:70-90` (+4) | M | P01.01 | `bug(`→`test(` : j08b-010 — `j08b/quota-bypass.spec.ts` |
| P26.04 | **t03b-006** (S2), j08b-012 (S3) | `usage_for_tenant` : exports, CDC, PostGIS comptés ou exclusion documentée | `core/app/quotas/service.py:99-140`, `core/app/quotas/service.py:99-118`, `core/app/export/routes.py:68-100` | M | — | `bug(`→`test(` : t03b-006 — `t03b/quota-usage.spec.ts` |
| P26.05 | j08b-002 (S3) | Un refus de quota supprime l'objet téléversé (comme attachments/tileset3d) ou l'exclut du comptage ; | `core/app/ingestion/routes.py:186-191`, `core/app/terrain3d/routes.py:112-118`, `core/app/quotas/service.py:155-190` | S | P26.02 | `bug(`→`test(` : j08b-002 — `j08b/quotas-api.spec.ts` |
| P26.06 | j08-016 (S3), j08b-011 (S3) | Supprimer les fichiers sources après import et poser un cycle de vie sur les buckets | `core/app/quotas/service.py:125-138`, `core/app/ingestion/routes.py:155-160`, `core/app/ingestion/tasks.py:95-120`, `core/app/quotas/service.py:155-190` | M | P26.05 | `bug(`→`test(` : j08b-011 — `j08b/quota-bypass.spec.ts` |
| P26.07 | j08b-007 (S4) | Unité adaptée (octets, Ko, Mo, Go) et séparateur décimal fr (virgule) ; | `shell/src/pages/AdminInfrastructurePage.tsx:26-29` | XS | — | `bug(`→`test(` : j08b-007 — `j08b/quotas-ui.spec.ts` |
| P26.08 | j08b-008 (S3) | Jauge avec seuil d'alerte, visible aussi pour les créateurs, et message de refus actionnable. | `shell/src/pages/AdminInfrastructurePage.tsx:93-116`, `shell/src/shell/NewItemButton.tsx:355-362` | M | — | `bug(`→`test(` : j08b-008 — `j08b/quotas-ui.spec.ts` |
| P26.09 | t02-014 (S4) | Un quota atteint a un statut ou un code d'erreur dédié (413/403 + type problem+json « quota-exceeded ») que le shell peut traiter (lien vers l'usage,… | `core/app/quotas/service.py:160-210` | S | — | critère de la cible (lecture de code) |

#### P27 — CI, tests et filets d'infrastructure

- Portée : Tests postgis skippés silencieusement, sauvegarde sans healthcheck, actions tierces non épinglées, jobs sans délai.
- Revue : CI/déploiement ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : job CI « stack composée » minimal (import GeoJSON + worker MapLibre + lien de partage + run de pipeline par l'API + export d'app) qui aurait attrapé RC-1/RC-2/RC-3/RC-4.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P27.01 | **c05-001** (S2) | Un run local ou CI sans base réelle échoue (ou avertit bruyamment) au lieu de passer vert. | `core/tests/conftest.py:30-33` | S | — | repro inversé : `cd core && CORE_TEST_DATABASE_URL= uv run pytest tests/test_collections_spatial_index.py tests/test_migration_0035_indexes.py tests/test_in…` |
| P27.02 | c05-002 (S3) | Une seule fixture/helper centralise le skip conditionnel. | `core/tests/test_migration_0035_indexes.py:30-38`, `core/tests/test_migration_0024_downgrade.py:30-35` | S | P27.01 | repro inversé : `grep -rn 'CORE_TEST_DATABASE_URL non défini' core/tests` |
| P27.03 | c05-003 (S3) | Assertion sur une propriété structurelle (nombre de requêtes/batchs, débit relatif) ou seuil calibré avec marge mesurée. | `core/tests/test_ingestion_importer_perf.py:29`, `core/tests/test_ingestion_importer_perf.py:101-103` | S | — | repro inversé : `grep -n PERF_BUDGET core/tests/test_ingestion_importer_perf.py` |
| P27.04 | c05-004 (S4) | Attendre un signal observable (requête réseau absente via waitForRequest négatif borné, ou état stable) plutôt qu'un délai. | `shell/e2e/analytics-context.spec.ts:1918`, `shell/e2e/analytics-context.spec.ts:600` | XS | — | repro inversé : `grep -n waitForTimeout shell/e2e/*.ts` |
| P27.05 | c05-005 (S3) | Un id non mocké échoue bruyamment (404 ou erreur de test) au lieu de servir une config plausible. | `shell/e2e/mocks.ts:593-610`, `shell/e2e/mocks.ts:614-632` | S | — | repro inversé : `sed -n 560,635p shell/e2e/mocks.ts` |
| P27.06 | c05-006 (S3) | Rapport de couverture reproductible par module avec base réelle, et modules à faible couverture (runtime.py, aggregate.py, features/repository.py) id… | `core/coverage.xml:1` | M | P27.01 | repro inversé : `cd core && python3 -c "import xml.etree.ElementTree as E;r=E.parse('coverage.xml').getroot();print(r.get('line-rate'))"` |
| P27.07 | **c06-002** (S2) | Un échec d'envoi hors-site est borné (quelques tentatives espacées), la rotation locale s'exécute quand même et l'archive locale n'est pas dupliquée. | `deploy/backup/entrypoint.sh:8-18`, `deploy/backup/backup.sh:86-105`, `deploy/backup/retention.py:32-39` | S | — | critère de la cible (lecture de code) |
| P27.08 | **c06-003** (S2) | Une sonde de fraîcheur (dernier backup réussi < 26 h) rend l'état unhealthy et alimente une alerte. | `docker-compose.prod.yml:318-350` | S | — | repro inversé : `python3 -c "import yaml" avec loader ignorant !reset/!override sur docker-compose.yml + docker-compose.prod.yml, lister 'healthcheck' par s…` |
| P27.09 | c06-006 (S3) | Toute modification de retention.py est gardée par la CI. | `deploy/backup/test_retention.py:14-33`, `core/pyproject.toml:207-209` | XS | — | repro inversé : `cd core && grep -n testpaths pyproject.toml && grep -rn test_retention ../.github/workflows \|\| echo aucune référence CI` |
| P27.10 | c06-007 (S3) | Actions épinglées par SHA (Dependabot github-actions les met à jour), builds reproductibles, images signées. | `.github/workflows/_build-and-push.yml:75-79`, `.github/workflows/_build-and-push.yml:165`, `.github/workflows/desktop-etl-webdriver.yml:41-44` | M | — | critère de la cible (lecture de code) |
| P27.11 | **c06-009** (S2) | Runtime Node supporté (22/24 LTS) et images de base surveillées par Dependabot (et idéalement épinglées par digest). | `shell/Dockerfile:1`, `.github/workflows/ci.yml:207`, `deploy/appexport-runtime-builder/Dockerfile:7` | M | — | critère de la cible (lecture de code) |
| P27.12 | c06-011 (S3) | Le bilan committé est indépendant du contexte d'exécution CI (ou la fraîcheur ne compare que les champs déterministes), et le push bot ne peut pas éc… | `.github/workflows/ci.yml:316-347` | S | — | repro inversé : `gh run list --workflow ci.yml --limit 8 --json headSha,event,conclusion` |
| P27.13 | c06-012 (S4) | cancel-in-progress sur les PR et timeout-minutes par job. | `.github/workflows/ci.yml:8` | XS | — | repro inversé : `grep -n 'timeout-minutes\\|concurrency' .github/workflows/*.yml` |
| P27.14 | c06-014 (S3) | Tous les services long-vivants ont restart: unless-stopped et une sonde. | `docker-compose.prod.yml:34`, `docker-compose.yml:690-700` | S | — | repro inversé : `python3 avec loader yaml ignorant !reset/!override sur les deux fichiers compose` |

#### P28 — Import de fichiers

- Portée : Validation des coordonnées et séparateurs, typage des colonnes, messages d'erreur, sondage sans plafond.
- Revue : cœur — ingestion + shell ; niveau 2 ; dépend de : P01.
- Critères de clôture du paquet, en plus des tâches : import réel (sans semis SQL) rejoué après P01–P03.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P28.01 | j03-004 (S3) | Refus avec un message nommant la ligne et la valeur. | `core/app/ingestion/parsers.py:102-125` | S | — | `bug(`→`test(` : j03-004 — `j03/import-api.spec.ts` |
| P28.02 | j03-005 (S3) | Le séparateur est détecté, ou le choix de colonnes propose les vraies colonnes. | `shell/src/shell/ImportFileButton.tsx:148-150`, `core/app/ingestion/parsers.py:335-357` | S | — | `bug(`→`test(` : j03-005 — `j03/import-api.spec.ts`, `j03/map-ui.spec.ts` |
| P28.03 | j03-006 (S4) | Message français sans chemin serveur ni jargon. | `core/app/ingestion/parsers.py:755-759` | XS | — | `bug(`→`test(` : j03-006 — `j03/import-api.spec.ts` |
| P28.04 | j03-009 (S3) | La carte importée porte l'emprise des données importées. | `core/app/configs/bbox.py:48-70`, `core/app/ingestion/importer.py:308-315` | S | — | `bug(`→`test(` : j03-009 — `j03/map-api.spec.ts` |
| P28.05 | j03-010 (S3) | La couche générée déclare son type de rendu. | `core/app/ingestion/importer.py:308-315` | S | — | `bug(`→`test(` : j03-010 — `j03/map-api.spec.ts` |
| P28.06 | j03-021 (S3) | La collection tabulaire est listée dans le catalogue Données du créateur. | `core/app/ingestion/importer.py:269-320` | M | — | `bug(`→`test(` : j03-021 — `j03/import-api.spec.ts` |
| P28.07 | j05-025 (S3) | Inférence de types (entier, décimal, date) à l'import CSV, ou éditeur de types avant import. | `core/app/ingestion/importer.py:100-107`, `core/app/ingestion/parsers.py:161-203` | M | — | critère de la cible (lecture de code) |
| P28.08 | j03-019 (S3) | Le message distingue l'étape en échec (et le detail RFC 7807). | `shell/src/shell/ImportFileButton.tsx:268-274`, `shell/src/shell/ImportFileButton.tsx:296-301` | S | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j03 -g 'le tiroir s.ouvre'` |
| P28.09 | j03-020 (S3), t02-010 (S3) | Sondage du job d'import borné et état d'attente affiché | `shell/src/shell/ImportFileButton.tsx:155-170`, `shell/src/shell/ImportFileButton.tsx:155-187`, `shell/src/shell/ImportFileButton.tsx:329-341`, `shell/src/shell/ImportFileButton.tsx:555-565` | S | P01.04, P01.07 | `bug(`→`test(` : t02-010 — `t02/session-import.spec.ts` |
| P28.10 | t02-011 (S3) | Une erreur transitoire du sondage est retentée (quelques essais avec délai) ; | `shell/src/shell/ImportFileButton.tsx:155-187`, `shell/src/shell/ImportFileButton.tsx:250-254` | XS | — | `bug(`→`test(` : t02-011 — `t02/session-import.spec.ts` |

#### P29 — Données complètes et troncatures annoncées

- Portée : Troncatures silencieuses à 100 / 1 000 / 5 000 / 10 000 entités, export non streamé.
- Revue : cœur — features + shell ; niveau 2 ; dépend de : P01.
- Critères de clôture du paquet, en plus des tâches : téléchargement GeoJSON de 500 000 entités complet ou « N sur M » affiché.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P29.01 | **j03-008** (S2) | La carte affiche toutes les entités (ou bascule en tuiles vectorielles au-delà d'un seuil). | `core/app/ingestion/importer.py:308-315`, `core/app/features/routes.py:204` | S | P01.01 | `bug(`→`test(` : j03-008 — `j03/map-api.spec.ts` |
| P29.02 | **j03-013** (S2) | Symbologie et popup proposent les champs de la couche importée. | `shell/src/map/geojsonIntrospect.ts:5-7`, `shell/src/map/LayersPanel.tsx:24-31` | S | — | `bug(`→`test(` : j03-013 — `j03/map-ui.spec.ts` |
| P29.03 | **t03-007** (S2), t03b-005 (S3) | Lien GeoJSON de la fiche dataset borné à 1 000 sans l'annoncer | `shell/src/lib/datasetDownload.ts:12-33`, `shell/src/lib/datasetDownload.ts:23-36` | M | — | `bug(`→`test(` : t03b-005 — `t03b/ui-perf.spec.ts` |
| P29.04 | **t03-008** (S2), t03b-007 (S3) | Plafond d'export à 10 000 : export en flux ou par job | `core/app/features/routes.py:375-431`, `core/app/features/routes.py:375-376`, `core/app/features/routes.py:415-435` | M | — | `bug(`→`test(` : t03-008 — `t03/bigdata.spec.ts` |
| P29.05 | **t03-011** (S2) | Pagination serveur (limit/offset) ou au minimum le total réel et un avertissement de troncature. | `shell/src/api/domains/datasets.ts:235-262`, `shell/src/builder/widgets/data.tsx:271-312`, `shell/src/pages/DatasetPage.tsx:40-48` | M | — | `bug(`→`test(` : t03-011 — `t03/bigdata.spec.ts` |
| P29.06 | t03-010 (S3) | L'indicateur suit les tuiles réellement affichées (en-tête X-Tile-Truncated de chaque tuile visible). | `shell/src/map/LayersPanel.tsx:238-272` | S | — | `bug(`→`test(` : t03-010 — `t03/bigdata.spec.ts` |
| P29.07 | t03b-003 (S3) | Le CSV/XLSX porte la géométrie (WKT ou colonnes lon/lat) ou l'API signale qu'elle est omise. | `core/app/analytics/export.py:120-130`, `core/app/features/routes.py:378-400` | S | — | `bug(`→`test(` : t03b-003 — `t03b/export-items.spec.ts` |
| P29.08 | j09-010 (S4) | L'indicateur n'apparaît que si des entités ont réellement été omises (LIMIT max+1 puis comparaison stricte). | `core/app/features/tiles.py:184-185` | XS | — | `bug(`→`test(` : j09-010 — `j09/tiles.spec.ts` |
| P29.09 | t03-009 (S3), c09-013 (S3) | Tuile MVT plafonnée sans `ORDER BY` ni simplification | `core/app/features/tiles.py:41`, `core/app/features/tiles.py:103-114`, `core/app/features/tiles.py:99-122`, `core/app/features/tiles.py:174-186` | L | — | `bug(`→`test(` : t03-009 — `t03/bigdata.spec.ts` |

#### P30 — Carte : `MapView` et éditeur de carte

- Portée : `MapView.tsx` (1 479 lignes) appelle le cœur en direct, fuite DOM de l'éditeur, sonde de troncature sans jeton de partage.
- Revue : shell — carte ; niveau 3 ; dépend de : P04, P22.
- Critères de clôture du paquet, en plus des tâches : 8 cycles d'éditeur sans croissance de nœuds détachés.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P30.01 | **t03-012** (S2) | Retour à un état stable (delta ≈ 0) après chaque fermeture de l'éditeur. | `shell/src/map/MapView.tsx:1074-1215` | M | P04.01 | `bug(`→`test(` : t03-012 — `t03/polling.spec.ts` |
| P30.02 | c04-004 (S3) | Composants découpés en hooks/modules (init carte, popup, couches deck/3D, étiquettes) sous ~500 lignes, deps d'effets déclarées. | `shell/src/map/MapView.tsx:1-1479` | L | — | repro inversé : `cd shell/src && find . -name '*.ts' -o -name '*.tsx' \| grep -v generated \| grep -v test \| xargs wc -l \| sort -rn \| head -8` |
| P30.03 | c04-002 (S3), c08-010 (S4) | `MapView` : passer par `ItemClient` (pièces jointes, en-têtes) | `shell/src/map/MapView.tsx:1383-1394`, `shell/src/map/MapView.tsx:1416-1427`, `shell/src/map/MapView.tsx:1447`, `shell/src/map/MapView.tsx:1383` (+2) | M | P22.01 | repro inversé : `sed -n 1370,1460p shell/src/map/MapView.tsx` |
| P30.04 | c04-006 (S3) | La sonde utilise la même authentification que le chargement des tuiles, ou le badge est explicitement indisponible. | `shell/src/map/LayersPanel.tsx:258-261` | S | P30.03 | repro inversé : `sed -n 245,265p shell/src/map/LayersPanel.tsx` |
| P30.05 | t04-017 (S4) | Libellés MapLibre traduits (locale fr) ou contrôle nommé en français. | `shell/src/map/MapView.tsx:1076-1090`, `shell/src/pages/DatasetPage.tsx:1` | S | — | `bug(`→`test(` : t04-017 — `t04/labels.spec.ts` |

#### P31 — Mise en page mobile et carte tactile

- Portée : Triptyque non borné, barre du haut de 517 px, cibles tactiles sous 24 px, popup hors carte.
- Revue : shell — mise en page ; niveau 2 ; dépend de : P04.
- Critères de clôture du paquet, en plus des tâches : scrollHeight ≤ innerHeight à 360 et 1280 px ; E2E `triptych-narrow` et `responsive` verts ; `j12-005`/`j12-009` **sans** stub de worker.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P31.01 | **j02-009** (S2) | Le canvas de la carte occupe exactement la hauteur disponible de la fenêtre, les panneaux latéraux défilent. | `shell/src/shell/chrome/TriptychLayout.tsx:22-28`, `shell/src/pages/MapEditorPage.tsx:189` | S | — | `bug(`→`test(` : j02-009 — `j02/reader-ui.spec.ts` |
| P31.02 | **j12-002** (S2) | L'en-tête tient dans la largeur du téléphone (actions repliées dans un menu) : Notifications et Compte atteignables sans défilement horizontal. | `shell/src/shell/chrome/TopBar.tsx:18-35` | S | — | `bug(`→`test(` : j12-002 — `j12/layout.spec.ts` |
| P31.03 | **j12-003** (S2) | La hauteur de la zone de travail est bornée à la fenêtre (colonnes scrollables en interne), la carte est entièrement visible. | `shell/src/shell/AppLayout.tsx:70-79`, `shell/src/shell/chrome/TriptychLayout.tsx:22-30` | M | — | `bug(`→`test(` : j12-003, j12-004 — `j12/layout.spec.ts` |
| P31.04 | j03-016 (S3) | L'éditeur tient dans la fenêtre sans défilement de page. | `shell/src/pages/MapEditorPage.tsx:189-190` | S | — | `bug(`→`test(` : j03-016 — `j03/map-ui.spec.ts` |
| P31.05 | **j12-005** (S2) | Cible d'au moins 24×24 px (idéalement 44 px) avec marge tactile. | `shell/src/map/MapPopup.tsx:68-76` | XS | P04.01 | `bug(`→`test(` : j12-005 — `j12/map-touch.spec.ts` |
| P31.06 | **j12-009** (S2) | Le tracé libre fonctionne au toucher (événements pointeur/touch, dragPan suspendu pendant le tracé). | `shell/src/map/MapMeasureSketchToolbar.tsx:340-365` | M | P04.01 | `bug(`→`test(` : j12-009 — `j12/map-touch.spec.ts` |
| P31.07 | j12-006 (S3) | Commandes d'au moins 24×24 px (44 px tactile), placées hors du clipping du widget. | `shell/src/builder/GridCanvas.tsx:69-125` | XS | — | `bug(`→`test(` : j12-006 — `j12/builder-touch.spec.ts` |
| P31.08 | j12-007 (S3) | Cibles d'au moins 24×24 px avec espacement. | `shell/src/map/LayersPanel.tsx:309-346` | XS | — | `bug(`→`test(` : j12-007 — `j12/builder-touch.spec.ts` |
| P31.09 | j12-008 (S3) | Cibles primaires ≥ 44×44 px sur écran tactile. | `shell/src/shell/chrome/BottomNav.tsx:19-41`, `shell/src/shell/chrome/TriptychLayout.tsx:36-46`, `shell/src/shell/chrome/TopBar.tsx:21-33` | S | P31.02 | `bug(`→`test(` : j12-008 — `j12/layout.spec.ts` |
| P31.10 | j12-010 (S3) | Flèches gauche/droite, Home/End déplacent la sélection ; | `shell/src/shell/chrome/TriptychLayout.tsx:35-46` | S | — | `bug(`→`test(` : j12-010 — `j12/layout.spec.ts` |
| P31.11 | j12-011 (S3) | Le popup est repositionné/clampé dans le cadre visible de la carte. | `shell/src/map/MapPopup.tsx:61-67` | M | P04.01 | `bug(`→`test(` : j12-011 — `j12/map-touch.spec.ts` |
| P31.12 | j12-013 (S4) | Sur pointeur grossier, une simple icône de recherche sans hint clavier. | `shell/src/shell/chrome/TopBar.tsx:21-28` | XS | P31.02 | critère de la cible (lecture de code) |
| P31.13 | j12-014 (S4) | Un choix Clair/Sombre/Auto persistant (Paramètres) qui pose data-theme. | `shell/src/styles/tokens.css:78` | S | — | critère de la cible (lecture de code) |
| P31.14 | j12-015 (S3) | Saisie du texte dans un champ de la barre d'outils ; | `shell/src/map/MapMeasureSketchToolbar.tsx:286-300`, `shell/src/map/MapMeasureSketchToolbar.tsx:416-440` | M | — | critère de la cible (lecture de code) |
| P31.15 | j12-016 (S4) | Un mode intermédiaire à deux volets (carte + panneau) entre 640 et 899 px, ou un chrome plus compact en paysage. | `shell/src/shell/chrome/useNarrowViewport.ts:21` | S | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j12/layout.spec.ts -g '899 px et moins'` |

#### P32 — Canevas de pipeline

- Portée : Connexion et suppression d'arête impossibles au clavier (et d'arête à la souris), nœuds illisibles en sombre, cibles 16 px.
- Revue : shell — pipelines + a11y ; niveau 2 ; dépend de : P33.
- Critères de clôture du paquet, en plus des tâches : test Vitest de suppression d'arête au clavier ; E2E `pipeline-builder` vert.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P32.01 | **t01b-001** (S2) | Un utilisateur clavier peut relier deux nœuds (Entrée/Espace sur la cible, ou commande équivalente), WCAG 2.1.1. | `shell/src/builder/pipeline/PipelineCanvas.tsx:481-488`, `shell/src/builder/pipeline/PipelineCanvas.tsx:415-429` | S | — | `bug(`→`test(` : t01b-001 — `t01b/pipeline-canvas.spec.ts` |
| P32.02 | **t01b-008** (S2) | Une arête se sélectionne (clic ou Entrée) et se supprime (Suppr) ; | `shell/src/builder/pipeline/PipelineCanvas.tsx:387-398`, `shell/src/builder/pipeline/PipelineCanvas.tsx:265-274` | S | — | `bug(`→`test(` : t01b-008 — `t01b/pipeline-canvas.spec.ts` |
| P32.03 | **t01b-007** (S2) | Le texte des nœuds hérite de text-ink (ratio >= 4,5:1 en sombre). | `shell/src/builder/pipeline/PipelineCanvas.tsx:60`, `shell/src/builder/pipeline/PipelineCanvas.tsx:71-72`, `shell/src/builder/pipeline/PipelineCanvas.tsx:36-40` | XS | P33.02 | `bug(`→`test(` : t01b-007 — `t01b/pipeline-canvas.spec.ts` |
| P32.04 | t01b-002 (S3) | Nœud et arête focalisés portent un contour/anneau visible (focus-visible:ring-2 ring-accent). | `shell/src/builder/pipeline/PipelineCanvas.tsx:56-62`, `shell/src/builder/pipeline/PipelineCanvas.tsx:496` | XS | — | `bug(`→`test(` : t01b-002 — `t01b/pipeline-canvas.spec.ts` |
| P32.05 | t01b-003 (S4) | Nom court (l'opération) et description reliée par aria-describedby, ou séparateur explicite. | `shell/src/builder/pipeline/PipelinePalette.tsx:106-130` | XS | — | `bug(`→`test(` : t01b-003 — `t01b/pipeline-canvas.spec.ts` |
| P32.06 | t01b-004 (S3) | Le canevas est atteignable en moins de 30 tabulations (sections repliables, liste à un seul arrêt avec flèches, ou lien « Aller au canevas »). | `shell/src/builder/pipeline/PipelinePalette.tsx:99-104`, `shell/src/pages/PipelineBuilderPage.tsx:185-197` | S | — | `bug(`→`test(` : t01b-004 — `t01b/pipeline-canvas.spec.ts` |
| P32.07 | t01b-005 (S4) | Libellés du catalogue i18n pour les contrôles (aria-labelConfig de ReactFlow) et nom d'arête « de <titre source> vers <titre cible> ». | `shell/src/builder/pipeline/PipelineCanvas.tsx:495-496`, `shell/src/builder/pipeline/PipelineCanvas.tsx:265-274` | S | — | `bug(`→`test(` : t01b-005 — `t01b/pipeline-canvas.spec.ts` |
| P32.08 | t01b-006 (S3) | Cibles d'au moins 24×24 px (ou espacées), y compris les commandes flottantes des nœuds. | `shell/src/builder/pipeline/PipelineCanvas.tsx:98-116`, `shell/src/builder/pipeline/PipelineCanvas.tsx:202-212`, `shell/src/builder/pipeline/PipelineScheduleEditor.tsx:112-119` | S | — | `bug(`→`test(` : t01b-006 — `t01b/pipeline-canvas.spec.ts` |
| P32.09 | t01b-009 (S3) | Le champ en erreur porte aria-invalid=true et aria-describedby vers le message. | `shell/src/builder/pipeline/PipelineScheduleEditor.tsx:214-231`, `shell/src/builder/AlertRuleEditor.tsx:243-247` | S | — | `bug(`→`test(` : t01b-009 — `t01b/automation-forms.spec.ts` |
| P32.10 | j06b-014 (S4) | Message explicite « aucune opération ». | `shell/src/builder/pipeline/PipelinePalette.tsx:35-41` | XS | — | repro inversé : `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j06b/ui-builder.spec.ts -g "j06b-014"` |

#### P33 — Accessibilité transverse

- Portée : Fond/texte absents en sombre, contrastes de tokens, repères, menu Actions non ARIA, focus perdu.
- Revue : shell — a11y ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : `shell/e2e/a11y-audit.spec.ts` gagne un passage en thème sombre (éditeur de pipeline et `/reports/new` inclus).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P33.01 | **t01-004** (S2) | Chaque route a un titre distinct « Vue — GeoStudio » mis à jour à la navigation (WCAG 2.4.2, niveau A). | `shell/index.html:6`, `shell/src/shell/routes.tsx:232-241` | S | — | `bug(`→`test(` : t01-004 — `t01/structure.spec.ts` |
| P33.02 | **t01-005** (S2) | body { background: var(--gs-background); | `shell/src/index.css:1-12`, `shell/src/styles/tokens.css:121-125`, `shell/src/shell/AppLayout.tsx:67` | XS | — | `bug(`→`test(` : t01-005 — `t01/axe.spec.ts` |
| P33.03 | **t01-006** (S2) | Les routes publiques ont un fond thématisé (ou forcent le thème clair) avec un texte ≥ 4,5:1. | `shell/src/pages/DatasetPage.tsx:84-88`, `shell/src/pages/AppRuntimePage.tsx:145-150`, `shell/src/index.css:1-12` | XS | P33.02 | `bug(`→`test(` : t01-006 — `t01/axe.spec.ts` |
| P33.04 | **t01-009** (S2) | Le déclencheur porte aria-haspopup=menu et aria-expanded ; | `shell/src/shell/ItemActions.tsx:52-60`, `shell/src/shell/ItemActions.tsx:62-130` | S | — | `bug(`→`test(` : t01-009 — `t01/dialogs.spec.ts` |
| P33.05 | t01-001 (S3) | Le contenu principal de chaque page est dans un <main> unique. | `shell/src/shell/AppLayout.tsx:78` | XS | — | `bug(`→`test(` : t01-001, t01-002 — `t01/structure.spec.ts` |
| P33.06 | t01-003 (S3) | Chaque page a un <h1> décrivant sa vue (visible ou sr-only) ; | `shell/src/pages/CatalogPage.tsx:350-356`, `shell/src/pages/ReportEditPage.tsx:1` | S | — | `bug(`→`test(` : t01-003 — `t01/structure.spec.ts` |
| P33.07 | t01-007 (S3) | Tout texte des jetons ink-3 et warn atteint 4,5:1 sur les surfaces où il est utilisé. | `shell/src/styles/tokens.css:42-64`, `shell/src/styles/tokens.css:92-100` | XS | — | `bug(`→`test(` : t01-007 — `t01/structure.spec.ts` |
| P33.08 | t01-008 (S3) | Le contour des champs, cases et radios atteint 3:1 contre le fond adjacent. | `shell/src/styles/tokens.css:50-52`, `shell/src/ui/kit/Input.tsx:10-20` | S | — | `bug(`→`test(` : t01-008 — `t01/structure.spec.ts` |
| P33.09 | t01-010 (S3) | Échap et le clic extérieur ferment le menu et rendent le focus au déclencheur. | `shell/src/shell/ItemActions.tsx:62-64` | XS | P33.04 | `bug(`→`test(` : t01-010 — `t01/dialogs.spec.ts` |
| P33.10 | t01-011 (S3) | Le focus revient au bouton « Actions » de la carte après annulation. | `shell/src/shell/ItemActions.tsx:120-132`, `shell/src/ui/kit/useFocusRestoreOnClose.ts:16-29` | XS | P33.04 | `bug(`→`test(` : t01-011 — `t01/dialogs.spec.ts` |
| P33.11 | t01-012 (S4) | role=alertdialog avec aria-describedby vers le message. | `shell/src/ui/kit/ConfirmDialog.tsx:23-35`, `shell/src/ui/kit/Dialog.tsx:32-46` | XS | — | `bug(`→`test(` : t01-012 — `t01/dialogs.spec.ts` |
| P33.12 | t01-013 (S3) | Nom accessible unique par carte (« Ouvrir aud-… », « Actions de aud-… »). | `shell/src/ui/kit/ItemCard.tsx:32-36`, `shell/src/shell/ItemActions.tsx:52-60` | XS | — | `bug(`→`test(` : t01-013 — `t01/structure.spec.ts` |
| P33.13 | t01-015 (S3) | Une indication visible (« Échap puis Tab pour quitter l'éditeur ») ou un mode de focus par défaut évite le piège. | `shell/src/pages/SqlLabPage.tsx:180-199` | XS | — | `bug(`→`test(` : t01-015 — `t01/dialogs.spec.ts` |
| P33.14 | t01-016 (S3) | Une alternative clavier (champs ouest/sud/est/nord) applique le même filtre bbox (WCAG 2.1.1). | `shell/src/pages/CatalogSpatialFilter.tsx:57-140`, `shell/src/pages/CatalogSpatialFilter.tsx:153-162` | M | — | `bug(`→`test(` : t01-016 — `t01/structure.spec.ts` |
| P33.15 | t01-017 (S3) | Le déclencheur expose aria-expanded/aria-controls (usePanelTrigger). | `shell/src/pages/RolesAdminPage.tsx:71-82` | XS | — | `bug(`→`test(` : t01-017 — `t01/forms.spec.ts` |
| P33.16 | t01-018 (S3) | Le champ requis est marqué (required/aria-required) et le motif du blocage est lisible (message lié par aria-describedby), ou le bouton reste actif e… | `shell/src/shell/CreateRolePanel.tsx:10-80` | S | — | `bug(`→`test(` : t01-018 — `t01/forms.spec.ts` |
| P33.17 | t01-019 (S3) | Le compteur/état vide est dans une région role=status (polite) annoncée à chaque changement de filtre. | `shell/src/pages/CatalogPage.tsx:282-290`, `shell/src/pages/CatalogPage.tsx:350-358` | XS | — | `bug(`→`test(` : t01-019 — `t01/structure.spec.ts` |
| P33.18 | t01-020 (S4) | Libellé français (maplibregl.Map({ locale: {'Map.Title': …} })). | `shell/src/pages/CatalogSpatialFilter.tsx:58-80` | XS | — | `bug(`→`test(` : t01-020 — `t01/structure.spec.ts` |
| P33.19 | t01-021 (S4) | Tree suit le patron ARIA tree/treeitem ; | `shell/src/ui/kit/Tree.tsx:68-80`, `shell/src/ui/kit/Banner.tsx:16-28` | S | P33.07 | `bug(`→`test(` : t01-021 — `t01/axe.spec.ts` |
| P33.20 | t01-022 (S4) | Un réglage utilisateur clair/sombre/auto persistant, appliqué avant le premier rendu. | `shell/src/pages/KitGalleryPage.tsx:270-280` | M | — | repro inversé : `grep -rn "data-theme\\|dataset.theme" shell/src shell/index.html \| grep -v tokens` |
| P33.21 | t01-023 (S4) | Hiérarchie de titres continue. | `shell/src/builder/ConfigHistoryPanel.tsx:100` | XS | — | `bug(`→`test(` : t01-023 — `t01/axe.spec.ts` |
| P33.22 | t01b-010 (S4) | Nom accessible contenant le libellé visible (supprimer l'aria-label redondant, le <label> suffit). | `shell/src/pages/ComplianceAdminPage.tsx:39-44`, `shell/src/pages/ComplianceAdminPage.tsx:105-110` | XS | — | `bug(`→`test(` : t01b-010 — `t01b/admin-flags.spec.ts` |
| P33.23 | t01b-012 (S3) | aria-expanded reflète pickerOpen et aria-controls pointe le panneau. | `shell/src/builder/appexport/AppExportPanel.tsx:89-97`, `shell/src/builder/appexport/AppExportPanel.tsx:98-108` | XS | — | `bug(`→`test(` : t01b-012 — `t01b/export-tileset.spec.ts` |
| P33.24 | t01b-013 (S3) | Le focus revient sur le déclencheur (aria-disabled plutôt que disabled) et la progression est annoncée (role=status). | `shell/src/builder/appexport/AppExportPanel.tsx:52-66`, `shell/src/builder/appexport/AppExportPanel.tsx:89-94` | S | — | `bug(`→`test(` : t01b-013 — `t01b/export-tileset.spec.ts` |
| P33.25 | t01b-014 (S3) | La progression et la validation sont des régions live (role=status). | `shell/src/shell/Tileset3DUploadButton.tsx:158-165` | XS | — | `bug(`→`test(` : t01b-014 — `t01b/export-tileset.spec.ts` |
| P33.26 | t01b-015 (S3) | Le bouton est masqué sans le privilège d'écriture, comme Nouveau/Importer. | `shell/src/shell/chrome/TopBar.tsx:31`, `shell/src/shell/AppLayout.tsx:31` | XS | — | `bug(`→`test(` : t01b-015 — `t01b/export-tileset.spec.ts` |
| P33.27 | j03-014 (S4) | Libellé entièrement en français, via le catalogue i18n. | `shell/src/map/TerrainPanel.tsx:115-120` | XS | — | `bug(`→`test(` : j03-014 — `j03/map-ui.spec.ts` |

#### P34 — Cohérence UI et i18n

- Portée : Énumérations brutes, dates ISO, pluriels, libellés anglais, composants d'état contournés.
- Revue : shell — UI ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : `npm run lint` (détecteur i18n étendu aux `.ts` et gabarits) vert.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P34.01 | t04-001 (S3) | La pastille utilise RESOURCE_TYPE_LABELS comme le reste du catalogue. | `shell/src/pages/ItemDetailPage.tsx:108-110` | XS | — | `bug(`→`test(` : t04-001 — `t04/labels.spec.ts` |
| P34.02 | t04-002 (S3) | Une date localisée fr-FR, identique à celle de l'historique de versions. | `shell/src/pages/ItemDetailPage.tsx:97-98` | XS | — | `bug(`→`test(` : t04-002 — `t04/labels.spec.ts` |
| P34.03 | t04-003 (S3) | Libellés du tiroir alignés sur RESOURCE_TYPE_LABELS / la navigation (« Carte », « Application »...). | `shell/src/i18n/catalog.fr.ts:736-742`, `shell/src/shell/NewItemButton.tsx:238-243` | XS | P34.18 | `bug(`→`test(` : t04-003 — `t04/labels.spec.ts` |
| P34.04 | t04-004 (S4) | Libellé français compréhensible d'un non-géomaticien (« Entités », « Statistiques », « Statique »). | `shell/src/i18n/catalog.fr.ts:1506`, `shell/src/builder/DataSourcePanel.tsx:139-144` | XS | — | `bug(`→`test(` : t04-004 — `t04/labels.spec.ts` |
| P34.05 | t04-005 (S4) | Un libellé traduit du type de couche (« Vecteur », « Raster », « Tuiles 3D ») ou rien. | `shell/src/map/LayerPicker.tsx:145-151` | XS | — | `bug(`→`test(` : t04-005 — `t04/labels.spec.ts` |
| P34.06 | t04-006 (S3) | Ces contrôles utilisent Input/Select du kit (ou au minimum une hauteur et une bordure tokenisées). | `shell/src/builder/print/PrintLayoutPanel.tsx:26-86`, `shell/src/builder/PageManager.tsx:57-62`, `shell/src/builder/report/ReportScheduleEditor.tsx:35-55` | S | P34.07 | `bug(`→`test(` : t04-006 — `t04/consistency.spec.ts` |
| P34.07 | t04-007 (S4) | Une seule hauteur de champ par page ; | `shell/src/pages/DatasetEditPage.tsx:219-240`, `shell/src/builder/AlertRuleEditor.tsx:129-138`, `shell/src/builder/DataSourcePanel.tsx:139-145` | M | P34.06 | `bug(`→`test(` : t04-007 — `t04/consistency.spec.ts` |
| P34.08 | t04-008 (S4) | Un composant PageTitle du kit (niveau, taille, graisse) utilisé par toutes les pages de premier niveau. | `shell/src/pages/UsersAdminPage.tsx:82`, `shell/src/pages/DatasetPage.tsx:87`, `shell/src/pages/ItemDetailPage.tsx:111`, `shell/src/pages/VisualQueryWizardPage.tsx:371` (+1) | S | — | `bug(`→`test(` : t04-008 — `t04/consistency.spec.ts` |
| P34.09 | t04-009 (S4) | Tous les états de chargement utilisent LoadingState (SP-B7 « LoadingState uniforme »). | `shell/src/pages/HarvestSourcesAdminPage.tsx:114`, `shell/src/pages/RolesAdminPage.tsx:83`, `shell/src/pages/UsersAdminPage.tsx:95`, `shell/src/pages/CollectionsAdminPage.tsx:146` (+1) | XS | P34.19 | `bug(`→`test(` : t04-009 — `t04/states.spec.ts` |
| P34.10 | t04-013 (S3) | Toutes les dates et heures suivent le même format fr-FR, indépendant de la locale du navigateur. | `shell/src/shell/chrome/NotificationBell.tsx:55`, `shell/src/builder/report/ReportRunPanel.tsx:83`, `shell/src/map/FieldClassificationPicker.tsx:231`, `shell/src/map/MapSymbologyEditor.tsx:405` (+1) | XS | P34.02 | `bug(`→`test(` : t04-013 — `t04/labels.spec.ts` |
| P34.11 | t04-014 (S4) | « 0 élément », « 1 élément », « 2 éléments ». | `shell/src/i18n/index.ts:21-29`, `shell/src/pages/CatalogPage.tsx:352-357`, `shell/src/pages/DatasetPage.tsx:90-95` | XS | — | `bug(`→`test(` : t04-014 — `t04/labels.spec.ts` |
| P34.12 | t04-015 (S3) | Un état vide propre à la famille (« Aucun rapport... | `shell/src/pages/CatalogPage.tsx:282-318`, `shell/src/i18n/catalog.fr.ts:112-114` | S | — | `bug(`→`test(` : t04-015 — `t04/labels.spec.ts` |
| P34.13 | t04-016 (S3) | Toute valeur numérique affichée passe par le formateur fr-FR (« 1 234 567,75 »). | `shell/src/builder/widgets/indicator.tsx:188-190`, `shell/src/builder/widgets/chartOption.ts:104-106` | S | P34.21 | `bug(`→`test(` : t04-016 — `t04/labels.spec.ts` |
| P34.14 | t04-018 (S3) | Zéro libellé d'interface hors src/i18n/catalog.fr.ts ; | `shell/scripts/check-i18n-coverage.mjs:90-140`, `shell/src/builder/aggregates.ts:6-15`, `shell/src/builder/widgets/chartOption.ts:330-370`, `shell/src/api/resourceTypes.ts:13-26` (+1) | M | P34.15, P34.20 | `bug(`→`test(` : t04-018 — `t04/gates.spec.ts` |
| P34.15 | t04-019 (S4) | Nom accessible = titre/type du widget (« Sélectionner Table ») et libellés de rupture parlants (Mobile / Tablette / Bureau). | `shell/src/builder/GridCanvas.tsx:55-118`, `shell/src/pages/AppBuilderPage.tsx:422-435` | XS | P34.14 | `bug(`→`test(` : t04-019 — `t04/labels.spec.ts` |
| P34.16 | t04-020 (S4) | Titre de la ressource et libellé fonctionnel du journal d'activité. | `shell/src/pages/UsagePage.tsx:176-196`, `shell/src/i18n/catalog.fr.ts:84` | XS | — | `bug(`→`test(` : t04-020 — `t04/consistency.spec.ts` |
| P34.17 | t04-021 (S4) | Button variant=outline size=sm du kit pour toute action autonome. | `shell/src/builder/PageManager.tsx:93-99`, `shell/src/builder/ActionsPanel.tsx:179-185`, `shell/src/builder/VariablesPanel.tsx:132-138`, `shell/src/builder/DataSourcePanel.tsx:405-413` | S | P34.06 | `bug(`→`test(` : t04-021 — `t04/labels.spec.ts` |
| P34.18 | t04-022 (S4) | Un glossaire arrêté (ex. | `shell/src/api/resourceTypes.ts:13-26`, `shell/src/i18n/catalog.fr.ts:112-113`, `shell/src/i18n/catalog.fr.ts:412-416` | S | P34.14 | `bug(`→`test(` : t04-022 — `t04/labels.spec.ts` |
| P34.19 | t04-023 (S3) | Chargement, erreur et vide passent exclusivement par LoadingState / Banner (ou un QueryState) / EmptyState. | `shell/src/ui/kit/LoadingState.tsx:1-13`, `shell/src/ui/kit/Banner.tsx:1-28`, `shell/src/ui/kit/EmptyState.tsx:1-18` | M | — | repro inversé : `cd shell && grep -rnE '<p role="status">\{t\("common.loading"\)\}' src --include=*.tsx \| grep -v test \| wc -l` |
| P34.20 | t04-024 (S4) | Messages du catalogue, avec le titre du nœud et le libellé du paramètre plutôt que ses identifiants. | `shell/src/builder/pipeline/validation.ts:64-103`, `shell/src/pages/PipelineBuilderPage.tsx:448-458` | S | P34.14 | critère de la cible (lecture de code) |
| P34.21 | t04-025 (S4) | Format fr-FR (« 12,5 – 30,0 », « 1,5 Go »). | `shell/src/map/MapSymbologyLegend.tsx:54`, `shell/src/map/MapSymbologyLegend.tsx:114`, `shell/src/pages/CatalogPage.tsx:373`, `shell/src/pages/AdminInfrastructurePage.tsx:26-29` | XS | P34.10 | critère de la cible (lecture de code) |
| P34.22 | t04-026 (S4) | Couleurs de dataviz issues de jetons (--gs-*) lus au montage, ou pragma explicite. | `shell/src/builder/pipeline/PipelinePreviewMap.tsx:31-33`, `shell/src/builder/pipeline/PipelinePreviewMap.tsx:144`, `shell/src/pages/CatalogSpatialFilter.tsx:91-97`, `shell/scripts/check-raw-colors.mjs:40-44` | S | — | repro inversé : `cd shell && grep -rnE '"#[0-9a-fA-F]{6}"' src --include=*.tsx \| grep -v '\.test\.' \| grep -v ui/kit` |
| P34.23 | t04-027 (S4) | Paires clé One/Many via plural(). | `shell/src/i18n/catalog.fr.ts:201`, `shell/src/i18n/catalog.fr.ts:641`, `shell/src/i18n/catalog.fr.ts:1156` | XS | P34.11 | repro inversé : `cd shell && grep -nE '\(s\)' src/i18n/catalog.fr.ts` |
| P34.24 | j06-009 (S4) | Message orienté utilisateur (« Fonction indisponible sur cette instance, contactez votre administrateur »). | `shell/src/i18n/catalog.fr.ts:527` | XS | — | `bug(`→`test(` : j06-009 — `j06/etl-disabled-ui.spec.ts` |

#### P35 — Catalogue public, SEO et parcours lecteur

- Portée : Aucun catalogue anonyme côté shell, lecteur routé vers les éditeurs, SEO incomplet, pertinence de recherche.
- Revue : shell + cœur public ; niveau 3 ; dépend de : P07, P12, P24.
- Critères de clôture du paquet, en plus des tâches : seuil de taille de bundle respecté (t03-006 : 0,1 Ko de marge).

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P35.01 | **j01-001** (S2) | Une page de catalogue publique (items publiés, tri/tag/type) accessible sans connexion, alimentée par /v1/public/items. | `shell/src/shell/routes.tsx:251-253`, `core/app/public/routes.py:50-64` | L | P07.01, P24.05 | `bug(`→`test(` : j01-001 — `j01/anonymous.spec.ts` |
| P35.02 | **j02-008** (S2) | Un lecteur (write=false) ouvre l'app/dashboard en mode usage et une carte dans un visualiseur sans panneaux d'édition ; | `shell/src/shell/useOpenItem.ts:81-87`, `shell/src/pages/ItemDetailPage.tsx:111-127` | M | — | `bug(`→`test(` : j02-008 — `j02/reader-ui.spec.ts` |
| P35.03 | j01-002 (S3) | La page introuvable pose <meta name=robots content=noindex> (et un titre explicite) pour ne pas être indexée. | `shell/src/pages/SitePublicPage.tsx:43-51`, `shell/src/pages/PublicItemPage.tsx:41-49` | XS | — | `bug(`→`test(` : j01-002 — `j01/anonymous.spec.ts` |
| P35.04 | j01-003 (S3) | Titre, description et canonical dérivés de la collection (title/description) sur la fiche dataset publique. | `shell/src/pages/DatasetPage.tsx:54-100` | S | — | `bug(`→`test(` : j01-003 — `j01/anonymous.spec.ts` |
| P35.05 | j01-006 (S4) | HEAD répond 200 (certains crawlers/validateurs sondent en HEAD). | `core/app/public/routes.py:87-104` | XS | — | `bug(`→`test(` : j01-006 — `j01/anonymous.spec.ts` |
| P35.06 | j01-007 (S3) | Le sitemap couvre toutes les pages publiques indexables (sites, items publiés, datasets publics) avec lastmod. | `core/app/public/routes.py:26-32`, `core/app/public/routes.py:87-94` | S | — | repro inversé : `Lire core/app/public/routes.py : list_published_items(resource_type='site')` |
| P35.07 | j01-008 (S3) | Aperçu complet (og:url, og:type, og:image, twitter:card, contenu texte) et routage bots étendu aux pages publiques d'items et de datasets. | `core/app/public/routes.py:35-48`, `docker-compose.yml:420` | M | — | repro inversé : `Lire _render_social_preview_html et la règle traefik seo-bots` |
| P35.08 | j02-007 (S3) | La fiche dataset présente les métadonnées ouvertes (licence, mots-clés, colonnes, volume, emprise) et un accès lecture/téléchargement selon les droit… | `shell/src/pages/ItemDetailPage.tsx:106-127` | M | — | `bug(`→`test(` : j02-007 — `j02/reader-ui.spec.ts` |
| P35.09 | j02-011 (S3) | Le bouton n'est pas proposé (ou explique le droit manquant) à qui ne peut pas créer de bookmark. | `shell/src/pages/AppRuntimePage.tsx:165-186`, `core/app/roles/privileges.py:85-97` | XS | P12.10 | `bug(`→`test(` : j02-011 — `j02/reader-ui.spec.ts` |
| P35.10 | j02-012 (S3) | Une requête sans correspondance affiche l'état « Aucun résultat ». | `core/app/search/ranking.py:56-66` | S | — | `bug(`→`test(` : j02-012 — `j02/reader-ui.spec.ts` |
| P35.11 | j10-005 (S3) | Un site publié affiche son URL publique copiable et son slug est éditable avec les mêmes erreurs 409/422 que la création. | `shell/src/pages/ItemDetailPage.tsx:96-124`, `shell/src/ui/kit/MetadataForm.tsx:10-40` | S | — | `bug(`→`test(` : j10-005 — `j10/site-public-ui.spec.ts` |
| P35.12 | j10-003 (S3) | Les vignettes d'items publiés s'affichent pour un visiteur anonyme (URL absolue du cœur, route publique lisible sans jeton pour les items publiés) et… | `core/app/items/repository.py:143`, `shell/src/builder/widgets/gallery.tsx:125-127`, `shell/src/ui/kit/ItemCard.tsx:24-30`, `core/app/items/routes.py:209-223` | S | — | `bug(`→`test(` : j10-003 — `j10/site-public-ui.spec.ts` |

#### P36 — Documentation

- Portée : CLAUDE.md contredit le backlog et le dépôt (c07) ; allowlist du copilote mal décrite.
- Revue : doc ; niveau 1 ; dépend de : —.
- Critères de clôture du paquet, en plus des tâches : `scripts/check_claude_md_size.py` vert.

| Tâche | Findings | Cible | Fichiers | Effort | Dépend de | Acceptation |
|---|---|---|---|---|---|---|
| P36.01 | c07-001 (S3), c07-002 (S3), c07-003 (S3), c07-004 (S3), c07-005 (S4), c07-006 (S4), c07-007 (S4), c07-008 (S4) | Corriger CLAUDE.md contre le backlog et le dépôt (un seul commit) | `CLAUDE.md:667-669`, `core/app/mcp/tools/configs.py:167-190`, `CLAUDE.md:670-671`, `CLAUDE.md:688-690` (+10) | XS | — | repro inversé : `sed -n 167,190p core/app/mcp/tools/configs.py; sed -n 667,669p CLAUDE.md` |
| P36.02 | j11-014 (S4) | Documentation alignée sur les 8 outils réels. | `core/app/copilot/tools_allowlist.py:14-25` | XS | — | repro inversé : `grep -n 'allowlist' CLAUDE.md ; sed -n 14,25p core/app/copilot/tools_allowlist.py` |

### 6.3 Contrôle de couverture (script)

- ids de `merged.jsonl` : 447 ; affectés à une tâche : 429 ; rejetés avec motif : 18 ; non couverts : **0** ; doublons : **0**.
- S1/S2 : 127 dans `merged.jsonl`, 123 affectés, 4 rejetés (d01-001, d01-003, d01-004, j01-004) — table §7.
- Dépendances : graphe de paquets acyclique (3 niveaux) ; les `depends_on` pointant vers un id fusionné sont résolus vers le finding qui l'absorbe.

### 6.4 Rejets motivés

| Finding | Sév. | Motif |
|---|---|---|
| d01-001 | S2 | fonctionnalité nouvelle (op de pipeline client MCP tiers), pas un défaut : à instruire comme SP de feuille de route (OperationContract + garde d'egress) |
| d01-002 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-003 | S2 | app mobile / hors ligne = question produit ouverte Q11 (`REV-120`, GAP-26) ; aucun arbitrage §8 ne l'ouvre |
| d01-004 | S2 | co-édition = question produit ouverte Q10 (GAP-20) ; la protection contre l'écrasement est la tâche de j04-008 (P09) |
| d01-005 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-006 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-007 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-008 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-009 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-010 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-011 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-012 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-013 | S4 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| d01-014 | S3 | écart de benchmark = fonctionnalité nouvelle, pas un défaut : à arbitrer dans la feuille de route, hors plan correctif |
| j01-004 | S2 | non reproduit par v01 ; artefact de `stack-reset.sh` corrigé dans l'outillage (`scripts/audit/stack-reset.sh:89`) |
| j06-010 | S3 | réfuté par t01b : « Automatisation » n'est plus un `<span aria-disabled>` (test de régression qui passe) |
| j08-017 | S3 | angle mort d'audit levé par la passe flags (j08b a testé les quotas) ; périmètre réel porté par RC-12 (P26) |
| j10-011 | S3 | angle mort d'audit levé par la passe flags (`enable-flags.sh`) ; ses constats sont portés par les findings j10b |

## 7. Table de traçabilité S1/S2 (127)

V = verdict (C = confirmé par v01, NR = non reproduit par v01, A = `verified`
par la passe flags, non rejoué par v01, — = `probable`, non rejoué).
Vérification par script : ids S1/S2 de `merged.jsonl` ⊆ ids de cette table
(127/127, 0 manquant) ; chaque id affecté pointe vers une tâche existante et son paquet.

| Finding | Sév. | Type | Parcours | V | Tâche | Paquet |
|---|---|---|---|---|---|---|
| c02-003 | S1 | bug | harvest | C | P02.01 | P02 |
| c06-004 | S1 | bug | transverse | — | P08.01 | P08 |
| j02-002 | S1 | bug | pieces-jointes | C | P03.01 | P03 |
| j03-001 | S1 | bug | j03 | C | P01.01 | P01 |
| j05-001 | S1 | bug | sql-lab | C | P05.01 | P05 |
| j05b-002 | S1 | bug | requete-visuelle | A | P10.04 | P10 |
| j05b-005 | S1 | bug | export | A | P01.01 | P01 |
| j06b-001 | S1 | bug | j06 | A | P01.01 | P01 |
| j06b-005 | S1 | bug | j06 | A | P02.04 | P02 |
| j10b-010 | S1 | bug | export-apps | A | P11.01 | P11 |
| j10b-011 | S1 | bug | export-apps | A | P11.02 | P11 |
| j11-007 | S1 | bug | transverse | C | P07.01 | P07 |
| j12-001 | S1 | bug | transverse | C | P04.01 | P04 |
| c01-001 | S2 | security | transverse | C | P15.01 | P15 |
| c01-002 | S2 | security | transverse | C | P12.01 | P12 |
| c01-003 | S2 | security | transverse | — | P16.01 | P16 |
| c01-004 | S2 | bug | transverse | — | P15.02 | P15 |
| c02-001 | S2 | bug | transverse | C | P09.01 | P09 |
| c02-002 | S2 | bug | transverse | C | P09.02 | P09 |
| c02-004 | S2 | bug | compliance | C | P02.02 | P02 |
| c02-005 | S2 | bug | pipelines | C | P01.03 | P01 |
| c02-009 | S2 | perf | mcp | C | P23.01 | P23 |
| c03-001 | S2 | bug | transverse | C | P09.03 | P09 |
| c03-002 | S2 | security | transverse | C | P12.02 | P12 |
| c03-003 | S2 | gap | transverse | — | P18.01 | P18 |
| c03-004 | S2 | perf | transverse | C | P24.01 | P24 |
| c03-005 | S2 | perf | transverse | C | P24.02 | P24 |
| c05-001 | S2 | test-gap | transverse | C | P27.01 | P27 |
| c06-001 | S2 | bug | transverse | C | P08.02 | P08 |
| c06-002 | S2 | bug | transverse | — | P27.07 | P27 |
| c06-003 | S2 | gap | transverse | C | P27.08 | P27 |
| c06-005 | S2 | bug | transverse | — | P08.03 | P08 |
| c06-009 | S2 | debt | transverse | — | P27.11 | P27 |
| c08-002 | S2 | gap | transverse | C | P21.01 | P21 |
| c08-004 | S2 | gap | transverse | C | P21.02 | P21 |
| c09-001 | S2 | perf | transverse | C | P02.03 | P02 |
| c09-003 | S2 | perf | transverse | — | P24.06 | P24 |
| c09-004 | S2 | perf | transverse | — | P24.03 | P24 |
| c09-006 | S2 | perf | transverse | C | P24.05 | P24 |
| c09-008 | S2 | perf | transverse | C | P25.01 | P25 |
| c09-009 | S2 | perf | transverse | — | P25.02 | P25 |
| d01-001 | S2 | gap | transverse | — | **Rejet motivé** : fonctionnalité nouvelle (op de pipeline client MCP tiers), pas un défaut : à instruire comme SP de feuille de route (OperationContract + garde d'egress) | — |
| d01-003 | S2 | gap | transverse | — | **Rejet motivé** : app mobile / hors ligne = question produit ouverte Q11 (`REV-120`, GAP-26) ; aucun arbitrage §8 ne l'ouvre | — |
| d01-004 | S2 | gap | transverse | — | **Rejet motivé** : co-édition = question produit ouverte Q10 (GAP-20) ; la protection contre l'écrasement est la tâche de j04-008 (P09) | — |
| j01-001 | S2 | gap | catalogue-public | C | P35.01 | P35 |
| j01-004 | S2 | debt | transverse | NR | **Rejet motivé** : non reproduit par v01 ; artefact de `stack-reset.sh` corrigé dans l'outillage (`scripts/audit/stack-reset.sh:89`) | — |
| j02-001 | S2 | security | droits-lecteur | C | P13.01 | P13 |
| j02-003 | S2 | bug | donnees | C | P10.04 | P10 |
| j02-004 | S2 | bug | connexion-oidc | C | P07.02 | P07 |
| j02-008 | S2 | gap | catalogue-lecteur | C | P35.02 | P35 |
| j02-009 | S2 | bug | carte-lecture | C | P31.01 | P31 |
| j02-010 | S2 | bug | liens-directs | C | P07.03 | P07 |
| j03-003 | S2 | bug | j03 | C | P01.04 | P01 |
| j03-008 | S2 | bug | j03 | C | P29.01 | P29 |
| j03-011 | S2 | bug | j03 | C | P21.03 | P21 |
| j03-012 | S2 | gap | j03 | C | P14.04 | P14 |
| j03-013 | S2 | bug | j03 | C | P29.02 | P29 |
| j03-018 | S2 | debt | j03 | — | P01.02 | P01 |
| j04-001 | S2 | bug | j04 | C | P10.01 | P10 |
| j04-003 | S2 | bug | j04 | C | P09.06 | P09 |
| j04-008 | S2 | bug | j04 | C | P09.04 | P09 |
| j04-010 | S2 | bug | j04 | C | P10.02 | P10 |
| j04-011 | S2 | bug | j04 | C | P10.03 | P10 |
| j05-002 | S2 | bug | analytics-aggregate | C | P05.01 | P05 |
| j05-009 | S2 | security | exports | C | P13.04 | P13 |
| j05b-001 | S2 | bug | requete-visuelle | A | P01.08 | P01 |
| j05b-004 | S2 | bug | requete-visuelle | A | P05.01 | P05 |
| j05b-008 | S2 | bug | export | A | P06.01 | P06 |
| j06-001 | S2 | test-gap | transverse | C | P02.06 | P02 |
| j06-002 | S2 | bug | pipeline-builder | C | P18.02 | P18 |
| j06-014 | S2 | perf | connecteurs-erreurs | — | P16.03 | P16 |
| j06b-002 | S2 | bug | j06 | A | P05.01 | P05 |
| j06b-003 | S2 | bug | j06 | A | P03.02 | P03 |
| j06b-004 | S2 | security | j06 | A | P03.03 | P03 |
| j06b-010 | S2 | security | j06 | A | P16.02 | P16 |
| j07-002 | S2 | bug | j07 | C | P01.01 | P01 |
| j07-003 | S2 | bug | j07 | C | P19.01 | P19 |
| j07-006 | S2 | bug | j07 | C | P19.02 | P19 |
| j07-008 | S2 | bug | j07 | C | P19.03 | P19 |
| j07-017 | S2 | bug | j07 | C | P19.04 | P19 |
| j08-001 | S2 | security | rgpd-anonymisation | C | P12.03 | P12 |
| j08-002 | S2 | bug | rgpd-anonymisation | C | P12.04 | P12 |
| j08b-001 | S2 | bug | quotas | A | P26.01 | P26 |
| j08b-003 | S2 | bug | quotas | A | P26.02 | P26 |
| j08b-010 | S2 | bug | quotas | A | P26.03 | P26 |
| j09-001 | S2 | bug | alertes | C | P01.01 | P01 |
| j09-003 | S2 | gap | alertes | C | P20.01 | P20 |
| j09-013 | S2 | bug | alertes | C | P20.02 | P20 |
| j09b-004 | S2 | bug | alertes webhook | A | P20.03 | P20 |
| j09b-006 | S2 | security | alertes email | A | P16.08 | P16 |
| j09b-007 | S2 | security | passerelle Grafana | A | P17.01 | P17 |
| j09b-010 | S2 | bug | reprise de jobs | A | P01.04 | P01 |
| j09b-011 | S2 | bug | rapports planifiés | A | P03.04 | P03 |
| j10-001 | S2 | security | sites | C | P13.02 | P13 |
| j10-007 | S2 | security | export-apps | C | P15.03 | P15 |
| j10b-001 | S2 | bug | export-apps | A | P01.01 | P01 |
| j10b-008 | S2 | bug | export-apps | A | P03.04 | P03 |
| j10b-012 | S2 | bug | tiles3d | A | P03.01 | P03 |
| j11-005 | S2 | bug | transverse | C | P23.11 | P23 |
| j11-009 | S2 | bug | transverse | — | P07.04 | P07 |
| j11-015 | S2 | test-gap | transverse | C | P07.05 | P07 |
| j12-002 | S2 | bug | transverse | C | P31.02 | P31 |
| j12-003 | S2 | bug | transverse | C | P31.03 | P31 |
| j12-005 | S2 | a11y | transverse | C | P31.05 | P31 |
| j12-009 | S2 | bug | transverse | C | P31.06 | P31 |
| j13-001 | S2 | bug | partage-liens | C | P08.06 | P08 |
| j13-002 | S2 | security | partage-roles | C | P14.01 | P14 |
| j13-004 | S2 | gap | partage-groupes | C | P14.02 | P14 |
| j13-008 | S2 | gap | partage-donnees | C | P14.03 | P14 |
| t01-004 | S2 | a11y | transverse | C | P33.01 | P33 |
| t01-005 | S2 | a11y | transverse | C | P33.02 | P33 |
| t01-006 | S2 | a11y | transverse | C | P33.03 | P33 |
| t01-009 | S2 | a11y | catalogue | C | P33.04 | P33 |
| t01b-001 | S2 | a11y | pipelines | A | P32.01 | P32 |
| t01b-007 | S2 | a11y | pipelines | A | P32.03 | P32 |
| t01b-008 | S2 | bug | pipelines | A | P32.02 | P32 |
| t02-003 | S2 | bug | transverse | C | P09.05 | P09 |
| t02-004 | S2 | bug | transverse | C | P01.01 | P01 |
| t02-005 | S2 | security | admin-collections | C | P13.03 | P13 |
| t03-005 | S2 | perf | catalogue | C | P04.06 | P04 |
| t03-007 | S2 | bug | catalogue-public | — | P29.03 | P29 |
| t03-008 | S2 | gap | catalogue-public | C | P29.04 | P29 |
| t03-011 | S2 | bug | apps | C | P29.05 | P29 |
| t03-012 | S2 | bug | cartographie | C | P30.01 | P30 |
| t03b-001 | S2 | perf | pipeline-etl | A | P18.03 | P18 |
| t03b-002 | S2 | perf | pipeline-etl | A | P02.03 | P02 |
| t03b-006 | S2 | bug | quotas | A | P26.04 | P26 |

Bilan : 123 S1/S2 affectés, 4 rejets motivés.
Les 17 `probable` seront confirmés ou infirmés par le test d'acceptation de
leur tâche avant correction ; les 30 « A » gagneraient un rejeu v01 (§5.3).

## 8. Rejeu

Protocole complet : **`docs/revue/audit-2026-09-29/REJEU.md`** (pré-requis
`enable-flags.sh` → `seed-personas.sh` → `stack-reset.sh snapshot`, lanceur
`scripts/audit/run-suite.sh`, voies `parallel`/`serial`).

**Test d'acceptation commun à toutes les tâches** :
1. **Avant correctif** : `scripts/audit/run-suite.sh --verify --only "<dossiers>"`
   fait **échouer** les tests de la tâche (preuve du bug sur la stack du jour ;
   un test qui passe déjà signale un finding périmé, à reclasser avant de coder).
2. **Après correctif** : les mêmes tests **passent** ; on remplace alors `bug(`
   par `test(` (ou `fixme(` par `test(` dans `j04/`, dont le helper s'appelle
   `fixme`) : ils rejoignent la suite de non-régression de l'audit.
3. Les contournements de `REJEU.md` qui masquent le bug traité sont retirés
   dans la même tâche (`stubMap` → P04.01, défèrement manuel → P01.01,
   `ALTER TABLE … SET DEFAULT` → P10.04, second cœur `:8201` → P26,
   `ensure_uploads_bucket` neutralisé → P03.01), puis le dossier concerné est
   relancé **sans** contournement.
4. S'y ajoutent le test pérenne dans `core/tests/` ou `shell/e2e/` et les
   critères de clôture du paquet (§6.2).

Dossiers de parcours à relancer par paquet (tests `bug()`/`fixme()` présents
dans `shell/e2e/journeys/`, relevés par script ; le détail par tâche est dans
la colonne « Acceptation » du §6.2) :

| Paquet | Tâches avec test de parcours | Dossiers à relancer (`--only`) | Tâches acceptées par `repro` seul |
|---|---|---|---|
| P01 | 5/8 | j03 j05b j06b j07 j09 j09b j10b j11 t02 | P01.02, P01.05, P01.06 |
| P02 | 3/6 | j06b j07 j09b t03b | P02.02, P02.05, P02.06 |
| P03 | 4/7 | j02 j03 j06b j09b j10b | P03.05, P03.06, P03.07 |
| P04 | 6/7 | j12 t03 | P04.07 |
| P05 | 2/2 | j05 j05b j06b | — |
| P06 | 2/4 | j05b j09b | P06.01, P06.04 |
| P07 | 5/8 | j02 j05 j11 t02 | P07.04, P07.05, P07.08 |
| P08 | 1/8 | j13 | P08.01, P08.02, P08.03, P08.04, P08.05, P08.07, P08.08 |
| P09 | 6/10 | j03 j04 j13 t02 | P09.01, P09.03, P09.09, P09.10 |
| P10 | 13/16 | j02 j04 j05b j10 j12 t01 t02 | P10.11, P10.12, P10.13 |
| P11 | 6/7 | j10b | P11.03 |
| P12 | 10/16 | j05 j08 j08b | P12.02, P12.08, P12.09, P12.10, P12.11, P12.15 |
| P13 | 8/11 | j02 j03 j05 j06b j10 t02 | P13.06, P13.08, P13.09 |
| P14 | 8/14 | j03 j13 | P14.06, P14.10, P14.11, P14.12, P14.13, P14.14 |
| P15 | 3/5 | j07 j10 j10b | P15.01, P15.02 |
| P16 | 7/8 | j06 j06b j09b | P16.03 |
| P17 | 7/8 | j08b j09 j09b t01b | P17.08 |
| P18 | 6/12 | j06 j06b t03b | P18.01, P18.04, P18.05, P18.09, P18.10, P18.12 |
| P19 | 15/16 | j07 | P19.16 |
| P20 | 12/15 | j02 j09 j09b | P20.09, P20.12, P20.15 |
| P21 | 6/9 | j01 j03 j04 j08 j09 | P21.01, P21.02, P21.08 |
| P22 | 6/11 | t02 t04 | P22.01, P22.02, P22.03, P22.04, P22.05 |
| P23 | 6/16 | j11 | P23.01, P23.02, P23.03, P23.04, P23.05, P23.06, P23.07, P23.14, P23.15, P23.16 |
| P24 | 0/9 | — | P24.01, P24.02, P24.03, P24.04, P24.05, P24.06, P24.07, P24.08, P24.09 |
| P25 | 12/16 | j05 j05b t03b | P25.01, P25.02, P25.03, P25.04 |
| P26 | 8/9 | j08b t03b | P26.09 |
| P27 | 0/14 | — | P27.01, P27.02, P27.03, P27.04, P27.05, P27.06, P27.07, P27.08, P27.09, P27.10, P27.11, P27.12, P27.13, P27.14 |
| P28 | 8/10 | j03 t02 | P28.07, P28.08 |
| P29 | 9/9 | j03 j09 t03 t03b | — |
| P30 | 2/5 | t03 t04 | P30.02, P30.03, P30.04 |
| P31 | 11/15 | j02 j03 j12 | P31.12, P31.13, P31.14, P31.15 |
| P32 | 9/10 | t01b | P32.10 |
| P33 | 26/27 | j03 t01 t01b | P33.20 |
| P34 | 19/24 | j06 t04 | P34.19, P34.20, P34.21, P34.22, P34.23 |
| P35 | 10/12 | j01 j02 j10 | P35.06, P35.07 |
| P36 | 0/2 | — | P36.01, P36.02 |

Couverture : 261 des 386 tâches ont au moins un test de parcours ;
93 des 123 S1/S2 affectés relèvent d'une tâche qui en a un. Les autres
sont des constats de code, de migration, de CI ou de performance backend
(dossiers `c0x`) et j05b-008 (relevé par `docker inspect`) : leur acceptation
est le `repro` inversé.

## 9. Suites à donner hors tâches

- **À la clôture de chaque paquet** (CLAUDE.md § Comment on travaille) : ligne
  `### Livré`, historique continu, état des `GAP-nn` et `REV-nnn` cités par ses
  findings (champ `related_gap` ; par paquet : P01 REV-095 ; P03 REV-010, REV-194 ; P07 REV-003 ; P08 GAP-12 ; P09 GAP-22 ; P10 GAP-66 ; P11 GAP-14 ; P12 REV-203 ; P13 GAP-22, GAP-72, REV-009 ; P14 GAP-19, GAP-42, GAP-65, REV-009 ; P15 GAP-22 ; P16 REV-097, REV-197 ; P17 GAP-72 ; P19 GAP-62 ; P20 REV-008 ; P21 GAP-38, REV-174 ; P22 REV-053 ; P23 GAP-47, REV-096 ; P24 GAP-56, GAP-63, GAP-64, GAP-71 ; P25 REV-248 ; P26 GAP-73 ; P28 GAP-29 ; P33 GAP-05, REV-088, REV-176, REV-178 ; P35 GAP-05, GAP-07 ; P36 REV-108, REV-174, REV-175, REV-178),
  inventaire de fonctionnalités et bilan régénéré, OpenAPI + types TS.
- Les tests d'audit `shell/e2e/journeys/` ne tournent pas en CI : la condition
  de sortie de chaque tâche inclut un test pérenne dans `core/tests/` ou
  `shell/e2e/`, et P27 ajoute un job « stack composée » minimal.
- Rejouer v01 sur les 30 S1/S2 « A » et lancer les passes restantes du §5.3
  (LLM fake, observabilité, connecteurs externes, PDF/`ReportSchedule`,
  terrain 3D) dès que leurs paquets bloquants sont fusionnés.
- Les 14 rejets du §6.4 issus du benchmark (d01) sont à instruire dans la
  feuille de route, pas dans ce plan correctif.
