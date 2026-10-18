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
  const files = initialChunkFiles(manifest, entryKey);
  let totalBytes = 0;
  const sizes = [];
  for (const file of files) {
    const bytes = readFileSync(join(distDir, file)).length;
    totalBytes += bytes;
    sizes.push([file, bytes]);
  }
  const totalKb = totalBytes / 1024;
  const thresholdKb = Number(readFileSync(thresholdPath, "utf-8").trim());
  console.log(
    `Charge JS/CSS initiale mesurée : ${totalKb.toFixed(1)} Ko (seuil : ${thresholdKb} Ko)`,
  );
  // AUD-138 : sans contributeurs nommés, un dépassement est un nombre sans piste ; la marge
  // restante signale un seuil devenu fragile avant qu'il ne casse.
  const top = sizes
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([f, b]) => `${(b / 1024).toFixed(1)} Ko ${f}`);
  console.log(`Plus gros contributeurs :\n  ${top.join("\n  ")}`);
  if (totalKb <= thresholdKb && thresholdKb - totalKb < thresholdKb * 0.03) {
    console.warn(
      `AVERTISSEMENT : marge de ${(thresholdKb - totalKb).toFixed(1)} Ko (< 3 %) — déplacer du code vers un import dynamique plutôt que relever le seuil.`,
    );
  }
  if (totalKb > thresholdKb) {
    console.error(`ÉCHEC : charge initiale ${totalKb.toFixed(1)} Ko > seuil ${thresholdKb} Ko`);
    process.exit(1);
  }
}

main(process.argv[2], process.argv[3]);
