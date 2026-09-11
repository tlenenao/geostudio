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

// Valeurs hex des tokens d'un bloc, pour le calcul de contraste WCAG ci-dessous
// (tokensOf ci-dessus ne garde que les noms). Les tokens de ce fichier sont
// tous des littéraux hex #rrggbb (cf. le test "ne déclare aucune couleur en
// dur hors des trois blocs d'ambiance" plus bas, qui le garantit).
function valuesOf(source: string): Map<string, string> {
  return new Map(
    [...source.matchAll(/--gs-([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]),
  );
}

// Luminance relative et ratio de contraste WCAG 2.x (formule standard :
// https://www.w3.org/TR/WCAG21/#dfn-relative-luminance).
function relativeLuminance(hex: string): number {
  const [r, g, b] = [hex.slice(1, 3), hex.slice(3, 5), hex.slice(5, 7)].map(
    (h) => parseInt(h, 16) / 255,
  );
  const linearize = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [rl, gl, bl] = [linearize(r), linearize(g), linearize(b)];
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
}

function contrastRatio(hexA: string, hexB: string): number {
  const [lA, lB] = [relativeLuminance(hexA), relativeLuminance(hexB)];
  const [lighter, darker] = lA >= lB ? [lA, lB] : [lB, lA];
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL_TEXT_MIN_CONTRAST = 4.5;

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

describe("contraste WCAG AA (texte normal, seuil 4.5)", () => {
  // REV-176 (--gs-ink-3 assombri en ambiance claire) a montré que ce contrat
  // n'était pas outillé : un token d'encre peut redevenir illisible sur le
  // fond sans qu'aucun test ne le remarque. Ce bloc le vérifie mécaniquement
  // pour les trois niveaux d'encre, dans les deux ambiances.
  const LIGHT_VALUES = valuesOf(block(":root {"));
  const EXPLICIT_DARK_VALUES = valuesOf(block(':root[data-theme="dark"]'));

  it.each([
    ["ambiance claire", LIGHT_VALUES],
    ["ambiance sombre", EXPLICIT_DARK_VALUES],
  ])("%s : ink/ink-2/ink-3 sur background >= 4.5:1", (_label, values) => {
    const background = values.get("background");
    expect(background).toBeDefined();
    for (const name of ["ink", "ink-2", "ink-3"]) {
      const ink = values.get(name);
      expect(ink, `token --gs-${name} introuvable`).toBeDefined();
      const ratio = contrastRatio(ink as string, background as string);
      expect(
        ratio,
        `--gs-${name} sur --gs-background : contraste ${ratio.toFixed(2)}:1, sous le seuil AA`,
      ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT_MIN_CONTRAST);
    }
  });
});
