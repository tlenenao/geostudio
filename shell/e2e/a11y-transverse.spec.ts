// SPDX-License-Identifier: Apache-2.0
//
// P33 — accessibilité transverse (audit 2026-09-29, findings t01-*, t01b-*, j03-014).
// Version pérenne, sur mocks, des parcours `shell/e2e/journeys/t01*` (qui exigent
// une stack réelle et ne tournent pas en CI).
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_ME, ANALYST_ME, READER_ME, mockCore, mockMe } from "./mocks";

async function openCatalog(page: Page) {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
}

test.describe("repères et titres de page", () => {
  test("t01-004 : chaque route a un titre de document distinct « Vue — GeoStudio »", async ({
    page,
  }) => {
    await mockCore(page);
    const titles = new Set<string>();
    for (const route of ["/", "/bookmarks", "/reports", "/settings"]) {
      await page.goto(route);
      await expect(page).toHaveTitle(/ — GeoStudio$/);
      titles.add(await page.title());
    }
    expect(titles.size).toBe(4);
  });

  test("t01-001/002 : un seul <main>, et un lien d'évitement en premier arrêt de tabulation", async ({
    page,
  }) => {
    await openCatalog(page);
    await expect(page.locator("main")).toHaveCount(1);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Aller au contenu principal" });
    await expect(skip).toBeFocused();
    await skip.press("Enter");
    await expect(page).toHaveURL(/#main-content$/);
  });

  test("t01-001 : l'éditeur d'app n'ajoute pas un second <main>", async ({ page }) => {
    await mockCore(page);
    await page.goto("/apps/1/edit");
    await expect(page.getByText("Titre version 2")).toBeVisible();
    await expect(page.locator("main")).toHaveCount(1);
  });

  test("t01-003 : chaque page porte un <h1>", async ({ page }) => {
    await mockCore(page);
    for (const route of [
      "/",
      "/bookmarks",
      "/reports",
      "/reports/new",
      "/maps/map-1",
      "/apps/1/edit",
      "/items/1",
    ]) {
      await page.goto(route);
      await expect(page.locator("h1").first(), route).toBeAttached();
    }
  });

  test("t01-013 : un nom accessible unique par carte (Ouvrir X, Actions de X)", async ({
    page,
  }) => {
    await openCatalog(page);
    await expect(page.getByRole("button", { name: "Ouvrir Alpha" })).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Actions de Alpha" })).toHaveCount(1);
  });

  test("t01-019 : le nombre de résultats / l'état vide est annoncé (role=status)", async ({
    page,
  }) => {
    await openCatalog(page);
    const status = page.getByRole("status").filter({ hasText: /élément/ });
    await expect(status).toHaveCount(1);
    await page.route("**/items?*", (route) =>
      route.fulfill({ json: { items: [], total: 0, page: 1, pageSize: 12 } }),
    );
    await page.getByRole("textbox", { name: "Rechercher" }).fill("zzzzzz-introuvable");
    await expect(page.getByRole("status").filter({ hasText: "Aucun résultat" })).toHaveCount(1);
  });
});

test.describe("menu « Actions » d'une carte", () => {
  test("t01-009/010/011 : menu ARIA, Échap, focus rendu au déclencheur", async ({ page }) => {
    await openCatalog(page);
    const trigger = page.getByRole("button", { name: "Actions de Alpha" });
    await expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    await trigger.click();
    // Radix masque le reste de la page (aria-hidden) tant que le menu est ouvert :
    // le déclencheur s'atteint donc par attribut, pas par rôle.
    const rawTrigger = page.locator('button[aria-label="Actions de Alpha"]');
    await expect(rawTrigger).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("menu")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(trigger).toBeFocused();

    // clic extérieur
    await trigger.click();
    // Radix n'écoute le pointerdown extérieur qu'après le montage du menu
    // (setTimeout 0) : cliquer avant que le menu soit visible est une course.
    await expect(page.getByRole("menu")).toBeVisible();
    await page.mouse.click(5, 400);
    await expect(page.getByRole("menu")).toHaveCount(0);

    // annulation d'une confirmation de suppression : alertdialog décrit, focus rendu
    await trigger.click();
    await page.getByRole("menuitem", { name: "Supprimer" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAccessibleDescription(/irréversible/);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});

test.describe("filtre spatial du catalogue", () => {
  test("t01-016/020 : alternative clavier (O/S/E/N) et carte au libellé français", async ({
    page,
  }) => {
    await openCatalog(page);
    await page.getByRole("button", { name: "Afficher la carte" }).click();
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    await expect(page.locator('[aria-label="Map"]')).toHaveCount(0);

    await page.getByLabel(/^Ouest/).fill("1");
    await page.getByLabel(/^Sud/).fill("2");
    await page.getByLabel(/^Est/).fill("3");
    await page.getByLabel(/^Nord/).fill("4");
    const req = page.waitForRequest((r) => /\/items\?/.test(r.url()) && r.url().includes("bbox="));
    await page.getByRole("button", { name: "Appliquer l'emprise" }).click();
    expect(decodeURIComponent((await req).url())).toContain("bbox=1,2,3,4");

    // emprise incohérente : message d'erreur, pas de filtre silencieux
    await page.getByLabel(/^Ouest/).fill("10");
    await page.getByRole("button", { name: "Appliquer l'emprise" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Emprise invalide" })).toBeVisible();
  });
});

test.describe("contrastes", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`t01-008 : le contour des champs atteint 3:1 (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await openCatalog(page);
      const ratio = await page.getByRole("textbox", { name: "Rechercher" }).evaluate((el) => {
        const cs = getComputedStyle(el);
        const lum = (rgb: string) => {
          const [r, g, b] = (rgb.match(/\d+/g) ?? []).slice(0, 3).map((v) => {
            const c = Number(v) / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const [a, b] = [lum(cs.borderTopColor), lum(cs.backgroundColor)].sort((x, y) => y - x);
        return (a + 0.05) / (b + 0.05);
      });
      expect(ratio).toBeGreaterThanOrEqual(3);
    });
  }
});

test.describe("formulaires et panneaux", () => {
  test("t01-017/018 : « Ajouter un rôle » expose aria-expanded/controls ; le nom requis est annoncé", async ({
    page,
  }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/roles", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({ json: [] });
    });
    await page.route("https://core.test/v1/roles/catalog", (route) => route.fulfill({ json: [] }));
    await page.goto("/admin/roles");
    const add = page.getByRole("button", { name: "Ajouter un rôle" });
    await expect(add).toHaveAttribute("aria-expanded", "false");
    await add.click();
    await expect(add).toHaveAttribute("aria-expanded", "true");
    await expect(add).toHaveAttribute("aria-controls", /.+/);
    const name = page.getByLabel("Nom", { exact: true });
    await expect(name).toHaveAttribute("aria-required", "true");
    const save = page.getByRole("button", { name: "Enregistrer" });
    await expect(save).toBeDisabled();
    await expect(save).toHaveAccessibleDescription(/obligatoire/);
    await name.fill("Support");
    await expect(save).toBeEnabled();
  });

  test("t01-015 : l'éditeur SQL dit comment le quitter au clavier", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ANALYST_ME);
    await page.goto("/analytics/sql");
    await expect(page.getByText("Échap puis Tab pour quitter l'éditeur")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Requête SQL" })).toHaveAccessibleDescription(
      /Échap puis Tab/,
    );
  });

  test("t01b-010 : champs RGPD nommés par leur libellé visible", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, { ...ADMIN_ME, privileges: [...ADMIN_ME.privileges, "compliance.manage"] });
    await page.goto("/admin/compliance");
    await expect(page.getByLabel(/Identifiant de l'utilisateur/)).toBeVisible();
    await expect(page.getByLabel(/Retapez le slug du tenant/)).toBeVisible();
  });
});

test.describe("réglage de thème", () => {
  test("t01-022 : clair/sombre/auto persistant, appliqué au rechargement", async ({ page }) => {
    await mockCore(page);
    await page.route("https://core.test/v1/notifications/preference", (route) =>
      route.fulfill({ json: { value: "all" } }),
    );
    await page.goto("/settings");
    const html = page.locator("html");
    await expect(html).not.toHaveAttribute("data-theme", /.+/);
    await page
      .getByRole("radiogroup", { name: "Apparence" })
      .getByRole("radio", { name: "Sombre" })
      .click();
    await expect(html).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
    await page
      .getByRole("radiogroup", { name: "Apparence" })
      .getByRole("radio", { name: /Automatique/ })
      .click();
    await expect(html).not.toHaveAttribute("data-theme", /.+/);
  });
});

test("t01-001 : une route publique (embed) porte un <main>", async ({ page }) => {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "app-1", title: "App", resourceType: "app", expiresAt: "2099-01-01" },
    }),
  );
  await page.route("**/v1/configs/by-item/app-1*", (route) =>
    route.fulfill({
      json: {
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", items: [] },
        },
      },
    }),
  );
  await page.goto("/embed/tok");
  await expect(page.locator("main")).toHaveCount(1);
});

test("t01b-015 : « Nouveau tileset 3D » masqué sans catalog.manage, visible avec", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, { ...READER_ME, capabilities: { tileset3dEnabled: true } });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Importer un fichier" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Nouveau tileset 3D" })).toHaveCount(0);
  await mockMe(page, { ...ADMIN_ME, capabilities: { tileset3dEnabled: true } });
  await page.reload();
  await expect(page.getByRole("button", { name: "Nouveau tileset 3D" })).toBeVisible();
});
