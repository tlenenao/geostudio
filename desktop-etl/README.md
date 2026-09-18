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
