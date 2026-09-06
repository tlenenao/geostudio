import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

// SP-58 Tâche 10 : /admin/compliance — purge de tenant (confirmation par
// slug obligatoire) et anonymisation d'utilisateur, visuellement séparées
// (spec §3.3, risque §5 : jamais confondre les deux actions).
test("un titulaire de compliance.manage purge un tenant après confirmation par slug", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, {
    ...ADMIN_ME,
    privileges: [...ADMIN_ME.privileges, "compliance.manage"],
  });

  let purgeRequestBody: unknown = null;
  await page.route("https://core.test/v1/compliance/tenants/t-mock/purge", async (route) => {
    purgeRequestBody = await route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { jobId: "purge-e2e-1" } });
  });
  await page.route("https://core.test/v1/compliance/purges/purge-e2e-1", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/problem+json",
      json: { type: "about:blank", title: "Accepted", status: 202, detail: "in progress" },
    });
  });

  await page.goto("/admin/compliance");
  await expect(page.getByText("Purger toutes les données du tenant")).toBeVisible();

  const purgeButton = page.getByRole("button", { name: "Purger définitivement ce tenant" });
  await expect(purgeButton).toBeDisabled();

  // Slug erroné : reste désactivé.
  await page.getByLabel("Confirmer le slug du tenant").fill("mauvais-slug");
  await expect(purgeButton).toBeDisabled();

  // Slug exact ("demo", cf. DEFAULT_ME de e2e/mocks.ts) : s'active.
  await page.getByLabel("Confirmer le slug du tenant").fill("demo");
  await expect(purgeButton).toBeEnabled();
  await purgeButton.click();

  await expect(page.getByText("Purge en cours…")).toBeVisible();
  expect(purgeRequestBody).toEqual({ confirmSlug: "demo" });
});

test("anonymiser un compte est une action visuellement distincte de la purge", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, {
    ...ADMIN_ME,
    privileges: [...ADMIN_ME.privileges, "compliance.manage"],
  });
  await page.route("https://core.test/v1/compliance/users/u42/erase", async (route) => {
    await route.fulfill({ status: 204 });
  });

  await page.goto("/admin/compliance");
  await expect(page.getByRole("heading", { name: "Anonymiser un compte" })).toBeVisible();

  await page.getByLabel("Identifiant de l'utilisateur à anonymiser").fill("u42");
  await page.getByRole("button", { name: "Anonymiser ce compte" }).click();
  await expect(page.getByText("Compte anonymisé.", { exact: true })).toBeVisible();

  // La purge n'a jamais été déclenchée par cette action (aucune requête
  // vers /compliance/tenants/*/purge n'a été émise).
  await expect(page.getByRole("button", { name: "Purger définitivement ce tenant" })).toBeVisible();
  await expect(page.getByText("Purge en cours…")).not.toBeVisible();
});

test("un utilisateur sans compliance.manage n'accède pas à /admin/compliance", async ({ page }) => {
  await mockCore(page);
  await mockMe(page); // rôle par défaut ("creator"), sans compliance.manage.
  await page.goto("/admin/compliance");
  await expect(page.getByText("Accès réservé à la conformité (RGPD).")).toBeVisible();
});
