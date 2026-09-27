// SPDX-License-Identifier: Apache-2.0
// Filet anti-régression D43 (docs/superpowers/specs/
// 2026-09-27-vague-c-polish-a11y-onboarding-design.md, SP-C2) :
// shell/e2e/a11y-audit.spec.ts n'auditait que 17 des 29 routes déclarées
// dans routes.tsx (12 manquantes, trouvées en revue de code — le diagnostic
// d'origine ne les comptait pas). Même patron d'extraction mécanique que
// routeReachability.test.ts (D01/GAP-80) : lire les deux fichiers en texte
// brut, jamais monter le routeur ni exécuter Playwright ici — ce test ne
// prouve pas qu'un audit passe, il prouve qu'un audit EXISTE pour chaque
// route déclarée, ou qu'elle est listée dans une allowlist explicite avec sa
// raison.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

const ROUTES_FILE = join(__dirname, "routes.tsx");
const A11Y_AUDIT_FILE = join(__dirname, "..", "..", "e2e", "a11y-audit.spec.ts");

// Routes volontairement hors périmètre de l'audit a11y automatisé — chaque
// entrée nomme la raison, jamais un simple "TODO". Ne pas ajouter une route
// ici pour faire taire ce test sans avoir vérifié qu'elle est vraiment hors
// périmètre.
const ALLOWLIST: Record<string, string> = {
  "/internal/kit-gallery":
    "galerie interne de développement (SP-29b), jamais exposée en production",
};

function extractDeclaredRoutePaths(): string[] {
  const content = readFileSync(ROUTES_FILE, "utf-8");
  return [...content.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1]);
}

function extractAuditedGotoPaths(): string[] {
  const content = readFileSync(A11Y_AUDIT_FILE, "utf-8");
  // Volontairement strict : seuls les littéraux "page.goto("...")" entre
  // guillemets doubles sont reconnus (patron déjà suivi par toutes les
  // routes de ce fichier, y compris celles ajoutées par ce plan) — un futur
  // ajout en template literal (`page.goto(\`/x/${y}\`)`) ne serait pas
  // détecté, choix assumé pour rester aussi simple que routeReachability.
  return [...content.matchAll(/page\.goto\("([^"]+)"\)/g)].map((m) => m[1]);
}

// Convertit un chemin déclaré ("/apps/:pk/:pageId?") en RegExp de
// correspondance contre un `page.goto("...")` littéral ("/apps/1"). Un
// segment ":nom" est un paramètre requis (n'importe quelle valeur, jamais
// "/"), un segment ":nom?" un paramètre optionnel final (React Router v6 —
// seule route de ce dépôt à en porter un : "/apps/:pk/:pageId?") : son "/"
// précédent devient optionnel avec lui.
function routePathToRegex(path: string): RegExp {
  const OPTIONAL_MARKER = "\u0000OPTIONAL\u0000";
  const segments = path.split("/").map((segment) => {
    if (segment.startsWith(":") && segment.endsWith("?")) return OPTIONAL_MARKER;
    if (segment.startsWith(":")) return "[^/]+";
    return segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  });
  const joined = segments.join("/").replace(new RegExp(`/${OPTIONAL_MARKER}`, "g"), "(?:/[^/]+)?");
  return new RegExp(`^${joined}$`);
}

test("chaque route de routes.tsx a un page.goto(...) dans a11y-audit.spec.ts, ou une exemption listée", () => {
  const declared = extractDeclaredRoutePaths();
  const audited = extractAuditedGotoPaths();
  const uncovered = declared.filter((path) => {
    if (path in ALLOWLIST) return false;
    const regex = routePathToRegex(path);
    return !audited.some((goto) => regex.test(goto));
  });
  expect(uncovered).toEqual([]);
});

test("l'allowlist ne porte que des routes réellement déclarées", () => {
  // Filet inverse : une entrée d'allowlist qui survit à un renommage/retrait
  // de route dans routes.tsx ne doit pas rester une exemption silencieuse
  // pour une route qui n'existe plus.
  const declared = new Set(extractDeclaredRoutePaths());
  for (const path of Object.keys(ALLOWLIST)) {
    expect(declared.has(path), `route allowlistée introuvable : ${path}`).toBe(true);
  }
});
