import { expect, test, type Page } from "@playwright/test";
import { axe, fmt, getA11ySeed, go, newSession, type A11ySeed, type Session } from "./helpers";

const SERIOUS = ["critical", "serious"];

async function seriousViolations(page: Page) {
  return (await axe(page)).filter((v) => SERIOUS.includes(v.impact));
}

async function sweep(page: Page, routes: string[]): Promise<string[]> {
  const bad: string[] = [];
  for (const r of routes) {
    await go(page, r, 2000);
    const v = await seriousViolations(page);
    if (v.length) bad.push(`${r}\n${fmt(v)}`);
  }
  return bad;
}

test.describe("axe-core : routes du shell en clair (creator)", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator");
  });
  test.afterAll(async () => s?.ctx.close());

  test("aucune violation critique/sérieuse sur les routes de production (clair)", async () => {
    test.setTimeout(240_000);
    const bad = await sweep(s.page, [
      "/",
      "/bookmarks",
      `/items/${seed.datasetId}`,
      `/items/${seed.appId}`,
      `/maps/${seed.mapId}`,
      `/apps/${seed.appId}/edit`,
      `/datasets/${seed.datasetId}/edit`,
      "/pipelines/new",
      "/datasets/visual-query/new",
      "/reports",
      "/reports/new",
      "/tasks",
      "/settings",
      `/apps/${seed.appId}`,
      `/sites/${seed.siteSlug}`,
      `/public/items/${seed.siteId}`,
      `/public/datasets/${seed.collectionId}`,
      "/route-inexistante",
    ]);
    expect(bad.join("\n\n")).toBe("");
  });

  // Le catalogue interne « kit gallery » n'est pas une page produit mais il est routé.
  test("t01-021 : la galerie du kit n'a aucune violation critique/sérieuse (clair)", async ({
    browser,
  }) => {
    // Finding t01-021 : role="tree" avec enfants <button> (aria-required-children) et
    // texte warn sur warn-soft à 4,46:1 ; constaté avec le persona admin.
    const a = await newSession(browser, "admin");
    try {
      await go(a.page, "/internal/kit-gallery", 3000);
      expect(fmt(await seriousViolations(a.page))).toBe("");
    } finally {
      await a.ctx.close();
    }
  });

  test("t01-023 : l'ordre des titres est valide dans l'éditeur d'app", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 3000);
    // Finding t01-023 : « Historique » (h3) sans h2 parent.
    const v = (await axe(s.page, ["heading-order"])).filter((x) => x.id === "heading-order");
    expect(fmt(v)).toBe("");
  });
});

test.describe("axe-core : administration (admin), clair", () => {
  test("aucune violation critique/sérieuse sur les 9 routes d'administration", async ({
    browser,
  }) => {
    test.setTimeout(180_000);
    const a = await newSession(browser, "admin");
    try {
      const bad = await sweep(a.page, [
        "/admin/extensions",
        "/admin/collections",
        "/admin/harvest",
        "/admin/roles",
        "/admin/users",
        "/admin/compliance",
        "/admin/infrastructure",
        "/tasks",
        "/settings",
      ]);
      expect(bad.join("\n\n")).toBe("");
    } finally {
      await a.ctx.close();
    }
  });
});

test.describe("axe-core : rôles restreints", () => {
  test("lecteur : catalogue, tâches et paramètres sans violation critique/sérieuse", async ({
    browser,
  }) => {
    const r = await newSession(browser, "reader");
    try {
      const bad = await sweep(r.page, ["/", "/tasks", "/settings"]);
      expect(bad.join("\n\n")).toBe("");
    } finally {
      await r.ctx.close();
    }
  });
});

test.describe("axe-core : thème sombre", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator", "dark");
  });
  test.afterAll(async () => s?.ctx.close());

  test("pages sobres (catalogue, favoris, tâches, paramètres, site) sans violation en sombre", async () => {
    test.setTimeout(120_000);
    const bad = await sweep(s.page, [
      "/",
      "/bookmarks",
      "/tasks",
      "/settings",
      `/sites/${seed.siteSlug}`,
      `/public/items/${seed.siteId}`,
    ]);
    expect(bad.join("\n\n")).toBe("");
  });

  test("t01-005 : les formulaires des éditeurs sont lisibles en sombre (contraste)", async () => {
    test.setTimeout(120_000);
    // Finding t01-005 : aucune couleur de texte/fond globale : les <label>/<select>/<button>
    // sans classe text-ink héritent du noir (#000) sur #0a1316 (1,11:1).
    const bad: string[] = [];
    for (const r of [
      "/reports/new",
      "/datasets/visual-query/new",
      `/apps/${seed.appId}/edit`,
      `/maps/${seed.mapId}`,
      `/datasets/${seed.datasetId}/edit`,
    ]) {
      await go(s.page, r, 2500);
      const v = (await axe(s.page, ["color-contrast"])).filter((x) => x.id === "color-contrast");
      if (v.length) bad.push(`${r}: ${v[0].nodes.length} nœuds, ex. ${v[0].nodes[0].target}`);
    }
    expect(bad.join("\n")).toBe("");
  });

  test("t01-006 : les routes publiques (fiche dataset) sont lisibles en sombre", async () => {
    // Finding t01-006 : hors AppLayout, aucun fond : texte clair (#e7eeec) sur blanc (1,17:1).
    await go(s.page, `/public/datasets/${seed.collectionId}`, 3000);
    const v = (await axe(s.page, ["color-contrast"])).filter((x) => x.id === "color-contrast");
    expect(fmt(v)).toBe("");
  });

  test("t01-006b : l'état « Accès refusé » d'une app est lisible en sombre", async () => {
    // Un lecteur sans droit sur l'app : fond blanc + texte danger clair (2,66:1).
    const r = await newSession(s.page.context().browser()!, "reader", "dark");
    try {
      await go(r.page, `/apps/${seed.appId}`, 3000);
      const v = (await axe(r.page, ["color-contrast"])).filter((x) => x.id === "color-contrast");
      expect(fmt(v)).toBe("");
    } finally {
      await r.ctx.close();
    }
  });
});
