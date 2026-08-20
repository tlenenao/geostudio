import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("login (mock) → list → open item", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await expect(page.getByText("GeoStudio")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  // Opening a non-map item now navigates directly to the builder, not to /items/:pk.
  await page
    .getByRole("button", { name: /ouvrir/i })
    .first()
    .click();
  await expect(page).toHaveURL(/\/apps\/1\/edit$/);
});

test("create an App → lands on the builder", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Titre").fill("Créée");
  await page.getByRole("button", { name: "Créer" }).click();
  // App creation now navigates directly to the app builder route.
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
});

test("delete an item from the catalog", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).first().click();
  await page
    .getByRole("button", { name: /^supprimer$/i })
    .first()
    .click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});

test("delete from the detail page returns to the catalog", async ({ page }) => {
  await mockCore(page);
  // Navigate directly to the item detail page — clicking "Ouvrir" now goes to the builder.
  await page.goto("/items/1");
  await expect(page).toHaveURL(/\/items\/1$/);
  await page.getByRole("button", { name: "Actions" }).click();
  await page
    .getByRole("button", { name: /^supprimer$/i })
    .first()
    .click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});

test("filters the catalog to my items (empty for the mock user)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByLabel("Portée").selectOption("mine");
  await expect(page.getByText("Aucun élément")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});

test("catalog search still sends q to the core (regression)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  const request = page.waitForRequest(
    (req) => req.url().includes("/items?") && req.url().includes("q=Alp"),
  );
  await page.getByRole("textbox", { name: "Rechercher" }).fill("Alp");
  await request;
});
