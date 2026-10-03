import { test, expect } from "@playwright/test";
import { apiFor } from "../j03/api";
import { createSite, getDatasetSeed, richItem, siteConfig } from "../j10/seed";
import { getMapSeed, getTwoColApp, go, openAs, stubBasemap, VIEWPORTS } from "./helpers";

test.setTimeout(120_000);
test.use({ viewport: VIEWPORTS.phone, hasTouch: true });

test.describe("j12 runtime d'app sur téléphone", () => {
  // Finding j12-012 : les widgets restent côte à côte à 360 px.
  test("j12-012 : deux widgets 6/12 s'empilent (≥ 300 px chacun) à 360 px", async ({ page }) => {
    const app = await getTwoColApp();
    await openAs(page, "creator");
    await go(page, `/apps/${app}`, 3000);
    const widths = await page.evaluate(() =>
      [...document.querySelectorAll("[data-col]")].map((e) => e.getBoundingClientRect().width),
    );
    expect(widths.length).toBe(2);
    for (const w of widths) expect(w).toBeGreaterThanOrEqual(300);
  });

  test("le runtime d'une app ne déborde pas horizontalement à 360 px et affiche les lignes de la table", async ({
    page,
  }) => {
    const app = await getTwoColApp();
    await openAs(page, "creator");
    await go(page, `/apps/${app}`, 3000);
    await expect(page.getByText("nom")).toBeVisible();
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(sw).toBeLessThanOrEqual(360);
  });
});

test.describe("j12 éditeur d'app au toucher", () => {
  // Finding j12-006 : commandes du widget sélectionné en 18×16 px.
  test("j12-006 : les commandes Déplacer/Supprimer d'un widget sélectionné font au moins 24×24 px", async ({
    page,
  }) => {
    const app = await getTwoColApp();
    await openAs(page, "creator");
    await go(page, `/apps/${app}/edit`, 3500);
    await page.getByRole("tab", { name: "Canevas" }).tap();
    await page.getByRole("button", { name: /Sélectionner widget-tbl/ }).tap();
    const boxes = await page
      .locator('[aria-label^="Déplacer widget-tbl"], [aria-label^="Supprimer widget-tbl"]')
      .evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return [Math.round(r.width), Math.round(r.height)];
        }),
      );
    expect(boxes.length).toBe(5);
    for (const [w, h] of boxes) {
      expect(w).toBeGreaterThanOrEqual(24);
      expect(h).toBeGreaterThanOrEqual(24);
    }
  });
});

test.describe("j12 éditeur de carte sur téléphone", () => {
  // Finding j12-007 : boutons du panneau Couches en 18×16 px.
  test("j12-007 : les boutons monter/descendre/masquer/supprimer d'une couche font au moins 24×24 px", async ({
    page,
  }) => {
    const m = await getMapSeed();
    await stubBasemap(page);
    await openAs(page, "creator");
    await go(page, `/maps/${m.pk}`, 4000);
    await page.getByRole("tab", { name: "Couches" }).tap();
    const boxes = await page
      .locator(
        '[aria-label^="Monter"], [aria-label^="Descendre"], [aria-label^="Masquer"], [aria-label^="Supprimer"]',
      )
      .evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return [Math.round(r.width), Math.round(r.height)];
        }),
      );
    expect(boxes.length).toBeGreaterThanOrEqual(3);
    for (const [w, h] of boxes) {
      expect(w).toBeGreaterThanOrEqual(24);
      expect(h).toBeGreaterThanOrEqual(24);
    }
  });
});

test.describe("j12 surfaces publiques sur téléphone", () => {
  test("un site publié avec un tableau Markdown large ne déborde pas de 360 px", async ({
    page,
  }) => {
    const creator = await apiFor("creator");
    const md =
      "| a | b | c | d | e | f |\n|---|---|---|---|---|---|\n| une-valeur-longue-1 | une-valeur-longue-2 | une-valeur-longue-3 | une-valeur-longue-4 | une-valeur-longue-5 | une-valeur-longue-6 |\n\nhttps://exemple.org/un/chemin/tres/long/sans/aucun/espace/qui/depasse/la/largeur/ecran/du/telephone";
    const s = await createSite(creator, "aud-j12-site", siteConfig([richItem("r", md)]), {
      publish: true,
    });
    await page.goto(`/sites/${s.slug}`);
    await expect(page.getByText("une-valeur-longue-1")).toBeVisible();
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(sw).toBeLessThanOrEqual(360);
  });

  test("la fiche publique d'un dataset tient dans 360 px", async ({ page }) => {
    const ds = await getDatasetSeed();
    await page.goto(`/public/datasets/${ds.collectionId}`);
    await expect(page.getByRole("link", { name: "Télécharger GeoJSON" })).toBeVisible();
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(sw).toBeLessThanOrEqual(360);
  });
});
