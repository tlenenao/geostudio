import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const GAUGE_MANIFEST = {
  id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
  moduleUrl: "/fixtures/gauge-extension-widget.js",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

const THROWING_MANIFEST = {
  id: "test.throwing", tag: "throwing-extension-widget", label: "Widget qui plante",
  moduleUrl: "/fixtures/throwing-extension-widget.js",
  props: [], events: [], actions: ["boom"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("une extension dont l'action lève une exception ne bloque pas le message composé suivant vers un autre widget", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST, THROWING_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App containment");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  await page.getByRole("button", { name: "Widget qui plante" }).click();
  await page.getByRole("button", { name: "Bouton" }).click();

  // Le message vers le widget qui plante est câblé en premier — s'il casse
  // la boucle, le second message (vers la Jauge) ne s'exécute jamais.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Widget qui plante" });
  await page.getByLabel("Action", { exact: true }).selectOption("boom");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const gauge = page.locator("gauge-extension-widget");
  await gauge.getByRole("button", { name: "+1" }).click();
  await gauge.getByRole("button", { name: "+1" }).click();
  await expect(gauge.getByText("2", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(gauge.getByText("0", { exact: true })).toBeVisible();
});
