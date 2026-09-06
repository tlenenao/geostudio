import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a Saisie widget bound to a number variable updates a Texte widget reading it, at runtime", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app saisie");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Ajoute une variable "seuil" (number) via le panneau Variables.
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("seuil");
  await page.getByLabel(/Type de la variable/).selectOption({ label: "Nombre" });

  // Ajoute le widget Saisie, le lie à "seuil". `exact: true` : d'autres
  // libellés de la palette pourraient un jour contenir "Saisie" en
  // sous-chaîne (getByRole matche par défaut en sous-chaîne) — confirmé par
  // falsification que ce test resterait vert sans cette précision.
  await page.getByRole("button", { name: "Saisie", exact: true }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await propsPanel.getByLabel("Variable liée").selectOption({ label: "seuil" });

  // Ajoute un widget Texte dont le texte interpole {{var:seuil}}.
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Valeur : {{var:seuil}}");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("seuil").fill("42");
  await expect(page.getByText("Valeur : 42")).toBeVisible();
});
