#!/usr/bin/env node
// Filtre `npm audit --json` : bloque sur toute vulnérabilité High/Critical
// non listée dans ALLOWLIST. Un paquet alloué reste bloquant sur tout NOUVEAU
// paquet vulnérable — seule l'entrée exacte du nom de paquet est ignorée.
import { readFileSync } from "node:fs";

const IMAGE_SIZE_DOS =
  "Transitif via @deck.gl/geo-layers (3D Tiles, rendu 3D) -> " +
  "@loaders.gl/3d-tiles/@loaders.gl/gltf/@luma.gl/gltf -> " +
  "@loaders.gl/textures -> texture-compressor@1.0.2 (non maintenu, pas de " +
  "version corrigée) -> image-size@0.7.5 (GHSA-w3rx-r6r6-pgpr, " +
  "GHSA-5p2g-fcmc-qvqq — déni de service via parseurs ICNS/JXL/HEIF). " +
  "Risque jugé nul : texture-compressor n'est utilisé par " +
  "@loaders.gl/textures que dans encodeImageURLToCompressedTextureURL, un " +
  "encodeur qui spawn `npx texture-compressor` en CLI Node — jamais appelé " +
  "par notre code (on ne fait que lire/afficher des tilesets 3D Tiles, pas " +
  "en écrire), et de toute façon inatteignable depuis le bundle navigateur " +
  "shipé au client. Revu 2026-08-14 — à retirer si loaders.gl publie un " +
  "correctif upstream (aucun disponible : `npm audit fix` ne propose qu'un " +
  "downgrade majeur vers @loaders.gl/3d-tiles@3.0.14, une régression).";

const ALLOWLIST = {
  "lodash-es":
    "Transitif via cel-js@0.8.2 -> chevrotain@11.0.3 (GHSA-r5fr-rjxr-66jc " +
    "et avis liés). Aucun correctif upstream : chevrotain 11.0.3 est la " +
    "dernière version publiée. Risque jugé faible : lodash-es n'est utilisé " +
    "qu'en interne par le parseur CEL (tokenisation), jamais avec un template " +
    "contrôlé par un utilisateur non fiable. Revu 2026-07-16 — à retirer dès " +
    "qu'un correctif existe en amont.",
  "@deck.gl/geo-layers": IMAGE_SIZE_DOS,
  "@deck.gl/mesh-layers": IMAGE_SIZE_DOS,
  "@loaders.gl/3d-tiles": IMAGE_SIZE_DOS,
  "@loaders.gl/gltf": IMAGE_SIZE_DOS,
  "@loaders.gl/textures": IMAGE_SIZE_DOS,
  "@luma.gl/gltf": IMAGE_SIZE_DOS,
  "image-size": IMAGE_SIZE_DOS,
  "texture-compressor": IMAGE_SIZE_DOS,
};

const path = process.argv[2];
if (!path) {
  console.error("usage: check-npm-audit.mjs <npm-audit.json>");
  process.exit(2);
}

const report = JSON.parse(readFileSync(path, "utf-8"));
const vulnerabilities = report.vulnerabilities ?? {};

const blocking = [];
for (const [pkg, info] of Object.entries(vulnerabilities)) {
  if (info.severity !== "high" && info.severity !== "critical") continue;
  if (Object.prototype.hasOwnProperty.call(ALLOWLIST, pkg)) {
    console.log(`ignoré (accepted-risk documenté) : ${pkg} (${info.severity})`);
    continue;
  }
  blocking.push(`${pkg} (${info.severity})`);
}

if (blocking.length > 0) {
  console.error("Vulnérabilités High/Critical non couvertes par l'allowlist :");
  for (const b of blocking) console.error(`  - ${b}`);
  process.exit(1);
}

console.log("Aucune vulnérabilité High/Critical bloquante (hors accepted-risk documenté).");
