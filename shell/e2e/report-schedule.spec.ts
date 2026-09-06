// shell/e2e/report-schedule.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-17b — depuis "Mes vues", programmer un rapport PDF hebdomadaire sur un
// signet existant, avec un webhook comme canal ; l'historique des
// exécutions affiche un run "Terminé" avec un lien de téléchargement.
test("programmer un rapport sur un signet, voir son historique d'exécutions", async ({ page }) => {
  await mockCore(page);

  // ReportSchedule est conditionné à la capacité export (revue finale
  // SP-17b, I3) : l'entrée « Programmer un rapport » ne s'affiche que si
  // GET /instance annonce exportEnabled, et le cœur refuse la création en 403
  // sinon. Le défaut de mockCore ne porte que readOnly.
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: false, exportEnabled: true } });
  });

  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          {
            pk: "bookmark-1",
            resourceType: "bookmark",
            title: "Récents 2026",
            abstract: "",
            owner: "mockuser",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: "cfg-bookmark",
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      },
    });
  });

  let createdReportConfig: unknown = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    if (body?.config?.kind === "report") {
      createdReportConfig = body;
      await route.fulfill({
        status: 201,
        json: { id: "cfg-report", kind: "report", itemId: "report-1" },
      });
      return;
    }
    return route.fallback();
  });
  await page.route("**/configs/by-item/report-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-report",
        itemId: "report-1",
        kind: "report",
        config: (createdReportConfig as { config: unknown })?.config ?? {
          kind: "report",
          report: {
            bookmarkItemId: "bookmark-1",
            refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
            channels: [{ kind: "webhook", url: "https://example.test/hook" }],
          },
        },
      },
    });
  });
  await page.route("**/reports/report-1/runs", async (route) => {
    await route.fulfill({
      json: [
        {
          id: "run-1",
          status: "done",
          resultUrl: "https://s3.test/renders/run-1.pdf",
          error: null,
          notifiedAt: "2026-08-09T08:00:05Z",
          createdAt: "2026-08-09T08:00:00Z",
        },
      ],
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Programmer un rapport" }).click();
  await expect(page).toHaveURL(/\/reports\/new$/);

  await page.getByLabel("URL du webhook").fill("https://example.test/hook");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page).toHaveURL(/\/reports\/report-1\/edit$/);

  expect(createdReportConfig).not.toBeNull();
  expect(createdReportConfig).toMatchObject({
    config: {
      kind: "report",
      report: {
        bookmarkItemId: "bookmark-1",
        channels: [{ kind: "webhook", url: "https://example.test/hook" }],
      },
    },
  });

  await expect(page.getByText("Terminé")).toBeVisible();
  await expect(page.getByRole("link", { name: "Télécharger" })).toHaveAttribute(
    "href",
    "https://s3.test/renders/run-1.pdf",
  );
});
