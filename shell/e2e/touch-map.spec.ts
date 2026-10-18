// SPDX-License-Identifier: Apache-2.0
//
// REV-286 (c) — « appareil tactile réel » remplacé par un automatisme.
// Ne tourne que sous les projets Playwright d'émulation `mobile-touch`
// (iPhone 13, 390 px) et `tablet-touch` (iPad, 810 px), tous deux
// `hasTouch: true` / `isMobile: true` (`playwright.config.ts`).
//
// Les gestes multi-points (pan, pincement, tracé, annulation) passent par le
// protocole DevTools `Input.dispatchTouchEvent` : Chromium fabrique alors de
// vrais événements `touchstart/move/end/cancel`, que MapLibre consomme comme
// sur un appareil. Limite acceptée et consignée (backlog REV-286) : ni
// l'inertie ni la pression/le rayon d'un vrai doigt, ni le clavier virtuel,
// ni la reconnaissance de gestes du système (retour arrière, zoom du
// navigateur) ne sont émulés — le résiduel « vrai appareil » est assumé.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type CDPSession, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

const isPhone = () => test.info().project.name === "mobile-touch";

// Enregistre chaque tuile demandée : MapLibre ne charge de nouvelles tuiles
// (autre z/x/y) que si la vue a réellement bougé — seul témoin observable du
// pan/zoom sans poignée sur l'instance de carte.
async function openMap(page: Page) {
  await mockCore(page);
  const tiles = new Set<string>();
  await page.route("**/collections/communes/tiles/**", (route) => {
    tiles.add(new URL(route.request().url()).pathname.split("/tiles/")[1]);
    return route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    });
  });
  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  await expect.poll(() => tiles.size).toBeGreaterThan(0);
  const box = (await canvas.boundingBox())!;
  return { canvas, box, tiles };
}

type Pt = { x: number; y: number };

async function touch(
  cdp: CDPSession,
  type: "touchStart" | "touchMove" | "touchEnd" | "touchCancel",
  points: Pt[],
) {
  await cdp.send("Input.dispatchTouchEvent", {
    type,
    touchPoints:
      type === "touchEnd" || type === "touchCancel" ? [] : points.map((p, id) => ({ ...p, id })),
  });
}

// Interpole un geste d'un jeu de points vers un autre en `steps` mouvements.
async function gesture(cdp: CDPSession, from: Pt[], to: Pt[], steps = 12) {
  await touch(cdp, "touchStart", from);
  for (let k = 1; k <= steps; k++) {
    const f = k / steps;
    await touch(
      cdp,
      "touchMove",
      from.map((p, i) => ({ x: p.x + (to[i].x - p.x) * f, y: p.y + (to[i].y - p.y) * f })),
    );
  }
  await touch(cdp, "touchEnd", []);
}

test.describe("gestes tactiles sur la carte", () => {
  test("pan au doigt : la carte se déplace (rendu du canevas modifié)", async ({ page }) => {
    const { canvas, box } = await openMap(page);
    // Laisser la carte au repos avant la mesure de référence.
    await page.waitForTimeout(800);
    const before = await canvas.screenshot();
    const cdp = await page.context().newCDPSession(page);
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await gesture(cdp, [{ x: cx + box.width / 3, y: cy }], [{ x: cx - box.width / 3, y: cy }]);
    await expect
      .poll(async () => !(await canvas.screenshot()).equals(before), { timeout: 8000 })
      .toBe(true);
  });

  test("pincement à deux doigts : le zoom change (tuiles d'un autre niveau)", async ({ page }) => {
    const { box, tiles } = await openMap(page);
    const zooms = () => new Set([...tiles].map((t) => t.split("/")[0]));
    const before = zooms();
    const cdp = await page.context().newCDPSession(page);
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    // Écartement : les deux doigts s'éloignent -> zoom avant. AUD-137 : un geste synthétique
    // émis avant que la carte soit réellement au repos peut être perdu sous charge ; on le
    // rejoue (chaque rejeu zoome encore, donc reste « un autre niveau »).
    await expect(async () => {
      await gesture(
        cdp,
        [
          { x: cx - 20, y: cy },
          { x: cx + 20, y: cy },
        ],
        [
          { x: cx - box.width / 3, y: cy },
          { x: cx + box.width / 3, y: cy },
        ],
        16,
      );
      await expect
        .poll(() => [...zooms()].some((z) => !before.has(z)), { timeout: 4000 })
        .toBe(true);
    }).toPass({ timeout: 24_000 });
  });

  test("tap sur une entité : popup, fermable au doigt (cible 44 px)", async ({ page }) => {
    const { canvas, box } = await openMap(page);
    const popup = page.getByRole("dialog", { name: "Attributs de l'entité" });
    await expect(async () => {
      await canvas.tap({ position: { x: box.width / 4, y: box.height / 4 } });
      await expect(popup).toBeVisible({ timeout: 300 });
    }).toPass({ timeout: 10_000 });
    const close = popup.getByRole("button", { name: "Fermer" });
    const cb = (await close.boundingBox())!;
    expect(cb.width).toBeGreaterThanOrEqual(44);
    expect(cb.height).toBeGreaterThanOrEqual(44);
    await close.tap();
    await expect(popup).toHaveCount(0);
  });
});

test.describe("mesure et croquis au toucher", () => {
  test("mesure : deux taps posent deux points et affichent une distance", async ({ page }) => {
    const { canvas, box } = await openMap(page);
    await page.getByRole("button", { name: "Mesurer" }).tap();
    await expect(page.getByRole("button", { name: "Mesurer" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await canvas.tap({ position: { x: box.width / 2 - 40, y: box.height / 2 } });
    await canvas.tap({ position: { x: box.width / 2 + 40, y: box.height / 2 } });
    await expect(page.getByText(/^\d[\d\s,.]*\s?(m|km)$/)).toBeVisible();
    // Effacer tout au doigt remet la mesure à zéro.
    await page.getByRole("button", { name: "Effacer tout" }).tap();
    await expect(page.getByText(/^\d[\d\s,.]*\s?(m|km)$/)).toHaveCount(0);
  });

  test("tracé libre : un geste complet pose une forme, un touchcancel l'annule", async ({
    page,
  }) => {
    const { box } = await openMap(page);
    await page.getByRole("button", { name: "Croquis" }).tap();
    await page.getByRole("button", { name: "Tracé libre" }).tap();
    const cdp = await page.context().newCDPSession(page);
    const y = box.y + box.height / 2;
    const stroke = async (end: "touchEnd" | "touchCancel") => {
      await touch(cdp, "touchStart", [{ x: box.x + 60, y }]);
      for (let k = 1; k <= 10; k++) {
        await touch(cdp, "touchMove", [{ x: box.x + 60 + 12 * k, y: y + 6 * k }]);
      }
      await touch(cdp, end, []);
    };
    // Annulé par le système (appel entrant, geste de l'OS) : rien n'est posé.
    await stroke("touchCancel");
    await expect(page.getByText(/\d+ tracé/)).toHaveCount(0);
    // Validé : une forme.
    await stroke("touchEnd");
    await expect(page.getByText(/^1 tracé/)).toBeVisible();
  });
});

test.describe("mise en page selon l'appareil", () => {
  test("le triptyque s'adapte : 3 onglets sur téléphone, 2 volets sur tablette", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    const tabs = page.getByRole("tab");
    if (isPhone()) {
      // Un seul volet à la fois, trois onglets.
      await expect(tabs).toHaveCount(3);
    } else {
      // Tablette : volet de travail ET volet latéral côte à côte, deux onglets
      // latéraux (parcourir / inspecter).
      await expect(tabs).toHaveCount(2);
      const work = (await page.getByRole("main").boundingBox())!;
      const side = (await page.getByRole("tabpanel").boundingBox())!;
      expect(work.width).toBeGreaterThan(300);
      expect(side.x).toBeGreaterThanOrEqual(work.x);
    }
    await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1);
    // Changer d'onglet au doigt bascule la sélection.
    const second = tabs.nth(1);
    await second.tap();
    await expect(second).toHaveAttribute("aria-selected", "true");
    // Aucune page horizontale à faire défiler.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});

// WCAG 2.5.8 (AA) : cible d'au moins 24x24 px. Hors champ : les liens inline
// dans une phrase (exemptés par la norme) et le lien d'évitement masqué.
async function undersizedTargets(page: Page) {
  return page.evaluate(() => {
    const sel =
      "button, [role=tab], [role=menuitem], input:not([type=hidden]), select, textarea, [role=checkbox], [role=switch], [role=slider], nav a[href]";
    const bad: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(sel)) {
      const s = getComputedStyle(el);
      if (s.visibility === "hidden" || s.display === "none") continue;
      if (el.closest('[aria-hidden="true"], .sr-only, .maplibregl-ctrl-attribution')) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      // Case/radio natives habillées par leur <label> : la cible est le label.
      const target = el.closest("label") ?? el;
      const tr = target.getBoundingClientRect();
      if (tr.width < 24 || tr.height < 24) {
        bad.push(
          `${el.tagName.toLowerCase()}[${el.className.toString().slice(0, 70)}] "${(el.getAttribute("aria-label") ?? el.getAttribute("placeholder") ?? (el.textContent || el.parentElement?.textContent) ?? "").trim().slice(0, 30)}" ${Math.round(tr.width)}x${Math.round(tr.height)}`,
        );
      }
    }
    return bad;
  });
}

test.describe("cibles tactiles >= 24x24 px", () => {
  test("catalogue", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    expect(await undersizedTargets(page)).toEqual([]);
  });

  test("éditeur de carte (barre de mesure comprise)", async ({ page }) => {
    await openMap(page);
    expect(await undersizedTargets(page)).toEqual([]);
  });
});
