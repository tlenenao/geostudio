import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { etlEnabled } from "../_fixtures/env";
import { openAs, spaGoto } from "./helpers";

// Expérience utilisateur quand la capacité ETL est coupée (etlEnabled=false, stack d'audit).
// Navigation par le routeur SPA (history.pushState) : un rechargement complet perd la
// destination après la reconnexion OIDC (défaut j02-004).

test.describe("j06 ETL désactivé — shell (créateur)", () => {
  test.beforeAll(async () => {
    test.skip(
      await etlEnabled(),
      "stack avec CORE_ETL_ENABLED=true : parcours « ETL éteint » sans objet",
    );
  });
  test.beforeEach(async ({ page }) => {
    await openAs(page, "creator");
  });

  test("le domaine Automatisation est visible mais verrouillé (pas un lien)", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Domaines" });
    await expect(nav.getByText("Automatisation")).toBeVisible();
    await expect(nav.getByRole("link", { name: "Automatisation" })).toHaveCount(0);
    await expect(nav.getByText("Automatisation")).toHaveAttribute("aria-disabled", "true");
  });

  test("/pipelines/new affiche l'indisponibilité, sans canevas ni palette", async ({ page }) => {
    await spaGoto(page, "/pipelines/new");
    await expect(page.getByRole("status")).toContainText(
      "Fonction indisponible sur cette instance",
    );
    await expect(page.getByRole("button", { name: "Exécuter" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Enregistrer" })).toHaveCount(0);
  });

  test("/pipelines/:pk/edit sur un id inconnu : « Pipeline introuvable »", async ({ page }) => {
    await spaGoto(page, "/pipelines/inconnu/edit");
    await expect(page.getByText("Pipeline introuvable.")).toBeVisible();
  });

  test("le formulaire « Nouvel élément » ne propose ni Pipeline ni Requête visuelle", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Nouveau" }).click();
    const options = await page
      .getByRole("dialog")
      .getByLabel("Type")
      .locator("option")
      .allInnerTexts();
    expect(options.join("|")).not.toMatch(/pipeline|requête visuelle/i);
  });

  test("requête visuelle : formulaire affiché mais « Créer » reste désactivé", async ({ page }) => {
    await spaGoto(page, "/datasets/visual-query/new");
    await expect(page.getByRole("heading", { name: "Nouvelle requête visuelle" })).toBeVisible();
    await page.getByLabel("Titre", { exact: true }).fill("aud-j06 requête");
    await expect(page.getByRole("button", { name: "Créer" })).toBeDisabled();
    await expect(page.getByText("Fonction indisponible sur cette instance")).toBeVisible();
  });

  test("requête visuelle inconnue : « Requête introuvable »", async ({ page }) => {
    await spaGoto(page, "/datasets/visual-query/inconnue/edit");
    await expect(page.getByText("Requête introuvable.")).toBeVisible();
  });

  // Finding j06-009 : le message final expose le nom d'une variable d'environnement serveur.
  test("j06-009 : le message d'indisponibilité ne cite pas CORE_ETL_ENABLED", async ({ page }) => {
    await spaGoto(page, "/pipelines/new");
    await expect(page.getByRole("status")).toContainText("Fonction indisponible");
    await expect(page.getByRole("status")).not.toContainText("CORE_ETL_ENABLED");
  });

  // Finding j06-010 : entrée verrouillée = <span aria-disabled> + title natif seulement.
  bug("j06-010 : l'entrée verrouillée est atteignable au clavier et décrite", async ({ page }) => {
    const item = page.getByRole("navigation", { name: "Domaines" }).getByText("Automatisation");
    const focusable = await item.evaluate((e) => (e as HTMLElement).tabIndex >= 0);
    const described = await item.evaluate(
      (e) => e.hasAttribute("aria-describedby") || e.hasAttribute("aria-label"),
    );
    expect(focusable && described).toBe(true);
  });

  // Finding j06-011 : la palette ⌘K propose le domaine verrouillé et y navigue.
  test("j06-011 : la palette de commandes n'offre pas le domaine verrouillé", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Palette de commandes" })).toBeVisible();
    await expect(
      page.getByRole("dialog", { name: "Palette de commandes" }).getByText("Automatisation"),
    ).toHaveCount(0);
  });
});

test.describe("j06 ETL désactivé — shell (lecteur)", () => {
  test.beforeEach(async ({ page }) => {
    await openAs(page, "reader");
  });

  test("le domaine Automatisation est absent de la navigation (privilège manquant)", async ({
    page,
  }) => {
    await expect(
      page.getByRole("navigation", { name: "Domaines" }).getByText("Automatisation"),
    ).toHaveCount(0);
  });

  test("/pipelines/new n'expose aucun éditeur au lecteur", async ({ page }) => {
    await spaGoto(page, "/pipelines/new");
    await expect(page.getByRole("status")).toBeVisible();
    await expect(page.getByRole("button", { name: "Enregistrer" })).toHaveCount(0);
  });
});
