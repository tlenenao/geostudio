// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

const PORTAL = "https://www.data.gouv.fr";

test("un admin déclare une source data.gouv.fr (udata) en copie", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let created: unknown = null;
  await page.route("https://core.test/v1/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-u",
          type: "udata",
          url: PORTAL,
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({ json: { sources: [] } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(PORTAL);
  await panel.getByLabel("Type").selectOption("udata");
  await panel.getByLabel("Mode").selectOption("copy");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({ type: "udata", url: PORTAL, mode: "copy", enabled: true });
});
