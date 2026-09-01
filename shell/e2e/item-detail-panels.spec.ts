import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("modifier le titre depuis le menu Actions ouvre le panneau d'édition sur la fiche", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Actions" }).first().click();
  await page.getByRole("button", { name: "Modifier" }).click();
  await expect(page).toHaveURL(/\/items\/1\?panel=edit$/);
  const title = page.getByLabel("Titre");
  await title.fill("Alpha renommé");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByRole("heading", { name: "Alpha renommé" })).toBeVisible();
  await expect(page).toHaveURL(/\/items\/1$/);
});

test("partager depuis la fiche ouvre le formulaire de partage inline, sans dialogue", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/items/1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Partager" }).click();
  await expect(page).toHaveURL(/\/items\/1\?panel=share$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Partager l'élément")).toBeVisible();
});

test("390 px : le catalogue passe en onglets, un volet à la fois", async ({ page }) => {
  // 390px : largeur de téléphone étroit représentative, confortablement
  // sous le seuil de useNarrowViewport.ts (640px depuis la revue transverse
  // SP-30l) — pas une borne à défendre au pixel près.
  await page.setViewportSize({ width: 390, height: 800 });
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Catalogue" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.getByRole("tab", { name: "Filtrer" }).click();
  await expect(page.getByLabel("Rechercher")).toBeVisible();
});

test("390 px : la fiche d'un item passe en onglets", async ({ page }) => {
  // 390px : largeur de téléphone étroit représentative, confortablement
  // sous le seuil de useNarrowViewport.ts (640px depuis la revue transverse
  // SP-30l) — pas une borne à défendre au pixel près.
  await page.setViewportSize({ width: 390, height: 800 });
  await mockCore(page);
  await page.goto("/items/1");
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Élément" })).toHaveAttribute("aria-selected", "true");
});
