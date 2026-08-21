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
  kind: "app",
  theme: {},
  navigationMode: "tabs",
  variables: [],
  messages: [],
  dataSources: [
    {
      id: "s1",
      type: "static",
      service: "core",
      layer: "",
      query: { records: [{ id: 1, properties: { name: "Alpha" } }] },
    },
  ],
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

// `prefix` lets a test serve the bundle under a non-root sub-path (e.g.
// "/mon-app") — the case that actually exercises Vite's `base` setting
// (C1): served at "/" every asset URL is indistinguishable whether it's
// absolute-from-root or relative, so a root-only server can't catch a
// regression there.
async function startStaticServer(prefix = ""): Promise<{ server: Server; url: string }> {
  const server = createServer(async (req, res) => {
    const reqUrl = req.url ?? "/";
    if (prefix && !reqUrl.startsWith(prefix)) {
      res.statusCode = 404;
      res.end("not found");
      return;
    }
    const withoutPrefix = prefix ? reqUrl.slice(prefix.length) || "/" : reqUrl;
    if (withoutPrefix === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(FROZEN_CONFIG));
      return;
    }
    const filePath = withoutPrefix === "/" || !withoutPrefix ? "/index.export.html" : withoutPrefix;
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
  return { server, url: `http://127.0.0.1:${port}` };
}

// Garde-fou partagé : ce fichier dépend d'un artefact bâti localement
// (`npm run build:export-runtime`, Task 10) qui n'est pas commité
// (dist-export/ est gitignored) et n'est pas reconstruit par le
// webServer de playwright.config.ts (qui ne bâtit que l'app normale).
// On saute proprement plutôt que d'échouer de façon opaque si absent —
// même esprit que les specs @pytest.mark.playwright/@pytest.mark.qgis
// du cœur pour une dépendance optionnelle non installée.
async function skipIfNoBuild() {
  await access(path.join(DIST_EXPORT, "index.export.html")).catch(() => {
    test.skip(
      true,
      "dist-export/index.export.html absent — lancer `npm run build:export-runtime` avant ce test",
    );
  });
}

test("static export bundle renders with zero GeoStudio backend", async ({ page }) => {
  await skipIfNoBuild();

  const { server, url } = await startStaticServer();
  try {
    await page.goto(url);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
  } finally {
    server.close();
  }
});

// Regression for C1 (vite.export.config.ts had no `base`, so built asset
// URLs were absolute-from-root `/assets/...` — a bundle unzipped anywhere
// but the server root 404s on every asset, blank page). Serving at "/" (the
// test above) can't catch this: absolute-from-root and relative both work
// there. Serving under a sub-path prefix is the only way to prove the fix.
test("static export bundle renders when served under a non-root sub-path", async ({ page }) => {
  await skipIfNoBuild();

  const { server, url } = await startStaticServer("/mon-app");
  try {
    await page.goto(`${url}/mon-app/index.export.html`);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
  } finally {
    server.close();
  }
});

// Regression for C3: entry.tsx used to pass a fixed `pageId` prop to
// AppRenderer with no `onNavigate`, which permanently pinned the active
// page — nav widgets/tabs/story buttons rendered but did nothing in a
// multi-page export. `navigationMode: "story"` renders built-in
// Précédent/Suivant buttons (AppRenderer.tsx) driven by the same
// handleNavigate path as any other in-app navigation, so it's a minimal
// way to exercise the bug without authoring a nav widget.
const MULTI_PAGE_CONFIG = {
  kind: "app",
  theme: {},
  navigationMode: "story",
  variables: [],
  messages: [],
  dataSources: [
    {
      id: "s1",
      type: "static",
      service: "core",
      layer: "",
      query: { records: [{ id: 1, properties: { name: "Alpha" } }] },
    },
    {
      id: "s2",
      type: "static",
      service: "core",
      layer: "",
      query: { records: [{ id: 2, properties: { name: "Beta" } }] },
    },
  ],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [{ id: "w1", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s1" } }],
  },
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
    {
      id: "p2",
      name: "P2",
      onEnter: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          { id: "w2", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s2" } },
        ],
      },
    },
  ],
};

test("static export bundle can navigate between pages", async ({ page }) => {
  await skipIfNoBuild();

  const server = createServer(async (req, res) => {
    if (req.url === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(MULTI_PAGE_CONFIG));
      return;
    }
    const filePath = req.url === "/" || !req.url ? "/index.export.html" : req.url;
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
    await expect(page.getByText("Beta")).not.toBeVisible();
    await page.getByRole("button", { name: "Suivant" }).click();
    await expect(page.getByText("Beta")).toBeVisible({ timeout: 10_000 });
  } finally {
    server.close();
  }
});
