import { expect, test } from "@playwright/test";
import { getA11ySeed, go, seriousViolations, session } from "./helpers";

test.setTimeout(120_000);

// Rapports planifiés et règles d'alerte (CORE_EXPORT_ENABLED / CORE_ETL_ENABLED allumés).
test.describe("t01b rapports et alertes : formulaires", () => {
  test("axe : aucune violation critique/grave en clair sur /reports, /reports/new, /reports/:id/edit et l'éditeur de dataset (règles d'alerte)", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    for (const r of [
      "/reports",
      "/reports/new",
      `/reports/${s.reportId}/edit`,
      `/datasets/${s.datasetId}/edit`,
    ]) {
      await go(page, r, 2500);
      expect(await seriousViolations(page), r).toEqual([]);
    }
    await ctx.close();
  });

  // t01b-009 : finding. L'erreur est un <p role=alert> dans le <label> ; le champ n'est ni
  // aria-invalid ni relié à son message.
  test("t01b-009 : un cron invalide marque le champ aria-invalid et le relie à son message", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    await go(page, `/reports/${s.reportId}/edit`, 2500);
    await page.getByRole("checkbox", { name: /planification automatique/i }).check();
    await page.getByRole("combobox", { name: /mode/i }).selectOption("advanced");
    const field = page.getByLabel("Expression cron", { exact: false }).last();
    await field.fill("pas un cron");
    await expect(page.getByRole("alert").filter({ hasText: /cron|format/i })).toBeVisible();
    expect(await field.getAttribute("aria-invalid")).toBe("true");
    expect(await field.getAttribute("aria-describedby")).toBeTruthy();
    await ctx.close();
  });

  // Réfute j06-010 (domaine verrouillé = <span aria-disabled> quand l'ETL est coupé).
  test("ETL allumé : « Automatisation » est un vrai lien clavier, plus un span aria-disabled (réfute j06-010)", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "creator");
    const nav = page.getByRole("navigation", { name: /domaines/i });
    const link = nav.getByRole("link", { name: "Automatisation" });
    await expect(link).toBeVisible();
    await link.focus();
    await expect(link).toBeFocused();
    await expect(nav.locator("[aria-disabled=true]")).toHaveCount(0);
    await ctx.close();
  });
});
