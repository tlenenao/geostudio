import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

// ARC-24 : un administrateur mappe une valeur de claim IdP vers un groupe du cœur.
test("un administrateur ajoute puis retire un mapping claim vers groupe", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let mappings: { id: string; groupId: string; claimValue: string }[] = [];
  let posted: unknown = null;
  await page.route("https://core.test/v1/roles", (r) => r.fulfill({ json: [] }));
  await page.route(/https:\/\/core\.test\/v1\/users(\?.*)?$/, (r) =>
    r.fulfill({ json: { users: [], total: 0 } }),
  );
  await page.route(/https:\/\/core\.test\/v1\/groups(\?.*)?$/, (r) =>
    r.fulfill({ json: [{ id: "g1", name: "Équipe SIG", createdBy: "u", canManage: true }] }),
  );
  await page.route("https://core.test/v1/groups/claim-mappings", async (route) => {
    if (route.request().method() === "POST") {
      posted = route.request().postDataJSON();
      mappings = [{ id: "m1", groupId: "g1", claimValue: "SIG" }];
      return route.fulfill({ status: 201, json: mappings[0] });
    }
    return route.fulfill({ json: mappings });
  });
  await page.route("https://core.test/v1/groups/claim-mappings/m1", async (route) => {
    mappings = [];
    await route.fulfill({ status: 204 });
  });

  await page.goto("/admin/users");
  await expect(page.getByText("Aucun mapping")).toBeVisible();
  await page.getByLabel("Valeur du claim").fill("SIG");
  await page.getByRole("combobox", { name: /^Groupe/ }).selectOption("g1");
  await page.getByRole("button", { name: "Ajouter le mapping" }).click();
  await expect(page.getByRole("button", { name: /Retirer le mapping SIG/ })).toBeVisible();
  expect(posted).toEqual({ groupId: "g1", claimValue: "SIG" });
  await page.getByRole("button", { name: /Retirer le mapping SIG/ }).click();
  await expect(page.getByText("Aucun mapping")).toBeVisible();
});
