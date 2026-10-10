// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCollection, mockCore } from "./mocks";

// REV-297 : « Modifier » un secret (PUT /secrets/{id}) depuis le sélecteur de
// secret de l'éditeur d'alerte, et affichage du 422 motivé par le cœur.
test("modifier un secret SMTP : PUT avec le payload entier, puis refus 422 affiché", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          mockCollection({
            id: "incidents",
            title: "Incidents",
            tableName: "incidents",
            isPublic: true,
            permissions: { read: true, write: true, delete: false, share: false },
            featureCount: 3,
          }),
        ],
      },
    });
  });
  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents",
        pk: "id",
        geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "category", type: "string" }],
      },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset",
        itemId: "dataset-1",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "incidents", columns: {} },
        },
      },
    });
  });
  await page.route("https://core.test/v1/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1",
        resourceType: "dataset",
        title: "Incidents partagés",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: "cfg-dataset",
        isPublished: false,
        keywords: [],
      },
    });
  });
  await page.route("**/datasets/dataset-1/alerts", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: [] });
  });

  const summary = {
    id: "s-smtp",
    name: "smtp-prod",
    kind: "smtp",
    createdAt: "2026-10-01T00:00:00Z",
    updatedAt: "2026-10-01T00:00:00Z",
  };
  let putBody: unknown = null;
  let putAttempts = 0;
  await page.route("https://core.test/v1/secrets", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: [summary] });
  });
  await page.route("https://core.test/v1/secrets/s-smtp", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    putAttempts += 1;
    if (putAttempts === 1) {
      await route.fulfill({
        status: 422,
        contentType: "application/problem+json",
        json: { title: "Unprocessable", detail: "useTls=false n'est accepté que pour localhost" },
      });
      return;
    }
    putBody = route.request().postDataJSON();
    await route.fulfill({ json: { ...summary, updatedAt: "2026-10-10T00:00:00Z" } });
  });

  await page.goto("/datasets/dataset-1/edit");
  await page.getByLabel("Canal").selectOption("email");
  await page.getByRole("button", { name: "Modifier smtp-prod" }).click();
  await expect(page.getByLabel("Nom", { exact: true })).toBeDisabled();

  const form = page.locator("form", { hasText: "ressaisissez-la en entier" });
  await page.getByRole("textbox", { name: "Hôte" }).fill("smtp.example.org");
  await page.getByRole("spinbutton", { name: "Port" }).fill("587");
  await page.getByLabel("Adresse d'expédition").fill("noreply@example.org");
  await form.getByRole("button", { name: "Enregistrer" }).click();
  await expect(form.getByRole("alert")).toContainText("n'est accepté que pour localhost");

  await form.getByRole("button", { name: "Enregistrer" }).click();
  await expect(form).toHaveCount(0);
  expect(putBody).toMatchObject({
    payload: { kind: "smtp", host: "smtp.example.org", port: 587, useTls: true },
  });
});
