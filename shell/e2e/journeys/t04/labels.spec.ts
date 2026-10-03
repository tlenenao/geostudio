import { expect, test } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor } from "../j03/api";
import {
  bug,
  createApp,
  getA11ySeed,
  go,
  newSession,
  type A11ySeed,
  type Session,
} from "./helpers";

test.describe("libellés, vocabulaire et formats (creator, navigateur en-US)", () => {
  let s: Session;
  let seed: A11ySeed;
  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    s = await newSession(browser, "creator");
  });
  test.afterAll(async () => s?.ctx.close());

  test("le filtre de type du catalogue porte des libellés français et l'historique formate en fr-FR", async () => {
    await go(s.page, "/", 1500);
    expect(await s.page.locator("html").getAttribute("lang")).toBe("fr");
    const opts = await s.page.locator("select[aria-label='Type'] option").allInnerTexts();
    for (const label of ["Carte", "Alerte", "Rapport", "Vue enregistrée"]) {
      expect(opts).toContain(label);
    }
    // l'historique de versions formate les dates en fr-FR malgré un navigateur en-US
    await go(s.page, `/apps/${seed.appId}/edit`, 2500);
    const text = await s.page.locator("body").innerText();
    expect(text).toMatch(/Version 1 — \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}/);
  });

  test("le compteur du catalogue s'accorde au singulier (1 élément) et le filtre vide propose de réinitialiser", async () => {
    await go(s.page, "/bookmarks", 2000);
    await expect(s.page.getByText("1 élément", { exact: true })).toBeVisible();
    await go(s.page, "/", 1500);
    await s.page
      .locator("select[aria-label='Portée']")
      .selectOption({ label: "Partagés avec moi" });
    await expect(s.page.getByText("Aucun résultat")).toBeVisible();
    await expect(s.page.getByRole("button", { name: "Réinitialiser les filtres" })).toBeVisible();
  });

  // Finding t04-001 : la fiche d'item affiche l'énumération brute (DATASET, ALERT, BOOKMARK)
  // au-dessus du titre, alors que le panneau de gauche de la même page dit « Alerte ».
  test("t04-001 : l'étiquette de type de la fiche d'item est traduite", async () => {
    await go(s.page, `/items/${seed.alertId}`, 2000);
    const eyebrow = s.page.locator("article span.uppercase").first();
    await expect(eyebrow).toBeVisible();
    expect((await eyebrow.innerText()).toLowerCase()).toBe("alerte");
  });

  // Finding t04-002 : « Modifié » de la fiche d'item est l'horodatage ISO brut du cœur.
  test("t04-002 : la date de modification de la fiche d'item est formatée", async () => {
    await go(s.page, `/items/${seed.datasetId}`, 2000);
    const dd = s.page
      .locator("dt", { hasText: "Modifié" })
      .locator("xpath=following-sibling::dd[1]");
    await expect(dd).not.toHaveText(/\d{4}-\d{2}-\d{2}T\d{2}:/);
  });

  // Finding t04-003 : le tiroir « Nouveau » propose « Map » (catalogue : « Carte »).
  test("t04-003 : le tiroir Nouveau n'a aucune option en anglais (« Map »)", async () => {
    await go(s.page, "/", 1500);
    await s.page.getByRole("button", { name: "Nouveau" }).click();
    const opts = await s.page
      .locator("[role=dialog] select")
      .first()
      .locator("option")
      .allInnerTexts();
    expect(opts).not.toContain("Map");
    await s.page.keyboard.press("Escape");
  });

  // Finding t04-004 : le type de source « Features » (anglais) côtoie « Statistiques » et « Statique ».
  test("t04-004 : le sélecteur de type de source de l'éditeur d'app est entièrement français", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 2500);
    const opts = await s.page
      .locator("select[aria-label^='Type de la source']")
      .first()
      .locator("option")
      .allInnerTexts();
    expect(opts).not.toContain("Features");
  });

  // Finding t04-005 : le sélecteur de couches affiche la clé technique « vector » à côté du titre.
  test("t04-005 : la liste des sources de couche n'expose pas la clé technique « vector »", async () => {
    await go(s.page, `/maps/${seed.mapId}`, 2500);
    await expect(s.page.getByText("vector", { exact: true })).toHaveCount(0);
  });

  // Finding t04-014 : « 0 éléments » (le français ne met au pluriel qu'à partir de 2).
  test("t04-014 : le compteur du catalogue s'accorde « 0 élément »", async () => {
    await go(s.page, "/reports", 2000);
    await expect(s.page.getByText("0 élément", { exact: true })).toBeVisible();
  });

  // Finding t04-015 : l'état vide d'une famille (Rapports) invite à créer « votre première carte, appli
  // ou jeu de données » et affiche en plus « 0 élément(s) » + pagination.
  test("t04-015 : l'état vide de la page Rapports parle de rapports", async () => {
    await go(s.page, "/reports", 2000);
    const body = await s.page.locator("body").innerText();
    expect(body).toMatch(/rapport/i);
    expect(body).not.toMatch(/Créez votre première carte/);
  });

  // Finding t04-013 : la cloche formate createdAt via toLocaleString() sans locale : format du
  // navigateur (ici en-US) alors que tout le reste de l'application force fr-FR.
  test("t04-013 : les dates de la cloche de notifications suivent le format fr-FR", async ({
    browser,
  }) => {
    // Session dédiée : la liste est lue au montage de la cloche, la route doit précéder la connexion.
    const n = await newSession(browser, "creator", "en-US", async (page) => {
      await page.route(/\/v1\/notifications\?/, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            notifications: [
              {
                id: "n1",
                kind: "ingestion",
                status: "success",
                itemId: null,
                itemResourceType: null,
                itemTitle: "t04-notif",
                errorMessage: null,
                createdAt: "2026-09-30T14:05:09Z",
                readAt: null,
              },
            ],
            total: 1,
          }),
        }),
      );
    });
    try {
      await go(n.page, "/", 1000);
      await n.page.getByRole("button", { name: "Notifications", exact: true }).click();
      await expect(n.page.getByText("t04-notif")).toBeVisible();
      const row = n.page.locator("div").filter({ hasText: "t04-notif" }).last();
      // Observé en en-US : « 9/30/2026, 2:05:09 PM ».
      await expect(row).toContainText(/30\/09\/2026/);
    } finally {
      await n.ctx.close();
    }
  });

  // Finding t04-016 : l'indicateur affiche String(value) : ni séparateur de milliers ni virgule décimale.
  test("t04-016 : l'indicateur formate ses valeurs en fr-FR", async () => {
    const api = await apiFor("creator");
    const id = await createApp(api, `${stamp("t04")}-kpi`, {
      version: 1,
      kind: "app",
      theme: {},
      dataSources: [
        {
          id: "s1",
          type: "static",
          service: "core",
          layer: "",
          query: {
            records: [
              { id: 1, properties: { amount: 1234567.5 } },
              { id: 2, properties: { amount: 0.25 } },
            ],
          },
        },
      ],
      messages: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          {
            id: "kpi",
            widget: "indicator",
            x: 0,
            y: 0,
            w: 6,
            h: 4,
            props: { dataSourceId: "s1", agg: "sum", field: "amount", label: "Total" },
          },
        ],
      },
    });
    await go(s.page, `/apps/${id}`, 2500);
    const text = await s.page.locator("body").innerText();
    // Observé : « 1234567.75 ». Attendu fr-FR : « 1 234 567,75 ».
    expect(text).toMatch(/1\s234\s567,75/);
  });

  // Finding t04-017 : le contrôle d'attribution MapLibre garde ses libellés anglais (aucune locale passée).
  bug("t04-017 : les contrôles de carte sont libellés en français", async () => {
    await go(s.page, `/maps/${seed.mapId}`, 2500);
    const labels = await s.page
      .locator("[aria-label],[title]")
      .evaluateAll((els) =>
        els.flatMap((e) => [e.getAttribute("aria-label"), e.getAttribute("title")]).filter(Boolean),
      );
    expect(labels).not.toContain("Toggle attribution");
    expect(labels).not.toContain("Map");
  });

  // Finding t04-019 : le canevas nomme les widgets par leur id technique (« Sélectionner widget-tbl »)
  // et les boutons de point de rupture restent « sm / md / lg ».
  test("t04-019 : le canevas de l'éditeur d'app n'expose pas d'identifiants techniques", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 2500);
    const labels = await s.page
      .locator("button[aria-label]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
    expect(labels.filter((l) => /widget-[a-z0-9]+/i.test(l))).toEqual([]);
    expect(labels.filter((l) => /^Éditer en (sm|md|lg)$/.test(l))).toEqual([]);
  });

  // Finding t04-021 : « Ajouter une page/source/action/variable » sont des <button> natifs sans style
  // (police 16 px, fond transparent) à côté de Button du kit (12 px, fond surface).
  test("t04-021 : les boutons « Ajouter… » de l'éditeur d'app utilisent le Button du kit", async () => {
    await go(s.page, `/apps/${seed.appId}/edit`, 2500);
    const info = await s.page.evaluate(() => {
      const pick = (re: RegExp) =>
        [...document.querySelectorAll("button")]
          .filter((b) => re.test((b.textContent ?? "").trim()))
          .map((b) => {
            const cs = getComputedStyle(b);
            return { t: (b.textContent ?? "").trim(), fs: cs.fontSize, bg: cs.backgroundColor };
          });
      return { add: pick(/^Ajouter une (page|source|action|variable)$/), kit: pick(/^Annuler$/) };
    });
    expect(info.add.length).toBeGreaterThan(0);
    const kitFont = info.kit[0]?.fs;
    for (const b of info.add) expect(b.fs, b.t).toBe(kitFont);
  });

  // Finding t04-022 : « Dataset » / « jeu de données » / « Jeu de données partagé » / « App » / « Application » / « appli ».
  test("t04-022 : un seul terme désigne un jeu de données dans l'interface", async () => {
    await go(s.page, "/reports", 2000);
    const empty = await s.page.locator("body").innerText();
    const usesFrench = /jeu de données/i.test(empty);
    await s.page.getByRole("button", { name: "Nouveau" }).first().click();
    const dialog = await s.page.locator("[role=dialog]").innerText();
    await s.page.keyboard.press("Escape");
    const usesAnglicism = /\bDataset\b/.test(dialog);
    expect(usesFrench && usesAnglicism).toBe(false);
  });
});
