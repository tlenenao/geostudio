// SPDX-License-Identifier: Apache-2.0
// desktop-etl/src-tauri/src/main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SidecarConnection {
    base_url: String,
    token: String,
}

struct SidecarState(Mutex<Option<SidecarConnection>>);

#[tauri::command]
fn get_sidecar_connection(state: tauri::State<SidecarState>) -> Result<SidecarConnection, String> {
    state
        .0
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "sidecar not ready yet".to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(SidecarState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![get_sidecar_connection])
        .setup(|app| {
            let token = uuid::Uuid::new_v4().to_string();
            // tauri-plugin-shell résout ce nom relativement au dossier de
            // l'exécutable final (relative_command_path, process/mod.rs) —
            // il faut donc le nom NU, sans le préfixe "binaries/" ni le
            // suffixe de triplet-cible : c'est sous cette forme que Tauri
            // copie le externalBin à côté du binaire final (bundle ou
            // `cargo tauri build --debug --no-bundle`), jamais dans un
            // sous-dossier binaries/. Vérifié en faisant échouer le spawn
            // avec le chemin complet (Tâche 6, vérification Windows
            // réelle) : Io(NotFound) — la ressource existe bien mais pas à
            // ce chemin.
            let sidecar_command = app
                .shell()
                .sidecar("pipeline-sidecar")
                .expect("failed to resolve sidecar binary")
                .env("GEOSTUDIO_SIDECAR_TOKEN", &token);
            let (mut rx, _child) = sidecar_command.spawn().expect("failed to spawn sidecar");

            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stdout(line_bytes) = event {
                        let line = String::from_utf8_lossy(&line_bytes);
                        if let Some(port_str) = line.trim().strip_prefix("PORT=") {
                            if let Ok(port) = port_str.parse::<u16>() {
                                let state = app_handle.state::<SidecarState>();
                                *state.0.lock().unwrap() = Some(SidecarConnection {
                                    base_url: format!("http://127.0.0.1:{port}"),
                                    token: token.clone(),
                                });
                            }
                            break;
                        }
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
