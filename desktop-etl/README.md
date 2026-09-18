# desktop-etl

Application Tauri (Windows uniquement en v1) qui embarque le sidecar
Python `core/scripts/pipeline_sidecar.py` (gelé PyInstaller, Tâche 2 de
`docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md`) et le canvas
pipeline existant du shell (`shell/src/desktop/entry.tsx`, Tâche 5).

## Développement (Windows uniquement)

1. Geler le sidecar (ou télécharger l'artefact CI de
   `.github/workflows/desktop-etl-sidecar-freeze.yml`) :
   `cd core && uv run pyinstaller --onefile --name pipeline-sidecar --paths . --collect-all dlt scripts/pipeline_sidecar.py`
2. `node desktop-etl/scripts/prepare-sidecar-binary.mjs core/dist/pipeline-sidecar.exe`
3. `cd shell && npm run build:desktop-runtime`
4. `cd desktop-etl/src-tauri && cargo tauri dev` (ou `cargo run` si le
   plugin CLI `tauri` n'est pas installé globalement — voir
   `cargo install tauri-cli --version "^2"`).

## Pièges rencontrés (Tâche 3, vérification Windows réelle)

- **`icons/icon.ico` manquant** — `tauri-build` exige une icône Windows
  pour générer la ressource `.exe` ; absente du plan initial (aucune tâche
  ne la créait). `icons/` a été généré par `cargo tauri icon
  icon-source.png` (icône plate de substitution, teinte
  `#0d9488`) — **à remplacer par la vraie identité visuelle GeoStudio
  avant toute diffusion**, `icon-source.png` sert de source pour
  régénérer (`cargo tauri icon <nouvelle-source-1024×1024>`).
- **`cargo check`/`cargo build` échouent sur un chemin UNC** (`CARGO_TARGET_DIR`
  par défaut sous `\\wsl.localhost\...` quand le dépôt est ouvert depuis
  WSL) — erreur `incremental compilation: could not create session
  directory lock file`. Contournement : positionner `CARGO_TARGET_DIR` sur
  un chemin local Windows (ex. `$env:CARGO_TARGET_DIR =
  'C:\Users\<vous>\geostudio-desktop-etl-target'`) avant toute commande
  `cargo` lancée depuis un chemin UNC.

## Pièges rencontrés (Tâche 6, intégration bout-en-bout réelle)

Golden path (créer un pipeline `reader.file`→`writer.file`, l'exécuter, en
vérifier la sortie) vérifié réel sur Windows le 2026-09-18 — 5 défauts
trouvés et corrigés, aucun visible avant un lancement réel de l'app :

- **`main.rs` passait le mauvais nom au sidecar** —
  `app.shell().sidecar("binaries/pipeline-sidecar")` au lieu du nom nu
  `"pipeline-sidecar"` : `tauri-plugin-shell` résout ce nom relativement au
  dossier de l'exécutable final, sans le préfixe `binaries/` ni le
  suffixe de triplet-cible — c'est sous ce nom nu que Tauri copie le
  `externalBin` à côté du binaire. Le spawn échouait toujours avec
  `Io(NotFound)`.
- **`vite.desktop.config.ts` produisait `index.desktop.html`**, jamais
  chargé par Tauri (`frontendDist` exige `index.html` à la racine, sans
  moyen de configurer un autre nom) — `asset not found: index.html` au
  lancement. Un plugin Vite renomme la sortie après build.
- **Course au démarrage confirmée réelle** (anticipée par la Tâche 5,
  jamais vérifiée avant) : le premier `invoke("get_sidecar_connection")`
  de la webview arrive presque toujours avant que `.setup()` (Rust) ait
  fini de peupler `SidecarState`, rejetant avec la chaîne brute "sidecar
  not ready yet" → écran "Erreur de démarrage : undefined" à chaque
  lancement. `entry.tsx` réessaie maintenant avec un court délai.
- **CORS totalement absent du sidecar** — la webview Tauri (origine
  `http://tauri.localhost`) appelle le sidecar en cross-origin
  (`127.0.0.1:<port>`) ; sans `CORSMiddleware`, chaque `fetch()` était
  bloqué côté navigateur avant même d'atteindre les routes, laissant React
  Query en `isLoading` indéfiniment sans jamais lever d'erreur visible
  ("Chargement…" perpétuel). Le plus difficile à diagnostiquer des cinq —
  trouvé en ouvrant les DevTools WebView2 (`F12`) puis en lisant le
  code source, pas par un message d'erreur explicite.
- **`DesktopItemClient.getItem()` non implémenté** — la route
  `/pipelines/:pk/edit` appelle aussi `useItem(pk)` (garde de permission
  `hasPermission(itemQuery.data, "write")`), pas seulement
  `getPipelineConfig(pk)`. `getItem()` rejetait toujours (méthode
  générique laissée hors périmètre desktop) → "Pipeline introuvable."
  juste après un `Enregistrer` réussi, sur le tout premier pipeline
  jamais créé dans l'app réelle.

Après ces 5 correctifs, le golden path complet a été rejoué avec succès :
statut `succeeded`, compteurs de lignes affichés sur les deux nœuds,
fichier `out.gpkg` réel (98 Ko) produit sur disque à partir d'un
`in.geojson` à 2 features.
