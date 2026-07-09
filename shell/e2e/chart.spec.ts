import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("statistics source with a split field feeds a multi-series Chart in the runtime", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App graphiques");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Statistics source over "villes": group by region, split by annee (→ 2 series), sum pop.
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Type de la source/).selectOption("statistics");
  await page.getByLabel(/Collection de la source/).fill("villes");
  await page.getByLabel(/Grouper par/).fill("region");
  await page.getByLabel(/Séparer par/).fill("annee");
  await page.getByLabel(/Agrégation/).selectOption("sum");
  await page.getByLabel(/Champ agrégé/).fill("pop");

  // Chart bound to the source.
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("region");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: the ECharts panel renders a canvas with two series.
  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart).toHaveAttribute("data-chart-series", "2");
  await expect(chart.locator("canvas")).toBeVisible();
});
