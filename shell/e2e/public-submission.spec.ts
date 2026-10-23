// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, mockCollection, ADMIN_ME } from "./mocks";

// ARC-10 : file de modération des soumissions publiques d'une collection.
test("un modérateur approuve une soumission et crée un lien de soumission", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);

  let approved = false;
  let createdBody: unknown = null;

  await page.route("https://core.test/v1/collections*", async (route) => {
    await route.fulfill({ json: { collections: [mockCollection({ title: "Signalements" })] } });
  });
  await page.route("https://core.test/v1/collections/points_interet/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith("/submissions") && method === "GET") {
      await route.fulfill({
        json: {
          submissions: approved
            ? []
            : [
                {
                  id: "s1",
                  status: "pending",
                  properties: { nom: "Nid-de-poule" },
                  geometry: null,
                  attachment: null,
                  createdAt: null,
                },
              ],
        },
      });
      return;
    }
    if (url.endsWith("/submissions/s1/approve")) {
      approved = true;
      await route.fulfill({ json: { fid: "7" } });
      return;
    }
    if (url.endsWith("/submission-tokens") && method === "POST") {
      createdBody = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "k1",
          name: "mairie",
          prefix: "gss_abc",
          expiresAt: null,
          maxSubmissions: 100,
          submissionCount: 0,
          revokedAt: null,
          token: "gss_abc_SECRET",
        },
      });
      return;
    }
    if (url.endsWith("/submission-tokens")) {
      await route.fulfill({ json: { tokens: [] } });
      return;
    }
    await route.fallback();
  });

  await page.goto("/admin/collections");
  await page.getByRole("button", { name: "Soumissions" }).click();
  await expect(page.getByText(/Nid-de-poule/)).toBeVisible();
  await page.getByRole("button", { name: "Approuver la soumission s1" }).click();
  await expect.poll(() => approved).toBe(true);
  await expect(page.getByText("Aucune soumission en attente.")).toBeVisible();

  await page.getByLabel("Nom du lien").fill("mairie");
  await page.getByRole("button", { name: "Créer un lien" }).click();
  await expect(page.getByText("gss_abc_SECRET", { exact: true })).toBeVisible();
  expect(createdBody).toEqual({ name: "mairie", expiresInDays: 30, maxSubmissions: 100 });
  await expect(page.getByText(/\/collect\/gss_abc_SECRET/)).toBeVisible();
});

// L8 : page publique `/collect/:token` — hors session, kit public, preuve de travail, envoi multipart.
test.describe("page publique de collecte", () => {
  const KIT = {
    version: 1,
    title: "Signalement citoyen",
    schema: {
      geometry: { column: "geom", type: "Point", srid: 4326, required: true },
      fields: [{ name: "nom", type: "string", required: true, label: "Votre nom" }],
    },
    rules: [],
    geometryRequired: true,
    updatedAt: null,
    etag: "k1",
  };

  test("saisie, preuve de travail résolue dans le navigateur, envoi puis remerciement", async ({
    page,
  }) => {
    let posted: string | null = null;
    await page.route("https://core.test/v1/public/submit/tok/kit", (r) => r.fulfill({ json: KIT }));
    await page.route("https://core.test/v1/public/submit/tok/challenge", (r) =>
      r.fulfill({
        json: { challenge: "v1.9999999999.0123456789abcdef.mac", bits: 10, required: true },
      }),
    );
    await page.route("https://core.test/v1/public/submit/tok", async (r) => {
      posted = r.request().postData();
      await r.fulfill({ status: 202, json: { status: "pending" } });
    });
    await page.goto("/collect/tok");
    await expect(
      page.getByRole("heading", { level: 1, name: "Signalement citoyen" }),
    ).toBeVisible();
    await page.getByLabel(/Votre nom/).fill("Marie");
    await page.getByRole("button", { name: "Envoyer" }).click();
    // Géométrie requise : refus tant qu'aucune position n'est saisie.
    await expect(page.getByText("La géométrie est obligatoire.")).toBeVisible();
    expect(posted).toBeNull();
    await page.getByLabel("Longitude").fill("2.35");
    await page.getByLabel("Latitude").fill("48.85");
    await page.getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByText(/votre saisie a bien été envoyée/)).toBeVisible();
    expect(posted).toContain('name="powNonce"');
    expect(posted).toContain('name="clientOpId"');
    expect(posted).toContain("Marie");
    const nonce = /name="powNonce"\r\n\r\n([^\r]+)\r\n/.exec(posted ?? "")?.[1] ?? "";
    const { createHash } = await import("node:crypto");
    const digest = createHash("sha256")
      .update(`v1.9999999999.0123456789abcdef.mac:${nonce}`)
      .digest();
    expect((digest[0] << 2) | (digest[1] >> 6)).toBe(0); // 10 bits de tête à zéro
  });

  test("lien révoqué : message dédié et aucun formulaire", async ({ page }) => {
    await page.route("https://core.test/v1/public/submit/old/kit", (r) =>
      r.fulfill({
        status: 410,
        contentType: "application/problem+json",
        json: { title: "Gone", detail: "submission link expired or revoked" },
      }),
    );
    await page.goto("/collect/old");
    await expect(page.getByText(/expiré ou a été révoqué/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Envoyer" })).toHaveCount(0);
  });
});
