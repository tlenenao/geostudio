# Vagues 4 à 6 — ARC-31 à ARC-35 + reliquat FME (rangs 1-8, 11, 15) — Plan d'exécution parallèle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal :** fermer tout ce qui reste de la feuille de route de rattrapage ArcGIS Enterprise (ARC-31, 32, 33, 34, 35) et le reliquat ETL du classement FME (§6 : rangs 1-8, 11, 15) pour atteindre l'ISO fonctionnel : ~187 j-h en 3 vagues de ≤ 4 voies.

**Sources de vérité :** `docs/revue/2026-10-11-comparatif-fme-arcgis-enterprise.md` §6 (rangs FME) et §6.1.2 (lignes ARC-31 à ARC-35 : livrable, critères, dépendances). Ce plan les ordonne, les répartit et fixe le protocole. Chaque critère d'acceptation est un test à écrire en premier (TDD). Protocole, pièges et fichiers réservés à l'intégration : identiques à `2026-10-12-arc-vague1-bloquants-collectivite.md`.

**Architecture :** une branche éphémère par voie (`arc4-lane-<x>`, worktree via `EnterWorktree`), fusionnée une à une dans `dev` par le contrôleur ; une tâche d'intégration par vague (seule à toucher aux fichiers partagés).

**Tech Stack :** FastAPI/SQLAlchemy/Alembic/pytest (`core/`), React/Vitest/Playwright (`shell/`), DuckDB (+ GDAL spatial), dlt, procrastinate, TiTiler/rasterio, Valhalla (service externe), Docker Compose/Helm.

## État vérifié dans le code (2026-10-13, piège n°12)

- **Livré** : ARC-01 à ARC-30 (vagues 0 à 3 ; restent ARC-31 à ARC-35). Rangs FME 9, 10, 12, 13, 14, 16 (HA documentée, ARC-18), 17 (ARC-24) = livrés par les ARC correspondants.
- **Absent** (grep `app/` vide) : `upsert`/mode de `writer.collection`, `quarantine`, paramètres de run, `incremental`, retry/reprise de run, `outbox`/webhooks sortants/déclencheurs fichier-S3, `transform.geocode`, `testFilter`/`sampler`/`sqlExecutor`/`neighborFinder`, vue d'impact (les occurrences de `lineage` sont du DCAT). Raster : TiTiler existe en compose mais non exposé ; aucun service worker dans `shell/`.
- **À vérifier à l'étape 0 de la voie M** : `reader.file` (`pipelines/ops/contracts.py:612`) existe ; la matrice FME compte encore 45 `planned_gdal` et 50 `planned_duckdb`.
- Tête Alembic : **0062** (à revérifier au départ).

## Global Constraints

- Arbitrages A1–A40 non rediscutés ; toute écriture passe par `can()` ; `tenant_id` + `audit_log` sur toute table/écriture ; `lint-imports` vert.
- Branche de promotion `dev` seulement ; commits conventionnels, petits, un sujet ; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` ; docs en français, code en anglais.
- TDD ; chaque fonctionnalité visible a sa spec E2E Playwright ; toute nouvelle surface (route REST, outil MCP, route shell) est inventoriée dans `docs/revue/inventaire-fonctionnalites.jsonl` (porte CI, intégration).
- Pièges : n°1 (OpenAPI/types), n°2 (compose par valeur), n°3 (vérifier chaque `fichier:ligne`), n°4 (revue par tâche **et** finale), n°5 (`toFrontLayer()`), n°8 (migration sur base non vide, deux sens), n°9 (ledgers `.superpowers/sdd/arc4-<voie>-*`), n°14 (commit puis defer → balayage de reprise ; jumelles de garde listées).
- Tout nouvel egress (webhook sortant, Valhalla, TiTiler, WFS) passe par la garde SSRF/egress existante (`net_pin.py`, `*/egress.py`).
- RLS, masquage de champs (GAP-22) et limites géographiques s'appliquent à **toute** nouvelle voie de lecture (raster par item, routage, webhooks, quarantaine).
- Pas de dépendance GPL/AGPL embarquée (précédent `transform.qgis`) ; licences vérifiées avant ajout (rasterio/GDAL BSD/MIT, Valhalla MIT).
- Ne jamais utiliser le `postgis-test` partagé pour un test destructif ; **≤ 4 worktrees/voies actives** (plafond RAM WSL2 ~12 Go, crash du 2026-09-06).

## ADR à écrire avant lancement (contrôleur)

- [ ] **ADR 0023 — Hors ligne (ARC-31)** : rouvre explicitement REV-120/Q11 (fermée par décision le 2026-10-10) ; périmètre = collecte de saisies seulement (pas d'édition générale), file d'écritures + `If-Match` (ARC-04), résolution de conflit côté utilisateur, cache de zone borné.
- [ ] **ADR 0024 — Raster (ARC-33)** : positionnement Q2 (horizontal), COG seul en entrée, proxy TiTiler authentifié par `can()` (jamais de route publique Martin/TiTiler), stockage S3.
- [ ] **ADR 0025 — Routage (ARC-34)** : Valhalla (MIT) en service externe sous egress, profil compose optionnel, pas de pgRouting (GPL-2) ; données OSM fournies par l'opérateur.
- [ ] **ADR 0026 — Temps réel (ARC-35)** : rouvre REV-114/Q10. **Recommandation : SSE minimal (notifications, alertes, rafraîchissement de widget), pas de clone de GeoEvent.** Si Tanguy ne valide pas, ARC-35 est clos « non cible » dans le comparatif et la voie R est supprimée.
- [ ] **ADR 0027 — Sortants et déclencheurs (rang 6)** : outbox transactionnelle, signature HMAC, egress gardé, déclencheur S3 par sondage (pas d'écoute d'événements MinIO exposée).

## Répartition en voies et vagues

| Vague | Voie | Chantiers (ordre) | Effort | Zone exclusive |
|---|---|---|---|---|
| 4 | **K1 — Écriture ETL** | F1 `writer.collection` upsert/update/delete → F2 port Rejected + quarantaine + rapport qualité | 16 j | `pipelines/ops/execute.py`, `pipelines/ops/contracts.py` (writer), `quality/`, `analytics/profile.py` (lecture) |
| 4 | **K2 — Cycle de vie des runs** | F3 paramètres de run → F5 retry/reprise par nœud → F4 incrémental dlt | 24 j | `pipelines/routes.py`, `jobs.py`, `repository.py`, `models.py`, `connector_runtime.py`, shell `/tasks` + pipeline builder |
| 4 | **L — Ouverture et gouvernance** | F6 webhooks sortants + déclencheurs fichier/S3 → F15 lineage/impact | 16 j | nouveau `core/app/outbox/`, `alerts/` (réutilisation de la livraison), nouveau `core/app/lineage/`, shell dialogues de suppression |
| 4 | **M — Opérateurs** | F11 `transform.geocode` → F7 readers GDAL vecteur → F8 familles Filtering/Database | 19 j | `pipelines/ops/` (nouveaux fichiers d'op : `ops/geocode.py`, `ops/filtering.py`, `ops/database.py`), `geocoding/` |
| 5 | **N — Raster** | ARC-33 | 30 j | nouveau `core/app/raster/`, `deploy/titiler`, `docker-compose.yml`, `deploy/helm/`, shell widget/couche raster |
| 5 | **O — HA réelle** | ARC-32 | 25 j | `ratelimit/`, `cdc/`, `deploy/`, `scripts/replay/`, `docs/runbooks/` |
| 5 | **P — Routage** | ARC-34 | 20 j | nouveau `core/app/routing/`, `pipelines/ops/` (op réseau, fichier dédié), profil compose `routing` |
| 5 | **Q — Hors ligne** | ARC-31 | 25 j | `shell/src/offline/` (nouveau), `shell/public/` (service worker), `shell/src/builder/widgets/form.tsx` (file d'écritures) |
| 6 | **R — Temps réel** (conditionnelle) | ARC-35 | 12 j | nouveau `core/app/realtime/`, `notifications/` (bascule sondage → SSE) |

Total ≈ 187 j-h ; chemin critique de la vague 4 : K2 (24 j), de la vague 5 : N (30 j).

**Pourquoi ces regroupements :** K1/K2 se partagent `pipelines/` : K1 ne touche que l'exécution d'op, K2 que routes/jobs/modèles ; conflits résiduels arbitrés par le contrôleur. M n'ajoute que des **fichiers neufs** d'op et une entrée de registre `OPERATIONS` (un point de collision unique, trivial). F1 avant F2 (le port Rejected consomme le statut `detectChanges`). F3 avant F5 (le rejeu réutilise les paramètres). F11 avant F7/F8 pour valider le patron d'op d'abord. ARC-31 après ARC-04/15/27 (livrés). ARC-35 en dernier : décision conditionnelle.

**Migrations (tête = 0062, à revérifier au départ) :** F3 → `0063_pipeline_run_params`, F4 → `0064_pipeline_reader_state`, F5 → `0065_pipeline_run_retry`, F6 → `0066_outbound_webhooks`, ARC-33 → `0067_raster_assets`, ARC-32 → `0068_shared_ratelimit`. Une voie qui en découvre une autre demande le numéro suivant au contrôleur. Chaque migration est testée sur base non vide, deux sens (piège n°8).

**Fichiers réservés à l'intégration :** `core/openapi.json`, `shell/src/api/generated/*`, `docs/revue/inventaire-fonctionnalites.jsonl`, `docs/revue/bilan-fonctionnalites.*`, `docs/revue/2026-09-04-backlog.md`, `docs/revue/2026-09-04-analyse-gaps.md`, `docs/revue/matrice-couverture-fme.jsonl`, `CLAUDE.md`, archive d'historique.

## Protocole commun à chaque voie (repris dans chaque prompt de subagent)

- [ ] **Étape 0 — Vérifier le plan contre le code** (piège n°3) : relire chaque `fichier:ligne` ; corriger sans redemander, consigner l'écart dans `.superpowers/sdd/arc4-<voie>-ledger.md`.
- [ ] **Étape 1 — Worktree dédié** `arc4-lane-<x>` (base = `dev` à jour, `git fetch` + `rev-list --left-right --count origin/dev...dev`) ; jamais d'écriture hors de la zone exclusive.
- [ ] **Étape 2 — Par chantier** : tests d'acceptation rouges → implémentation → verts → E2E si surface visible → commit conventionnel.
- [ ] **Étape 3 — Revue par tâche** (sous-agent distinct) ; jumelles de garde listées avant clôture.
- [ ] **Étape 4 — Rapport de voie** : fichiers, migrations, surfaces à inventorier, écarts. Le contrôleur vérifie `git show --stat` et le trailer lui-même.

## Vague 4 — ETL robuste et ouverture

### Voie K1 — Écriture ETL
- [ ] **F1 `writer.collection` modes** : paramètre `mode ∈ {insert, upsert, update, delete}` + `keyColumns` ; applique la colonne de statut produite par `detectChanges` (`NEW/CHANGED/DELETED/UNCHANGED`) ; transaction unique, `can()`, validation ARC-13/14 à chaque ligne, journal d'entité ARC-15. *Acceptation* : 1) rejeu idempotent (2e run = 0 écriture) ; 2) `delete` borné aux clés fournies (jamais de `TRUNCATE` implicite) ; 3) 100 000 lignes upsert < 60 s mesuré ; 4) un champ masqué reste non écrivable.
- [ ] **F2 port Rejected + quarantaine** : sortie `rejected` sur les ops de validation/écriture ; les lignes rejetées vont dans une collection de quarantaine `<cible>__rejected` (colonnes : ligne source JSON, règle, message FR, `run_id`) créée à la demande, **sous les mêmes RLS que la collection source** ; rapport de qualité réutilisant `analytics/profile.py` (taux de nulls, rejets par règle) exposé dans le détail de run. *Acceptation* : 1) 50 lignes dont 7 invalides → 43 écrites, 7 en quarantaine, run `succeeded_with_rejects` ; 2) la quarantaine n'est lisible que par qui peut écrire la cible ; 3) rapport visible dans `/tasks`.

### Voie K2 — Cycle de vie des runs
- [ ] **F3 paramètres de run publiés** : bloc `parameters: [{name, type, default, required}]` dans la config du pipeline (schéma + validation), accessibles aux nœuds via `{{param.x}}`/CEL ; saisie au `POST /v1/pipelines/{id}/run` (`params` validés par type), au webhook entrant (SP-53) et par MCP `run_pipeline`. *Acceptation* : 1) paramètre manquant requis = 422 RFC 7807 ; 2) valeur injectée **jamais interpolée dans du SQL** (liée) — test d'injection ; 3) le run historisé garde ses paramètres.
- [ ] **F5 retry et reprise par nœud** : politique `retry: {max, backoff}` par pipeline ; reprise d'un run échoué **depuis le nœud en échec** (résultats intermédiaires conservés dans le runtime DuckDB du run, durée de rétention bornée), bouton « Rejouer / Reprendre » dans `/tasks`, route `POST /v1/pipelines/runs/{id}/retry`. Respecter le patron commit-puis-defer (piège n°14) : balayage de reprise des runs `retrying`. *Acceptation* : 1) échec simulé au 3e nœud → reprise ne rejoue pas les 2 premiers ; 2) verrou de run (déjà livré) empêche deux reprises concurrentes ; 3) annulation d'une reprise.
- [ ] **F4 incrémental dlt** : état par reader connecteur (curseur `incremental` dlt persisté dans `pipeline_reader_state`, clé = pipeline+nœud) ; option « réinitialiser » ; migration 0064. *Acceptation* : 1) 2e run ne ramène que les lignes plus récentes que le curseur ; 2) échec du run = curseur non avancé ; 3) l'état est purgé avec le pipeline (RGPD `purge_tenant`).

### Voie L — Ouverture et gouvernance
- [ ] **F6 webhooks sortants + déclencheurs** : ADR 0027 ; table `outbound_webhooks` (+ file `outbox` transactionnelle) ; événements `item.created/updated`, `pipeline.run.finished`, `submission.pending` ; signature HMAC (secret du coffre), egress gardé, retries exponentiels, livraison tracée et rejouable (réutiliser le mécanisme d'alertes) ; déclencheur de pipeline sur dépôt de fichier S3 par **sondage borné** du préfixe. *Acceptation* : 1) événement émis dans la même transaction que l'écriture (pas de perte au crash) ; 2) destination privée/RFC1918 refusée ; 3) 5 échecs → désactivation + notification ; 4) dépôt d'un fichier déclenche exactement un run.
- [ ] **F15 lineage et impact** : graphe dérivé des configs (carte → collections, app → cartes/pipelines, pipeline → collections, alerte/rapport → bookmarks) calculé à la demande (aucune table) ; `GET /v1/items/{id}/impact` et `…/lineage` filtrés par ce que l'utilisateur peut voir ; dialogue d'impact avant suppression (liste des dépendants **visibles** + compte des dépendants masqués) dans le shell + outil MCP `get_item_impact`. *Acceptation* : 1) supprimer une collection utilisée par 2 cartes et 1 pipeline affiche les 3 ; 2) un dépendant non lisible est compté sans être nommé ; 3) graphe de 5 000 items < 1 s.

### Voie M — Opérateurs
- [ ] **F11 `transform.geocode`** : op par ligne, colonnes adresse → géométrie + score, BAN par lots (≤ 500, `POST /v1/geocode/batch` existant), egress existant (`geocoding/egress.py`), reprise sur échec partiel, option à l'import CSV. *Acceptation* : 1 000 adresses → ≥ 95 % géocodées en jeu de test mocké ; aucune requête hors garde d'egress ; lignes non géocodées sur le port Rejected (si F2 fusionné, sinon colonne `geocode_error`).
- [ ] **F7 readers GDAL vecteur** : étendre `reader.file` (ou op sœur `reader.gdal`) aux SHP, GPKG, GeoJSON, KML, GML via `ST_Read`, **WFS** via connecteur sous egress ; mêmes bornes que SP-56 (taille, VRT refusés REV-333, `allowed_directories` gardé par `CORE_PIPELINE_FILE_IO_ENABLED`). Passer les lignes `planned_gdal` correspondantes de la matrice FME à `implemented`.
- [ ] **F8 Filtering/Database** : ops `transform.testFilter` (sorties passed/failed), `transform.sampler`, `transform.neighborFinder`, `transform.sqlExecutor` (SQL **lecture seule** sur le lac, sandbox SQL-analyste existante, jamais d'écriture) et familles Database de la matrice (`planned_duckdb`). Chaque op = entrée `OperationContract` unique (schéma/moteur/licence/compilateur). *Acceptation* : un test par op ; `sqlExecutor` refuse `DROP`/`ATTACH`/`COPY` ; catalogue exposé mis à jour (compte dans `CLAUDE.md`).

## Vague 5 — Plateforme (4 voies, après intégration de la vague 4)

### Voie N — Raster (ARC-33, ADR 0024)
- [ ] Ingestion COG (upload S3 présigné → job de validation `rio cogeo validate`, conversion si non COG, emprise/SRID/bandes persistés) ; migration 0067.
- [ ] Proxy TiTiler **authentifié** : `GET /v1/raster/{item}/tiles/{z}/{x}/{y}` sous `can()` + limites géographiques ; TiTiler jamais exposé publiquement (compose : réseau interne, vérifié par valeur, piège n°2) ; jeton de passerelle SP-32 pour l'admin.
- [ ] Statistiques par zone (`POST /v1/raster/{item}/zonal-stats`, polygones d'une collection ou GeoJSON ≤ 1 000) + op `reader.raster` + outil dans le widget Analyse (ARC-25) et MCP.
- [ ] Shell : couche raster dans l'éditeur de carte et le widget carte avec rampe de couleurs/opacité (`toFrontLayer()`, piège n°5).
- *Acceptation* : COG 1 Go servi en tuiles (p95 < 500 ms à z10 mesuré) ; RLS par item (test croisé 403/404) ; zonal stats d'un polygone = valeur de référence rasterio ± 1e-6 ; quota de stockage appliqué.

### Voie O — HA réelle (ARC-32)
- [ ] Limiteur de débit partagé (Postgres, `ratelimit/`), compatible 2+ réplicas `core` ; garde du comportement dégradé si la base est lente.
- [ ] Élection du `cdc-worker` (verrou consultatif Postgres) : un seul actif, bascule automatique.
- [ ] `core` sans état vérifié (aucun cache de session en mémoire non rechargeable ; tâches de fond idempotentes) ; chart Helm (ARC-29) avec `replicaCount`, PDB, sondes ; runbook Postgres primaire/standby + MinIO distribué (`docs/runbooks/`), RPO/RTO publiés.
- [ ] Test de bascule scripté en CI/rejeu (`scripts/replay/`) sur stack jetable.
- *Acceptation* : tuer un `core` sous charge → bascule < 30 s, **0 écriture perdue** (compte avant/après) ; tuer le `cdc-worker` actif → l'autre reprend < 30 s sans doublon GeoParquet ; budget de débit par jeton cohérent entre réplicas. Support « contractuel » = hors code, noté dans le runbook.

### Voie P — Routage (ARC-34, ADR 0025)
- [ ] Service Valhalla (MIT) en profil compose `routing` + sous-chart Helm optionnel, tuiles de routage fournies par l'opérateur (doc de préparation OSM).
- [ ] Module `app/routing/` : `POST /v1/routing/route`, `/isochrone`, `/service-area`, `/matrix` ; appels sous egress, timeout et plafonds (points, durée max), audit de chaque appel, `can()` + privilège `analytics.view`.
- [ ] Ops de pipeline `transform.isochrone`/`transform.route` (fichier d'op dédié) ; widget « Directions » dans le builder ; outils MCP.
- *Acceptation* : isochrone 10 min < 2 s (mesuré sur extrait OSM de test) ; service absent = erreur 503 RFC 7807 lisible, jamais de crash ; aucun appel hors garde d'egress ; 101e requête/min = 429.

### Voie Q — Hors ligne (ARC-31, ADR 0023)
- [ ] Service worker + manifeste PWA (mode collecte uniquement), cache de zone (tuiles MVT/raster bornées en nombre et en octets, purge LRU), jamais de donnée masquée en cache pour un autre utilisateur (clé de cache = utilisateur, purge à la déconnexion).
- [ ] File d'écritures (IndexedDB) du widget Formulaire : saisies + pièces jointes, rejeu ordonné au retour réseau avec `If-Match` (ARC-04) ; conflit 412 → écran de résolution (garder ma version / la version serveur / fusion champ par champ).
- [ ] Indicateur d'état (bannière de connectivité existante étendue : « n saisies en attente »), reprise après fermeture de l'onglet.
- *Acceptation* : saisie hors ligne de 20 enregistrements puis synchro sans perte ni doublon (E2E Playwright avec `context.setOffline`) ; conflit 412 résolu côté utilisateur ; données d'un autre utilisateur absentes du cache après changement de compte ; a11y axe verte.

## Vague 6 — Conditionnelle

### Voie R — Temps réel (ARC-35, ADR 0026) — **uniquement si l'ADR est validé**
- [ ] `GET /v1/realtime/stream` (SSE) authentifié, canaux = notifications, alertes, rafraîchissement de dataset ; mêmes contrôles `can()` par message ; repli sur sondage si SSE indisponible ; compatible multi-réplicas (diffusion via `LISTEN/NOTIFY` Postgres, pas de broker).
- *Acceptation* : latence < 2 s sur 50 abonnés (mesure) ; un abonné sans droit ne reçoit jamais l'événement ; coupure réseau = reconnexion avec reprise (`Last-Event-ID`). Sinon : clore ARC-35 « non cible » dans le comparatif et REV-114.

## Tâche d'intégration (fin de chaque vague)

- [ ] Fusion voie par voie dans `dev` ; migrations re-chaînées ; tests de chaque voie rejoués après chaque fusion.
- [ ] OpenAPI + types TS (incantation `api-types-drift`) ; inventaire ; `feature_health_cli.py --write` ; matrice FME (`matrice-couverture-fme.jsonl`) mise à jour.
- [ ] Portes : `ruff`, `mypy --strict`, `lint-imports` (nouvelles entrées pour `outbox`, `lineage`, `raster`, `routing`, `realtime`), `pytest` (base réelle), `npm run test`, `npm run build`, **E2E complète verte**, `test_deployability` (nouvelles variables câblées par valeur).
- [ ] **Revue finale de branche** (sous-agent opus) : jumelles croisées — RLS/masquage sur raster, routage, quarantaine, webhooks (payload ne fuite pas de champ masqué), cache hors ligne ; `pending` (ARC-10) × webhooks × historique.
- [ ] Documentation : lignes `### Livré` de `CLAUDE.md`, archive d'historique, statut dans le comparatif (ARC-31 à 35 et rangs FME), `GAP-nn`/`REV-nnn` fermés (REV-114/120 selon décisions), ADR 0023-0027.
- [ ] Supprimer worktrees et branches `arc4-lane-*` fusionnés ; PR `dev` → `main`.

## Pré-lancement

- [ ] `git fetch` + `git rev-list --left-right --count origin/dev...dev` ; tête Alembic ; `git worktree list` (pas de worktree orphelin — confirmation explicite de Tanguy avant suppression).
- [ ] Tanguy valide **les 4 ADR de décision** (0023 hors ligne, 0024 raster, 0025 routage, 0026 temps réel) : ils rouvrent REV-120 et REV-114, fermées par décision.

## Hors périmètre (inchangé)

H1 (versioning de branche/géodatabase d'entreprise), H2 (I3S, splats, vidéo, QuickCapture, Notebooks, GeoEnrichment, certifications), rangs FME 20-21 (SDK de transformer Python, notebooks) — non demandés ici.
