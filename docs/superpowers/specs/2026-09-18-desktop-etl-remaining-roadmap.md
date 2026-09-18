# Desktop ETL — feuille de route du reste (E→K)

> Date : 2026-09-18 · Statut : décomposition validée, remplace le §11 de
> [`2026-09-17-desktop-etl-standalone-design.md`](2026-09-17-desktop-etl-standalone-design.md)
> (le reste du design doc — §1 à §10 — reste la référence d'architecture,
> inchangé). Ce document part d'une revue directe du code (pas de la
> mémoire ni des docs) et corrige plusieurs approximations du design
> original repérées à cette occasion (piège CLAUDE.md #3/#12).

## 1. Où on en est réellement (vérifié dans le code, pas dans CLAUDE.md)

Fait à ce jour (`dev`, HEAD `9f820ce4`) :

- **Spike freeze PyInstaller** (D1) : GO, `--collect-all dlt` suffit pour
  `connector_runtime.py` (dlt/duckdb/sqlalchemy) sur Linux **et**
  Windows CI. `geopandas`/`shapely`/`pyproj` **jamais gelés** par ce spike
  (absents du graphe — `reader.connector.rest` ne les importe pas) :
  risque résiduel non prouvé, cf. §4.
- **Seam `SecretResolver`** (D2) : `Protocol` dans
  `core/app/pipelines/connector_runtime.py:51-61` (une seule méthode,
  `get(name: str) -> SecretPayload`, **pas de `set`** — écrire un secret
  reste un chemin Postgres direct non abstrait,
  `core/app/secrets/repository.py::create_secret`). `PostgresSecretResolver`
  reste codé en dur aux 3 points d'appel dans `runtime.py` (lignes 269,
  297, 325) — **pas encore de DI** : un futur runtime desktop qui veut
  `reader.connector.*` doit soit patcher ces 3 call sites, soit s'en passer
  en v1 (cf. §3, Phase I).
- **Seam `RunTracker`** (D3) : `Protocol` dans `jobs.py:144-152` (3
  méthodes : `mark_running`/`mark_succeeded`/`mark_failed`).
  `PostgresRunTracker` reste construit en dur dans `run_pipeline_task`
  (`jobs.py:190-192`) — **pas de DI non plus**. Un sidecar ne peut pas
  réutiliser `run_pipeline_task` tel quel ; il doit écrire son propre
  wrapper fin qui construit un tracker en mémoire et appelle
  `runtime.run_pipeline()` directement (cf. Phase E).
- **`reader.file`/`writer.file`** (D4) : mergés
  (`27a52081`..`64aa711d`+`9f820ce4`), gardés par
  `CORE_PIPELINE_FILE_IO_ENABLED` (`is_pipeline_file_io_enabled()`,
  `core/app/auth/dependency.py:49-58`, défaut `false`, docstring anticipe
  déjà explicitement le sidecar desktop). **`OperationContract.enabled_when`
  ne gate que la visibilité dans `ops_catalog()`** — le vrai garde-fou vit
  dans `runtime.py` à l'exécution. `_lock_down()` accepte déjà
  `extra_allowed_dirs` (calculés par `_prepare()` à partir des nœuds
  `writer.file` du payload, **avant** le verrouillage DuckDB) — le
  mécanisme d'allowlist n'a pas besoin d'être réécrit pour le desktop, un
  chemin choisi par l'utilisateur suffit à l'alimenter.
  - La Tâche 6 du plan `2026-09-18-desktop-etl-reader-writer-file.md`
    (bout-en-bout + suite complète + portes de qualité) a été close en
    session concurrente pendant l'écriture de ce document (commit
    `06a67828`, "test(core): pipeline reader.file -> transform ->
    writer.file bout-en-bout" — a aussi trouvé et corrigé un vrai défaut
    croisé, `_write_file` sans `os.makedirs` du répertoire parent, cf.
    `9f820ce4`) : suite complète 2878 passed/0 failed/272 skipped,
    couverture 87.76 %. **Reste ouvert, mécanique, à faire à l'occasion** :
    le plan lui-même (`docs/superpowers/plans/2026-09-18-desktop-etl-reader-writer-file.md`)
    est encore *untracked* — le versionner suit le patron déjà utilisé
    pour les 4 plans desktop-etl précédents (commit `774ea184`).
- **`writer.core.collection`** : n'existe pas encore (confirmé par grep) —
  Phase J.
- **Aucun fichier Tauri/Rust** (`src-tauri/`, `Cargo.toml`,
  `tauri.conf.json`) n'existe dans le dépôt — la Phase G part de zéro.
- **Aucun code PKCE/loopback OIDC natif** n'existe dans le dépôt (grep
  `PKCE|code_verifier|code_challenge` : zéro hit en dehors des docs et de
  l'attribut Keycloak `pkce.code.challenge.method`) — la Phase J part de
  zéro (le design §5 en esquisse déjà le patron en prose : `gh auth
  login`/`aws sso login`).

## 2. Corrections apportées au design original (§2, §6, §11)

Trois approximations du design du 2026-09-17, corrigées par lecture directe
du code réel avant d'écrire ce document (piège CLAUDE.md #3) :

1. **Décompte de fichiers du canvas** (§2) : le design estimait « ~10
   fichiers » de `shell/src/builder/pipeline/`. Le compte réel est **24
   fichiers, 3628 lignes** (14 fichiers source hors tests) — sans compter
   `shell/src/pages/PipelineBuilderPage.tsx` (280 lignes), qui fait le
   pont entre `useItemClient()` et le canvas. Le choix « copie ciblée vs
   package minimal » (§2 du design) doit être tranché sur cette base
   réelle, pas sur l'estimation.
2. **`CollectionParamSelect`/`SecretParamSelect` ne sont PAS un blocage
   du chemin d'or v1** (§6/§7 du design). `ReaderFileParams.path` et
   `WriterFileParams.path` (`core/app/pipelines/ops/schemas.py:375-395`)
   sont de simples `str` **sans** `format` JSON-schema particulier —
   `PipelineNodeInspector.tsx`'s `renderControl()` (lignes 127-148) ne
   dispatche sur un composant dédié que pour `prop.format ===
   "collection-id"` ou `"secret-name"` ; un champ `path` tombe dans le
   input texte générique. **Le pipeline fichier→fichier (chemin d'or de
   la Phase G) ne nécessite donc aucun remplacement de composant** — un
   simple champ texte où l'utilisateur colle un chemin absolu suffit pour
   la v1. Le remplacement par un vrai sélecteur de fichier natif
   (Tauri `dialog` plugin, nouveau `format: "file-path"`) devient une
   **amélioration UX différée (Phase I)**, pas un prérequis du golden
   path. `SecretParamSelect` (trousseau OS) ne devient nécessaire que
   quand `reader.connector.*` entre au périmètre (Phase I aussi).
3. **Architecture de réutilisation de l'UI — précision manquante dans le
   design.** Le design dit « la webview charge une build Vite du même
   code React... pointée sur le loopback » sans dire comment
   `PipelineBuilderPage.tsx` obtient/persiste sa `PipelinePayload` — or ce
   composant appelle `client.getPipelineConfig(pk)` /
   `client.savePipelineConfig(pk, payload)` / `client.createPipelineItem(...)`,
   qui passent par `/configs/by-item/{pk}` côté cœur (`shell/src/api/domains/pipelines.ts:60-76`),
   **pas** par les routes `/pipelines/*` que le sidecar rejoue. Le sidecar
   n'a pas de table `configs` — il n'a même pas de concept de tenant/item
   persistant. **Décision d'architecture prise ici** (Phase G) : le
   desktop construit un **`ItemClient` alternatif** implémentant au moins
   `PipelinesMethods` (le sous-ensemble typé dans
   `shell/src/api/domains/pipelines.ts:14-26`), où :
   - `getPipelineOps` / `runPipeline` / `getPipelineRuns` /
     `previewPipeline` parlent HTTP au sidecar loopback (formes identiques
     à celles du cœur, cf. §3.1) ;
   - `createPipelineItem` / `getPipelineConfig` / `savePipelineConfig`
     lisent/écrivent le fichier local `.gspipeline` (Tauri
     `fs`/`dialog`), **et** poussent la charge utile courante au sidecar
     via un nouvel appel (`PUT /pipelines/{itemId}`, cf. §3.1) pour que le
     moteur d'exécution connaisse le pipeline actif avant `run`/`preview`.

   Avec cette seule adaptation côté `ItemClient`, **aucun fichier de
   `shell/src/builder/pipeline/` n'a besoin d'être modifié** pour le
   chemin d'or (ils consomment tous `useItemClient()`, jamais l'API
   directement) — sauf `PipelineBuilderPage.tsx` lui-même, qui reste
   inchangé aussi puisqu'il n'appelle que des méthodes de l'interface
   `ItemClient`, quelle que soit l'implémentation injectée par `App.tsx`.
   Ceci réduit drastiquement le risque « postmortem extraction shell »
   (§4 du design, cf. rappel ci-dessous) : **zéro fichier de
   `builder/pipeline/` déplacé ou dupliqué pour la v1** — seulement un
   nouvel `ItemClient` desktop et un point d'injection dans un
   `App.tsx` desktop-spécifique (qui, lui, n'existe pas encore et sera
   écrit neuf, pas extrait).

4. **`connector_runtime.py` (donc `dlt`/`sqlalchemy`) est importé au
   niveau module par `runtime.py`** (`from app.pipelines import compiler,
   connector_runtime`, ligne 47) — **même un sidecar qui n'exécute jamais
   `reader.connector.*`** doit geler `dlt` dans son binaire, puisque
   `runtime.py` (le module qu'il importe pour `reader.file`/`writer.file`)
   importe `connector_runtime.py` de toute façon. `--collect-all dlt`
   reste donc nécessaire au freeze même en v1 « fichier→fichier
   seulement » — pas une option à activer plus tard.
5. **`PipelineRunPanel.tsx` ne poll jamais un run par id** — il appelle
   `GET /pipelines/{pk}/runs?limit=100` en boucle (`setTimeout` 1500 ms,
   patron `ImportFileButton.tsx`) et prend `latest[0]` comme run courant
   (`PipelineRunPanel.tsx:75-92`). **Le sidecar n'a donc besoin que d'un
   endpoint de liste** (`GET /pipelines/{itemId}/runs`, triée du plus
   récent au plus ancien), pas d'un endpoint par id — simplification
   réelle par rapport à ce que le design laissait supposer.

## 3. Rappel du risque postmortem (à ne pas reproduire)

`docs/superpowers/specs/2026-09-08-app-builder-package-extraction-postmortem.md`
(tentative d'extraction npm workspace de `shell/src/ui/kit` +
`shell/src/builder`, abandonnée) documente 7 classes de défauts :
scan de sources Tailwind v4 aveugle aux workspaces, lockfile/contexte
Docker désynchronisés, nouveaux packages sans tooling CI hérité, seuils de
couverture qui ne suivent pas le code déplacé, collisions `git mv` sur des
fichiers-pont, **signatures d'interface écrites depuis des noms de
méthode seuls puis fausses à l'implémentation**, et `workspace:` non
supporté par npm 9.2.0 de ce dépôt. Le point 4.3 ci-dessus **élimine le
besoin même de déplacer ou dupliquer du code du canvas pour la v1** — donc
élimine structurellement les classes 1/2/3/4/5/7 de ce postmortem pour la
Phase G. La classe 6 (signature d'interface non vérifiée) reste un risque
générique pour le nouvel `ItemClient` desktop — traité en écrivant ses
méthodes directement contre les signatures réelles de `PipelinesMethods`
(§2.3 ci-dessus), pas depuis des noms mémorisés.

## 3.1 Contrat HTTP du sidecar (verrouillé ici, réutilisé par la Phase E)

Le sidecar rejoue les formes JSON du cœur (design §4) mais avec un
**stockage de payload différent** (§2.3) :

| Méthode | Route | Corps | Réponse | Écart vs le cœur |
|---|---|---|---|---|
| `PUT` | `/pipelines/{itemId}` | `PipelinePayload` (JSON) | `204` | **Nouveau** — n'existe pas côté cœur (qui charge par `item_id` depuis Postgres) ; ici stocke la charge active en mémoire pour cet `itemId`. |
| `GET` | `/pipelines/ops` | — | `dict[str, PipelineOpEntry]` (`ops_catalog()`) | Identique. |
| `POST` | `/pipelines/{itemId}/run` | — | `202 {"runId": str}` | Identique en forme ; utilise la dernière charge `PUT`ée pour `itemId` (404 si aucune) au lieu d'un chargement Postgres. |
| `GET` | `/pipelines/{itemId}/runs?limit=&offset=` | — | `RunStatus[]` (le plus récent d'abord) | Identique en forme (`id`/`status`/`startedAt`/`finishedAt`/`error`/`nodeStats`, cf. `routes.py:33-43`) ; source en mémoire au lieu de Postgres. |
| `POST` | `/pipelines/{itemId}/preview?upTo=` | — | `list[dict]` (`200`) ou `400` si `PipelineRuntimeError` | Identique en forme ; utilise la dernière charge `PUT`ée. |

Aucune authentification (`Authorization` bearer) sur ces routes — le
sidecar n'écoute que sur `127.0.0.1`, mono-utilisateur, mono-process,
lancé et arrêté par Tauri (design §1, non-but « multi-utilisateur/partage »).

## 4. Découpage en phases (E→K)

Chaque phase = un futur `writing-plans` (TDD, tâches bout-en-bout,
commits, revue). Ordre contraint par les dépendances indiquées.

### Phase E — Moteur sidecar + API loopback (pur Python, sans Tauri)

**Close** (`b4578e79..c4cb132c` — `b4578e79`/`70038719`/`680b258a`/
`c4cb132c`, 4 commits ; 2 commits interleavés dans cette plage,
`da5f3385`/`dc16a85f`, appartiennent à une session concurrente sur
`reader.file`/`writer.file`, sans rapport avec cette phase) : plan
[`2026-09-18-desktop-etl-sidecar-engine.md`](../plans/2026-09-18-desktop-etl-sidecar-engine.md)
exécuté intégralement (4 tâches de code + Tâche 5 vérification). Testé
entièrement sur la machine de dev actuelle (Linux, pytest,
`httpx.ASGITransport`) — aucune dépendance à Windows/Tauri/PyInstaller
pour cette phase, conforme à l'objectif. Prérequis Tâche 6
`reader-writer-file` était déjà levé (§1 ci-dessus). Aucune surface
externe nouvelle : l'app FastAPI du sidecar n'est jamais montée dans
`core/app/main.py`. Reste pour la suite (Phase G) : port
Tauri/PyInstaller réel du binaire, pas testé ici.

### Phase F — Spike gel géospatial (risque résiduel du spike D1)

**Objectif.** Prouver que `geopandas`/`shapely`/`pyproj` (chargés
transitivement par `app/ingestion/parsers.py` — **pas** par
`connector_runtime.py`, donc jamais exercés par le spike D1) se gèlent et
s'exécutent correctement dans un binaire PyInstaller sur `windows-latest`,
en particulier :
- `pyproj` a besoin de son répertoire de données PROJ (`proj.db`) —
  typiquement `--collect-data pyproj`, à vérifier empiriquement (pas
  supposé).
- `shapely` a besoin de sa bibliothèque native GEOS — le point le plus
  susceptible de casser silencieusement sous Windows (DLL manquante
  découverte seulement à l'exécution, cf. piège CLAUDE.md #3).

**Pourquoi une phase séparée, avant Phase G.** Le design (§9) l'identifie
déjà comme risque secondaire non prouvé. Le decouvrir APRÈS avoir construit
tout le shell Tauri serait cher à corriger (risque explicitement à éviter,
même paragraphe du design). GO/NO-GO : si `geopandas`/`shapely`/`pyproj`
ne gèlent pas proprement, `reader.file`/`writer.file` sur des formats qui
en dépendent (le driver GDAL utilisé par `ST_Read()`/`COPY` est en réalité
fourni par le binding `duckdb` `spatial`, **pas** par `geopandas`/`shapely`
directement — à confirmer : `app/analytics/duckdb_conn.py` charge
l'extension DuckDB `spatial`, qui embarque GDAL en statique. Le besoin réel
de `geopandas`/`shapely`/`pyproj` dans le graphe du sidecar v1
fichier→fichier est **à vérifier en tout premier geste de cette phase**
par un `grep` d'imports transitifs réel, avant même d'écrire un test —
il est possible que ces 3 paquets ne soient PAS nécessaires du tout au
sidecar v1 s'il n'appelle jamais `app/ingestion/parsers.py`/`app/cdc/*`,
auquel cas cette phase se réduit à confirmer une non-dépendance plutôt qu'à
réparer un freeze cassé).

### Phase G — Bootstrap Tauri + persistance locale + chemin d'or E2E

**Objectif.** `src-tauri/` neuf (Rust + `tauri.conf.json`), lancement du
sidecar (binaire Phase E, figé Phase F) comme sous-processus, lecture du
port éphémère depuis stdout (handshake, cf. plan Phase E Tâche 4),
build Vite d'un nouveau point d'entrée desktop (nouveau
`App.tsx` desktop-spécifique — **écrit neuf**, pas extrait — construisant
le `PipelineBuilderPage.tsx` existant, **inchangé**, avec un `ItemClient`
desktop implémentant `PipelinesMethods` (§2.3, §3.1) + persistance
`.gspipeline` via `fs`/`dialog` Tauri. E2E golden path (Tauri WebDriver,
design §10) : créer un pipeline fichier→fichier, exécuter, vérifier le
fichier de sortie. **Marque la v1 « utilisable » au sens minimal du
design** (objectif §1, sans connecteurs ni push).

### Phase H — (fusionnée dans G)

Le découpage initial du design séparait « persistance locale » de
l'intégration Tauri — regroupées ici car le chemin d'or de la Phase G ne
peut pas être démontré sans un mécanisme de sauvegarde/ouverture de
fichier réel (« créer un pipeline » implique déjà « le persister »).

### Phase I — Connecteurs desktop + secrets trousseau OS + UX de chemin

**Objectif.** `reader.connector.rest/postgres/snowflake` utilisables
depuis le desktop : un `SecretResolver` desktop (trousseau OS, ex. paquet
Python `keyring`) implémentant le seul `get(name) -> SecretPayload` du
Protocol (§1) — nécessite de patcher les 3 call sites codés en dur dans
`runtime.py` (lignes 269/297/325) pour accepter une injection, puisque ce
DI n'existe pas encore. **Écriture** d'un secret dans le trousseau OS n'a
aucun seam existant à réutiliser (§1) — UI + code desktop entièrement
neufs. Amélioration UX différée de la correction §2 point 2 : un vrai
sélecteur de fichier natif (`format: "file-path"` nouveau, composant Tauri
`dialog`) remplaçant le champ texte brut pour `path`.

### Phase J — Push vers un cœur distant

**Objectif.** Nouvel op `writer.core.collection` (ajout au registre
partagé `OPERATIONS`, cf. `app/pipelines/ops/contracts.py` — client HTTP
OGC API Features, pas un accès SQL direct) + flux OIDC PKCE + listener
loopback (greenfield confirmé, §1) + nouveau client Keycloak public
`desktop-etl` (réplique de `geostudio-shell` dans
`deploy/keycloak/geostudio-realm.json`, avec `redirectUris` pointant sur
le loopback local au lieu de `localhost:8300`) + stockage du refresh token
dans le même trousseau que la Phase I.

### Phase K — Packaging, CI de dérive, distribution

**Objectif.** Freeze onefile complet (sidecar + toutes les op activées) +
bundler Tauri (installeur `.msi`/`.exe`) + job CI qui **reconstruit et
fait tourner les tests du sidecar dès qu'un fichier de
`core/app/pipelines/` change** (porte de dérive version cœur/desktop,
design §3 — même patron que `test_feature_inventory.py`, une porte pas
une discipline). Décisions produit encore ouvertes, à trancher **au
moment de cette phase, pas avant** : signature de code (SmartScreen),
graduation de `desktop-etl-spike.yml` (aujourd'hui `workflow_dispatch` +
`push`, non taggé) vers le flux `release.yml` tagué existant
(`v*.*.*` → `test-gate` → `build-and-push`, 9 legs de matrice) ou
maintien d'un fichier séparé.

## 5. Ce que ce document ne couvre pas

Pas de détail tâche-par-tâche pour les phases F, G, I, J, K — chacune sera
son propre plan `writing-plans`, écrit **juste avant son exécution**
(patron déjà suivi pour D1-D4, cf. §1) : les détails d'API tierce (Rust
Tauri, `keyring`, endpoints Keycloak Admin, options PyInstaller pour
GDAL/PROJ) doivent être vérifiés contre la source réelle au moment de
l'écriture, pas mémorisés à l'avance (piège CLAUDE.md #3) — un plan
écrit aujourd'hui pour la Phase J, par exemple, risquerait de figer des
signatures d'API qui n'auront jamais été vérifiées avant l'exécution.
