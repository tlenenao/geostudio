import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { apiFor } from "../j03/api";
import { getMapSeed, go, openAs, smallTargets, stubMap, VIEWPORTS } from "./helpers";

test.setTimeout(120_000);

test.beforeAll(async () => {
  // Assez d'items pour que le catalogue dépasse la hauteur d'un téléphone.
  const creator = await apiFor("creator");
  for (let i = 0; i < 8; i++) {
    await creator.send("POST", "/v1/configs", {
      title: `aud-j12-cat-${i}`,
      config: { version: 1, kind: "app", layout: { type: "grid", breakpoints: {}, items: [] } },
    });
  }
});

test.describe("j12 gabarit triptyque : seuils de viewport", () => {
  test("899 px et moins : onglets + navigation basse ; 900 px et plus : trois colonnes + barre de domaines", async ({
    page,
  }) => {
    await openAs(page, "creator");
    for (const [vp, narrow] of [
      [VIEWPORTS.phone, true],
      [VIEWPORTS.tablet, true],
      [VIEWPORTS.narrowEdge, true],
      [VIEWPORTS.wideEdge, false],
      [VIEWPORTS.desktop, false],
    ] as const) {
      await page.setViewportSize(vp);
      await go(page, "/", 1200);
      await expect(page.getByRole("tablist")).toHaveCount(narrow ? 1 : 0);
      await expect(page.getByRole("navigation", { name: /domaines/i })).toHaveCount(narrow ? 0 : 1);
    }
  });
});

test.describe("j12 chrome sur téléphone (360 px)", () => {
  test.use({ viewport: VIEWPORTS.phone, hasTouch: true });

  // Finding j12-002 : la barre du haut exige ~517 px, le bouton Compte sort de l'écran.
  test.fixme("j12-002 : l'en-tête tient dans 360 px (Notifications et Compte atteignables sans défilement horizontal)", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await go(page, "/", 1500);
    const acc = await page.getByRole("button", { name: "Compte" }).boundingBox();
    expect(acc!.x + acc!.width).toBeLessThanOrEqual(360);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(sw).toBeLessThanOrEqual(360);
  });

  // Finding j12-004 : la navigation basse n'est pas ancrée à l'écran.
  test.fixme("j12-004 : la navigation basse reste visible sans défiler le catalogue", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await go(page, "/", 2500);
    const top = await page
      .getByRole("navigation", { name: /navigation/i })
      .last()
      .evaluate((n) => n.getBoundingClientRect().top);
    expect(top).toBeLessThan(740);
  });

  // Finding j12-008 : cibles de 32 px partout (44 px recommandés).
  test.fixme("j12-008 : les boutons de la navigation basse et les onglets font au moins 44 px de haut", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await go(page, "/", 1500);
    const small = (await smallTargets(page)).filter(
      (t) => t.h < 44 && /Catalogue|Cartes|Tâches|Plus|Filtrer|Résumé/.test(t.text),
    );
    expect(small).toEqual([]);
  });

  // Finding j12-010 : les onglets ne sont pas pilotables aux flèches.
  test.fixme("j12-010 : les flèches gauche/droite déplacent la sélection de l'onglet (patron tablist)", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await go(page, "/", 1500);
    const tabs = page.getByRole("tab");
    await tabs.nth(1).focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
  });

  test("les onglets exposent le panneau actif et le changement d'onglet remplace le contenu", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await go(page, "/", 1500);
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(3);
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
    const before = await page.getByRole("tabpanel").innerText();
    await tabs.first().tap();
    await expect(tabs.first()).toHaveAttribute("aria-selected", "true");
    expect(await page.getByRole("tabpanel").innerText()).not.toBe(before);
  });

  test("le tiroir d'import reste utilisable quand le clavier virtuel réduit la fenêtre à 300 px", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await page.setViewportSize({ width: 360, height: 300 });
    await page.getByRole("button", { name: "Importer un fichier" }).click({ force: true });
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Titre de la collection").focus();
    await dialog.getByRole("button", { name: "Importer", exact: true }).scrollIntoViewIfNeeded();
    const box = await dialog.getByRole("button", { name: "Importer", exact: true }).boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(300);
    const dlgBox = await dialog.boundingBox();
    expect(dlgBox!.width).toBeLessThanOrEqual(360);
  });
});

test.describe("j12 thèmes et mouvement", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`thème ${scheme} à 360 px : axe ne relève ni contraste insuffisant ni cible de moins de 24 px sur 5 écrans`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize(VIEWPORTS.phone);
      await openAs(page, "admin");
      for (const route of ["/", "/tasks", "/admin/users", "/settings", "/analytics/sql"]) {
        await go(page, route, 1800);
        const res = await new AxeBuilder({ page })
          .withRules(["color-contrast", "target-size"])
          .analyze();
        expect(
          res.violations.map((v) => `${route} ${v.id} ${v.nodes.length}`),
          `${scheme} ${route}`,
        ).toEqual([]);
      }
    });
  }

  test("prefers-reduced-motion : toutes les transitions CSS des boutons sont neutralisées", async ({
    page,
  }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openAs(page, "creator");
    const durations = await page
      .locator("button")
      .evaluateAll((els) => els.map((e) => getComputedStyle(e).transitionDuration));
    expect(durations.length).toBeGreaterThan(3);
    for (const d of durations) {
      for (const part of d.split(",")) expect(parseFloat(part)).toBeLessThanOrEqual(0.0001);
    }
  });
});

test.describe("j12 carte : hauteur de la mise en page large", () => {
  // Finding j12-003 : sur ≥ 900 px la grille grandit avec le panneau le plus haut.
  test.fixme("j12-003 : à 1280×800 l'éditeur de carte ne dépasse pas la hauteur de la fenêtre", async ({
    page,
  }) => {
    await stubMap(page);
    const m = await getMapSeed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await openAs(page, "creator");
    await go(page, `/maps/${m.pk}`, 4000);
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(h).toBeLessThanOrEqual(800 + 2);
  });
});
