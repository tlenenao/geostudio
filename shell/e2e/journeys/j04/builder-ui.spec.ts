import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder, widgetBtn, spaGo, fixme } from "./helpers";

test.setTimeout(90_000);

const text = (id: string, t: string, extra: object = {}) => ({
  id,
  widget: "text",
  x: 0,
  y: 0,
  w: 6,
  h: 2,
  props: { text: t },
  ...extra,
});

test.describe("j04 App Builder — édition", () => {
  test("nominal : ajouter un widget Texte, l'éditer, enregistrer, le retrouver au runtime", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("nominal");
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Texte", exact: true }).click();
    await page.getByLabel("Texte du widget").fill("Bonjour j04");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await page.waitForTimeout(1500);
    await spaGo(page, `/apps/${id}`);
    await expect(page.getByText("Bonjour j04")).toBeVisible();
  });

  test("j04-002 : la palette n'expose que des widgets de production (pas d'exemples SDK)", async ({
    page,
  }) => {
    const s = await getSeed();
    await openBuilder(page, s.emptyApp);
    // Le shell enregistre les widgets de démonstration dans la palette de tout créateur.
    const names = await page.locator("button", { hasText: /Compteur/ }).allInnerTexts();
    expect(names).toEqual([]);
  });

  test("undo/redo : boutons et clavier restaurent l'état, Annuler désactivé à l'origine", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("undo", baseApp({ layout: grid([text("a", "Alpha")]) }));
    await openBuilder(page, id);
    await expect(page.getByRole("button", { name: "Annuler", exact: true })).toBeDisabled();
    await widgetBtn(page).first().click();
    await page.getByRole("button", { name: /^Supprimer Texte/ }).click();
    await expect(widgetBtn(page)).toHaveCount(0);
    await page.getByRole("button", { name: "Annuler", exact: true }).click();
    await expect(widgetBtn(page)).toHaveCount(1);
    await page.getByRole("button", { name: "Rétablir" }).click();
    await expect(widgetBtn(page)).toHaveCount(0);
  });

  test("touche Suppr supprime le widget sélectionné et purge son câblage", async ({ page }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "suppr",
      baseApp({
        layout: grid([
          text("a", "Alpha"),
          { id: "b", widget: "button", x: 0, y: 2, w: 3, h: 1, props: { label: "Go" } },
        ]),
        messages: [{ id: "m1", from: "b", event: "click", to: "a", action: "setText" }],
      }),
    );
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner Bouton" }).click();
    await page
      .locator("body")
      .click({ position: { x: 5, y: 5 } })
      .catch(() => {});
    await page.getByRole("button", { name: "Sélectionner Bouton" }).click();
    await page.keyboard.press("Delete");
    await expect(page.getByRole("button", { name: "Sélectionner Bouton" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Retirer l'action/ })).toHaveCount(0);
  });

  test("garde de brouillon : quitter avec modifications propose la confirmation, annuler reste", async ({
    page,
  }) => {
    const s = await getSeed();
    await openBuilder(page, s.emptyApp);
    await page.getByRole("button", { name: "Texte", exact: true }).click();
    await page
      .getByRole("link", { name: /Catalogue/ })
      .first()
      .click();
    await expect(
      page.getByRole("alertdialog", { name: /Modifications non enregistrées/ }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: /Annuler/ })
      .last()
      .click();
    await expect(page).toHaveURL(/\/edit/);
  });

  test("garde de brouillon : après enregistrement, quitter ne demande plus rien", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("garde-save");
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Texte", exact: true }).click();
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await page.waitForTimeout(1500);
    await page
      .getByRole("link", { name: /Catalogue/ })
      .first()
      .click();
    await page.waitForTimeout(800);
    await expect(
      page.getByRole("alertdialog", { name: /Modifications non enregistrées/ }),
    ).toHaveCount(0);
    await expect(page).not.toHaveURL(/\/edit/);
  });

  // finding j04-003
  fixme(
    "j04-003 : fermer l'onglet (beforeunload) avec un brouillon non enregistré prévient de la perte",
    async ({ page }) => {
      const s = await getSeed();
      await openBuilder(page, s.emptyApp);
      await page.getByRole("button", { name: "Texte", exact: true }).click();
      let dialogSeen = false;
      page.on("dialog", async (d) => {
        if (d.type() === "beforeunload") dialogSeen = true;
        await d.dismiss();
      });
      await page.evaluate(() =>
        window.dispatchEvent(new Event("beforeunload", { cancelable: true })),
      );
      const prevented = await page.evaluate(() => {
        const e = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(e);
        return e.defaultPrevented;
      });
      expect(prevented || dialogSeen).toBe(true);
    },
  );

  test("condition d'affichage invalide : alerte et Enregistrer désactivé", async ({ page }) => {
    const s = await getSeed();
    await openBuilder(page, s.emptyApp);
    await page.getByRole("button", { name: "Texte", exact: true }).click();
    await page.getByLabel("Condition d'affichage (visibleWhen)").fill("vars.x >");
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  });
});
