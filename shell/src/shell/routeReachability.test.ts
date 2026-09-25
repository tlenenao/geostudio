// SPDX-License-Identifier: Apache-2.0
// Filet anti-régression D01 (docs/revue/2026-09-24-diagnostic-ui-ux.md §4) :
// une route déclarée dans routes.tsx sans aucun lien entrant ailleurs dans
// le shell est un écran fonctionnel mais invisible (cf. GAP-80/GAP-81,
// SP-46). Ce test lit routes.tsx en texte brut (pas d'exécution du routeur :
// un test générique par exécution devrait mocker tout l'arbre applicatif
// pour peu de valeur ajoutée) et vérifie que chaque chemin statique déclaré
// apparaît au moins une fois ailleurs dans shell/src (un <Link to="...">,
// un navigate("..."), ou une entrée du registre ci-dessous pour les routes
// dont l'absence de lien est un choix assumé).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

const SHELL_SRC = join(__dirname, "..");
const ROUTES_FILE = join(__dirname, "routes.tsx");

// Routes volontairement atteignables uniquement par deep-link (paramétrées,
// ou dont le seul point d'entrée légitime est hors du shell — email,
// partage externe, publication) : ne pas ajouter une route ici pour faire
// taire ce test sans avoir vérifié qu'elle est vraiment deep-link-only.
const DEEP_LINK_ONLY_ROUTES = new Set<string>([
  "/", // racine : atteinte par tout <Link to="/">, trop générique pour un grep utile
  "/login",
  "/logout",
  "/embed/:token",
  "/sites/:slug",
  "/items/:pk",
  "/maps/:pk",
  "/datasets/:pk/edit",
  "/apps/:pk/edit",
  "/pipelines/new",
  "/pipelines/:pk/edit",
  "/datasets/visual-query/new",
  "/datasets/visual-query/:pipelinePk/edit",
  "/reports/new",
  "/reports/:pk/edit",
  "/internal/kit-gallery", // galerie interne de développement (SP-29b)
]);

function extractStaticRoutePaths(): string[] {
  const content = readFileSync(ROUTES_FILE, "utf-8");
  const matches = [...content.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1]);
  // Seules les routes statiques (sans ":") sont vérifiables par un grep
  // littéral du chemin — les routes paramétrées sont couvertes une à une
  // dans DEEP_LINK_ONLY_ROUTES ci-dessus ou par leurs propres tests.
  return matches.filter((p) => !p.includes(":") && !DEEP_LINK_ONLY_ROUTES.has(p));
}

function allSourceFilesExcludingRoutes(): string[] {
  const files: string[] = [];
  function walk(dir: string) {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (entry === "node_modules") continue;
        walk(full);
      } else if (
        (entry.endsWith(".ts") || entry.endsWith(".tsx")) &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".test.tsx") &&
        full !== ROUTES_FILE
      ) {
        files.push(full);
      }
    }
  }
  walk(SHELL_SRC);
  return files;
}

test("chaque route statique de routes.tsx a un lien entrant ailleurs dans shell/src, ou est listée deep-link-only", () => {
  const paths = extractStaticRoutePaths();
  const files = allSourceFilesExcludingRoutes();
  const contents = files.map((f) => readFileSync(f, "utf-8"));
  const unreachable = paths.filter((p) => !contents.some((c) => c.includes(`"${p}"`)));
  expect(unreachable).toEqual([]);
});
