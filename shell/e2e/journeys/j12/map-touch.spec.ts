import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { SHELL_URL } from "../_fixtures/env";
import { evalMap, getMapSeed, go, openAs, stubBasemap, touchGesture, VIEWPORTS } from "./helpers";

test.setTimeout(120_000);
test.use({ viewport: VIEWPORTS.phone, hasTouch: true });

async function openMap(page: Page, persona: "creator" | "reader" = "creator"): Promise<string> {
  const m = await getMapSeed();
  await stubBasemap(page);
  await openAs(page, persona);
  await go(page, `/maps/${m.pk}`, 5000);
  await expect
    .poll(() => evalMap<boolean>(page, "return m.loaded();"), { timeout: 20_000 })
    .toBe(true);
  return m.pk;
}

// Position écran (px CSS) d'un point géographique.
async function screenOf(page: Page, lng: number, lat: number): Promise<{ x: number; y: number }> {
  return evalMap(
    page,
    `const p = m.project([${lng}, ${lat}]); const r = m.getCanvas().getBoundingClientRect();
     return { x: r.left + p.x, y: r.top + p.y };`,
  );
}

test.describe("j12 carte : rendu et worker", () => {
  // Finding j12-001 : nginx sert le worker MapLibre en application/octet-stream.
  bug(
    "j12-001 : le worker MapLibre est servi avec un type MIME JavaScript",
    async ({ request }) => {
      const r = await request.get(`${SHELL_URL}/assets/maplibre-gl-worker.mjs`);
      expect(r.status()).toBe(200);
      expect(r.headers()["content-type"]).toMatch(/javascript/);
    },
  );

  // Finding j12-001 (même cause : le worker ne démarre pas, les tuiles restent « loading »).
  bug(
    "j12-001 : sans contournement, la couche vectorielle de la carte est rendue",
    async ({ page }) => {
      const m = await getMapSeed();
      await stubBasemap(page);
      await openAs(page, "creator");
      await go(page, `/maps/${m.pk}`, 8000);
      const n = await evalMap<number>(
        page,
        "return m.queryRenderedFeatures({layers:['j12-pts']}).length;",
      );
      expect(n).toBeGreaterThan(0);
    },
  );

  test("avec le type MIME rétabli, la carte charge ses tuiles et affiche les 12 points", async ({
    page,
  }) => {
    await openMap(page);
    const n = await evalMap<number>(
      page,
      "return m.queryRenderedFeatures({layers:['j12-pts']}).length;",
    );
    expect(n).toBeGreaterThan(5);
  });
});

test.describe("j12 carte tactile : popups", () => {
  test("un tap sur une entité ouvre le popup avec ses attributs, le bouton Fermer le referme", async ({
    page,
  }) => {
    await openMap(page);
    const p = await screenOf(page, 2.5, 46.25);
    await page.touchscreen.tap(p.x, p.y);
    const dialog = page.getByRole("dialog", { name: "Attributs de l'entité" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("P5");
    await dialog.getByRole("button", { name: "Fermer" }).tap();
    await expect(dialog).toHaveCount(0);
  });

  // Finding j12-005 : le bouton Fermer du popup fait 18×16 px.
  bug(
    "j12-005 : le bouton Fermer du popup offre une cible d'au moins 24×24 px",
    async ({ page }) => {
      await openMap(page);
      const p = await screenOf(page, 2.5, 46.25);
      await page.touchscreen.tap(p.x, p.y);
      const box = await page
        .getByRole("dialog", { name: "Attributs de l'entité" })
        .getByRole("button", { name: "Fermer" })
        .boundingBox();
      expect(box!.width).toBeGreaterThanOrEqual(24);
      expect(box!.height).toBeGreaterThanOrEqual(24);
    },
  );

  // Finding j12-011 : le popup n'est pas ramené dans la carte près d'un bord.
  bug(
    "j12-011 : un popup ouvert sur une entité au bord droit reste entièrement dans la fenêtre",
    async ({ page }) => {
      await openMap(page);
      const target = await screenOf(page, 2.9, 46.45);
      const dx = target.x - 350;
      await evalMap(
        page,
        `m.jumpTo({ center: m.unproject([m.project(m.getCenter()).x + ${dx}, m.project(m.getCenter()).y]) });`,
      );
      await page.waitForTimeout(1200);
      const edge = await screenOf(page, 2.9, 46.45);
      await page.touchscreen.tap(edge.x, edge.y);
      const dialog = page.getByRole("dialog", { name: "Attributs de l'entité" });
      await expect(dialog).toBeVisible();
      const box = await dialog.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(360);
    },
  );
});

test.describe("j12 carte tactile : gestes", () => {
  test("le pincement à deux doigts zoome la carte", async ({ page }) => {
    await openMap(page);
    const z0 = await evalMap<number>(page, "return m.getZoom();");
    await touchGesture(
      page,
      [
        { x: 150, y: 400 },
        { x: 210, y: 400 },
      ],
      [
        { x: 100, y: 400 },
        { x: 260, y: 400 },
      ],
    );
    await page.waitForTimeout(800);
    expect(await evalMap<number>(page, "return m.getZoom();")).toBeGreaterThan(z0 + 0.5);
  });

  test("le glissement à un doigt déplace la carte", async ({ page }) => {
    await openMap(page);
    const c0 = await evalMap<number>(page, "return m.getCenter().lng;");
    await touchGesture(page, [{ x: 250, y: 450 }], [{ x: 100, y: 450 }]);
    await page.waitForTimeout(500);
    expect(await evalMap<number>(page, "return m.getCenter().lng;")).toBeGreaterThan(c0);
  });
});

test.describe("j12 carte tactile : mesure et croquis au doigt", () => {
  test("Mesurer : deux taps donnent une distance et n'ouvrent aucun popup", async ({ page }) => {
    await openMap(page);
    await page.getByRole("button", { name: "Mesurer" }).tap();
    const a = await screenOf(page, 2.4, 46.2);
    const b = await screenOf(page, 2.6, 46.3);
    await page.touchscreen.tap(a.x, a.y);
    await page.touchscreen.tap(b.x, b.y);
    await expect(page.getByText(/^\d+([.,]\d+)?\s*(m|km)$/)).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Attributs de l'entité" })).toHaveCount(0);
  });

  test("Croquis rectangle : deux taps posent une forme comptabilisée", async ({ page }) => {
    await openMap(page);
    await page.getByRole("button", { name: "Croquis" }).tap();
    await page.getByRole("button", { name: "Rectangle" }).tap();
    await page.touchscreen.tap(80, 350);
    await page.touchscreen.tap(250, 500);
    await expect(page.getByText(/1 rectangle/i)).toBeVisible();
  });

  // Finding j12-009 : le tracé libre n'écoute que les événements souris.
  bug(
    "j12-009 : le tracé libre au doigt pose une forme au lieu de déplacer la carte",
    async ({ page }) => {
      await openMap(page);
      await page.getByRole("button", { name: "Croquis" }).tap();
      await page.getByRole("button", { name: "Tracé libre" }).tap();
      await touchGesture(page, [{ x: 100, y: 500 }], [{ x: 250, y: 560 }], 12);
      await expect(page.getByText(/1 tracé/i)).toBeVisible();
    },
  );
});

test.describe("j12 carte : mouvement réduit et lecteur", () => {
  for (const reduced of [true, false]) {
    test(`prefers-reduced-motion=${reduced ? "reduce" : "no-preference"} : « Ajuster à l'emprise des données » ${reduced ? "cadre sans animation" : "anime (témoin)"}`, async ({
      page,
    }) => {
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.emulateMedia({ reducedMotion: reduced ? "reduce" : "no-preference" });
      await openMap(page);
      await evalMap(page, "m.jumpTo({ center: [0, 0], zoom: 3 });");
      await page.getByRole("button", { name: "Ajuster à l'emprise des données" }).click();
      const moving = await evalMap<boolean>(page, "return m.isMoving();");
      expect(moving).toBe(!reduced);
    });
  }
});
