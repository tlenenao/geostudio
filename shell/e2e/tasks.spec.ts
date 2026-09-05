// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { ADMIN_ME, mockCore, mockMe } from "./mocks";

test("persona Créateur : voit ses tâches, pas la section usage plateforme", async ({ page }) => {
  await mockCore(page);
  await mockMe(page); // défaut = creator, cf. DEFAULT_ME (mocks.ts) — porte tasks.view
  await page.route("https://core.test/usage/tasks**", async (route) => {
    await route.fulfill({
      json: {
        tasks: [
          {
            id: 1,
            actorId: "u-mock",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "p1",
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        pageSize: 50,
      },
    });
  });

  await page.goto("/tasks");
  await expect(page.getByText("Mes tâches récentes")).toBeVisible();
  await expect(page.getByText("Exécution de pipeline")).toBeVisible();
  await expect(page.getByText("Usage de la plateforme")).toHaveCount(0);
});

test("persona Administrateur : voit les deux sections", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  await page.route("https://core.test/usage/tasks**", async (route) => {
    await route.fulfill({ json: { tasks: [], total: 0, page: 1, pageSize: 50 } });
  });
  await page.route("https://core.test/usage/summary**", async (route) => {
    await route.fulfill({
      json: {
        byActor: [{ actorId: "u1", actorUsername: "alice", count: 3 }],
        byResource: [{ objectType: "collection", objectId: "c1", count: 2 }],
        totalActions: 3,
        windowStart: "2026-08-01T00:00:00Z",
        windowEnd: "2026-09-01T00:00:00Z",
      },
    });
  });

  await page.goto("/tasks");
  await expect(page.getByText("Mes tâches récentes")).toBeVisible();
  await expect(page.getByText("Aucune tâche récente.")).toBeVisible();
  await expect(page.getByText("Usage de la plateforme")).toBeVisible();
  await expect(page.getByText(/alice/)).toBeVisible();
});
