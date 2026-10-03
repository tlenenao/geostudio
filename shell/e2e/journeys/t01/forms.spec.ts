import { expect, test } from "@playwright/test";
import { getA11ySeed, go, newSession, type Session } from "./helpers";

test.describe("panneaux et formulaires d'administration (admin)", () => {
  let s: Session;
  test.beforeAll(async ({ browser }) => {
    await getA11ySeed();
    s = await newSession(browser, "admin");
  });
  test.afterAll(async () => s?.ctx.close());

  test("collections : Éditer/Partager exposent aria-expanded", async () => {
    await go(s.page, "/admin/collections", 2500);
    const btn = s.page.getByRole("button", { name: "Éditer" }).first();
    await expect(btn).toHaveAttribute("aria-expanded", "false");
    await btn.click();
    await expect(btn).toHaveAttribute("aria-expanded", "true");
  });

  test("t01-017 : « Ajouter un rôle » expose aria-expanded/aria-controls", async () => {
    // Finding t01-017 : bascule d'un formulaire en ligne sans état exposé (cf. REV-088).
    await go(s.page, "/admin/roles", 2000);
    const btn = s.page.getByRole("button", { name: "Ajouter un rôle" });
    await btn.click();
    expect(await btn.getAttribute("aria-expanded")).not.toBeNull();
    expect(await btn.getAttribute("aria-controls")).not.toBeNull();
  });

  test("t01-018 : le bouton « Enregistrer » d'un formulaire invalide dit pourquoi", async () => {
    // Finding t01-018 : <button disabled> sans aria-describedby ; champ « Nom » sans aria-required.
    await go(s.page, "/admin/roles", 2000);
    await s.page.getByRole("button", { name: "Ajouter un rôle" }).click();
    const save = s.page.getByRole("button", { name: "Enregistrer" });
    const attrs = await save.evaluate((e) => ({
      disabled: (e as HTMLButtonElement).disabled,
      describedby: e.getAttribute("aria-describedby"),
    }));
    const name = s.page.getByLabel("Nom", { exact: true }).first();
    const required =
      (await name.getAttribute("aria-required")) === "true" ||
      (await name.getAttribute("required")) !== null;
    expect(!attrs.disabled || attrs.describedby !== null || required).toBe(true);
  });

  test("paramètres : le choix de notifications est un radiogroup nommé", async ({ browser }) => {
    const c = await newSession(browser, "creator");
    try {
      await go(c.page, "/settings", 2000);
      const group = c.page.getByRole("radiogroup", { name: "Notifications" });
      await expect(group).toBeVisible();
      await expect(group.getByRole("radio")).toHaveCount(3);
      await expect(group.getByRole("radio", { name: "Toutes" })).toBeChecked();
    } finally {
      await c.ctx.close();
    }
  });

  test("tableau public trié au clavier : Entrée sur l'en-tête change aria-sort", async ({
    browser,
  }) => {
    const seed = await getA11ySeed();
    const c = await newSession(browser, "reader");
    try {
      await go(c.page, `/public/datasets/${seed.collectionId}`, 3000);
      const th = c.page.locator("th").first();
      await th.focus();
      await c.page.keyboard.press("Enter");
      await expect(th).toHaveAttribute("aria-sort", "ascending");
    } finally {
      await c.ctx.close();
    }
  });
});
