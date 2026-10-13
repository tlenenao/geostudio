// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// ARC-K2 (F3/F5) : paramètres de run saisis avant « Exécuter », puis reprise
// d'un run échoué depuis le nœud en échec.
test("un auteur lance un pipeline paramétré puis reprend le run échoué", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", (route) =>
    route.fulfill({ json: { readOnly: false, etlEnabled: true } }),
  );
  await page.route("https://core.test/v1/pipelines/ops", (route) =>
    route.fulfill({
      json: {
        "reader.collection": {
          kind: "reader",
          paramsSchema: {
            properties: { collectionId: { type: "string", format: "collection-id" } },
          },
        },
        "writer.collection": {
          kind: "writer",
          paramsSchema: {
            properties: { collectionId: { type: "string", format: "collection-id" } },
          },
        },
      },
    }),
  );
  const config = {
    kind: "pipeline",
    pipeline: {
      parameters: [{ name: "minPop", type: "integer", required: true }],
      retry: { max: 2, backoff: "fixed", delaySeconds: 5 },
      nodes: [
        { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
        { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: {} },
      ],
      edges: [{ id: "e1", from: "r1", to: "w1" }],
    },
  };
  await page.route("https://core.test/v1/configs/by-item/pipe-1", (route) =>
    route.fulfill({ json: { id: "cfg-pipe1", itemId: "pipe-1", kind: "pipeline", config } }),
  );

  let runBody: unknown = null;
  let retryBody: unknown = null;
  let resumed = false;
  await page.route("https://core.test/v1/pipelines/pipe-1/run", async (route) => {
    runBody = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { runId: "run-1" } });
  });
  await page.route("https://core.test/v1/pipelines/runs/run-1/retry", async (route) => {
    retryBody = route.request().postDataJSON();
    resumed = true;
    await route.fulfill({ status: 202, json: { runId: "run-2" } });
  });
  await page.route("https://core.test/v1/pipelines/pipe-1/runs*", async (route) => {
    const base = { startedAt: "2026-08-06T10:00:00Z", nodeStats: {}, params: { minPop: 5 } };
    await route.fulfill({
      json: resumed
        ? [
            {
              ...base,
              id: "run-2",
              status: "succeeded",
              finishedAt: "2026-08-06T10:00:09Z",
              error: null,
              attempt: 1,
              resumeOf: "run-1",
            },
          ]
        : [
            {
              ...base,
              id: "run-1",
              status: "failed",
              finishedAt: "2026-08-06T10:00:02Z",
              error: "boom",
              attempt: 3,
              resumable: true,
            },
          ],
    });
  });

  await page.goto("/pipelines/pipe-1/edit");
  await page.getByLabel("minPop (obligatoire)").fill("5");
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect.poll(() => runBody).toEqual({ params: { minPop: "5" } });

  await expect(page.getByText("tentative 3")).toBeVisible();
  await expect(page.getByText("Paramètres : minPop=5")).toBeVisible();
  await page.getByRole("button", { name: "Reprendre" }).click();
  await expect.poll(() => retryBody).toEqual({ fromStart: false });
  await expect(page.locator('span:text-is("Terminé")')).toBeVisible({ timeout: 10_000 });
});
