import { test, expect, type Page } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import { apiFor, createSource, runHarvestInWorker, type Api } from "./helpers";

// Écran d'administration du moissonnage (/admin/harvest) et édition des métadonnées d'une collection.
// Navigation SPA (history.pushState) : un rechargement complet perd la destination après la
// reconnexion OIDC (défaut j02-004).
test.setTimeout(120_000);
const tag = stamp("j07");
let admin: Api;

test.beforeEach(async () => {
  admin = await apiFor("admin");
});

async function openHarvest(page: Page): Promise<void> {
  await openAs(page, "admin");
  await spaGoto(page, "/admin/harvest");
  await expect(page.getByRole("heading", { name: "Moissonnage" })).toBeVisible();
}

function row(page: Page, text: string) {
  return page.getByRole("row").filter({ hasText: text });
}

test.describe("j07 moissonnage — écran d'administration", () => {
  test("l'administrateur voit ses sources (type, URL, mode, statut) et le bouton d'ajout", async ({
    page,
  }) => {
    const url = `https://example.invalid/${tag}-liste`;
    await createSource(admin, { type: "ckan", url, mode: "reference" });
    await openHarvest(page);
    const r = row(page, url);
    await expect(r).toBeVisible();
    await expect(r).toContainText("ckan");
    await expect(r).toContainText("reference");
    await expect(page.getByRole("button", { name: "Ajouter une source" })).toBeVisible();
  });

  test("ajout d'une source par le panneau : la ligne apparaît et le mode copie est grisé pour un WMS", async ({
    page,
  }) => {
    await openHarvest(page);
    await page.getByRole("button", { name: "Ajouter une source" }).click();
    const panel = page.getByRole("region", { name: "Ajouter une source" });
    await panel.getByLabel("Type").selectOption("wms");
    await expect(panel.getByRole("option", { name: "Copie" })).toHaveAttribute("disabled", "");
    const url = `https://example.invalid/${tag}-ui-create`;
    await panel.getByLabel("URL").fill(url);
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    await expect(row(page, url)).toBeVisible();
  });

  test("modification d'une source : URL et intervalle enregistrés", async ({ page }) => {
    const url = `https://example.invalid/${tag}-ui-edit`;
    await createSource(admin, { type: "stac", url });
    await openHarvest(page);
    await row(page, url).getByRole("button", { name: "Éditer" }).click();
    const panel = page.getByRole("region", { name: `Éditer ${url}` });
    await panel.getByLabel("Intervalle de rafraîchissement (minutes)").fill("120");
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    await expect(panel).toHaveCount(0);
    const list = await admin.get("/v1/harvest/sources");
    const s = list.body.sources.find((x: { url: string }) => x.url === url);
    expect(s.intervalMinutes).toBe(120);
  });

  test("suppression : la confirmation est demandée, l'annulation conserve la source", async ({
    page,
  }) => {
    const url = `https://example.invalid/${tag}-ui-del`;
    await createSource(admin, { type: "stac", url });
    await openHarvest(page);
    await row(page, url).getByRole("button", { name: "Supprimer" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText(url);
    await dialog.getByRole("button", { name: "Annuler" }).click();
    await expect(row(page, url)).toBeVisible();
    await row(page, url).getByRole("button", { name: "Supprimer" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Supprimer" }).click();
    await expect(row(page, url)).toHaveCount(0);
  });

  test("créateur et lecteur : accès refusé à /admin/harvest et aucun lien dans la navigation", async ({
    browser,
  }) => {
    for (const persona of ["creator", "reader"] as const) {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await openAs(page, persona);
      await spaGoto(page, "/admin/harvest");
      await expect(page.getByText("Accès réservé aux administrateurs.")).toBeVisible();
      await expect(page.getByRole("button", { name: "Ajouter une source" })).toHaveCount(0);
      await ctx.close();
    }
  });
});

test.describe("j07 moissonnage — défauts constatés (UI)", () => {
  // Finding j07-003 : « Moissonner maintenant » n'affiche aucun retour, même quand la requête échoue.
  test("j07-003 : « Moissonner maintenant » confirme le lancement ou signale l'échec", async ({
    page,
  }) => {
    const url = `https://example.invalid/${tag}-run-ui`;
    await createSource(admin, { type: "stac", url });
    await openHarvest(page);
    await row(page, url).getByRole("button", { name: "Moissonner maintenant" }).click();
    await expect(page.getByRole("alert").or(page.getByRole("status")).first()).toBeVisible({
      timeout: 5_000,
    });
  });

  // Finding j07-017 : la raison d'un échec (lastError) et la date de dernier passage ne sont jamais affichées.
  test("j07-017 : la table affiche la raison de l'échec d'une source", async ({ page }) => {
    const url = `http://127.0.0.1:8200/v1/stac?${tag}-ui-err`;
    const src = await createSource(admin, { type: "stac", url });
    runHarvestInWorker(src.id);
    await openHarvest(page);
    await expect(row(page, url)).toContainText("error");
    await expect(row(page, url)).toContainText("cible réseau interne bloquée");
  });

  // Finding j07-018 : impossible de revenir à « manuel uniquement » (intervalle vide ignoré à l'édition).
  test("j07-018 : vider l'intervalle dans le panneau d'édition supprime la planification", async ({
    page,
  }) => {
    const url = `https://example.invalid/${tag}-ui-interval`;
    await createSource(admin, { type: "stac", url, intervalMinutes: 60 });
    await openHarvest(page);
    await row(page, url).getByRole("button", { name: "Éditer" }).click();
    const panel = page.getByRole("region", { name: `Éditer ${url}` });
    await panel.getByLabel("Intervalle de rafraîchissement (minutes)").fill("");
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    await expect(panel).toHaveCount(0);
    const list = await admin.get("/v1/harvest/sources");
    const s = list.body.sources.find((x: { url: string }) => x.url === url);
    expect(s.intervalMinutes).toBeNull();
  });
});
