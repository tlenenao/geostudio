import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

test("un admin voit les extensions (actives et désactivées) et peut les activer/désactiver depuis le shell", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let patchedBody: unknown;
  // Host-scoped (not "**/extensions*"): the shell's own client-side route to
  // this very page is "/admin/extensions" — a path-only glob would also
  // intercept the browser's document navigation and break rendering (same
  // rationale as "/items/1"/"/items/9" in mockCore, mocks.ts). "**" (not "*")
  // so it also matches the nested PATCH path "/extensions/{id}".
  await page.route("https://core.test/v1/extensions**", async (route) => {
    if (route.request().method() === "PATCH") {
      patchedBody = await route.request().postDataJSON();
      await route.fulfill({ json: { id: "acme.gauge", enabled: false } });
      return;
    }
    await route.fulfill({
      json: {
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: true,
          },
        ],
      },
    });
  });

  await page.goto("/admin/extensions");
  // Le lien "Extensions" de l'ancien menu latéral a disparu avec l'ancien
  // chrome (Task 12) : la barre de domaines n'a plus qu'un seul lien
  // "Administration" pour ce domaine. On vérifie à la place que la page
  // elle-même (inchangée) a bien rendu, via son propre titre.
  await expect(page.getByRole("heading", { name: "Extensions" })).toBeVisible();
  const toggle = page.getByRole("checkbox", { name: "Actif : Jauge (extension)" });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect.poll(() => patchedBody).toEqual({ enabled: false });
});

test("un utilisateur non-admin voit un message d'accès refusé et n'appelle jamais /extensions", async ({
  page,
}) => {
  await mockCore(page);
  let extensionsCalled = false;
  // Host-scoped — see rationale in the test above.
  await page.route("https://core.test/v1/extensions**", async (route) => {
    extensionsCalled = true;
    await route.fulfill({ json: { extensions: [] } });
  });

  await page.goto("/admin/extensions");
  await expect(page.getByRole("alert")).toHaveText("Accès réservé aux administrateurs.");
  expect(await page.getByRole("link", { name: "Extensions" }).count()).toBe(0);
  expect(extensionsCalled).toBe(false);
});
