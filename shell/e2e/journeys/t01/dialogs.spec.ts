import { expect, test } from "@playwright/test";
import { focusDesc, getA11ySeed, go, newSession, type A11ySeed, type Session } from "./helpers";

test.describe("dialogues, menus et popovers (creator)", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator");
  });
  test.afterAll(async () => s?.ctx.close());
  test.beforeEach(async () => {
    await go(s.page, "/", 2000);
  });

  test("Drawer « Nouveau » : focus dans le dialogue, piégé, Échap ferme et rend le focus", async () => {
    const trigger = s.page.getByRole("button", { name: "Nouveau", exact: true });
    await trigger.click();
    const dialog = s.page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    for (let i = 0; i < 12; i++) {
      await s.page.keyboard.press("Tab");
      const inside = await s.page.evaluate(
        () => !!document.activeElement?.closest("[role=dialog]"),
      );
      expect(inside).toBe(true);
    }
    await s.page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect(await focusDesc(s.page)).toContain("Nouveau");
  });

  test("palette de commandes : Ctrl+K met le focus sur le champ, Échap ferme", async () => {
    await s.page.keyboard.press("Control+k");
    const combo = s.page.getByRole("combobox", { name: /Rechercher une action/ });
    await expect(combo).toBeFocused();
    await s.page.keyboard.press("Escape");
    await expect(combo).toBeHidden();
  });

  test("cloche de notifications : Échap ferme et rend le focus au déclencheur", async () => {
    const bell = s.page.getByRole("button", { name: "Notifications" }).first();
    await bell.click();
    await expect(s.page.getByRole("dialog")).toBeVisible();
    await s.page.keyboard.press("Escape");
    await expect(s.page.getByRole("dialog")).toBeHidden();
    await expect(bell).toBeFocused();
  });

  test("menu du compte : Échap ferme et rend le focus au déclencheur", async () => {
    const account = s.page.getByRole("button", { name: "Compte" });
    await account.click();
    await expect(s.page.getByRole("button", { name: "Déconnexion" })).toBeVisible();
    await s.page.keyboard.press("Escape");
    await expect(s.page.getByRole("button", { name: "Déconnexion" })).toBeHidden();
    await expect(account).toBeFocused();
  });

  test("t01-009 : le menu « Actions » d'une carte expose menu/aria-expanded", async () => {
    // Finding t01-009 : ItemActions = <div> de <button> sans role=menu ni aria-haspopup/expanded.
    const trigger = s.page.getByRole("button", { name: "Actions" }).first();
    await trigger.click();
    const attrs = await trigger.evaluate((e) => ({
      popup: e.getAttribute("aria-haspopup"),
      expanded: e.getAttribute("aria-expanded"),
    }));
    expect(attrs.popup).not.toBeNull();
    expect(attrs.expanded).toBe("true");
    expect(await s.page.locator("[role=menu]").count()).toBeGreaterThan(0);
  });

  test("t01-010 : Échap ferme le menu « Actions » d'une carte", async () => {
    // Finding t01-010 : aucun gestionnaire clavier ; le menu reste ouvert après Échap.
    await s.page.getByRole("button", { name: "Actions" }).first().click();
    await expect(s.page.getByRole("button", { name: "Supprimer" }).first()).toBeVisible();
    await s.page.keyboard.press("Escape");
    await expect(s.page.getByRole("button", { name: "Supprimer" })).toHaveCount(0);
  });

  test("confirmation de suppression : focus initial sur Annuler, focus piégé", async () => {
    await s.page.getByRole("button", { name: "Actions" }).first().click();
    await s.page.getByRole("button", { name: "Supprimer" }).first().click();
    await expect(s.page.getByRole("dialog")).toBeVisible();
    await expect(s.page.getByRole("button", { name: "Annuler" })).toBeFocused();
    for (let i = 0; i < 4; i++) {
      await s.page.keyboard.press("Tab");
      expect(await s.page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(
        true,
      );
    }
    await s.page.getByRole("button", { name: "Annuler" }).click();
    await expect(s.page.getByRole("dialog")).toBeHidden();
  });

  test("t01-011 : annuler une confirmation de suppression rend le focus", async () => {
    // Finding t01-011 : après Échap, document.activeElement === body (menu démonté).
    await s.page.getByRole("button", { name: "Actions" }).first().click();
    await s.page.getByRole("button", { name: "Supprimer" }).first().click();
    await expect(s.page.getByRole("dialog")).toBeVisible();
    await s.page.keyboard.press("Escape");
    await expect(s.page.getByRole("dialog")).toBeHidden();
    expect(await focusDesc(s.page)).not.toBe("body");
  });

  test("t01-012 : la confirmation destructive est un alertdialog décrit", async () => {
    // Finding t01-012 : role=dialog sans aria-describedby pour « Cette action est irréversible ».
    await s.page.getByRole("button", { name: "Actions" }).first().click();
    await s.page.getByRole("button", { name: "Supprimer" }).first().click();
    const d = s.page.locator("[role=alertdialog], [role=dialog]").first();
    await expect(d).toBeVisible();
    expect(await d.getAttribute("role")).toBe("alertdialog");
    expect(await d.getAttribute("aria-describedby")).not.toBeNull();
  });

  test("éditeur d'app : Entrée sur « Sélectionner widget » sélectionne et expose ses commandes", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 3000);
    const sel = s.page.getByRole("button", { name: "Sélectionner widget-txt" });
    await sel.focus();
    await s.page.keyboard.press("Enter");
    await expect(s.page.getByRole("button", { name: "Supprimer widget-txt" })).toBeVisible();
  });

  test("t01-014 : Retour arrière dans une liste déroulante ne supprime pas le widget", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 3000);
    await s.page.getByRole("button", { name: "Sélectionner widget-txt" }).click();
    const before = await s.page.getByRole("button", { name: /Sélectionner widget-/ }).count();
    await s.page.locator("select").first().focus();
    await s.page.keyboard.press("Backspace");
    await s.page.waitForTimeout(400);
    expect(await s.page.getByRole("button", { name: /Sélectionner widget-/ }).count()).toBe(before);
  });
});

test.describe("SQL Lab (analyst)", () => {
  test("Échap puis Tab libère le focus de l'éditeur (pas de piège permanent)", async ({
    browser,
  }) => {
    const s = await newSession(browser, "analyst");
    try {
      await go(s.page, "/analytics/sql", 3000);
      await s.page.locator(".cm-content").first().click();
      await s.page.keyboard.type("select 1");
      await s.page.keyboard.press("Tab");
      await s.page.keyboard.press("Escape");
      await s.page.keyboard.press("Tab");
      expect(await focusDesc(s.page)).toContain("Exécuter");
    } finally {
      await s.ctx.close();
    }
  });

  test("t01-015 : la touche Tab de l'éditeur SQL est documentée ou ne piège pas", async ({
    browser,
  }) => {
    // Finding t01-015 : Tab insère une indentation (WCAG 2.1.2) ; la sortie par Échap n'est dite nulle part.
    const s = await newSession(browser, "analyst");
    try {
      await go(s.page, "/analytics/sql", 3000);
      await s.page.locator(".cm-content").first().click();
      await s.page.keyboard.press("Tab");
      const stillInEditor = await s.page.evaluate(
        () => !!document.activeElement?.closest(".cm-content"),
      );
      const hint = await s.page.getByText(/Échap/).count();
      expect(!stillInEditor || hint > 0).toBe(true);
    } finally {
      await s.ctx.close();
    }
  });
});
