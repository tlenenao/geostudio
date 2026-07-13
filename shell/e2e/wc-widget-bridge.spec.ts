import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un widget Web Component se pose dans le builder, suit le thème, émet un event vers une action composée et répond à une action du bus", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App WC");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Compteur (WC) posé sur le canvas : props par défaut affichées. Un clic
  // à l'intérieur du widget est intercepté par l'overlay de sélection du
  // mode édition (même convention que theme.spec.ts / widget-sdk.spec.ts) :
  // le rendu vivant (incréments, couleur) se vérifie plus bas, en runtime.
  await page.getByRole("button", { name: "Compteur (WC)" }).click();
  const counter = page.locator("gs-counter");
  await expect(counter.getByText("0", { exact: true })).toBeVisible();

  await page.getByLabel("Couleur du texte").fill("#ff0000");

  // Bouton (déclenchera reset sur le Compteur WC) et Texte (affichera la variable count).
  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  // Compteur (WC).changed -> Variable(count).set
  await page.getByLabel("Widget émetteur").selectOption({ label: "Compteur (WC)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  // { exact: true } : après une première action ajoutée, sa ligne dans la
  // liste porte des aria-label ("Retirer l'action <id>", "Condition de
  // l'action <id>") qui matchent aussi la sous-chaîne "action" par défaut.
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  // Bouton.clicked -> Compteur (WC).reset
  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Compteur (WC)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, defaultProps.initial = 0, thème appliqué
  // via les mêmes CSS custom properties que les widgets React (héritées
  // nativement à travers le DOM, rien de spécifique au pont WC).
  await page.goto("/apps/9");
  const runtimeCounter = page.locator("gs-counter");
  await expect(runtimeCounter.getByText("0", { exact: true })).toBeVisible();
  const color = await runtimeCounter.locator("span").evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(255, 0, 0)");

  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await expect(runtimeCounter.getByText("3", { exact: true })).toBeVisible();

  // L'event "changed" a déclenché l'action composée jusqu'au Texte.
  await expect(page.getByText("Compte : 3")).toBeVisible();

  // Bouton.clicked déclenche l'action "reset" du bus sur le widget WC.
  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeCounter.getByText("0", { exact: true })).toBeVisible();
});
