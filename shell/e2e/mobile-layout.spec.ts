import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// P31 (audit 2026-09-29) : zone de travail bornée à la fenêtre, en-tête qui
// tient dans 360 px, onglets au clavier, cibles tactiles >= 24 px (44 px sur
// pointeur grossier). Sur mocks : les parcours j12/j02/j03 de
// `e2e/journeys/` ne tournent pas en CI.

const PHONE = { width: 360, height: 740 };
const DESKTOP = { width: 1280, height: 800 };

async function pageOverflow(page: Page) {
  return page.evaluate(() => ({
    scrollHeight: document.scrollingElement!.scrollHeight,
    innerHeight: window.innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
  }));
}

for (const [name, vp] of [
  ["360", PHONE],
  ["1280", DESKTOP],
] as const) {
  test.describe(`fenêtre ${name} px`, () => {
    test.use({ viewport: vp });

    for (const route of ["/maps/map-1", "/"]) {
      test(`${route} : scrollHeight <= innerHeight (j02-009, j03-016, j12-003)`, async ({
        page,
      }) => {
        await mockCore(page);
        await page.goto(route);
        await expect(page.getByRole("main")).toBeVisible();
        // Contenu très haut dans une colonne/un onglet : il doit défiler en
        // interne, jamais étirer la page (les mocks seuls sont trop courts).
        await page.evaluate(() => {
          const host =
            document.querySelector("main ul")?.parentElement ??
            document.querySelector("main [role=tabpanel]") ??
            document.querySelector("main")!;
          const tall = document.createElement("div");
          tall.style.height = "3000px";
          host.appendChild(tall);
        });
        const o = await pageOverflow(page);
        expect(o.scrollHeight).toBeLessThanOrEqual(o.innerHeight);
      });
    }
  });
}

test.describe("éditeur de carte large", () => {
  test.use({ viewport: DESKTOP });

  test("le canevas de la carte tient dans la fenêtre (j02-009)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/maps/map-1");
    const canvas = page.locator("canvas.maplibregl-canvas").first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box!.height).toBeLessThanOrEqual(DESKTOP.height);
  });

  test("les boutons du panneau Couches font au moins 24x24 px (j12-007)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/maps/map-1");
    const btns = page.locator(
      '[aria-label^="Monter"], [aria-label^="Descendre"], [aria-label^="Masquer"], [aria-label^="Supprimer"]',
    );
    await expect(btns.first()).toBeVisible();
    for (const b of await btns.all()) {
      const box = await b.boundingBox();
      expect(box!.width).toBeGreaterThanOrEqual(24);
      expect(box!.height).toBeGreaterThanOrEqual(24);
    }
  });
});

test.describe("chrome sur téléphone (360 px)", () => {
  test.use({ viewport: PHONE, hasTouch: true });

  test("l'en-tête tient dans 360 px, actions repliées dans un menu (j12-002)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    const account = page.getByRole("button", { name: "Compte" });
    await expect(account).toBeVisible();
    const box = await account.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(360);
    expect((await pageOverflow(page)).scrollWidth).toBeLessThanOrEqual(360);
    const toggle = page.getByRole("button", { name: "Actions" });
    await expect(page.getByRole("button", { name: "Nouveau" })).toBeHidden();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("button", { name: "Nouveau" })).toBeVisible();
    expect((await pageOverflow(page)).scrollWidth).toBeLessThanOrEqual(360);
  });

  test("la navigation basse reste ancrée et les cibles font 44 px (j12-004, j12-008)", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/");
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
    const nav = page.getByRole("navigation", { name: "Navigation" });
    const nb = await nav.boundingBox();
    expect(nb!.y + nb!.height).toBeLessThanOrEqual(PHONE.height);
    for (const b of await nav.getByRole("button").all()) {
      expect((await b.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    for (const tab of await page.getByRole("tab").all()) {
      expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    // Pointeur grossier : simple icône de recherche, pas de hint clavier (j12-013).
    await page.getByRole("button", { name: "Actions" }).click();
    await expect(page.getByText("⌘K")).toBeHidden();
    const search = page.getByRole("button", { name: "Rechercher" });
    expect((await search.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });

  test("les onglets se pilotent aux flèches, Home et End (j12-010)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(3);
    await tabs.nth(1).focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
    await expect(tabs.nth(2)).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Home");
    await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowLeft");
    await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
  });
});

test("les commandes d'un widget sélectionné font au moins 24x24 px (j12-006)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App tactile");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Texte", exact: true }).click();
  await page.getByRole("button", { name: /^Sélectionner / }).click();
  const ctl = page.locator('[aria-label^="Déplacer"], [aria-label^="Supprimer"]');
  await expect(ctl.first()).toBeVisible();
  expect(await ctl.count()).toBeGreaterThanOrEqual(5);
  for (const b of await ctl.all()) {
    const box = await b.boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(24);
    expect(box!.height).toBeGreaterThanOrEqual(24);
  }
});
