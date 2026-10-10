import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder } from "./helpers";

test.setTimeout(90_000);
const text = (id: string, t: string, y = 0) => ({
  id,
  widget: "text",
  x: 0,
  y,
  w: 6,
  h: 2,
  props: { text: t },
});

test.describe("j04 raccourcis clavier du builder", () => {
  // finding j04-011
  test("j04-011 : Retour arrière dans un menu déroulant du panneau ne supprime pas le widget sélectionné", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("kbd-select", baseApp({ layout: grid([text("a", "A")]) }));
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner Texte" }).click();
    await page.getByLabel("Widget émetteur").focus();
    await page.keyboard.press("Backspace");
    await expect(page.getByRole("button", { name: "Sélectionner Texte" })).toHaveCount(1);
  });

  // finding j04-012
  test("j04-012 : en mode Aperçu, Suppr ne supprime pas un widget resté sélectionné", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "kbd-preview",
      baseApp({ layout: grid([text("a", "Visible en aperçu")]) }),
    );
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner Texte" }).click();
    await page.getByRole("button", { name: "Aperçu" }).click();
    await page.keyboard.press("Delete");
    await page.getByRole("button", { name: "Édition" }).click();
    await expect(page.getByRole("button", { name: "Sélectionner Texte" })).toHaveCount(1);
  });

  test("Ctrl+Z après une saisie de texte annule la saisie entière (coalescing) et pas un caractère", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("kbd-undo-text", baseApp({ layout: grid([text("a", "Base")]) }));
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner Texte" }).click();
    const f = page.getByLabel("Texte du widget");
    await f.fill("");
    await page.waitForTimeout(600);
    await f.pressSequentially("Bonjour", { delay: 30 });
    await page.getByRole("button", { name: "Annuler", exact: true }).click();
    await page.waitForTimeout(400);
    await expect(f).not.toHaveValue(/^Bonjou/);
  });
});
