# Backlog — Plan A : lots L0 (clôtures), L2 (sécurité/intégrité), L3 (pipelines)

**Date :** 2026-10-03. **Source :** `docs/revue/2026-09-04-backlog.md`. Chaque affirmation
ci-dessous a été revérifiée dans le code le 2026-10-03 (piège n°12) ; les écarts avec le
backlog sont signalés. Un plan unique (`docs/superpowers/plans/2026-10-03-backlog-lots-l0-l2-l3.md`)
en découle. Les sous-points « rejeu sur stack réelle » sont **hors périmètre** (lot L6).

REV couvertes : 111, 116, 187, 188, 239 (L0) ; 185, 186, 197, 269, 271, 272, 273, 290 (L2) ;
195, 196, 198, 199, 275 (L3).

## L0 — Clôtures documentaires (aucun code)

| REV | Écriture à faire |
|---|---|
| 111 | État → fermé par SP-62 ; aligner la section détail de GAP-17 dans `analyse-gaps.md` (encore décrite ouverte). |
| 116 | État → fermé (GAP-22, 2026-09-13 ; bypass pipelines/exports P15 le 2026-10-02) ; renvoi 185/186/187/188/270 ; aligner `analyse-gaps.md` (détail ~l.290, répartition ~l.436). |
| 187, 188 | Reclasser **observation** (limites de conception assumées, spec GAP-22 §1.5/§4). |
| 239 | Fermé pour D56 au niveau « historique local relisible » (`shell/src/lib/copilotHistory.ts`, `CopilotPanel.tsx`) ; reste éventuelle persistance serveur → observation sauf demande produit. Noter dans `docs/revue/2026-09-24-diagnostic-ui-ux.md` (D56). |

Recompter mécaniquement le sommaire du backlog (fermées/ouvertes) en fin de lot.

## L2 — Sécurité et intégrité

### REV-185 — `can_manage_collections` sur les routes features (lecture seule)
`core/app/features/routes.py` appelle `get_readable_collection()` sans
`can_manage_collections=has_privilege(user, Privilege.ADMIN_COLLECTIONS_MANAGE)` aux lignes
219, 281, 336, 410, 556 (lecture). **Décision : lecture seulement** — `_get_writable` (l.568)
inchangé. Jumelles à traiter dans le même geste (piège n°14) : `features/tiles.py`,
`app/attachments`, outils MCP `query_features`/`run_analytics_query`, `analytics/sql`,
`alerts/jobs._measure_value` — tous passent par le même helper ; auditer chacun et aligner
REST/MCP. Tests : privilège seul (non propriétaire, collection privée) → 200 sur items,
agrégat, 2 exports, feature unitaire ; sans privilège → 404.

### REV-186 — `apply_collection_ddl` ne doit pas coder `[]` en dur
`core/app/collections/ddl.py:147` passe `[]` à `sync_masked_role_grants`. Ajouter un paramètre
`sensitive_fields` (défaut vide) transmis à la synchro ; les appelants (`collections/routes.py:184`,
`ingestion/importer.py:316`, `provisioning.py`) restent inchangés (aucun ne ré-applique sur une
collection sensible). Test postgis : `sensitive_fields=["x"]`, ré-application de la DDL,
`gis_rls_masked` n'a toujours pas SELECT sur `x`.

### REV-197 — scoping réel du secret blob (décision : vrai scoping)
`connector_runtime.py:599` dérive `bucket_url` de `params.path`. Ajouter `bucketUrl` aux 3
payloads blob de `core/app/secrets/schemas.py` (s3/azure/gcs) ; exiger que `params.path` ait ce
préfixe, sinon `ConnectorRuntimeError`. **Compatibilité :** un secret blob existant sans
`bucketUrl` reste lisible mais l'exécution échoue avec un message explicite demandant de le
renseigner (pas de migration silencieuse). Retombées : formulaire de secret côté shell,
OpenAPI + types TS à régénérer, docstring de `ReaderConnectorBlobParams` et ligne CLAUDE.md
(« jamais un upload ni une URL arbitraire ») alignés. Tests : chemin hors bucket refusé,
nominal OK, secret sans `bucketUrl` → erreur claire. Jumelles : vérifier que les autres
`materialize_*_connector` lient bien endpoint/DSN au secret.

### REV-290 — `authFetch` ne doit jamais porter le jeton hors du cœur (décision : lever)
`shell/src/api/base.ts:328`. Remonter `isCoreServed` avant `authFetch` (gérer les URL relatives
via `new URL(url, coreUrl)`) et **lever** si l'URL n'est pas servie par le cœur. Seul `fetchUrl`
(`base.ts:442`, URL issue d'une config) peut en pratique viser l'extérieur ; les autres
appelants (`base.ts` 467/488/515/532/547, `domains/features|exportsIngestion|layers|items|extensionsAdminTools`)
visent le cœur — la suite vitest **et** E2E (URL mockées possiblement différentes de `coreUrl`)
doit rester verte. Vérifier un par un les `fetch`/`authFetch` directs de `pages/*`,
`Tileset3DUploadButton`, `Terrain3DUploadButton`, `LayerPicker`, `form.tsx`, `embed/resolveShareLink.ts`.
Tests : `authFetch("https://evil.example/x")` lève et n'émet aucune requête.

### REV-271 — `If-Match` généralisé
Côté cœur c'est déjà garanti (`configs/routes.py:223,443` → `StaleConfigVersion`). À faire :
- **Shell** : lire `version` au chargement et envoyer `If-Match` (via `extraHeaders`) dans
  `domains/layers.ts:120` (cartes), `datasets.ts:250`, `pipelines.ts:73`, `reports.ts:63`,
  `alerts.ts:65`, sur le patron de `domains/apps.ts:110` + `baseVersionRef` de
  `AppBuilderPage` ; **UX de conflit 412 commune** réutilisée de l'App Builder (commit `5ed004d1`).
- **MCP** : `save_app_config` (`mcp/tools/configs.py:170-187`) gagne `expectedVersion` optionnel
  transmis à `update_config` ; vérifier que `get_app_config` renvoie la version.
- **Jumelles** : `rollback_config`, copilote. `pipelines/runtime.py:1087` = écrivain interne,
  exception documentée.
Tests : un 412 par éditeur (vitest) + MCP + cœur.

### REV-272 — reliquats techniques
- (b) `VITE_CORE_URL` relatif : `shell/src/config.ts:50` résout via `new URL(v, window.location.origin)`
  si la valeur commence par `/` ; jumelles `isCoreServed` (`base.ts:445`), URL de tuiles/MVT,
  `staticExport/entry.tsx`. Test vitest `loadConfig("/api")`.
- (c) Parcours E2E d'audit P14.14 : lien de partage à échéance courte rejoué en anonyme
  (nominal / expiré / révoqué) dans `shell/e2e/journeys/`.
- (a) Tombstone RGPD (`users/repository.py:15-20`, sha256 nu) : **bloqué par décision DPO**
  (colonne dédiée vs HMAC). Hors plan ; si HMAC retenu : clé dérivée de `CORE_SECRETS_MASTER_KEY`,
  tests ancien/nouveau hash.

### REV-273 — connecteurs (sous-points codables)
- (b) Lecteur blob sans plafond/délai (`materialize_blob_connector`) : plafond de fichiers,
  `resource.add_limit(_max_rows())`, plafond d'octets, timeouts fsspec ; test dépassement → `ConnectorRuntimeError`.
- (c) 409 de `delete_secret_unless_used` (`secrets/repository.py:119-122`) liste des titres sans
  `can()` : filtrer par `can(user,"read",item)` dans la route, afficher « N autres objets non visibles ».
- (d) TOCTOU DNS dans `pipelines/egress.py:49-71` : connexion à l'IP validée (Host/SNI préservés ;
  `hostaddr` pour les DSN) **dans la couche commune** — jumelles : LLM copilote, moissonnage,
  webhooks `alerts/notify.py`, endpoint S3. Test : double résolveur public puis 127.0.0.1 → refus.
- (e) STARTTLS (`alerts/notify.py:129-132`) : refuser `useTls=False` hors localhost, `SMTP_SSL`
  sur le port 465, validation dès la création du secret (`secrets/schemas.py`) ; secrets existants
  `useTls=False` : message explicite, pas de bascule silencieuse.
- (a) rejeu j06-004 → L6.

### REV-269 — actions hors code (checklist, pas de tâche TDD)
Protection de `main` + checks requis (réglage GitHub) ; release `v0.1.1` (bump `GEOSTUDIO_VERSION`
dans `.env.example` et `geostudio_version` Ansible **avant** de tagger, sinon `verify-tag`
échoue ; `CHANGELOG.md` : minio/titiler, absents de `v0.1.0`) ; note de migration Keycloak
(politique Trusted Hosts du DCR sur instances existantes) ; hôtes MCP = décision produit (L1).
Le tag et les réglages GitHub sont **proposés à Tanguy, jamais exécutés sans demande**.

## L3 — Pipelines

### REV-195 — `groupBy` optionnel
`ops/execute.py:44-58, 75-86`. Champ `groupBy: list[str] = []` sur `TransformTriangulateParams`
et `TransformMinimumBoundingCircleParams` (`ops/schemas.py`) ; vide = comportement global actuel.
Helper `_group_frames(df, group_by)` (`groupby(dropna=False, sort=False)`), logique actuelle
extraite en `_one(frame)`, résultats concaténés ; colonnes de groupe conservées ; colonne
absente → `PipelineRuntimeError`. Signature d'`execute` inchangée → `OPERATIONS`/`OP_PARAMS`
intacts. Tests : 2 groupes → 2 cercles, triangulation sans pontage inter-groupes (remplace le
test de pontage de la Task 24) ; maj des lignes de `docs/revue/matrice-couverture-fme.jsonl` ;
OpenAPI + types TS à régénérer.

### REV-196 — entrées dégénérées
En tête de `_read_geometry_rows` : filtrer `geometry IS NOT NULL` (en SQL, règle aussi `densify`) ;
court-circuit sur DataFrame vide (piège `BinderException` sur colonne `object` vide : créer la
table via `… WHERE false` / caster en `bytes`) ; `triangulate` sur non-point →
`PipelineRuntimeError` (import local, circularité). Tests : les 5 lignes du tableau du backlog +
test de route `preview_pipeline_route` → 400 (pas 500). Vérifier la jumelle `_write_geometry_rows`
avec NULL après `segmentize`.

### REV-198 — tables parallèles
Dériver `_JOIN_PARAM_MODELS = {op: OP_PARAMS[op] for op in BINARY_OPS}` (supprime la table) ;
test : `BINARY_OPS <= {k | _COLLECTION_PARAM_FIELD[k] == "withCollectionId"}` (l'égalité stricte du
backlog est fausse : `_COLLECTION_PARAM_FIELD` contient aussi reader/writer).

### REV-199 — 12 Minor (état réel + décision)
M1 renommer 4 tests `…fifty_one…` ; M2 réécrire le commentaire « décision ouverte de Task 27 » ;
M3 retirer `qgis-worker` de `.env.example:384` (vérifier `geostudio-titiler`) ; M4 retirer
`core-qgis`/`run-qgis-tests.sh` de `deploy/postgis/Dockerfile:25-26` ; M5 réécrire 3 commentaires
périmés (`deploy/oci/ansible/group_vars/all.yml:4,10`, `terrain3d/jobs.py:31`) — **ne pas toucher
« 9 images »** de `_build-and-push.yml` (correct depuis MinIO) ; **M6 supprimer**
`scripts/generate_qgis_worker_allowlist.py` et `generate_qgis_algorithm_schemas.py` (vérifier
qu'aucun test/pre-commit ne les référence) ; M7 non corrigeable (historique) → noté ;
M8 ajouter `### Added` sous `[Unreleased]` du `CHANGELOG.md` (comptes à relire dans le code) ;
**M9 `engine="shapely"`** pour les 3 op (vérifier les consommateurs de `.engine`) ;
M10 garde `__post_init__` (transform : pas les deux à la fois, ni aucun si faisable — vérifier
d'abord les 45 transforms, repli « pas les deux ») ; **M11 figer le produit cartésien** de
`snapToLayer` (`compiler.py:772-776`) par un test, pas de changement SQL ; **M12** lever une erreur
si 0 ligne chargée avec glob littéral (`connector_runtime.py:652-655`) + test.

### REV-275 — reliquats P18
- (c) `mark_running` conditionnel (`repository.py:103-113`) : `WHERE status IN ('queued','pending')`,
  retour `bool`, sortie sans exécution si faux ; adapter le Protocol `RunTracker` + `PostgresRunTracker`
  (`jobs.py:153,181`) + test de seam ; `routes.py:130` : `cancel` répété sur `cancel_requested`/`cancelled`
  → 200 idempotent. Export/fichier restent non interruptibles (documenté).
- (d) `mem_limit: ${WORKER_MEM_LIMIT:-2g}` sur le service `worker` + documentée dans `.env.example`
  (règle `test_deployability`).
- (e) Jumelles à jeton : `GET /v1/share-links/{token}` hors limiteur → groupe `share-link`
  (60/min) dans `route_group`, **clé IP seule** (le chemin contient le jeton) ; test 61e requête
  avec jetons différents → 429. Constat à porter : `ProxyHeadersMiddleware(trusted_hosts="*")`
  rend la clé IP falsifiable — restreindre au réseau Traefik = décision de déploiement, notée en L1.
- (a)(b) rejeu `j06b` + bascule `bug(`→`test(` → L6 (ne pas basculer sans rejeu).

## Transverse
Régénérer OpenAPI + types TS (REV-195, 197, 271 MCP éventuel) ; inventaire de fonctionnalités et
bilan (`feature_health_cli.py --write`) si surface nouvelle ; `lint-imports` ; `CLAUDE.md` §Livré
(une ligne) + archive d'exécution à la clôture ; ledger `.superpowers/sdd/backlogA-*`.

## Hors périmètre
L1 (décisions produit), L6 (rejeu stack réelle, mesures), REV-272(a) (DPO), REV-269 actions
GitHub/release (checklist seulement).
