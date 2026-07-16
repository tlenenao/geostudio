#!/usr/bin/env node
// Filtre `npm audit --json` : bloque sur toute vulnérabilité High/Critical
// non listée dans ALLOWLIST. Un paquet alloué reste bloquant sur tout NOUVEAU
// paquet vulnérable — seule l'entrée exacte du nom de paquet est ignorée.
import { readFileSync } from "node:fs";

const ALLOWLIST = {
  "lodash-es":
    "Transitif via cel-js@0.8.2 -> chevrotain@11.0.3 (GHSA-r5fr-rjxr-66jc " +
    "et avis liés). Aucun correctif upstream : chevrotain 11.0.3 est la " +
    "dernière version publiée. Risque jugé faible : lodash-es n'est utilisé " +
    "qu'en interne par le parseur CEL (tokenisation), jamais avec un template " +
    "contrôlé par un utilisateur non fiable. Revu 2026-07-16 — à retirer dès " +
    "qu'un correctif existe en amont.",
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
