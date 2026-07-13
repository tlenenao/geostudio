import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const EXTERNAL_MANIFEST = {
  id: "example.external-counter", tag: "external-example-widget", label: "Compteur externe (exemple)",
  moduleUrl: "http://localhost:4174/widget.js",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("un widget hébergé sur une origine distincte (CORS) se charge, respecte le thème, et fonctionne comme n'importe quel widget d'extension", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [EXTERNAL_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App widget externe");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // La palette liste le widget hébergé cross-origin sans redéploiement du shell.
  await page.getByRole("button", { name: "Compteur externe (exemple)" }).click();
  const widget = page.locator("external-example-widget");
  await expect(widget.getByText("0", { exact: true })).toBeVisible();

  await page.getByLabel("Couleur du texte").fill("#0000ff");

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Compteur externe (exemple)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Compteur externe (exemple)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, import() cross-origin ré-exécuté depuis le
  // cache mémoïsé du module (moduleCache.ts) — preuve qu'il a réussi malgré
  // l'origine distincte (CORS), pas seulement au premier chargement en édition.
  await page.goto("/apps/9");
  const runtimeWidget = page.locator("external-example-widget");
  await expect(runtimeWidget.getByText("0", { exact: true })).toBeVisible();
  const color = await runtimeWidget.locator("span").evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(0, 0, 255)");

  await runtimeWidget.getByRole("button", { name: "+1" }).click();
  await runtimeWidget.getByRole("button", { name: "+1" }).click();
  await expect(runtimeWidget.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("Compte : 2")).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeWidget.getByText("0", { exact: true })).toBeVisible();
});
