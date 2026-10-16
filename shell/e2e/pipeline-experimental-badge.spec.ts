// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// Lot 9 : une op expérimentale n'apparaît dans la palette (avec son badge) que si le cœur
// l'expose, c'est-à-dire flag CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED allumé.
const STABLE = {
  "reader.collection": {
    kind: "reader",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
    experimental: false,
  },
};
const EXPERIMENTAL = {
  "writer.slack": {
    kind: "writer",
    paramsSchema: { properties: {}, required: [] },
    experimental: true,
  },
};

async function openBuilder(page: import("@playwright/test").Page, catalog: object) {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
  });
  await page.route("https://core.test/v1/pipelines/ops", async (route) => {
    await route.fulfill({ json: catalog });
  });
  await page.goto("/pipelines/new");
}

test("flag allumé : l'op expérimentale porte le badge Expérimental", async ({ page }) => {
  await openBuilder(page, { ...STABLE, ...EXPERIMENTAL });
  const slack = page.getByRole("button", { name: "writer.slack" });
  await expect(slack).toBeVisible();
  await expect(slack.getByText("Expérimental")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "reader.collection" }).getByText("Expérimental"),
  ).toHaveCount(0);
});

test("flag éteint : aucune op expérimentale dans la palette", async ({ page }) => {
  await openBuilder(page, STABLE);
  await expect(page.getByRole("button", { name: "reader.collection" })).toBeVisible();
  await expect(page.getByRole("button", { name: "writer.slack" })).toHaveCount(0);
  await expect(page.getByText("Expérimental")).toHaveCount(0);
});
