import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { bug, CORE_READS, getA11ySeed, go, newSession, type Session } from "./helpers";

const BANNER = /Connexion au serveur perdue/;
const LIST_ERROR = /Erreur de chargement/;

// Coupe les lectures de la liste d'items (le catalogue et /bookmarks) mais laisse le chrome vivre.
async function cutReads(page: Page, on: () => boolean): Promise<void> {
  await page.route(`${CORE_URL}/v1/**`, (r: Route) => {
    const req = r.request();
    if (on() && CORE_READS(req.url(), req.method()) && /\/v1\/items(\?|$)/.test(req.url())) {
      return r.abort("connectionrefused");
    }
    return r.continue();
  });
}

// Double clic humain : deux clics souris séparés de `gapMs` (Playwright dblclick n'en laisse aucun).
async function doubleClick(page: Page, target: Locator, gapMs: number): Promise<void> {
  await target.click();
  await page.waitForTimeout(gapMs);
  await target.click({ force: true });
}

async function alerts(page: Page): Promise<string> {
  return (await page.locator("[role=alert]").allTextContents()).join(" | ");
}

test.describe("t02 UI : le cœur devient injoignable puis revient", () => {
  let s: Session;
  test.beforeEach(async ({ browser }) => {
    s = await newSession(browser, "creator");
  });
  test.afterEach(async () => {
    await s.ctx.close();
  });

  test("une lecture qui échoue par coupure réseau affiche la bannière et l'erreur de liste", async () => {
    let cut = true;
    await cutReads(s.page, () => cut);
    await go(s.page, "/bookmarks", 3500);
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible();
    await expect(s.page.getByRole("alert").filter({ hasText: LIST_ERROR })).toBeVisible();
    cut = false;
  });

  test("« Réessayer » après retour du cœur recharge la liste et fait disparaître la bannière", async () => {
    let cut = true;
    await cutReads(s.page, () => cut);
    await go(s.page, "/bookmarks", 3500);
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible();
    cut = false;
    await s.page.getByRole("button", { name: /Réessayer/ }).click();
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toHaveCount(0);
    await expect(s.page.getByRole("alert").filter({ hasText: LIST_ERROR })).toHaveCount(0);
  });

  // Finding t02-006 : la bannière annonce « nouvelle tentative en cours » mais rien ne réessaie jamais.
  bug("t02-006 : le retour du cœur est détecté sans action de l'utilisateur", async () => {
    let cut = true;
    await cutReads(s.page, () => cut);
    await go(s.page, "/bookmarks", 3500);
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible();
    cut = false;
    await s.page.waitForTimeout(25_000);
    expect(await alerts(s.page)).not.toMatch(BANNER);
  });

  // Finding t02-012 : n'importe quelle requête réussie (ici le sondage de notifications) efface la bannière.
  bug("t02-012 : la bannière persiste tant que la lecture de la page échoue", async () => {
    test.setTimeout(120_000);
    await cutReads(s.page, () => true);
    await go(s.page, "/bookmarks", 3500);
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible();
    // Le sondage de notifications (45 s) réussit pendant que la liste reste en erreur.
    await s.page.waitForTimeout(50_000);
    expect(await alerts(s.page)).toMatch(LIST_ERROR);
    expect(await alerts(s.page)).toMatch(BANNER);
  });

  // Finding t02-007 : hors ligne (navigator.onLine=false) les requêtes sont mises en pause sans aucun message.
  bug("t02-007 : le mode hors ligne du navigateur est signalé à l'utilisateur", async () => {
    await go(s.page, "/", 1500);
    await s.ctx.setOffline(true);
    await go(s.page, "/bookmarks", 4000);
    const text = (await s.page.locator("body").innerText()) + (await alerts(s.page));
    await s.ctx.setOffline(false);
    expect(text).toMatch(/hors ligne|hors-ligne|connexion|réseau/i);
  });

  test("la lecture qui dépasse 15 s est convertie en injoignabilité (bannière) après le rejeu", async () => {
    test.setTimeout(90_000);
    await s.page.route(`${CORE_URL}/v1/**`, async (r) => {
      const req = r.request();
      if (CORE_READS(req.url(), req.method()) && /\/v1\/items(\?|$)/.test(req.url())) {
        await new Promise((res) => setTimeout(res, 17_000));
        return r.abort("timedout").catch(() => undefined);
      }
      return r.continue();
    });
    await go(s.page, "/bookmarks", 500);
    await expect(s.page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible({
      timeout: 40_000,
    });
  });

  // Finding t02-008 : aucun traitement du 401 (jeton expiré/révoqué) : erreur générique, pas d'invite de reconnexion.
  bug("t02-008 : un 401 en cours de session invite à se reconnecter", async () => {
    await s.page.route(`${CORE_URL}/v1/**`, (r) => {
      const req = r.request();
      if (CORE_READS(req.url(), req.method()) && /\/v1\/items(\?|$)/.test(req.url())) {
        return r.fulfill({
          status: 401,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Unauthorized",
            status: 401,
            detail: "invalid token",
          }),
        });
      }
      return r.continue();
    });
    await go(s.page, "/bookmarks", 3500);
    expect(await alerts(s.page)).toMatch(/session|reconnect|connect(ez|er)-vous|expir/i);
  });
});

test.describe("t02 UI : création d'un élément sous erreur", () => {
  let s: Session;
  test.beforeEach(async ({ browser }) => {
    s = await newSession(browser, "creator");
    await go(s.page, "/", 1500);
  });
  test.afterEach(async () => {
    await s.ctx.close();
  });

  async function openCreate(page: Page, title: string): Promise<void> {
    await page.locator("#new-item-trigger").click();
    await page.getByRole("textbox", { name: "Titre", exact: true }).fill(title);
  }

  test("un 429 affiche le détail du cœur et le délai de reprise", async () => {
    await s.page.route(`${CORE_URL}/v1/configs`, (r) =>
      r.request().method() === "POST"
        ? r.fulfill({
            status: 429,
            contentType: "application/problem+json",
            headers: { "retry-after": "42" },
            body: JSON.stringify({ title: "Too Many Requests", status: 429, detail: "trop vite" }),
          })
        : r.continue(),
    );
    await openCreate(s.page, "aud-t02-429");
    await s.page.getByRole("button", { name: "Créer", exact: true }).click();
    await expect(s.page.getByRole("alert").filter({ hasText: "trop vite" })).toContainText(
      "Réessayez dans 42 s",
    );
  });

  test("un quota atteint (409) affiche le message du cœur et garde le tiroir ouvert", async () => {
    await s.page.route(`${CORE_URL}/v1/configs`, (r) =>
      r.request().method() === "POST"
        ? r.fulfill({
            status: 409,
            contentType: "application/problem+json",
            body: JSON.stringify({
              title: "Conflict",
              status: 409,
              detail: "quota d'items du tenant dépassé : 10/10",
            }),
          })
        : r.continue(),
    );
    await openCreate(s.page, "aud-t02-quota");
    await s.page.getByRole("button", { name: "Créer", exact: true }).click();
    await expect(s.page.getByRole("alert")).toContainText("quota d'items du tenant dépassé");
    await expect(s.page.getByRole("textbox", { name: "Titre", exact: true })).toHaveValue(
      "aud-t02-quota",
    );
  });

  test("une coupure réseau pendant la création affiche un échec générique et conserve la saisie", async () => {
    let cut = true;
    await s.page.route(`${CORE_URL}/v1/configs`, (r) =>
      r.request().method() === "POST" && cut ? r.abort("connectionrefused") : r.continue(),
    );
    await openCreate(s.page, "aud-t02-abort");
    await s.page.getByRole("button", { name: "Créer", exact: true }).click();
    await expect(s.page.getByRole("alert")).toContainText("Échec de la création.");
    await expect(s.page.getByRole("textbox", { name: "Titre", exact: true })).toHaveValue(
      "aud-t02-abort",
    );
    cut = false;
    await s.page.getByRole("button", { name: "Créer", exact: true }).click();
    await s.page.waitForURL(/\/apps\/[0-9a-f]+\/edit/);
  });

  test("un double clic sur « Créer » n'émet qu'une seule création", async () => {
    let posts = 0;
    await s.page.route(`${CORE_URL}/v1/configs`, async (r) => {
      if (r.request().method() === "POST") {
        posts++;
        await new Promise((res) => setTimeout(res, 1200));
      }
      return r.continue();
    });
    await openCreate(s.page, "aud-t02-dbl");
    const btn = s.page.getByRole("button", { name: "Créer", exact: true });
    await doubleClick(s.page, btn, 60);
    await s.page.waitForURL(/\/apps\/[0-9a-f]+\/edit/);
    expect(posts).toBe(1);
  });

  test("retour arrière puis avance après création ne recrée rien et ne perd pas l'éditeur", async () => {
    let posts = 0;
    s.page.on("request", (r) => {
      if (r.method() === "POST" && r.url() === `${CORE_URL}/v1/configs`) posts++;
    });
    await openCreate(s.page, "aud-t02-back");
    await s.page.getByRole("button", { name: "Créer", exact: true }).click();
    await s.page.waitForURL(/\/apps\/[0-9a-f]+\/edit/);
    const editorUrl = s.page.url();
    await s.page.goBack();
    await s.page.waitForTimeout(1200);
    await s.page.goForward();
    await s.page.waitForURL(editorUrl);
    await expect(s.page.getByRole("button", { name: "Enregistrer" })).toBeVisible();
    expect(posts).toBe(1);
  });
});

test.describe("t02 UI : enregistrement d'une app", () => {
  let s: Session;
  let appId: string;
  test.beforeEach(async ({ browser }) => {
    appId = (await getA11ySeed()).appId;
    s = await newSession(browser, "creator");
    await go(s.page, `/apps/${appId}/edit`, 3000);
  });
  test.afterEach(async () => {
    await s.ctx.close();
  });

  const PUT = (id: string) => `${CORE_URL}/v1/configs/by-item/${id}`;

  // Finding t02-009 : l'éditeur d'app réduit tout échec d'enregistrement à un message générique.
  bug("t02-009 : un refus 422 du cœur est expliqué à l'utilisateur", async () => {
    await s.page.route(PUT("*"), (r) =>
      r.request().method() === "PUT"
        ? r.fulfill({
            status: 422,
            contentType: "application/problem+json",
            body: JSON.stringify({
              title: "Unprocessable Entity",
              status: 422,
              detail: "la source de données s1 référence une collection inconnue",
            }),
          })
        : r.continue(),
    );
    await s.page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(s.page.getByRole("alert").filter({ hasText: /Échec/ })).toBeVisible();
    expect(await alerts(s.page)).toContain("collection inconnue");
  });

  test("un échec d'enregistrement garde le brouillon et un nouvel essai réussit", async () => {
    let cut = true;
    await s.page.route(PUT("*"), (r) =>
      r.request().method() === "PUT" && cut ? r.abort("connectionrefused") : r.continue(),
    );
    await s.page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(
      s.page.getByRole("alert").filter({ hasText: /Échec de l'enregistrement/ }),
    ).toBeVisible();
    cut = false;
    await s.page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(s.page.getByText("Application enregistrée")).toBeVisible();
    await expect(
      s.page.getByRole("alert").filter({ hasText: /Échec de l'enregistrement/ }),
    ).toHaveCount(0);
  });

  test("un double clic sur « Enregistrer » n'émet qu'une seule écriture", async () => {
    let puts = 0;
    await s.page.route(PUT("*"), async (r) => {
      if (r.request().method() === "PUT") {
        puts++;
        await new Promise((res) => setTimeout(res, 1200));
      }
      return r.continue();
    });
    await doubleClick(s.page, s.page.getByRole("button", { name: "Enregistrer" }), 60);
    await s.page.waitForTimeout(3000);
    expect(puts).toBe(1);
  });

  // Finding t02-003 (volet UI) : un second onglet ouvert avant la modification écrase celle-ci en enregistrant.
  bug(
    "t02-003 : enregistrer depuis un onglet périmé n'écrase pas la modification d'un autre onglet",
    async () => {
      const api = await (await import("../j03/api")).apiFor("creator");
      const cur = await api.get(`/v1/configs/by-item/${appId}`);
      const marker = `#${Date.now().toString(16).slice(-6).padStart(6, "0")}`;
      const changed = { ...cur.body.config, theme: { ...cur.body.config.theme, primary: marker } };
      const r = await api.send("PUT", `/v1/configs/by-item/${appId}`, changed);
      expect(r.status).toBe(200);
      // L'onglet B (déjà ouvert sur la version précédente) enregistre sans rien avoir modifié.
      await s.page.getByRole("button", { name: "Enregistrer" }).click();
      await s.page.waitForTimeout(1500);
      const after = await api.get(`/v1/configs/by-item/${appId}`);
      expect(after.body.config.theme?.primary).toBe(marker);
    },
  );
});
