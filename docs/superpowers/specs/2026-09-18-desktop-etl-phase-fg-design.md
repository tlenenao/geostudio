# Desktop ETL — Phase F+G combinées : freeze binaire réel, bootstrap Tauri, sécurité loopback

> Date : 2026-09-18 · Statut : design validé, pas encore planifié.
> Opérationnalise en un seul chantier planifiable les Phases F et G de
> [`2026-09-18-desktop-etl-remaining-roadmap.md`](2026-09-18-desktop-etl-remaining-roadmap.md)
> (qui fait foi pour tout ce qui n'est pas repris ici), la sécurité du
> loopback étant traitée **dans** cette tranche comme le roadmap l'exige
> (§4, Phase G). Références amont : [`2026-09-17-desktop-etl-standalone-design.md`](2026-09-17-desktop-etl-standalone-design.md)
> (design produit original, §1-§10 toujours valides), [`2026-09-17-desktop-etl-spike-01-findings.md`](2026-09-17-desktop-etl-spike-01-findings.md)
> (spike freeze PyInstaller, GO sur `--collect-all dlt`).

## 1. Objectif de cette tranche

Faire passer le sidecar desktop-etl de « moteur headless testé en mémoire
sur Linux » (Phase E, close) à **un exécutable Windows installable** que
l'utilisateur peut télécharger, lancer, et utiliser pour un pipeline
fichier→fichier de bout en bout — sans connecteurs, sans push vers un cœur
distant, sans CI de release taguée (ces trois éléments restent Phases I/J/K,
hors périmètre ici).

**Critère de complétude (golden path) :** sur une machine Windows propre
(sans Python ni Node installés), l'utilisateur installe le binaire produit
par cette tranche, ouvre l'app, crée un pipeline avec un nœud `reader.file`
(CSV/GeoJSON local), un `transform.*`, et un `writer.file`, clique
« Exécuter », et retrouve le fichier de sortie attendu sur disque.

## 2. Non-buts explicites de cette tranche

Repris du design §1 et du roadmap §4, non renégociés ici :

- `reader.connector.*`/`writer.core.collection` et tout secret trousseau OS
  (Phase I/J).
- Signature de code, CI de release taguée, distribution publique via
  `release.yml` (Phase K) — le binaire produit ici circule par artefact CI
  ou build local, pas par une GitHub Release publiée.
- macOS/Linux — Windows seul.
- `CollectionParamSelect`/`SecretParamSelect` : le champ `path` de
  `reader.file`/`writer.file` reste un input texte brut en v1 (le
  sélecteur de fichier natif Tauri est une amélioration UX différée à la
  Phase I, cf. roadmap §2 point 2).
- Historique de versions du pipeline, planification, multi-utilisateur —
  non-buts produit déjà actés (design §1).

## 3. Architecture

### 3.1 Disposition des fichiers

```
desktop-etl/                      # nouveau, racine, sibling de shell/ et core/
  src-tauri/
    Cargo.toml
    tauri.conf.json               # bundle.externalBin -> binaire sidecar figé
    src/
      main.rs                     # spawn sidecar, lit handshake stdout, injecte le token
  README.md                       # comment builder/lancer en dev

shell/
  src/desktop/
    main.tsx                      # point d'entrée Vite alternatif
    ItemClient.desktop.ts         # implémente PipelinesMethods, parle au sidecar
  index.desktop.html
  vite.config.desktop.ts          # build séparé -> shell/dist-desktop/
```

**Décision actée (remplace la proposition « nouveau dossier racine avec son
propre `package.json` » du design §2) :** le webview desktop est une cible
de build *supplémentaire à l'intérieur de `shell/`*, pas un second paquet
npm. Mêmes `node_modules`, même config Tailwind/tsconfig que le shell
serveur. Ceci élimine structurellement les 7 classes de défauts du
postmortem d'extraction npm workspace
(`2026-09-08-app-builder-package-extraction-postmortem.md`) pour cette
tranche : aucun `package.json` séparé, aucun lockfile à synchroniser, aucun
scan Tailwind cross-workspace, aucun tooling CI dupliqué.

`desktop-etl/src-tauri/` reste un dossier racine séparé car c'est du Rust,
sans lien avec le tooling npm du shell — seul son `tauri.conf.json` pointe
vers `shell/dist-desktop/` comme `distDir`.

Aucun fichier de `shell/src/builder/pipeline/` n'est modifié ou dupliqué
(confirmé possible par le roadmap §2 point 3 : `PipelineBuilderPage.tsx` et
tout le canvas ne consomment que `useItemClient()`).

### 3.2 `ItemClient` desktop

Implémente au moins `PipelinesMethods` (`shell/src/api/domains/pipelines.ts:14-26`,
signatures à vérifier contre la source réelle au moment de l'implémentation,
pas depuis ce document — piège CLAUDE.md #3) :

- `getPipelineOps`, `runPipeline`, `getPipelineRuns`, `previewPipeline` →
  HTTP vers le sidecar loopback, formes JSON identiques au cœur (contrat
  verrouillé au roadmap §3.1).
- `createPipelineItem`, `getPipelineConfig`, `savePipelineConfig` → lisent/
  écrivent un fichier local `.gspipeline` via les plugins Tauri `fs`/
  `dialog`, et poussent la charge active au sidecar via
  `PUT /pipelines/{itemId}` à chaque sauvegarde/ouverture pour que le
  moteur connaisse le payload avant `run`/`preview`.

### 3.3 Cycle de vie du sidecar

Tauri (`main.rs`) :
1. Génère un jeton aléatoire (ex. 32 octets, encodé hex) avant le spawn.
2. Lance le binaire sidecar via `tauri::api::process::Command` (mécanisme
   `externalBin` natif Tauri — pas de gestion de sous-processus maison) en
   lui passant le jeton par variable d'environnement.
3. Lit le handshake sur stdout du sidecar : `PORT=<n>\nTOKEN=<t>` (le
   sidecar réémet le jeton reçu pour confirmation, ou échoue au démarrage
   si absent).
4. Configure le client HTTP du webview avec `http://127.0.0.1:<n>` et
   l'en-tête `Authorization: Bearer <t>` sur chaque requête.
5. Termine le sous-processus sidecar à la fermeture de l'app (déjà un
   comportement par défaut des sidecars Tauri — à confirmer contre la doc
   Tauri réelle au moment de l'implémentation).

## 4. Sécurité du loopback (retouche de Phase E déjà mergé)

Le listener actuel (`core/app/pipelines/sidecar/app.py`) n'a ni
authentification ni validation d'en-tête `Host` — vulnérable au DNS
rebinding (une page web malveillante ouverte dans un autre navigateur sur
la même machine pourrait faire pointer un sous-domaine vers 127.0.0.1 et
soumettre des requêtes `fetch()` au sidecar). Cette tranche ferme ce trou
avant que le sidecar soit un vrai process lancé par Tauri :

- `pipeline_sidecar.py` : accepte le jeton via variable d'environnement
  (ex. `GEOSTUDIO_SIDECAR_TOKEN`), l'inclut dans le handshake stdout.
- `sidecar/app.py` : middleware FastAPI (`starlette.middleware`) qui,
  avant toute route `/pipelines/*` :
  - rejette (401) si `Authorization: Bearer <token>` ne correspond pas
    exactement au jeton attendu (comparaison à temps constant,
    `hmac.compare_digest`) ;
  - rejette (400) si l'en-tête `Host` est présent et ne vaut pas
    `127.0.0.1:<port>` (défense en profondeur contre le rebinding, en plus
    du bind explicite déjà existant sur `127.0.0.1`).
- Mode sans jeton (variable d'environnement absente) : comportement actuel
  inchangé, pour ne pas casser les tests Phase E existants qui invoquent
  l'app directement sans jeton — le jeton devient obligatoire uniquement
  quand `pipeline_sidecar.py` le reçoit à son démarrage (chemin réel Tauri).

**Vérification par falsification (piège CLAUDE.md #10) :** le test qui
prouve le rejet doit d'abord être vérifié en désactivant délibérément la
vérification (commenter le middleware), confirmer que le test échoue alors,
puis le réactiver — pas seulement constater qu'il passe une fois écrit.

## 5. Freeze géospatial + binaire réel (Phase F)

**Premier geste, avant tout code** : `grep -rn "geopandas\|shapely\|pyproj"`
sur le chemin d'import réel du sidecar (`core/app/pipelines/sidecar/`,
`core/app/pipelines/runtime.py`, `core/app/pipelines/connector_runtime.py`
et leurs imports transitifs) pour confirmer si ces 3 paquets sont
effectivement chargés par le sidecar v1 fichier→fichier, ou si (comme
soupçonné par le roadmap §4 Phase F) `duckdb` `spatial` suffit seul (GDAL
embarqué en statique dans l'extension DuckDB, pas besoin de `geopandas`/
`shapely`/`pyproj` côté Python).

- **Si non nécessaires** : documenter la non-dépendance (mise à jour de ce
  document ou note dans le ledger d'exécution), passer directement au
  freeze de l'entrypoint réel.
- **Si nécessaires** : reproduire le spike D1
  (`2026-09-17-desktop-etl-spike-01-findings.md`) spécifiquement pour ces 3
  paquets sur `windows-latest` : `--collect-data pyproj` (répertoire
  `proj.db`), vérifier que la DLL GEOS de `shapely` est bien embarquée
  (risque identifié : échec silencieux, DLL manquante découverte seulement
  à l'exécution).

**Sortie de la phase** : `core/scripts/pipeline_sidecar.py` (l'entrypoint
réel, pas `pipeline_sidecar_spike.py`) gelé en binaire onefile PyInstaller,
testé en CI `windows-latest` sur un cycle `reader.file`→`transform.*`→
`writer.file` réel (pas juste un import qui ne plante pas).

Rappel (roadmap §2 point 4) : même le freeze « fichier→fichier seulement »
doit inclure `--collect-all dlt` — `runtime.py` importe
`connector_runtime.py` au niveau module, donc `dlt`/`procrastinate`/
`sqlalchemy` sont tirés transitivement même si jamais exécutés par le
sidecar v1.

## 6. Tests / validation

| Surface | Où | Comment |
|---|---|---|
| Middleware auth+Host | CI Linux (existant) | pytest, `httpx.ASGITransport`, TDD par falsification (§4) |
| Freeze PyInstaller réel | CI `windows-latest` | job dédié (extension de `desktop-etl-spike.yml`), exécute le binaire produit sur un cycle réel |
| Spawn Tauri + parsing handshake | VM Windows de l'utilisateur (dev local) | tests Rust unitaires (`cargo test`) |
| `ItemClient` desktop | Vitest existant (jsdom) | mock du sidecar HTTP, formes JSON du contrat §3.1 du roadmap |
| E2E golden path | VM Windows (dev), puis CI `windows-latest` | Tauri WebDriver — créer pipeline, exécuter, vérifier fichier de sortie |

La suite E2E golden path est la porte de complétude de cette tranche
(cf. §1) — pas de déclaration de tranche terminée sans elle verte au moins
une fois sur `windows-latest`.

## 7. Risques identifiés

- **Itération lente sur Windows** : chaque changement Rust/Tauri nécessite
  soit la VM Windows de l'utilisateur (disponible, cf. décision actée),
  soit un aller-retour CI. Le découpage en tâches doit minimiser les
  allers-retours CI (grouper les vérifications Windows par tâche, pas par
  commit).
- **Dérive du contrat HTTP** : le contrat §3.1 du roadmap est verrouillé
  par les tests Phase E existants — toute modification du côté sidecar
  (ex. ajout du jeton) doit être vérifiée de ne pas casser ces tests avant
  d'toucher au client Tauri/`ItemClient` desktop.
- **Signatures d'API Tauri non vérifiées** : ce document ne fige aucune
  signature Rust/Tauri précise (`tauri::api::process::Command`, plugins
  `fs`/`dialog`) — à vérifier contre la documentation/les types réels de la
  version de Tauri utilisée au moment de l'implémentation (piège CLAUDE.md
  #3), pas depuis ce document.

## 8. Découpage en tâches attendu pour le plan

À détailler par `writing-plans`, ordre contraint par les dépendances :

1. Grep + décision go/no-go geospatial (§5) — bloquant pour la suite de la
   Phase F.
2. Jeton + validation `Host` sur le sidecar existant, TDD par falsification
   (§4) — indépendant du freeze, peut être fait en parallèle de la tâche 1.
3. Freeze PyInstaller de l'entrypoint réel + job CI `windows-latest` qui
   l'exécute sur un cycle réel (§5).
4. Bootstrap `desktop-etl/src-tauri/` minimal : spawn du binaire de la
   tâche 3, lecture handshake, injection du jeton (§3.3).
5. Build Vite desktop (`shell/src/desktop/`) + `ItemClient` desktop (§3.1,
   §3.2).
6. Intégration : webview Tauri charge le build de la tâche 5, pointé sur le
   sidecar de la tâche 4 — premier lancement bout-en-bout manuel sur la VM
   Windows.
7. E2E golden path Tauri WebDriver (§6), rejoué en CI `windows-latest`.
8. Vérification finale : suite complète (Linux + Windows), revue de
   branche, mise à jour CLAUDE.md/ledger.
