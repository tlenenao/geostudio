import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a Filtre wired to a variable updates a Texte widget reading it, in the runtime", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App variables");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add the Filtre (emitter) and Texte (reader) widgets.
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("message");
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Valeur : {{var:message}}");

  // Add a variable and name it "message".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("message");

  // Wire Filtre.changed -> Variable(message).set.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : message" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: typing into the Filtre updates the Texte widget's {{var:message}} binding.
  await page.goto("/apps/9");
  await page.getByLabel("Valeur du filtre").fill("bonjour");
  await expect(page.getByText("Valeur : bonjour")).toBeVisible();
});
