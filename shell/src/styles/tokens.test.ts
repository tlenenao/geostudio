// SPDX-License-Identifier: Apache-2.0
/**
 * Contrat des tokens : tout token défini dans une ambiance doit l'être dans
 * les trois blocs.
 *
 * Le bug classique d'une page à deux thèmes est un token défini uniquement
 * dans le bloc sombre : la page rend alors du texte d'une ambiance sur le fond
 * de l'autre. Ce test l'interdit mécaniquement, plutôt que de compter sur la
 * relecture.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// NOTE : ne pas résoudre ce chemin via `new URL("./tokens.css", import.meta.url)`.
// Sous l'environnement `jsdom` de ce dépôt (vitest.config), Vitest substitue à
// tout `URL` importé de "node:url" une classe compatible JSDOM dont le
// constructeur à 2 arguments ignore la base `file://` et résout la référence
// relative contre l'URL de document par défaut de jsdom
// (`http://localhost:3000`) — `fileURLToPath` lève alors "must be of scheme
// file", y compris une fois `tokens.css` créé. `fileURLToPath(import.meta.url)`
// seul n'est pas affecté : on construit le chemin avec `node:path` à la place.
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "tokens.css"), "utf8");

function block(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `bloc introuvable : ${selector}`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error(`bloc non fermé : ${selector}`);
}

function tokensOf(source: string): Set<string> {
  return new Set([...source.matchAll(/--gs-([a-z0-9-]+)\s*:/g)].map((m) => m[1]));
}

const LIGHT = tokensOf(block(":root {"));
const SYSTEM_DARK = tokensOf(block(':root:not([data-theme="light"])'));
const EXPLICIT_DARK = tokensOf(block(':root[data-theme="dark"]'));

describe("contrat des tokens", () => {
  it("définit une palette claire non vide", () => {
    expect(LIGHT.size).toBeGreaterThan(20);
  });

  it("redéfinit exactement les mêmes tokens dans l'ambiance sombre système", () => {
    expect([...SYSTEM_DARK].sort()).toEqual([...LIGHT].sort());
  });

  it("redéfinit exactement les mêmes tokens dans l'ambiance sombre explicite", () => {
    expect([...EXPLICIT_DARK].sort()).toEqual([...LIGHT].sort());
  });

  it("porte les six noms du contrat partagé avec le Theme des apps", () => {
    // spec §5.1 — c'est ce qui rend la marque blanche possible sans second système
    for (const name of ["primary", "background", "surface", "text", "muted", "border"]) {
      expect(LIGHT.has(name), `token du contrat partagé absent : --gs-${name}`).toBe(true);
    }
  });

  it("expose les tokens de carte, qui ne peuvent pas être dérivés", () => {
    for (const name of ["map-land", "map-alt", "map-water", "map-road"]) {
      expect(LIGHT.has(name), `token de carte absent : --gs-${name}`).toBe(true);
    }
  });

  it("expose les tokens d'élévation", () => {
    for (const name of ["shadow-sm", "shadow-md", "shadow-lg"]) {
      expect(LIGHT.has(name), `token d'élévation absent : --gs-${name}`).toBe(true);
    }
  });

  it("ne déclare aucune couleur en dur hors des trois blocs d'ambiance", () => {
    const outside = css
      .replace(block(":root {"), "")
      .replace(block(':root:not([data-theme="light"])'), "")
      .replace(block(':root[data-theme="dark"]'), "");
    expect(outside).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
