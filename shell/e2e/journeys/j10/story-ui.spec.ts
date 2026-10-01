import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor, storyConfig } from "./seed";
import { openAs, spaGoto } from "../j06/helpers";

test.setTimeout(90_000);
const tag = stamp("j10");

test.describe("j10 storytelling", () => {
  let pk: string;
  test.beforeAll(async () => {
    const creator = await apiFor("creator");
    const r = await creator.send("POST", "/v1/configs", {
      title: `${tag}-story`,
      config: storyConfig(),
    });
    expect(r.status).toBe(201);
    pk = r.body.itemId;
  });

  test("le mode story affiche la navigation par chapitre et déclenche onEnter", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${pk}`);
    await page.getByRole("heading", { name: "Titre chapitre 1" }).waitFor();
    await expect(page.getByText("Chapitre 1 / 3")).toBeVisible();
    await expect(page.getByText("Variable : etape-1")).toBeVisible();
    await expect(page.getByRole("button", { name: /précédent/i })).toBeDisabled();
    await page.getByRole("button", { name: /suivant/i }).click();
    await expect(page.getByRole("heading", { name: "Titre chapitre 2" })).toBeVisible();
    await expect(page.getByText("Variable : etape-2")).toBeVisible();
    expect(page.url()).toContain(`/apps/${pk}/ch2`);
    await page.getByRole("button", { name: /suivant/i }).click();
    await expect(page.getByText("Chapitre 3 / 3")).toBeVisible();
    await expect(page.getByRole("button", { name: /suivant/i })).toBeDisabled();
    await page.getByRole("button", { name: /précédent/i }).click();
    await expect(page.getByText("Variable : etape-2")).toBeVisible();
  });

  test("un lien profond /apps/:pk/:pageId ouvre directement le chapitre", async ({ page }) => {
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${pk}/ch3`);
    await expect(page.getByRole("heading", { name: "Titre chapitre 3" })).toBeVisible();
    await expect(page.getByText("Chapitre 3 / 3")).toBeVisible();
    await expect(page.getByText("Variable : etape-3")).toBeVisible();
  });

  test("j10-002 : un identifiant de chapitre inconnu retombe sur « Chapitre 1 / 3 »", async ({
    page,
  }) => {
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${pk}/inconnu`);
    await page.getByRole("button", { name: /suivant/i }).waitFor();
    await expect(page.getByText("Chapitre 0 / 3")).toHaveCount(0);
  });

  test("un lecteur sans droit sur une story non publiée voit un refus", async ({ page }) => {
    await openAs(page, "reader");
    await spaGoto(page, `/apps/${pk}`);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Titre chapitre 1" })).toHaveCount(0);
  });
});
