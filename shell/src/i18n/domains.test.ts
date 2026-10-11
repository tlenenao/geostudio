// SPDX-License-Identifier: Apache-2.0
// Garde de REV-307 b : tout fichier de production qui cite une clé d'un domaine
// du catalogue doit importer ce domaine (sinon `t()` rendrait la clé brute en
// production, là où les tests — qui importent `domains/all` — ne le voient pas),
// et aucun domaine ne doit être importé par le noyau de démarrage.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts"))
      out.push(full);
  }
  return out;
}

const DOMAINS = readdirSync(join(__dirname, "domains"))
  .filter((f) => f.endsWith(".ts") && f !== "all.ts")
  .map((f) => f.replace(/\.ts$/, ""));

function prefixesOf(domain: string): string[] {
  const text = readFileSync(join(__dirname, "domains", `${domain}.ts`), "utf-8");
  return [...new Set([...text.matchAll(/^\s+"([A-Za-z0-9]+)\.[^"]+":/gm)].map((m) => m[1]))];
}

describe("domaines du catalogue i18n", () => {
  it("chaque fichier qui cite une clé d'un domaine importe ce domaine", () => {
    const missing: string[] = [];
    const files = walk(SRC).filter((f) => !f.includes("/i18n/") && !f.includes("/test/"));
    for (const domain of DOMAINS) {
      const prefixes = prefixesOf(domain);
      for (const file of files) {
        const text = readFileSync(file, "utf-8");
        const cites = prefixes.some((p) => new RegExp(`"${p}\\.[A-Za-z0-9.]+"`).test(text));
        const imports = new RegExp(`import "[./]+/i18n/domains/${domain}";`).test(text);
        if (cites && !imports) missing.push(`${file.replace(SRC, "src")} -> ${domain}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("le noyau de démarrage ne dépend d'aucun domaine (hors types)", () => {
    const text = readFileSync(join(__dirname, "index.ts"), "utf-8");
    const runtimeImports = text.split("\n").filter((l) => /^import (?!type)/.test(l));
    expect(runtimeImports.filter((l) => l.includes("domains/"))).toEqual([]);
  });

  it("un préfixe de clé appartient à un seul domaine", () => {
    const seen = new Map<string, string>();
    for (const domain of DOMAINS) {
      for (const prefix of prefixesOf(domain)) {
        expect(seen.get(prefix), `préfixe ${prefix}`).toBeUndefined();
        seen.set(prefix, domain);
      }
    }
  });
});
