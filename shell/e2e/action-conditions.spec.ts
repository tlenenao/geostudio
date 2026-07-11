import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("une condition sur une action ne déclenche celle-ci que si l'expression s'évalue à vrai, sans code", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App conditions");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Filtre sur le champ "status" (même nom que la variable : c'est ce qui
  // permet à l'action Variable.set — inchangée depuis SP-4/SP-5a — de
  // reporter la valeur du payload dans la variable ; cf. valueFromPayload
  // dans AppRenderer.tsx).
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("status");

  // Texte affichant la variable "status".
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Sélection : {{var:status}}");

  // Variable "status".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("status");

  // Filtre.changed -> Variable(status).set, condition record.status == "Nord".
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : status" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();
  await page.getByLabel(/Condition de l'action/).fill('record.status == "Nord"');

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : rien saisi encore — la variable est vide.
  await page.goto("/apps/9");
  await expect(page.getByText("Sélection :")).toBeVisible();

  // Taper "Nord" : la condition est vraie, l'action se déclenche.
  await page.getByLabel("Valeur du filtre").fill("Nord");
  await expect(page.getByText("Sélection : Nord")).toBeVisible();

  // Taper "Sud" : la condition est fausse, l'action ne se déclenche pas —
  // la variable garde sa valeur précédente ("Nord").
  await page.getByLabel("Valeur du filtre").fill("Sud");
  await expect(page.getByText("Sélection : Nord")).toBeVisible();
});
