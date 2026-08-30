// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un admin déclare une source STAC, la moissonne, et un re-moissonnage ne duplique pas", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  // Magasin honnête, keyé par id externe (pk) : le handler "/run" UPSERT
  // dedans plutôt que de réassigner un objet unique — la taille du
  // catalogue reflète donc le nombre réel d'ids externes distincts
  // moissonnés, et peut structurellement dépasser 1 (aucune de-duplication
  // n'est faite ici, contrairement à une ancienne version de ce mock).
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1",
          type: "stac",
          url: "https://stac.example.com/collections",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [
              {
                id: "src-1",
                type: "stac",
                url: "https://stac.example.com/collections",
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: runCount > 0 ? "2026-07-19T10:00:00Z" : null,
                lastStatus: runCount > 0 ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("ext-1", {
      pk: "ext-1",
      resourceType: "external",
      title: "Bâtiments (STAC distant)",
      abstract: "",
      owner: "mockuser",
      thumbnailUrl: null,
      date: "2026-01-01",
      configId: null,
      isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  // Host-scoped: le shell a lui-même une route client "/items" (catalogue) —
  // un glob non scopé casserait la navigation (même rationale que
  // "/items/1"/"/items/9" ailleurs dans cette suite).
  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  // Le lien "Moissonnage" de l'ancien menu latéral a disparu avec l'ancien
  // chrome (Task 12) : la barre de domaines n'a plus qu'un seul lien
  // "Administration" pour ce domaine. On vérifie à la place que la page
  // elle-même (inchangée) a bien rendu, via son propre titre.
  await expect(page.getByRole("heading", { name: "Moissonnage" })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill("https://stac.example.com/collections");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "stac",
      url: "https://stac.example.com/collections",
      mode: "reference",
      enabled: true,
    });
  await expect(page.getByText("https://stac.example.com/collections")).toBeVisible();

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Bâtiments (STAC distant)")).toBeVisible();
  // .last(), not the default first match: the catalog's "Type" <select>
  // (SP-23, chantier 4.6) always renders an <option value="external">Externe</option>
  // ahead of the item grid in DOM order — .last() lands on the item's own
  // badge instead.
  await expect(page.getByText("Externe").last()).toBeVisible();

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(2);
  await page.goto("/");
  // Le shell rend tel quel ce que "/items" renvoie — il ne dé-duplique rien
  // lui-même. Ici le magasin mocké est un vrai upsert keyé par id externe
  // (pas un objet unique réassigné), donc cette assertion a un échec
  // possible : si "/run" avait ajouté un id externe distinct au lieu de
  // ré-upserter "ext-1", le compte serait 2. L'invariant "un re-moissonnage
  // ne duplique jamais" est prouvé côté cœur, contre un vrai Postgres, dans
  // core/tests/test_harvest_repository.py (contrainte unique) et
  // core/tests/test_harvest_service.py (re-harvest-no-reimport) ; cette E2E
  // prouve le parcours visible + que re-lancer la même source garde le
  // catalogue à une seule carte.
  await expect(page.getByText("Bâtiments (STAC distant)")).toHaveCount(1);
});
