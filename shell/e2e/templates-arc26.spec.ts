// SPDX-License-Identifier: Apache-2.0
// ARC-26 : chaque gabarit s'instancie depuis le catalogue, s'ouvre en runtime et
// passe l'audit axe (critical/serious) ; Swipe et galerie de fonds sont pilotables.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { bindTemplateSources, mockCore } from "./mocks";

const TEMPLATES: Array<{ id: string; kind: "app" | "dashboard"; title: string }> = [
  { id: "tableau-de-bord-territorial", kind: "dashboard", title: "Tableau de bord territorial" },
  { id: "suivi-de-chantier", kind: "app", title: "Suivi de chantier" },
  { id: "enquete-citoyenne", kind: "app", title: "Enquête citoyenne" },
  { id: "comparateur-de-cartes", kind: "app", title: "Comparateur de cartes" },
  { id: "galerie-de-fonds-de-carte", kind: "app", title: "Galerie de fonds de carte" },
  { id: "fiches-d-entites", kind: "app", title: "Fiches d'entités" },
  { id: "atlas-par-entite", kind: "app", title: "Atlas (une page par entité)" },
];

async function createFromTemplate(page: Page, id: string, kind: string) {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption(kind);
  await dialog.getByLabel("Modèle").selectOption(id);
  await bindTemplateSources(dialog);
  await dialog.getByLabel("Titre").fill("Depuis gabarit");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

for (const tpl of TEMPLATES) {
  test(`gabarit ${tpl.id} : s'instancie depuis le catalogue et passe axe en runtime`, async ({
    page,
  }) => {
    await createFromTemplate(page, tpl.id, tpl.kind);
    await page.goto("/apps/9");
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).analyze();
    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(blocking.map((v) => `${v.id}: ${v.nodes[0]?.html}`)).toEqual([]);
  });
}

test("comparateur : deux cartes et un curseur nommé", async ({ page }) => {
  await createFromTemplate(page, "comparateur-de-cartes", "app");
  await page.goto("/apps/9");
  const slider = page.getByRole("slider", { name: "Position du comparateur" });
  await expect(slider).toBeVisible();
  await slider.fill("25");
  await expect(slider).toHaveValue("25");
});

test("galerie de fonds : choisir un fond coche l'option sans erreur", async ({ page }) => {
  await createFromTemplate(page, "galerie-de-fonds-de-carte", "app");
  await page.goto("/apps/9");
  const voyager = page.getByRole("radio", { name: "Voyager" });
  await voyager.click();
  await expect(voyager).toHaveAttribute("aria-checked", "true");
});
