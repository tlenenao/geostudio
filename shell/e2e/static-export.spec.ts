// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { readFile, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Sert shell/dist-export/ (bâti par `npm run build:export-runtime`, Task 10)
// + un geostudio-app-config.json fabriqué à la main pour ce test — aucune
// route https://core.test n'est jamais enregistrée dans ce fichier (à la
// différence de tous les autres specs e2e/*.ts qui appellent mockCore(page)) :
// c'est la preuve que le mode Statique n'a besoin d'aucun backend.
// `shell/package.json` a `"type": "module"` : __dirname n'existe pas ici
// (contrairement au sketch illustratif du plan) — même patron que
// e2e/external-widget-server.mjs pour dériver un chemin absolu en ESM.
const DIST_EXPORT = fileURLToPath(new URL("../dist-export", import.meta.url));

const FROZEN_CONFIG = {
  kind: "app", theme: {}, navigationMode: "tabs", variables: [], messages: [],
  dataSources: [
    { id: "s1", type: "static", service: "core", layer: "", query: { records: [{ id: 1, properties: { name: "Alpha" } }] } },
  ],
  pages: [{
    id: "p1", name: "P1", onEnter: [],
    layout: { type: "grid", breakpoints: {}, items: [{ id: "w1", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s1" } }] },
  }],
};

async function startStaticServer(): Promise<{ server: Server; url: string }> {
  const server = createServer(async (req, res) => {
    if (req.url === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(FROZEN_CONFIG));
      return;
    }
    const filePath = req.url === "/" || !req.url ? "/index.export.html" : req.url;
    try {
      const body = await readFile(path.join(DIST_EXPORT, filePath.replace(/^\//, "")));
      const contentType = filePath.endsWith(".js") ? "application/javascript" : filePath.endsWith(".css") ? "text/css" : "text/html";
      res.setHeader("Content-Type", contentType);
      res.end(body);
    } catch {
      res.statusCode = 404;
      res.end("not found");
    }
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return { server, url: `http://127.0.0.1:${port}` };
}

test("static export bundle renders with zero GeoStudio backend", async ({ page }) => {
  // Garde-fou : ce test dépend d'un artefact bâti localement
  // (`npm run build:export-runtime`, Task 10) qui n'est pas commité
  // (dist-export/ est gitignored) et n'est pas reconstruit par le
  // webServer de playwright.config.ts (qui ne bâtit que l'app normale).
  // On saute proprement plutôt que d'échouer de façon opaque si absent —
  // même esprit que les specs @pytest.mark.playwright/@pytest.mark.qgis
  // du cœur pour une dépendance optionnelle non installée.
  await access(path.join(DIST_EXPORT, "index.export.html")).catch(() => {
    test.skip(true, "dist-export/index.export.html absent — lancer `npm run build:export-runtime` avant ce test");
  });

  const { server, url } = await startStaticServer();
  try {
    await page.goto(url);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
  } finally {
    server.close();
  }
});
