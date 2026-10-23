// SPDX-License-Identifier: Apache-2.0
// L8 : collecte hors-ligne de bout en bout, sur le BUILD servi par `preview` (service worker réel).
// « Hors réseau » = `context.setOffline(true)` (navigations et SW) + coupure des routes mockées
// (Playwright répond aux routes avant l'émulation réseau : sans le drapeau, un mock répondrait
// encore hors-ligne).
import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { mockFormApp, mockMe } from "./mocks";

const CORE = "https://core.test/v1";
const KEY_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// PNG 1x1 : une vraie image, le contenu importe peu.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

type Srv = {
  offline: boolean;
  /** Réponse de `POST /items` : `ok`, `422` (champ invalide) ou `401`. */
  create: "ok" | "422" | "401" | "503";
  /** Coupe la prochaine demande de présignature (réseau perdu entre création et photo). */
  presignDropsOnce: boolean;
  posts: { key: string | null; createdAt: string | null; titre: unknown }[];
  presigns: number;
  confirms: { key: string | null }[];
  publicPosts: string[];
};

async function setupCore(page: Page): Promise<Srv> {
  const srv: Srv = {
    offline: false,
    create: "ok",
    presignDropsOnce: false,
    posts: [],
    presigns: 0,
    confirms: [],
    publicPosts: [],
  };
  await mockFormApp(page);
  // Même app que `mockFormApp`, en mode collecte mobile avec un champ photo.
  await page.route(`${CORE}/configs/by-item/form-1*`, (route) =>
    route.fulfill({
      json: {
        id: "cfg-form-1",
        itemId: "form-1",
        kind: "app",
        version: 1,
        config: {
          version: 1,
          kind: "app",
          theme: {},
          dataSources: [
            { id: "s1", type: "features", service: "core", layer: "incidents", query: {} },
          ],
          messages: [],
          layout: {
            type: "grid",
            breakpoints: {},
            items: [
              {
                id: "fm",
                widget: "form",
                x: 0,
                y: 0,
                w: 6,
                h: 8,
                props: {
                  dataSourceId: "s1",
                  submitLabel: "Envoyer",
                  geometryType: null,
                  mobile: true,
                  fields: [
                    { name: "titre", label: "Titre", type: "string", required: true, order: 0 },
                    {
                      name: "photo",
                      label: "Photo",
                      type: "attachment",
                      kind: "image",
                      required: false,
                      order: 1,
                    },
                  ],
                },
              },
            ],
          },
        },
      },
    }),
  );
  await page.route(`${CORE}/collections/incidents/items*`, async (route) => {
    const req = route.request();
    if (req.method() !== "POST") return route.fallback();
    if (srv.create === "401") return route.fulfill({ status: 401, json: { detail: "expired" } });
    if (srv.create === "503") return route.fulfill({ status: 503, json: { detail: "down" } });
    if (srv.create === "422")
      return route.fulfill({
        status: 422,
        contentType: "application/problem+json",
        json: {
          title: "Unprocessable",
          errors: [{ field: "titre", code: "too_short", message: "Titre trop court" }],
        },
      });
    const body = req.postDataJSON() as { properties: { titre?: unknown } };
    srv.posts.push({
      key: await req.headerValue("idempotency-key"),
      createdAt: await req.headerValue("x-gs-offline-created-at"),
      titre: body.properties.titre,
    });
    await route.fulfill({ status: 201, json: { id: 41 } });
  });
  await page.route(`${CORE}/collections/incidents/items/41/attachments/presign`, async (route) => {
    srv.presigns++;
    if (srv.presignDropsOnce) {
      srv.presignDropsOnce = false;
      return route.abort("connectionreset");
    }
    await route.fulfill({ json: { uploadUrl: "https://s3.test/put/k1", key: "k1" } });
  });
  await page.route("https://s3.test/put/**", (route) => route.fulfill({ status: 200, body: "" }));
  await page.route(`${CORE}/collections/incidents/items/41/attachments`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    srv.confirms.push({ key: await route.request().headerValue("idempotency-key") });
    await route.fulfill({
      status: 201,
      json: { id: "a1", fieldKey: "photo", filename: "p.png", contentType: "image/png" },
    });
  });
  // Public.
  await page.route(`${CORE}/public/submit/tok/kit`, (route) =>
    route.fulfill({
      json: {
        version: 1,
        title: "Signalement citoyen",
        schema: {
          geometry: null,
          fields: [{ name: "nom", type: "string", required: true, label: "Votre nom" }],
        },
        rules: [],
        geometryRequired: false,
        updatedAt: null,
        etag: "k1",
      },
    }),
  );
  await page.route(`${CORE}/public/submit/tok/challenge`, (route) =>
    route.fulfill({
      json: { challenge: "v1.9999999999.0123456789abcdef.mac", bits: 8, required: true },
    }),
  );
  await page.route(`${CORE}/public/submit/tok`, async (route) => {
    srv.publicPosts.push(route.request().postData() ?? "");
    await route.fulfill({ status: 202, json: { status: "pending" } });
  });
  // Dernier enregistré = premier évalué : la coupure réseau prime sur tout mock.
  await page.route(/^https:\/\/(core|s3)\.test\//, (route) =>
    srv.offline ? route.abort("internetdisconnected") : route.fallback(),
  );
  return srv;
}

async function goOffline(context: BrowserContext, srv: Srv, offline: boolean) {
  srv.offline = offline;
  await context.setOffline(offline);
}

async function waitForServiceWorker(page: Page) {
  await expect
    .poll(() => page.evaluate(() => !!navigator.serviceWorker?.controller), { timeout: 15_000 })
    .toBe(true);
}

// Liste des saisies en file, sous le formulaire (la pastille de la barre du haut n'existe pas
// dans le runtime d'une app).
const queued = (page: Page) =>
  page
    .getByRole("region", { name: "Saisies hors-ligne" })
    .getByRole("listitem")
    .filter({ hasNotText: "Envoyée" });

async function fillAndSubmitPrivate(page: Page, titre: string, withPhoto: boolean) {
  await page.getByLabel(/^Titre/).fill(titre);
  if (withPhoto) {
    await page
      .locator('input[type="file"]')
      .setInputFiles({ name: "p.png", mimeType: "image/png", buffer: PNG });
  }
  await page.getByRole("button", { name: "Envoyer", exact: true }).click();
}

test.use({ serviceWorkers: "allow" });

test.describe("collecte hors-ligne (utilisateur connecté)", () => {
  test("saisie + photo hors-ligne, rechargement hors-ligne, retour du réseau : envoi unique", async ({
    page,
    context,
  }) => {
    const srv = await setupCore(page);
    await page.goto("/apps/form-1");
    await waitForServiceWorker(page);
    // Les chunks de route chargés avant la prise de contrôle ne sont pas en cache : un second
    // chargement, sous contrôle du SW, les y met (cas réel : l'agent a déjà ouvert l'app).
    await page.reload();
    await expect(page.getByLabel(/^Titre/)).toBeVisible();

    await goOffline(context, srv, true);
    await fillAndSubmitPrivate(page, "Fuite", true);
    await expect(page.getByText(/Hors-ligne : saisie enregistrée/)).toBeVisible();
    await expect(queued(page)).toHaveCount(1);
    await expect(page.getByLabel(/^Titre/)).toHaveValue(""); // vidé après l'écriture locale
    expect(srv.posts).toHaveLength(0);

    // Rechargement HORS-LIGNE : la coquille vient du service worker, la file est relue d'IndexedDB.
    await page.reload();
    await expect(page.getByRole("status").filter({ hasText: /Mode hors-ligne/ })).toBeVisible();

    await goOffline(context, srv, false);
    await expect.poll(() => srv.posts.length, { timeout: 20_000 }).toBe(1);
    await expect(page.getByRole("status").filter({ hasText: /Mode hors-ligne/ })).toHaveCount(0);
    expect(srv.posts[0].key).toMatch(KEY_RE);
    expect(srv.posts[0].createdAt).toMatch(/^20\d\d-/); // horodatage d'origine de la saisie
    expect(srv.posts[0].titre).toBe("Fuite");
    expect(srv.confirms).toHaveLength(1);
    expect(srv.confirms[0].key).toMatch(KEY_RE);
  });

  test("coupure entre la création et la photo : reprise sans doublon de saisie", async ({
    page,
    context,
  }) => {
    test.setTimeout(60_000);
    const srv = await setupCore(page);
    await page.goto("/apps/form-1");
    await waitForServiceWorker(page);
    await goOffline(context, srv, true);
    await fillAndSubmitPrivate(page, "Nid-de-poule", true);
    await expect(queued(page)).toHaveCount(1);

    srv.presignDropsOnce = true; // la création passe, la présignature de la photo est coupée
    await goOffline(context, srv, false);
    await expect.poll(() => srv.presigns, { timeout: 15_000 }).toBe(1);
    expect(srv.posts).toHaveLength(1);
    await expect(queued(page)).toHaveCount(1); // photo encore à envoyer

    // Le réessai programmé (≈ 5 s) reprend à la photo : la saisie n'est PAS recréée.
    await expect(queued(page)).toHaveCount(0, { timeout: 25_000 });
    expect(srv.posts).toHaveLength(1);
    expect(srv.confirms).toHaveLength(1);
  });

  test("422 : saisie « À corriger », correction depuis la liste, renvoi avec la même clé", async ({
    page,
    context,
  }) => {
    const srv = await setupCore(page);
    await page.goto("/apps/form-1");
    await waitForServiceWorker(page);
    await goOffline(context, srv, true);
    await fillAndSubmitPrivate(page, "x", false);
    srv.create = "422";
    await goOffline(context, srv, false);
    await expect(page.getByText("À corriger").first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("titre : Titre trop court")).toBeVisible();
    expect(srv.posts).toHaveLength(0); // jamais rejoué tant qu'on ne l'a pas corrigée

    srv.create = "ok";
    await page.getByRole("button", { name: "Modifier" }).click();
    await expect(page.getByLabel(/^Titre/)).toHaveValue("x");
    await page.getByLabel(/^Titre/).fill("Titre corrigé");
    await page.getByRole("button", { name: "Envoyer", exact: true }).click();
    await expect.poll(() => srv.posts.length).toBe(1);
    expect(srv.posts[0].titre).toBe("Titre corrigé");
    await expect(page.getByText("À corriger")).toHaveCount(0);
  });

  test("401 : file intacte et synchro suspendue, puis reprise sans perte", async ({
    page,
    context,
  }) => {
    const srv = await setupCore(page);
    await page.goto("/apps/form-1");
    await waitForServiceWorker(page);
    await goOffline(context, srv, true);
    await fillAndSubmitPrivate(page, "Session", false);
    srv.create = "401";
    await goOffline(context, srv, false);
    const resume = page.getByRole("button", { name: "Reprendre" });
    await expect(resume).toBeVisible({ timeout: 15_000 });
    expect(srv.posts).toHaveLength(0);
    srv.create = "ok";
    await resume.click();
    await expect(queued(page)).toHaveCount(0, { timeout: 15_000 });
    expect(srv.posts).toHaveLength(1);
    expect(srv.posts[0].titre).toBe("Session");
  });
});

test("isolation des files : la saisie en attente d'Alice n'est jamais envoyée par Bob", async ({
  page,
  context,
}) => {
  const srv = await setupCore(page);
  await mockMe(page, { id: "u-alice", tenantId: "t1" });
  await page.goto("/apps/form-1");
  await waitForServiceWorker(page);
  await goOffline(context, srv, true);
  await fillAndSubmitPrivate(page, "Pour Alice", false);
  await expect(queued(page)).toHaveCount(1);

  // Réseau revenu mais cœur en panne (503) : la saisie d'Alice reste en file, puis Bob se connecte.
  srv.create = "503";
  await goOffline(context, srv, false);
  await mockMe(page, { id: "u-bob", tenantId: "t1" });
  await page.goto("/apps/form-1");
  await waitForServiceWorker(page);
  await expect(page.getByLabel(/^Titre/)).toBeVisible();
  await expect(queued(page)).toHaveCount(0);
  srv.create = "ok";
  await page.waitForTimeout(1500);
  expect(srv.posts).toHaveLength(0); // jamais envoyée sous l'identité de Bob

  await mockMe(page, { id: "u-alice", tenantId: "t1" });
  await page.reload();
  await expect.poll(() => srv.posts.length, { timeout: 20_000 }).toBe(1);
  expect(srv.posts[0].titre).toBe("Pour Alice");
});

test.describe("page publique /collect/:token hors-ligne", () => {
  test("kit en cache, saisie hors-ligne mise en file, envoi au retour du réseau (preuve de travail incluse)", async ({
    page,
    context,
  }) => {
    const srv = await setupCore(page);
    await page.goto("/collect/tok");
    await expect(
      page.getByRole("heading", { level: 1, name: "Signalement citoyen" }),
    ).toBeVisible();
    await waitForServiceWorker(page);

    await goOffline(context, srv, true);
    await page.reload(); // coquille par le service worker, kit relu d'IndexedDB
    await expect(page.getByRole("heading", { level: 1, name: "Signalement citoyen" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/formulaire chargé depuis cet appareil/)).toBeVisible();
    await page.getByLabel(/Votre nom/).fill("Marie");
    await page.getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByText(/Hors-ligne : saisie enregistrée/).first()).toBeVisible();
    expect(srv.publicPosts).toHaveLength(0);

    await goOffline(context, srv, false);
    await expect.poll(() => srv.publicPosts.length, { timeout: 15_000 }).toBe(1);
    expect(srv.publicPosts[0]).toContain('name="powNonce"');
    expect(srv.publicPosts[0]).toContain("Marie");
    const opId = /name="clientOpId"\r\n\r\n([^\r]+)\r\n/.exec(srv.publicPosts[0])?.[1] ?? "";
    expect(opId).toMatch(KEY_RE);
    await expect(page.getByText("Envoyée").first()).toBeVisible();
  });
});
