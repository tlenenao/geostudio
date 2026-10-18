#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";

function initialChunkFiles(manifest, entryKey) {
  const seen = new Set();
  const files = new Set();
  function walk(key) {
    if (seen.has(key)) return;
    seen.add(key);
    const entry = manifest[key];
    if (!entry) return;
    files.add(entry.file);
    for (const css of entry.css ?? []) files.add(css);
    for (const imp of entry.imports ?? []) walk(imp);
    // volontairement : PAS entry.dynamicImports — c'est tout l'intérêt du
    // découpage par route (Task 8), un chunk atteint seulement par un
    // import dynamique ne doit jamais compter dans la charge initiale.
  }
  walk(entryKey);
  return files;
}

function main(manifestPath, thresholdPath) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const distDir = dirname(dirname(manifestPath)); // dist/.vite/manifest.json -> dist/
  const entryKey = Object.keys(manifest).find((k) => manifest[k].isEntry);
  if (!entryKey) {
    console.error("Aucune entrée trouvée dans le manifeste Vite.");
    process.exit(1);
  }
  // L8 : le service worker est émis hors du graphe de l'entrée (jamais compté ci-dessous) ; on
  // garantit seulement qu'il existe et que l'injection du plugin a bien eu lieu.
  let sw = "";
  try {
    sw = readFileSync(join(distDir, "sw.js"), "utf-8");
  } catch {
    console.error(
      "ÉCHEC : dist/sw.js absent (vite.serviceWorker.ts n'a pas émis le service worker).",
    );
    process.exit(1);
  }
  if (sw.includes("__BUILD_ID__") || sw.includes("__PRECACHE_")) {
    console.error("ÉCHEC : dist/sw.js contient des marqueurs d'injection non remplacés.");
    process.exit(1);
  }
  const files = initialChunkFiles(manifest, entryKey);
  let totalBytes = 0;
  for (const file of files) {
    totalBytes += readFileSync(join(distDir, file)).length;
  }
  const totalKb = totalBytes / 1024;
  const thresholdKb = Number(readFileSync(thresholdPath, "utf-8").trim());
  console.log(
    `Charge JS/CSS initiale mesurée : ${totalKb.toFixed(1)} Ko (seuil : ${thresholdKb} Ko)`,
  );
  if (totalKb > thresholdKb) {
    console.error(`ÉCHEC : charge initiale ${totalKb.toFixed(1)} Ko > seuil ${thresholdKb} Ko`);
    process.exit(1);
  }
}

main(process.argv[2], process.argv[3]);
