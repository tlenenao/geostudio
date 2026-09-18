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
