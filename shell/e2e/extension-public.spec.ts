// SPDX-License-Identifier: Apache-2.0
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test, expect, type Page } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

// L10 (AUD-107 / AUD-109) : un widget d'extension s'affiche sur la surface publique
// `/embed/:token` (client sans jeton), et le SRI épinglé au manifeste est vérifié par
// le navigateur avant exécution du module (hébergé en cross-origin sur le port 4174).
const TOKEN = "e2e-embed-ext";
const WIDGET_JS = readFileSync(
  fileURLToPath(new URL("../../examples/external-widget/widget.js", import.meta.url)),
);
const GOOD_SRI = "sha384-" + createHash("sha384").update(WIDGET_JS).digest("base64");
const BAD_SRI = "sha384-" + createHash("sha384").update("autre contenu").digest("base64");

function manifest(integrity: string | null) {
  return {
    id: "example.external-counter",
    tag: "external-example-widget",
    label: "Compteur externe (exemple)",
    moduleUrl: "http://localhost:4174/widget.js",
    props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
    events: ["changed"],
    actions: ["reset"],
    defaultSize: { w: 2, h: 2 },
    permissions: { collections: "all" },
    sdkVersion: 1,
    integrity,
    connectHosts: [],
    imgHosts: [],
  };
}

async function mockEmbed(page: Page, integrity: string | null) {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: {
        itemId: "app-ext",
        title: "App extension",
        resourceType: "app",
        expiresAt: "2099-01-01",
      },
    }),
  );
  await page.route("**/v1/extensions*", (route) =>
    route.fulfill({ json: { extensions: [manifest(integrity)] } }),
  );
  await page.route("**/v1/configs/by-item/app-ext*", (route) =>
    route.fulfill({
      json: {
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: {
            type: "grid",
            items: [
              {
                id: "w1",
                widget: "example.external-counter",
                x: 0,
                y: 0,
                w: 4,
                h: 4,
                props: { initial: 3 },
              },
            ],
          },
        },
      },
    }),
  );
}

test("AUD-107 : le widget d'extension s'affiche sur /embed/:token (jamais « Widget inconnu »)", async ({
  page,
}) => {
  await mockEmbed(page, null);
  await page.goto(`/embed/${TOKEN}`);
  const widget = page.locator("external-example-widget");
  await expect(widget.getByText("3", { exact: true })).toBeVisible();
  await expect(page.getByText(/Widget inconnu/)).toHaveCount(0);
});

test("AUD-109 : un SRI correct charge le module, un SRI erroné le bloque", async ({ page }) => {
  await mockEmbed(page, GOOD_SRI);
  await page.goto(`/embed/${TOKEN}`);
  await expect(
    page.locator("external-example-widget").getByText("3", { exact: true }),
  ).toBeVisible();

  const tampered = await page.context().newPage();
  await mockEmbed(tampered, BAD_SRI);
  await tampered.goto(`/embed/${TOKEN}`);
  await expect(tampered.getByText("Extension indisponible")).toBeVisible();
  await expect(tampered.locator("external-example-widget")).toHaveCount(0);
});

test("AUD-110 : l'admin importe un manifeste JSON complet (POST) et voit le badge d'intégrité", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let posted: unknown = null;
  const rows: unknown[] = [];
  await page.route("https://core.test/v1/extensions**", async (route) => {
    if (route.request().method() === "POST") {
      posted = route.request().postDataJSON();
      rows.push({ ...(posted as object), enabled: true });
      return route.fulfill({ status: 201, json: posted as object });
    }
    return route.fulfill({ json: { extensions: rows } });
  });
  await page.goto("/admin/extensions");
  await page.getByLabel("Manifeste JSON").fill(JSON.stringify(manifest(GOOD_SRI)));
  await page.getByRole("button", { name: "Importer le manifeste" }).click();
  await expect(page.getByText("Manifeste enregistré.")).toBeVisible();
  expect(posted).toMatchObject({
    id: "example.external-counter",
    integrity: GOOD_SRI,
    sdkVersion: 1,
  });
  await expect(page.getByText("Épinglée (SRI)")).toBeVisible();
});
