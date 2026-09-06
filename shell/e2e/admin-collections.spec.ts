import { test, expect } from "@playwright/test";
import { mockCore, mockMe, mockCollection, ADMIN_ME } from "./mocks";

test("un admin gère le cycle de vie complet d'une collection depuis le shell", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);

  let registered: unknown = null;
  let patchedTitle: string | null = null;
  let sharedBody: unknown = null;
  let deleted = false;

  // Host-scoped (not "**/collections*"): the shell's own client-side route to
  // this very page is "/admin/collections" — a path-only glob would also
  // intercept the browser's document navigation and break rendering (same
  // rationale as "/items/1"/"/items/9" and "/admin/extensions" elsewhere in
  // this suite). Registered after mockCore(page), so its more specific
  // pattern wins over mockCore's own "**/collections*" catch-all.
  await page.route("https://core.test/v1/collections/candidates", async (route) => {
    await route.fulfill({
      json: {
        candidates: [
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      },
    });
  });

  await page.route("https://core.test/v1/collections", async (route) => {
    if (route.request().method() === "POST") {
      registered = await route.request().postDataJSON();
      await route.fulfill({ status: 201, json: mockCollection() });
      return;
    }
    await route.fulfill({
      json: {
        collections: deleted
          ? []
          : registered
            ? [mockCollection({ title: patchedTitle ?? "Points d'intérêt" })]
            : [],
      },
    });
  });

  await page.route("https://core.test/v1/collections/points_interet**", async (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const body = await route.request().postDataJSON();
      patchedTitle = body.title ?? patchedTitle;
      await route.fulfill({ json: mockCollection({ title: patchedTitle ?? "Points d'intérêt" }) });
      return;
    }
    if (method === "DELETE") {
      deleted = true;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (route.request().url().endsWith("/sharing")) {
      if (method === "PUT") {
        sharedBody = await route.request().postDataJSON();
        await route.fulfill({ json: sharedBody });
        return;
      }
      await route.fulfill({ json: { public: false, groups: [] } });
      return;
    }
    await route.fallback();
  });

  await page.route("https://core.test/v1/groups", async (route) => {
    await route.fulfill({ json: [{ id: "g1", name: "Équipe terrain" }] });
  });

  await page.goto("/admin/collections");
  // Le lien "Collections" de l'ancien menu latéral a disparu avec l'ancien
  // chrome (Task 12) : la barre de domaines n'a plus qu'un seul lien
  // "Administration" pour ce domaine. On vérifie à la place que la page
  // elle-même (inchangée) a bien rendu, via son propre titre.
  await expect(page.getByRole("heading", { name: "Collections" })).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer une table" }).click();
  // Scoped to the panel: RegisterCollectionPanel's <section> carries
  // aria-label="Enregistrer une table" (role="region" implicite), dont le nom
  // accessible contient la sous-chaîne "Table" — un getByLabel("Table") non
  // scopé résoudrait à la fois ce conteneur et le <select>, faisant échouer
  // le mode strict de Playwright. Même schéma de correction que le scoping
  // "Supprimer" plus bas (ConfirmDialog vs. bouton de ligne). SP-30j : la
  // page bascule sur TriptychLayout, RegisterCollectionDialog (role="dialog")
  // devient RegisterCollectionPanel (role="region" implicite).
  const registerPanel = page.getByRole("region", { name: "Enregistrer une table" });
  await registerPanel.getByLabel("Table").selectOption("points_interet");
  await registerPanel.getByLabel("Titre").fill("Points d'intérêt");
  // exact: true — the page's own "Enregistrer une table" button (still in
  // the DOM, not behind an overlay anymore) is a substring superstring match
  // of "Enregistrer" and would otherwise trip Playwright's strict mode.
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => registered)
    .toEqual({ tableName: "points_interet", title: "Points d'intérêt", isPublic: false });
  await expect(page.getByText("Points d'intérêt")).toBeVisible();

  await page.getByRole("button", { name: "Éditer" }).click();
  const titleInput = page.getByLabel("Titre");
  await titleInput.fill("");
  await titleInput.fill("POI (édité)");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => patchedTitle).toBe("POI (édité)");
  await expect(page.getByText("POI (édité)")).toBeVisible();

  await page.getByRole("button", { name: "Partager" }).click();
  await page.getByLabel("Groupe Équipe terrain").click();
  await page.getByLabel("Rôle Équipe terrain").selectOption("editor");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => sharedBody)
    .toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });

  await page.getByRole("button", { name: "Supprimer" }).click();
  // The row-action button and the ConfirmDialog's confirm button share the
  // exact same accessible name once the dialog is open — Playwright's
  // strict mode would reject an unscoped getByRole here. Scope to the
  // dialog, same fix as CollectionsAdminPage.test.tsx (Task 5, Step 5).
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect.poll(() => deleted).toBe(true);
  // Scoped locators, not a bare getByText("POI (édité)"): while the DELETE
  // response is still unwinding (mutateAsync -> setDeleting(null)), the
  // ConfirmDialog's own message ("Désenregistrer « POI (édité) » ...") is a
  // second match for that text and trips Playwright's strict mode — wait for
  // the dialog to actually close first, then assert the row is gone (observed
  // through the refetch triggered by useDeleteCollection's cache invalidation,
  // not just the DELETE request having been sent).
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("cell", { name: "POI (édité)" })).not.toBeVisible();
});

test("un utilisateur non-admin ne voit pas le lien Collections et une navigation forcée affiche un message d'accès refusé", async ({
  page,
}) => {
  await mockCore(page);
  let collectionsAdminCalled = false;
  await page.route("https://core.test/v1/collections", async (route) => {
    collectionsAdminCalled = true;
    await route.fulfill({ json: { collections: [] } });
  });

  await page.goto("/admin/collections");
  await expect(page.getByRole("alert")).toHaveText("Accès réservé aux administrateurs.");
  expect(await page.getByRole("link", { name: "Collections" }).count()).toBe(0);
  expect(collectionsAdminCalled).toBe(false);
});
