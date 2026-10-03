import { expect, test } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor } from "../j03/api";
import { createApp, getA11ySeed, go, newSession, type A11ySeed, type Session } from "./helpers";

// Hauteurs des contrôles de saisie à ligne simple visibles sur la page courante.
async function controlHeights(s: Session): Promise<{ label: string; h: number }[]> {
  return s.page.evaluate(() => {
    const out: { label: string; h: number }[] = [];
    document
      .querySelectorAll(
        "input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=file]):not([type=color]):not([type=range]),select,button[role=combobox]",
      )
      .forEach((e) => {
        const b = e.getBoundingClientRect();
        if (b.width < 2 || b.height < 2) return;
        const label =
          e.getAttribute("aria-label") ?? (e as HTMLInputElement).placeholder ?? e.tagName;
        out.push({ label, h: Math.round(b.height) });
      });
    return out;
  });
}

test.describe("cohérence visuelle entre pages similaires (creator)", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator");
  });
  test.afterAll(async () => s?.ctx.close());

  test("les champs du kit du catalogue mesurent 36 px (h-9, convention du 2026-09-01)", async () => {
    await go(s.page, "/", 1500);
    const hs = await controlHeights(s);
    expect(hs.length).toBeGreaterThan(3);
    expect(new Set(hs.map((c) => c.h))).toEqual(new Set([36]));
  });

  // Finding t04-006 : le panneau « Mise en page d'impression », le renommage de page et le formulaire
  // de rapport utilisent des <select>/<input> natifs sans aucune classe : 18-30 px, look navigateur.
  test("t04-006 : aucun contrôle de formulaire ne reste sans style (hauteur < 32 px)", async () => {
    const tiny: string[] = [];
    for (const path of [`/apps/${seed.appId}/edit`, `/maps/${seed.mapId}`, "/reports/new"]) {
      await go(s.page, path, 2500);
      for (const c of await controlHeights(s))
        if (c.h < 32) tiny.push(`${path} ${c.label} ${c.h}px`);
    }
    // Observé : Format 18 px, Orientation 18 px, Titre 20 px, Renommer la page 18 px, /reports/new 28 et 30 px.
    expect(tiny, tiny.join("\n")).toEqual([]);
  });

  // Finding t04-007 : 72 contrôles natifs en h-8 contre 62 en h-9 ; sur une même page (dataset partagé)
  // le titre fait 36 px et les champs voisins 32 px.
  test("t04-007 : les champs d'une même page partagent une seule hauteur", async () => {
    await go(s.page, `/datasets/${seed.datasetId}/edit`, 2500);
    const hs = await controlHeights(s);
    expect(hs.length).toBeGreaterThan(5);
    expect([...new Set(hs.map((c) => c.h))]).toHaveLength(1);
  });
});

test.describe("cohérence des titres de page (admin)", () => {
  let s: Session;
  let appPk: string;
  test.beforeAll(async ({ browser }) => {
    const api = await apiFor("admin");
    appPk = await createApp(api, `${stamp("t04")}-admin-app`, {
      version: 1,
      kind: "app",
      theme: {},
      dataSources: [],
      messages: [],
      layout: { type: "grid", breakpoints: {}, items: [] },
    });
    s = await newSession(browser, "admin");
  });
  test.afterAll(async () => s?.ctx.close());

  async function firstHeading(path: string): Promise<string> {
    await go(s.page, path, 2000);
    return s.page.evaluate(() => {
      const h = document.querySelector("h1,h2");
      if (!h) return "aucun titre";
      const cs = getComputedStyle(h);
      return `${h.tagName.toLowerCase()} ${cs.fontSize} ${cs.fontWeight}`;
    });
  }

  test("les six pages d'administration partagent le même style de titre (h1 18 px / 700)", async () => {
    const styles = new Set<string>();
    for (const p of [
      "/admin/extensions",
      "/admin/roles",
      "/admin/users",
      "/admin/collections",
      "/admin/harvest",
      "/admin/infrastructure",
    ]) {
      styles.add(await firstHeading(p));
    }
    expect([...styles]).toEqual(["h1 18px 700"]);
  });

  // Finding t04-008 : aucun composant de titre de page : h1 18/700 (admin, réglages, tâches), h2 18/600
  // (requête visuelle, rapport), h2 20/600 (fiche d'item, dataset), h1 20/700 (fiche publique), aucun (catalogue).
  test("t04-008 : les pages de premier niveau partagent un style de titre commun", async () => {
    const seen: Record<string, string> = {};
    for (const p of [
      "/admin/users",
      "/settings",
      "/tasks",
      "/datasets/visual-query/new",
      `/items/${appPk}`,
      "/",
    ]) {
      seen[p] = await firstHeading(p);
    }
    expect(new Set(Object.values(seen)).size, JSON.stringify(seen)).toBe(1);
  });

  // Finding t04-020 : /tasks liste des identifiants hexadécimaux bruts (« item/75f41b05… — 2 », noms d'utilisateur
  // techniques) et cite « audit_log », un nom de table, dans le texte d'aide.
  test("t04-020 : la page Tâches n'expose ni identifiants bruts ni nom de table", async () => {
    await go(s.page, "/tasks", 2500);
    const text = await s.page.locator("body").innerText();
    expect(text).not.toMatch(/[0-9a-f]{32}/);
    expect(text).not.toMatch(/audit_log/);
  });
});
