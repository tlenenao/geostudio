import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import { apiFor, type Api } from "./helpers";

// Édition des métadonnées ouvertes et des champs sensibles depuis /admin/collections.
test.setTimeout(120_000);
const tag = stamp("j07");
let admin: Api;
let creator: Api;

test.beforeAll(async () => {
  [admin, creator] = await Promise.all([apiFor("admin"), apiFor("creator")]);
});

async function makeCollection(suffix: string): Promise<{ id: string; title: string }> {
  const title = `${tag}-${suffix}`;
  const made = await creator.send("POST", "/v1/collections/empty", {
    title,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "secret", sqlType: "text" },
    ],
    geometryType: "Point",
    srid: 4326,
  });
  expect(made.status).toBe(201);
  return { id: made.body.id, title };
}

async function openEditor(page: Page, title: string): Promise<void> {
  await openAs(page, "admin");
  await spaGoto(page, "/admin/collections");
  const row = page.getByRole("row").filter({ hasText: title });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Éditer" }).click();
  await expect(page.getByRole("region", { name: `Éditer ${title}` })).toBeVisible();
}

test.describe("j07 collections — édition des métadonnées", () => {
  test("licence, producteur et contact saisis dans l'onglet Métadonnées ouvertes sont persistés", async ({
    page,
  }) => {
    const { id, title } = await makeCollection("ui-meta");
    await openEditor(page, title);
    const panel = page.getByRole("region", { name: `Éditer ${title}` });
    await panel.getByRole("tab", { name: "Métadonnées ouvertes" }).click();
    await panel.getByRole("combobox", { name: "Licence" }).click();
    await page.getByRole("option", { name: /Licence Ouverte/ }).click();
    await panel.getByLabel("Producteur").fill("Service SIG j07");
    await panel.getByLabel("Contact").fill("sig@example.org");
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    await expect(panel).toHaveCount(0);
    const c = await admin.get(`/v1/collections/${id}`);
    expect(c.body).toMatchObject({
      license: "etalab-2.0",
      producer: "Service SIG j07",
      contact: "sig@example.org",
    });
  });

  test("le champ URI de licence n'apparaît que pour la licence « Autre »", async ({ page }) => {
    const { title } = await makeCollection("ui-other");
    await openEditor(page, title);
    const panel = page.getByRole("region", { name: `Éditer ${title}` });
    await panel.getByRole("tab", { name: "Métadonnées ouvertes" }).click();
    await expect(panel.getByLabel("URI de la licence")).toHaveCount(0);
    await panel.getByRole("combobox", { name: "Licence" }).click();
    await page.getByRole("option", { name: /^Autre/ }).click();
    await expect(panel.getByLabel("URI de la licence")).toBeVisible();
  });

  test("l'onglet Champs sensibles liste les colonnes et enregistre la sélection", async ({
    page,
  }) => {
    const { id, title } = await makeCollection("ui-sens");
    await openEditor(page, title);
    const panel = page.getByRole("region", { name: `Éditer ${title}` });
    await panel.getByRole("tab", { name: "Champs sensibles" }).click();
    await expect(panel.getByRole("checkbox", { name: "nom" })).toBeVisible();
    await expect(panel.getByRole("checkbox", { name: "secret" })).toBeVisible();
    await panel.getByRole("checkbox", { name: "secret" }).check();
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    await expect(panel).toHaveCount(0);
    const c = await admin.get(`/v1/collections/${id}`);
    expect(c.body.sensitiveFields).toEqual(["secret"]);
  });

  test("le créateur n'accède pas à /admin/collections (accès réservé)", async ({ page }) => {
    await openAs(page, "creator");
    await spaGoto(page, "/admin/collections");
    await expect(page.getByRole("button", { name: "Éditer" })).toHaveCount(0);
  });

  // Finding j07-019 : l'URI de licence obsolète est renvoyée alors que la licence n'est plus « Autre ».
  bug(
    "j07-019 : changer la licence « Autre » vers une licence du catalogue efface l'ancienne URI",
    async ({ page }) => {
      const { id, title } = await makeCollection("ui-stale-uri");
      await creator.send("PATCH", `/v1/collections/${id}`, {
        license: "other",
        licenseUri: "https://example.org/ancienne",
      });
      await openEditor(page, title);
      const panel = page.getByRole("region", { name: `Éditer ${title}` });
      await panel.getByRole("tab", { name: "Métadonnées ouvertes" }).click();
      await panel.getByRole("combobox", { name: "Licence" }).click();
      await page.getByRole("option", { name: /Licence Ouverte/ }).click();
      await panel.getByRole("button", { name: "Enregistrer" }).click();
      await expect(panel).toHaveCount(0);
      const c = await admin.get(`/v1/collections/${id}`);
      expect(c.body.licenseUri).toBe("");
    },
  );
});
