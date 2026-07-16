import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("mode démo lecture seule : bannière visible, Formulaire masqué, écriture forcée refusée (403)", async ({ page }) => {
  await mockCore(page);
  // Surcharge posée APRÈS mockCore : Playwright privilégie la route la plus
  // récemment enregistrée qui matche (même patron que incident-form.spec.ts).
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: true } });
  });
  await page.route("**/collections/incidents/items*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 403,
        json: { detail: "Mode démo : lecture seule, écritures désactivées." },
      });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");
  await expect(
    page.getByText("Mode démo — lecture seule, les modifications ne sont pas enregistrées."),
  ).toBeVisible();

  // Créer l'app depuis le gabarit "Application de saisie" (config créée via
  // le mock /configs — la création de config n'est pas ce que ce test
  // exerce, cf. Task 1/2 côté cœur pour le vrai 403 serveur sur les
  // mutations REST/MCP).
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Démo lecture seule");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Déclarer l'incident" })).not.toBeVisible();

  // Écriture forcée (contournement de l'UI, ex. devtools) : le serveur refuse.
  const status = await page.evaluate(async () => {
    const res = await fetch("https://core.test/collections/incidents/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "Feature", properties: { titre: "Forcé", gravite: "haute" }, geometry: null }),
    });
    return res.status;
  });
  expect(status).toBe(403);
});
