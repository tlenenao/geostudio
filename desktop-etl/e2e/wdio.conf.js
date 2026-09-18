// SPDX-License-Identifier: Apache-2.0
// desktop-etl/e2e/wdio.conf.js
import os from "os";
import path from "path";
import { spawn, spawnSync } from "child_process";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
let tauriDriver;
let exiting = false;

export const config = {
  host: "127.0.0.1",
  port: 4444,
  specs: ["./specs/**/*.js"],
  maxInstances: 1,
  capabilities: [
    {
      maxInstances: 1,
      "tauri:options": {
        application: "../src-tauri/target/debug/geostudio-desktop-etl.exe",
      },
    },
  ],
  reporters: ["spec"],
  framework: "mocha",
  mochaOpts: { ui: "bdd", timeout: 60000 },
  onPrepare: () => {
    // desktop-etl/src-tauri est un projet Cargo pur (pas de package.json,
    // donc pas de script npm "tauri") -- appel direct de `cargo tauri build`.
    spawnSync("cargo", ["tauri", "build", "--", "--debug", "--no-bundle"], {
      cwd: path.resolve(__dirname, "../src-tauri"),
      stdio: "inherit",
      shell: true,
    });
  },
  beforeSession: () => {
    tauriDriver = spawn(path.resolve(os.homedir(), ".cargo", "bin", "tauri-driver"), [], {
      stdio: [null, process.stdout, process.stderr],
    });
    tauriDriver.on("error", (error) => {
      console.error("tauri-driver error:", error);
      process.exit(1);
    });
    tauriDriver.on("exit", (code) => {
      if (!exiting) {
        console.error("tauri-driver exited with code:", code);
        process.exit(1);
      }
    });
  },
  afterSession: () => closeTauriDriver(),
};

function closeTauriDriver() {
  exiting = true;
  tauriDriver?.kill();
}
process.on("exit", closeTauriDriver);
process.on("SIGINT", closeTauriDriver);
