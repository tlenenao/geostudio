import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("publishing an item, capturing a thumbnail, and the runtime route still work", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");

  // Create an app (lands on /apps/9/edit, per every other E2E spec's convention).
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App publication");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // 1. Publish toggle from the item detail page.
  await page.goto("/items/9");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await expect(page.getByRole("button", { name: "Actions" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 2. Authenticated runtime route still renders after the routing change.
  await page.goto("/apps/9");
  await expect(page.getByRole("alert")).toHaveCount(0);

  // 3. Thumbnail capture from the builder.
  await page.goto("/apps/9/edit");
  await page.getByRole("button", { name: "Capturer une miniature" }).click();
  await expect(page.getByRole("button", { name: "Capturer une miniature" })).toBeEnabled();
  await expect(page.getByText("Échec de la capture.")).toHaveCount(0);
});
