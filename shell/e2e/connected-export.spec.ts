// SPDX-License-Identifier: Apache-2.0
// Preuve en conditions réelles (pas assérée) que le mode Connecté (SP-18b)
// fait un vrai fetch cross-origin dans Chromium depuis l'origine du bundle
// exporté vers une origine "cœur" distincte, et que ce fetch part sans
// aucun header Authorization — même esprit que static-export.spec.ts (SP-18a)
// prouvant le mode Statique sans aucun backend : ici on prouve le mode
// Connecté avec un vrai backend, sur un vrai domaine tiers, sans identifiant
// embarqué. La fausse "core" ci-dessous répond avec Access-Control-Allow-
// Origin: * — c'est le comportement que core/app/main.py's CORS middleware
// (Task 5) doit fournir en vrai ; ce test ne remplace pas test_appexport_cors.py,
// il prouve le côté client du contrat.
import { test, expect } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { readFile, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST_EXPORT = fileURLToPath(new URL("../dist-export", import.meta.url));

const CONNECTED_CONFIG = {
  kind: "app",
  theme: {},
  navigationMode: "tabs",
  variables: [],
  messages: [],
  dataSources: [{ id: "s1", type: "features", service: "core", layer: "col1", query: {} }],
  pages: [
    {
      id: "p1",
      name: "P1",
      onEnter: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          { id: "w1", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s1" } },
        ],
      },
    },
  ],
};

async function skipIfNoBuild() {
  await access(path.join(DIST_EXPORT, "index.export.html")).catch(() => {
    test.skip(
      true,
      "dist-export/index.export.html absent — lancer `npm run build:export-runtime` avant ce test",
    );
  });
}

async function startFakeCore(): Promise<{
  server: Server;
  url: string;
  sawAuthHeader: () => boolean;
}> {
  let sawAuthHeader = false;
  const server = createServer((req, res) => {
    if (req.headers.authorization) sawAuthHeader = true;
    res.setHeader("Access-Control-Allow-Origin", "*");
    // SP-57b : le shell prefixe toutes ses routes de cœur par /v1
    // (createBase() l'ajoute à `coreUrl`). Ce faux cœur est un serveur HTTP
    // local, invisible des greps de routes qui ont porté cette migration —
    // et ce test ne s'exécute QUE quand dist-export/ existe (sinon il se
    // skippe), donc il ne tourne jamais en local : le décalage n'a été vu
    // qu'en CI, plusieurs semaines après.
    if (req.url === "/v1/collections/col1/items") {
      res.setHeader("Content-Type", "application/json");
      res.end(
        JSON.stringify({
          type: "FeatureCollection",
          features: [{ id: 1, type: "Feature", properties: { name: "Alpha" }, geometry: null }],
        }),
      );
      return;
    }
    res.statusCode = 404;
    res.end("not found");
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return { server, url: `http://127.0.0.1:${port}`, sawAuthHeader: () => sawAuthHeader };
}

test("connected export bundle renders live data from a real cross-origin core, with no auth header", async ({
  page,
}) => {
  await skipIfNoBuild();

  const fakeCore = await startFakeCore();
  const connection = { coreUrl: fakeCore.url };

  const server = createServer(async (req, res) => {
    const reqUrl = req.url ?? "/";
    if (reqUrl === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(CONNECTED_CONFIG));
      return;
    }
    if (reqUrl === "/geostudio-connection.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(connection));
      return;
    }
    const filePath = reqUrl === "/" ? "/index.export.html" : reqUrl;
    try {
      const body = await readFile(path.join(DIST_EXPORT, filePath.replace(/^\//, "")));
      const contentType = filePath.endsWith(".js")
        ? "application/javascript"
        : filePath.endsWith(".css")
          ? "text/css"
          : "text/html";
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
  const url = `http://127.0.0.1:${port}`;

  try {
    await page.goto(url);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
    expect(fakeCore.sawAuthHeader()).toBe(false);
  } finally {
    server.close();
    fakeCore.server.close();
  }
});
