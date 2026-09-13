// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";

const TOKEN = "e2e-embed-token";

test("un jeton invité valide rend l'App sans jamais envoyer Authorization", async ({ page }) => {
  const requestsSeen: { url: string; hasAuth: boolean; hasShareHeader: boolean }[] = [];

  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "app-1", title: "App de démo", resourceType: "app", expiresAt: "2099-01-01" },
    }),
  );
  await page.route("**/v1/configs/by-item/app-1*", async (route) => {
    const headers = route.request().headers();
    requestsSeen.push({
      url: route.request().url(),
      hasAuth: "authorization" in headers,
      hasShareHeader: headers["x-share-link-token"] === TOKEN,
    });
    await route.fulfill({
      json: {
        config: {
          kind: "app",
          theme: {},
          dataSources: [
            { id: "ds1", type: "features", service: "core", layer: "incidents", query: {} },
          ],
          messages: [],
          layout: {
            type: "grid",
            items: [
              { id: "w1", widget: "table", x: 0, y: 0, w: 4, h: 4, props: { dataSourceId: "ds1" } },
            ],
          },
        },
      },
    });
  });
  // Le widget Table (DataProvider, cf. shell/src/builder/DataContext.tsx)
  // résout le pk/la géométrie de la collection derrière une source directe
  // (`type: "features"`, `service: "core"`, `layer`, sans `datasetId`) via
  // GET /collections/{layer}/schema avant de requêter ses features — sans ce
  // mock, la requête de schéma reste en attente indéfiniment et le widget
  // n'affiche jamais rien (vérifié contre le code réel, pas supposé).
  await page.route("**/v1/collections/incidents/schema*", async (route) => {
    const headers = route.request().headers();
    requestsSeen.push({
      url: route.request().url(),
      hasAuth: "authorization" in headers,
      hasShareHeader: headers["x-share-link-token"] === TOKEN,
    });
    await route.fulfill({
      json: { collection: "incidents", pk: "id", geometry: null, fields: [] },
    });
  });
  await page.route("**/v1/collections/incidents/items*", async (route) => {
    const headers = route.request().headers();
    requestsSeen.push({
      url: route.request().url(),
      hasAuth: "authorization" in headers,
      hasShareHeader: headers["x-share-link-token"] === TOKEN,
    });
    await route.fulfill({
      json: { type: "FeatureCollection", features: [], numberMatched: 0, numberReturned: 0 },
    });
  });

  await page.goto(`/embed/${TOKEN}`);
  await expect(page.locator("body")).not.toContainText("Chargement");

  expect(requestsSeen.length).toBeGreaterThan(0);
  for (const seen of requestsSeen) {
    expect(seen.hasAuth).toBe(false);
    expect(seen.hasShareHeader).toBe(true);
  }
});

test("un lien vers un type non intégrable affiche un message explicite", async ({ page }) => {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "map-1", title: "Une carte", resourceType: "map", expiresAt: "2099-01-01" },
    }),
  );

  await page.goto(`/embed/${TOKEN}`);

  await expect(page.getByText(/ne peut pas être intégré/i)).toBeVisible();
});

test("un jeton invalide affiche un message explicite, jamais une page blanche", async ({
  page,
}) => {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({ status: 401, json: { detail: "invalid or expired share link" } }),
  );

  await page.goto(`/embed/${TOKEN}`);

  await expect(page.getByText(/expiré ou révoqué/i)).toBeVisible();
});
