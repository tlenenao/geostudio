import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("an sdk-only example widget appears in the palette and wires through ActionsPanel", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App SDK");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add two Compteur widgets — the palette lists it purely because it's
  // registered, with no special-casing anywhere in the builder.
  await page.getByRole("button", { name: "Compteur (exemple SDK)" }).click();
  await page.getByRole("button", { name: "Compteur (exemple SDK)" }).click();

  // Wire the first's "changed" event to the second's "reset" action. Both
  // counters render the identical label "Compteur (exemple SDK)", so
  // selectOption({label}) would ambiguously resolve to whichever comes
  // first in both selects — use position instead. ActionsPanel lists
  // "Widget émetteur" options as [placeholder, counter 1, counter 2] (both
  // declare `events`, in the order they were added) and "Widget cible" as
  // [placeholder, counter 1, counter 2] (both declare `actions`, same
  // order) — index 1 is counter 1, index 2 is counter 2, in both selects.
  await page.getByLabel("Widget émetteur").selectOption({ index: 1 }); // counter 1
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ index: 2 }); // counter 2
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: increment the second counter, then click the first's "+1" —
  // the wired reset action should bring the second counter back to 0.
  await page.goto("/apps/9");
  const plusButtons = page.getByRole("button", { name: "+1" });
  await plusButtons.nth(1).click();
  // getByText does substring matching by default, which would also match
  // the "+1" button labels — use exact matching so this only targets the
  // counter's numeric display span.
  await expect(page.getByText("1", { exact: true })).toBeVisible();
  await plusButtons.nth(0).click();
  await expect(page.getByText("0", { exact: true })).toBeVisible();
});
