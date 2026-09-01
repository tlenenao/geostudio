// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const NARROW_WIDTH = 390;
const NARROW_HEIGHT = 844;

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(1);
}

function meRoute(page: Page, overrides: Record<string, boolean>) {
  return page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: true,
        version: "0.1.0",
        tenantSlug: "demo",
        ...overrides,
      },
    });
  });
}

const SCREENS: Array<{
  name: string;
  path: string;
  before?: (page: Page) => Promise<void>;
}> = [
  { name: "Catalogue", path: "/" },
  { name: "Cartes", path: "/maps/map-1" },
  { name: "Apps & sites", path: "/apps/1/edit" },
  { name: "Analytique", path: "/analytics/sql", before: (p) => meRoute(p, { isAnalyst: true }) },
  { name: "Automatisation", path: "/pipelines/new" },
  { name: "Tâches", path: "/tasks" },
  {
    name: "Administration",
    path: "/admin/extensions",
    before: (p) => meRoute(p, { isAdmin: true }),
  },
  { name: "Paramètres", path: "/settings" },
];

for (const screen of SCREENS) {
  test(`${screen.name} à 390 px : barre de navigation basse, aucun débordement horizontal`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: NARROW_WIDTH, height: NARROW_HEIGHT });
    await mockCore(page);
    if (screen.before) {
      await screen.before(page);
    }
    await page.goto(screen.path);

    await expect(page.getByRole("navigation", { name: "Navigation" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const tabs = page.getByRole("tab");
    const tabCount = await tabs.count();
    for (let i = 0; i < tabCount; i++) {
      await tabs.nth(i).click();
      await expectNoHorizontalOverflow(page);
    }
  });
}
