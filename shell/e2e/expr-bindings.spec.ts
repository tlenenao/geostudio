import { test, expect, type Page, type Route } from "@playwright/test";
import { mockCore } from "./mocks";

// Seeds the very first config GET for item 9 with a Bouton whose label is a
// { $expr } binding — no builder UI can produce this today (SP-5c §5), so it
// stands in for a hand- or MCP-authored config. Fires once, then defers
// (route.fallback()) to mockCore's own handler for every later GET/PUT, so
// the seeded widget round-trips normally through the rest of the test.
async function seedExprBoundButton(page: Page) {
  let seeded = false;
  await page.route("**/configs/by-item/**", async (route: Route) => {
    if (seeded || route.request().method() !== "GET" || !route.request().url().endsWith("/9")) {
      await route.fallback();
      return;
    }
    seeded = true;
    await route.fulfill({
      json: {
        id: "cfg-9", itemId: "9", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [
            { id: "btn-expr", widget: "button", x: 0, y: 4, w: 2, h: 1,
              props: { label: { $expr: "vars.selected.properties.region" }, href: "" } },
          ] },
        },
      },
    });
  });
}

test("un binding { \$expr } sur une prop non-Texte lit un champ imbriqué d'une variable record, sans code pour le câblage", async ({ page }) => {
  await mockCore(page);
  await seedExprBoundButton(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App bindings");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Le Bouton { $expr } semé est déjà dans le canvas ; vars.selected vaut
  // encore null (variable pas encore créée) donc l'expression échoue en
  // silence et le Bouton retombe sur son libellé par défaut. .last() : en
  // édition, la palette de widgets porte aussi un bouton "Bouton" (même
  // libellé que le type de widget, rendu avant le canvas dans le DOM) — le
  // widget du canvas est donc toujours le second match.
  await expect(page.getByRole("button", { name: "Bouton" }).last()).toBeVisible();

  // Source de données : collection "villes" (region: Nord|Sud, annee, pop).
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("villes");

  // Table liée à la source.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Colonnes").fill("region,annee");

  // Variable "selected", type "record".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("selected");
  await page.getByLabel(/Type de la variable/).selectOption("record");

  // Table.itemSelected -> Variable(selected).set.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Table" });
  await page.getByLabel("Événement").selectOption("itemSelected");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : selected" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Bouton" })).toBeVisible();

  // Cliquer une ligne "Nord" : Table.itemSelected émet le DataRecord entier,
  // la variable "selected" (record) le reçoit tel quel, le Bouton relit
  // vars.selected.properties.region par expression.
  await page.getByRole("cell", { name: "Nord" }).first().click();
  await expect(page.getByRole("button", { name: "Nord" })).toBeVisible();
});
