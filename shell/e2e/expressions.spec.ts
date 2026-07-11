import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un Filtre pilote par expression la visibilité d'un widget et une colonne calculée, sans code", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App expressions");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Source de données : collection "villes" (region: Nord|Sud, annee, pop).
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("villes");

  // Widget Texte, masqué tant que la variable "seuil" ne vaut pas "Nord".
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Région Nord sélectionnée");
  await page.getByLabel("Condition d'affichage (visibleWhen)").fill('vars.seuil == "Nord"');

  // Widget Table, liée à la même source, avec une colonne calculée.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Colonnes").fill("region,annee");
  await page.getByRole("button", { name: "Ajouter une colonne calculée" }).click();
  await page.getByLabel(/Libellé de la colonne calculée/).fill("Correspond");
  await page.getByLabel(/Expression de la colonne calculée/).fill("record.region == vars.seuil");

  // Filtre + variable "seuil", câblés Filtre.changed -> Variable(seuil).set.
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("seuil");
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("seuil");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : seuil" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : "seuil" vaut "" au départ — le Texte est caché, aucune ligne ne correspond.
  await page.goto("/apps/9");
  await expect(page.getByText("Région Nord sélectionnée")).toBeHidden();
  await expect(page.getByRole("cell", { name: "false" })).toHaveCount(4);
  await expect(page.getByRole("cell", { name: "true" })).toHaveCount(0);

  // Taper "Nord" dans le Filtre : le Texte apparaît, la colonne calculée distingue Nord/Sud.
  await page.getByLabel("Valeur du filtre").fill("Nord");
  await expect(page.getByText("Région Nord sélectionnée")).toBeVisible();
  await expect(page.getByRole("cell", { name: "true" })).toHaveCount(2);
  await expect(page.getByRole("cell", { name: "false" })).toHaveCount(2);
});
