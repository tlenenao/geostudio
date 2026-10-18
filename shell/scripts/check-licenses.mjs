// SPDX-License-Identifier: Apache-2.0
// AUD-111 : refuse les dépendances npm installées sous GPL/AGPL/LGPL, sauf entrée de
// scripts/license-exceptions.json ({"<paquet>": "raison"}). Usage : node scripts/check-licenses.mjs
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const BAD = /\b(A|L)?GPL\b/i;

export function licenseOf(pkg) {
  const l = pkg.license ?? pkg.licenses;
  if (Array.isArray(l)) return l.map((x) => x.type ?? x).join(" OR ");
  return typeof l === "object" && l ? (l.type ?? "") : (l ?? "");
}

export function violations(pkgs, exceptions) {
  return (
    pkgs
      // « MIT OR GPL » : on peut choisir l'alternative permissive, donc bad = toutes les branches.
      .filter(
        (p) => p.license.split(/\s+OR\s+/i).every((l) => BAD.test(l)) && !(p.name in exceptions),
      )
      .map((p) => `${p.name}: ${p.license}`)
      .sort()
  );
}

function installed(root) {
  const out = [];
  for (const d of readdirSync(root)) {
    const dirs = d.startsWith("@") ? readdirSync(join(root, d)).map((s) => join(d, s)) : [d];
    for (const dir of dirs) {
      const f = join(root, dir, "package.json");
      if (!existsSync(f)) continue;
      const pkg = JSON.parse(readFileSync(f, "utf8"));
      out.push({ name: pkg.name ?? dir, license: String(licenseOf(pkg)) });
    }
  }
  return out;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const exceptions = JSON.parse(readFileSync(join(here, "license-exceptions.json"), "utf8"));
  const pkgs = installed(join(here, "..", "node_modules"));
  const bad = violations(pkgs, exceptions);
  console.log(bad.join("\n") || `licences npm : ${pkgs.length} paquets, aucune violation`);
  process.exit(bad.length ? 1 : 0);
}
