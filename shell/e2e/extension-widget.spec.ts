import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const GAUGE_MANIFEST = {
  id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
  moduleUrl: "/fixtures/gauge-extension-widget.js",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("un widget d'extension chargé dynamiquement par URL se pose dans le builder et se comporte comme un widget WC ordinaire", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App extension");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // La palette liste l'extension sans redéploiement du shell.
  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  const gauge = page.locator("gauge-extension-widget");
  await expect(gauge.getByText("0", { exact: true })).toBeVisible();

  // Bouton (déclenchera reset) et Texte (affichera la variable count).
  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, import() du module ré-exécuté depuis le cache navigateur.
  await page.goto("/apps/9");
  const runtimeGauge = page.locator("gauge-extension-widget");
  await expect(runtimeGauge.getByText("0", { exact: true })).toBeVisible();

  await runtimeGauge.getByRole("button", { name: "+1" }).click();
  await runtimeGauge.getByRole("button", { name: "+1" }).click();
  await expect(runtimeGauge.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("Compte : 2")).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeGauge.getByText("0", { exact: true })).toBeVisible();
});

test("désactiver une extension affiche un placeholder au lieu de casser une app qui l'utilisait", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App extension désactivée");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // L'admin désactive l'extension : /extensions ne la renvoie plus.
  await page.unroute("**/extensions*");
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [] } });
  });

  await page.goto("/apps/9");
  await expect(page.getByText("Widget inconnu : acme.gauge")).toBeVisible();
  await expect(page.locator("gauge-extension-widget")).toHaveCount(0);
});
