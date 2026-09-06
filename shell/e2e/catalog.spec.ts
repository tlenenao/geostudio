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

test("filtrer sur Dataset ne ramène que les datasets", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByLabel("Type").selectOption("dataset");

  await expect(page.getByRole("heading", { name: "Alpha" })).toBeHidden();
  // .last(), not .first(): the "Type" <select> above the grid always renders
  // an <option value="dataset">Dataset</option> (RESOURCE_TYPE_ORDER is
  // exhaustive over ResourceType, cf. resourceTypes.ts), and that option
  // precedes the item grid in DOM order — .first() resolves to it and fails
  // toBeVisible() (native <option> elements report hidden outside an open
  // dropdown), for a reason unrelated to the filter under test. .last()
  // reliably lands on the one ItemCard badge left after filtering.
  await expect(page.getByText("Dataset", { exact: true }).last()).toBeVisible();
});

test("SP-55 : trie le catalogue par titre (A→Z)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  await page.getByLabel("Trier par").selectOption("title_asc");
  // La fixture mock renvoie les items déjà triés par titre quand ?sort=
  // est présent (e2e/mocks.ts) — Alpha < Beta < Gamma alphabétiquement,
  // donc trier par titre_desc doit inverser l'ordre observable.
  await page.getByLabel("Trier par").selectOption("title_desc");
  const headings = page.getByRole("heading");
  await expect(headings.first()).toHaveText("Gamma");
});

test("SP-55 : filtre le catalogue par mot-clé", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/items/facets*", async (route) => {
    await route.fulfill({
      json: { owners: [], keywords: [{ keyword: "important", count: 1 }] },
    });
  });
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    const keywords = url.searchParams.getAll("keyword");
    if (keywords.includes("important")) {
      await route.fulfill({
        json: {
          items: [
            {
              pk: "1",
              resourceType: "app",
              title: "Alpha",
              abstract: "A",
              owner: "alice",
              thumbnailUrl: null,
              date: "2026-01-01",
              configId: null,
              isPublished: false,
              permissions: { read: true, write: true, delete: true, share: true },
            },
          ],
          total: 1,
          page: 1,
          pageSize: 12,
        },
      });
    } else {
      await route.fallback();
    }
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Beta" })).toBeVisible();

  await page.getByRole("button", { name: /^important/ }).click();
  await expect(page.getByRole("heading", { name: "Beta" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
});

test("SP-55 : dessine un rectangle et ne garde que les items dont la bbox intersecte", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    const bbox = url.searchParams.get("bbox");
    // La valeur exacte dépend de la résolution du canvas de test et du
    // point de dépôt réel de la souris — seule sa PRÉSENCE est vérifiée
    // (le composant l'envoie bien), pas une valeur littérale fragile.
    if (bbox) {
      await route.fulfill({
        json: {
          items: [
            {
              pk: "1",
              resourceType: "app",
              title: "Alpha",
              abstract: "A",
              owner: "alice",
              thumbnailUrl: null,
              date: "2026-01-01",
              configId: null,
              isPublished: false,
              permissions: { read: true, write: true, delete: true, share: true },
            },
          ],
          total: 1,
          page: 1,
          pageSize: 12,
        },
      });
    } else {
      await route.fallback();
    }
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Beta" })).toBeVisible();

  const canvas = page
    .locator('[aria-label="Dessiner un rectangle de recherche spatiale"] canvas')
    .first();
  await expect(canvas).toBeVisible();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6, { steps: 5 });
  await page.mouse.up();

  await expect(page.getByRole("heading", { name: "Beta" })).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
});

test("changer de filtre ne remplit pas l'historique (retour arrière direct)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByLabel("Type").selectOption("dataset");
  await page.getByLabel("Type").selectOption("map");
  await page.goBack();
  // Un seul retour doit sortir de la page (revenir à about:blank / page
  // précédente réelle), pas rejouer "dataset" — la preuve la plus fiable
  // ici est que l'URL ne contient plus aucun ?type= issu de nos deux
  // changements de filtre consécutifs.
  await expect(page).not.toHaveURL(/type=(dataset|map)/);
});
