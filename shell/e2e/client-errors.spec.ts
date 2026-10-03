// SPDX-License-Identifier: Apache-2.0
// P22 : connectivité (sondage, hors ligne, levée ciblée) et états d'erreur de lecture.
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const BANNER = /Connexion au serveur perdue/;

test("P22.06/08 : la bannière d'injoignabilité est levée par le sondage, sans action de l'utilisateur", async ({
  page,
}) => {
  await page.clock.install();
  await mockCore(page);
  let cut = true;
  await page.route("**/v1/items?*", (route) =>
    cut ? route.abort("connectionrefused") : route.fallback(),
  );
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: BANNER })).toBeVisible();
  cut = false;
  await page.clock.fastForward(6_000);
  await expect(page.getByRole("alert").filter({ hasText: BANNER })).toHaveCount(0);
  await expect(page.getByText("Alpha").first()).toBeVisible();
});

test("P22.07 : hors ligne, une bannière dédiée est affichée puis levée au retour du réseau", async ({
  page,
  context,
}) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByText("Alpha").first()).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByRole("alert").filter({ hasText: /hors ligne/ })).toBeVisible();
  await context.setOffline(false);
  await expect(page.getByRole("alert").filter({ hasText: /hors ligne/ })).toHaveCount(0);
});

test("P22.09 : un 404 est « introuvable », un 500 est une erreur de chargement avec Réessayer", async ({
  page,
}) => {
  await mockCore(page);
  let status = 404;
  await page.route("**/v1/items/1", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          status,
          contentType: "application/problem+json",
          body: JSON.stringify({ title: "x", detail: "d" }),
        })
      : route.fallback(),
  );
  await page.goto("/items/1");
  await expect(page.getByRole("alert").filter({ hasText: /introuvable/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toHaveCount(0);

  status = 500;
  await page.goto("/items/1");
  await expect(page.getByRole("alert").filter({ hasText: /Erreur de chargement/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toBeVisible();
});
