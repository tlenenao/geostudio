// desktop-etl/scripts/prepare-sidecar-binary.mjs
// Copie/renomme le binaire gelé (Tâche 2) avec le suffixe target-triple que
// Tauri exige pour un externalBin (docs Tauri v2, "sidecar naming").
import { execSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const sourcePath = process.argv[2];
if (!sourcePath) {
  console.error("usage: node prepare-sidecar-binary.mjs <path-to-frozen-binary>");
  process.exit(2);
}

const targetTriple = execSync("rustc --print host-tuple").toString().trim();
const ext = process.platform === "win32" ? ".exe" : "";
const destDir = resolve(__dirname, "../src-tauri/binaries");
mkdirSync(destDir, { recursive: true });
const destPath = resolve(destDir, `pipeline-sidecar-${targetTriple}${ext}`);
copyFileSync(sourcePath, destPath);
console.log(`copied ${sourcePath} -> ${destPath}`);
