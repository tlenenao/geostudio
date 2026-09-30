import { expect, test } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import {
  bug,
  failCoreReads,
  getA11ySeed,
  go,
  newSession,
  slowCoreReads,
  stateSnap,
  type A11ySeed,
  type Session,
  type StateSnap,
} from "./helpers";

const ADMIN_LISTS = [
  "/admin/extensions",
  "/admin/roles",
  "/admin/users",
  "/admin/collections",
  "/admin/harvest",
  "/tasks",
];

test.describe("états d'erreur (le cœur répond 500 aux lectures)", () => {
  let creator: Session;
  let admin: Session;
  let seed: A11ySeed;
  const items: Record<string, StateSnap> = {};
  const lists: Record<string, StateSnap> = {};
  let catalog: StateSnap;
  let settings: StateSnap;

  test.beforeAll(async ({ browser }) => {
    seed = await getA11ySeed();
    creator = await newSession(browser, "creator");
    await failCoreReads(creator.page);
    for (const p of [
      `/items/${seed.datasetId}`,
      `/datasets/${seed.datasetId}/edit`,
      `/apps/${seed.appId}/edit`,
      `/maps/${seed.mapId}`,
    ]) {
      await go(creator.page, p, 3000);
      items[p] = await stateSnap(creator.page);
    }
    await go(creator.page, "/bookmarks", 3000);
    catalog = await stateSnap(creator.page);
    await creator.ctx.close();

    admin = await newSession(browser, "admin");
    await failCoreReads(admin.page);
    for (const p of ADMIN_LISTS) {
      await go(admin.page, p, 3000);
      lists[p] = await stateSnap(admin.page);
    }
    await admin.page.route(`${CORE_URL}/v1/notifications/preference`, (r) =>
      r.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' }),
    );
    await go(admin.page, "/settings", 3000);
    settings = await stateSnap(admin.page);
    await admin.ctx.close();
  });

  test("le catalogue et les listes d'administration signalent l'erreur (role=alert)", () => {
    expect(catalog.alerts.join(" ")).toMatch(/Erreur de chargement/);
    expect(catalog.retry).toBe(true);
    for (const p of ADMIN_LISTS) {
      expect(lists[p].alerts.join(" "), p).toMatch(/Échec du chargement/);
    }
  });

  // Finding t04-010 : quatre écrans traduisent toute erreur de lecture (500, réseau) par « … introuvable. »
  bug("t04-010 : une erreur serveur n'est pas présentée comme « introuvable »", () => {
    for (const [p, snap] of Object.entries(items)) {
      expect(snap.alerts.join(" "), p).not.toMatch(/introuvable/i);
    }
  });

  // Finding t04-011 : seul le catalogue offre « Réessayer » ; les six listes d'administration n'ont ni bouton
  // ni formulation commune (« Erreur de chargement. » contre « Échec du chargement des … »).
  bug("t04-011 : toute erreur de chargement propose « Réessayer »", () => {
    for (const p of ADMIN_LISTS) expect(lists[p].retry, p).toBe(true);
  });

  // Finding t04-012 : si la préférence de notifications ne se charge pas, la section reste un titre vide.
  bug("t04-012 : Paramètres signale l'échec de chargement des préférences", () => {
    expect(settings.alerts.join(" ")).toMatch(/échec|erreur/i);
  });
});

test.describe("états de chargement (lectures retardées de 5 s)", () => {
  const snaps: Record<string, StateSnap> = {};
  test.beforeAll(async ({ browser }) => {
    const admin = await newSession(browser, "admin");
    await slowCoreReads(admin.page, 5000);
    for (const p of ADMIN_LISTS) {
      await go(admin.page, p, 900);
      snaps[p] = await stateSnap(admin.page);
    }
    await admin.ctx.close();
  });

  test("chaque liste affiche « Chargement… » dans une région role=status pendant l'attente", () => {
    for (const p of ADMIN_LISTS) {
      expect(snaps[p].status.map((x) => x.text).join(" "), p).toContain("Chargement");
    }
  });

  // Finding t04-009 : seul /admin/extensions utilise LoadingState (pastille animée) ; les cinq autres écrans
  // affichent un <p role=status> nu sans indicateur visuel.
  bug(
    "t04-009 : tous les écrans de chargement utilisent la même présentation (LoadingState)",
    () => {
      for (const p of ADMIN_LISTS) {
        expect(
          snaps[p].status.some((x) => x.spinner),
          p,
        ).toBe(true);
      }
    },
  );
});

test.describe("accès refusé (reader)", () => {
  test("un lecteur sur /admin/users reçoit un message français sans détail technique", async ({
    browser,
  }) => {
    const s = await newSession(browser, "reader");
    await go(s.page, "/admin/users", 2000);
    const text = await s.page.locator("body").innerText();
    expect(text).toContain("Accès réservé à la gestion des utilisateurs.");
    expect(text).not.toMatch(/forbidden|403|privilege/i);
    await s.ctx.close();
  });
});
