import { expect, test } from "@playwright/test";
import {
  contrast,
  getA11ySeed,
  go,
  hexToRgb,
  newSession,
  type A11ySeed,
  type Session,
} from "./helpers";

test.describe("structure des pages (creator)", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator");
  });
  test.afterAll(async () => s?.ctx.close());

  test("la page déclare lang=fr et une navigation nommée", async () => {
    await go(s.page, "/", 1500);
    expect(await s.page.locator("html").getAttribute("lang")).toBe("fr");
    await expect(s.page.getByRole("navigation", { name: "Domaines" })).toBeVisible();
    await expect(s.page.getByRole("banner")).toBeVisible();
  });

  test("t01-001 : chaque page porte un repère <main>", async () => {
    // Finding t01-001 : AppLayout rend un <div> ; seul l'éditeur d'app a un <main>.
    await go(s.page, "/", 1500);
    expect(await s.page.locator("main, [role=main]").count()).toBeGreaterThan(0);
  });

  test("t01-002 : un lien d'évitement mène au contenu principal", async () => {
    // Finding t01-002 : 1er arrêt de tabulation = « Rechercher ⌘K », puis 11 contrôles de chrome.
    await go(s.page, "/", 1500);
    await s.page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await s.page.keyboard.press("Tab");
    const href = await s.page.evaluate(() => {
      const a = document.activeElement as HTMLAnchorElement | null;
      return a?.tagName === "A" ? a.getAttribute("href") : null;
    });
    expect(href).toMatch(/^#/);
  });

  test("t01-003 : chaque page porte un titre de niveau 1", async () => {
    // Finding t01-003 : catalogue, favoris, cartes, datasets, pipelines… n'ont aucun <h1>.
    const missing: string[] = [];
    for (const r of [
      "/",
      "/bookmarks",
      `/maps/${seed.mapId}`,
      `/datasets/${seed.datasetId}/edit`,
      "/datasets/visual-query/new",
      "/reports/new",
      "/pipelines/new",
      "/reports",
    ]) {
      await go(s.page, r, 2000);
      if ((await s.page.locator("h1").count()) === 0) missing.push(r);
    }
    expect(missing).toEqual([]);
  });

  test("t01-004 : le titre du document change à chaque route", async () => {
    // Finding t01-004 : document.title reste « GeoStudio » partout (WCAG 2.4.2).
    const titles = new Set<string>();
    for (const r of ["/", "/bookmarks", "/settings", "/tasks"]) {
      await go(s.page, r, 1500);
      titles.add(await s.page.title());
    }
    expect(titles.size).toBe(4);
  });

  test("t01-013 : les boutons d'une carte du catalogue ont un nom unique", async () => {
    // Finding t01-013 : N boutons « Ouvrir » et N boutons « Actions » de même nom accessible.
    await go(s.page, "/", 2500);
    const names = await s.page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>("button"))
        .filter((b) =>
          /^(Ouvrir|Actions)/.test(b.getAttribute("aria-label") ?? b.textContent ?? ""),
        )
        .map((b) => b.getAttribute("aria-label") ?? b.textContent?.trim() ?? ""),
    );
    expect(names.length).toBeGreaterThan(2);
    expect(new Set(names).size).toBe(names.length);
  });

  test("t01-019 : le nombre de résultats / l'état vide du catalogue est annoncé", async () => {
    // Finding t01-019 : aucune région aria-live/role=status ; « Aucun élément… » muet.
    await go(s.page, "/", 2000);
    await s.page.getByRole("textbox", { name: "Rechercher" }).fill("zzzzzz-introuvable");
    await expect(s.page.getByText("Aucun élément ne correspond")).toBeVisible();
    const live = await s.page
      .locator("[aria-live]:not([aria-live=off]), [role=status], [role=alert]")
      .filter({ hasText: /Aucun|résultat|éléments/ })
      .count();
    expect(live).toBeGreaterThan(0);
  });

  test("t01-016 : le filtre spatial du catalogue a une alternative clavier", async () => {
    // Finding t01-016 : le rectangle ne se dessine qu'à la souris (mousedown/mouseup).
    await go(s.page, "/", 2000);
    const alt = await s.page
      .getByLabel(/emprise|ouest|nord|bbox|coordonn/i)
      .filter({ has: s.page.locator("input") })
      .count();
    const inputs = await s.page
      .locator("input[type=number], input[aria-label*=mprise], input[aria-label*=bbox]")
      .count();
    expect(alt + inputs).toBeGreaterThan(0);
  });

  test("t01-020 : la carte du filtre spatial porte un libellé français", async () => {
    // Finding t01-020 : MapLibre pose aria-label="Map" sur son canevas/région.
    await go(s.page, "/", 2000);
    const english = await s.page.locator('[aria-label="Map"]').count();
    expect(english).toBe(0);
  });
});

test.describe("contrastes (jetons)", () => {
  async function tokens(browser: import("@playwright/test").Browser, scheme: "light" | "dark") {
    const s = await newSession(browser, "creator", scheme);
    try {
      await go(s.page, "/settings", 1500);
      return await s.page.evaluate(() => {
        const cs = getComputedStyle(document.documentElement);
        const v = (n: string) => cs.getPropertyValue(`--gs-${n}`).trim();
        return Object.fromEntries(
          [
            "ink",
            "ink-2",
            "ink-3",
            "warn",
            "danger",
            "ok",
            "accent",
            "background",
            "surface",
            "raised",
            "sunken",
            "accent-soft",
            "ai-soft",
            "ok-soft",
            "warn-soft",
            "danger-soft",
            "rule",
          ].map((n) => [n, v(n)]),
        ) as Record<string, string>;
      });
    } finally {
      await s.ctx.close();
    }
  }

  test("le texte principal (ink, ink-2) atteint 4,5:1 sur toutes les surfaces, clair et sombre", async ({
    browser,
  }) => {
    for (const scheme of ["light", "dark"] as const) {
      const t = await tokens(browser, scheme);
      const low: string[] = [];
      for (const fg of ["ink", "ink-2"])
        for (const bg of ["background", "surface", "raised", "sunken", "accent-soft"]) {
          const r = contrast(hexToRgb(t[fg]), hexToRgb(t[bg]));
          if (r < 4.5) low.push(`${scheme} ${fg} sur ${bg} = ${r.toFixed(2)}`);
        }
      expect(low).toEqual([]);
    }
  });

  test("t01-007 : ink-3 et warn atteignent 4,5:1 sur les surfaces teintées", async ({
    browser,
  }) => {
    // Finding t01-007 : ink-3 sur sunken 4,26 ; warn sur warn-soft 4,46 (clair) ; ink-3 sur accent-soft 4,05 (sombre).
    const low: string[] = [];
    for (const scheme of ["light", "dark"] as const) {
      const t = await tokens(browser, scheme);
      for (const fg of ["ink-3", "warn"])
        for (const bg of ["surface", "sunken", "accent-soft", "warn-soft", "danger-soft"]) {
          const r = contrast(hexToRgb(t[fg]), hexToRgb(t[bg]));
          if (r < 4.5) low.push(`${scheme} ${fg} sur ${bg} = ${r.toFixed(2)}`);
        }
    }
    expect(low).toEqual([]);
  });

  test("t01-008 : la bordure des champs atteint 3:1 (WCAG 1.4.11)", async ({ browser }) => {
    // Finding t01-008 : --gs-rule sur --gs-surface = 1,41:1 (clair), 1,35:1 (sombre).
    const low: string[] = [];
    for (const scheme of ["light", "dark"] as const) {
      const s = await newSession(browser, "creator", scheme);
      try {
        await go(s.page, "/", 2000);
        const c = await s.page.getByRole("textbox", { name: "Rechercher" }).evaluate((e) => {
          const cs = getComputedStyle(e);
          return { border: cs.borderTopColor, bg: cs.backgroundColor };
        });
        const r = contrast(c.border, c.bg);
        if (r < 3) low.push(`${scheme} bordure ${c.border} sur ${c.bg} = ${r.toFixed(2)}`);
      } finally {
        await s.ctx.close();
      }
    }
    expect(low).toEqual([]);
  });
});

test.describe("focus visible", () => {
  test("tous les arrêts de tabulation du catalogue montrent un indicateur de focus", async ({
    browser,
  }) => {
    const s = await newSession(browser, "creator");
    try {
      await go(s.page, "/", 2500);
      const bad: string[] = [];
      for (let i = 0; i < 22; i++) {
        await s.page.keyboard.press("Tab");
        const r = await s.page.evaluate(() => {
          const a = document.activeElement as HTMLElement | null;
          if (!a || a === document.body) return null;
          const cs = getComputedStyle(a);
          const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
          const ring = /rgb\(\d+, \d+, \d+\) 0px 0px 0px [2-9]px/.test(cs.boxShadow);
          return {
            outline,
            ring,
            d: `${a.tagName}|${a.getAttribute("aria-label") ?? a.textContent}`,
          };
        });
        if (r && !r.outline && !r.ring) bad.push(r.d);
      }
      expect(bad).toEqual([]);
    } finally {
      await s.ctx.close();
    }
  });
});
