// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

// L9 (AUD-106/149) : /admin/copilot — consommation de jetons du tenant et
// fournisseur LLM propre au tenant (clé en écriture seule).
test("l'administrateur voit la consommation, règle son fournisseur puis l'efface", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  await page.route("https://core.test/v1/copilot/usage", (route) =>
    route.fulfill({
      json: {
        dailyLimit: 5000,
        usedToday: 1200,
        days: [{ day: "2026-10-18", calls: 4, promptTokens: 900, completionTokens: 300 }],
      },
    }),
  );
  let configured = false;
  let putBody: unknown = null;
  await page.route("https://core.test/v1/copilot/llm-settings", async (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      putBody = route.request().postDataJSON();
      configured = true;
      return route.fulfill({
        json: {
          configured: true,
          model: "gpt-x",
          apiUrl: "https://llm.example.com/v1",
          hasApiKey: true,
        },
      });
    }
    if (method === "DELETE") {
      configured = false;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({
      json: configured
        ? {
            configured: true,
            model: "gpt-x",
            apiUrl: "https://llm.example.com/v1",
            hasApiKey: true,
          }
        : { configured: false, hasApiKey: false },
    });
  });

  await page.goto("/admin/copilot");
  await expect(
    page.getByRole("heading", { name: "IA : consommation et fournisseur" }),
  ).toBeVisible();
  await expect(page.getByText(/1\s200 jetons sur 5\s000/)).toBeVisible();
  await expect(page.getByText("Ce tenant utilise le fournisseur de l'instance.")).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((v) => v.impact === "critical" || v.impact === "serious"),
  ).toEqual([]);

  await page.getByLabel("Modèle").fill("gpt-x");
  await page.getByLabel("URL de l'API").fill("https://llm.example.com/v1");
  await page.getByLabel("Clé d'API").fill("sk-secret");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Réglages enregistrés.")).toBeVisible();
  expect(putBody).toEqual({
    model: "gpt-x",
    apiUrl: "https://llm.example.com/v1",
    apiKey: "sk-secret",
    dailyTokenLimit: null,
  });
  await expect(page.getByText("Ce tenant utilise son propre fournisseur.")).toBeVisible();
  // La clé n'est jamais réaffichée.
  await expect(page.getByLabel("Clé d'API")).toHaveValue("");

  await page.getByRole("button", { name: "Revenir au fournisseur de l'instance" }).click();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Revenir au fournisseur de l'instance" })
    .click();
  await expect(page.getByText("Réglages supprimés.")).toBeVisible();
});

test("sans settings.instance.manage, /admin/copilot est refusé", async ({ page }) => {
  await mockCore(page);
  await mockMe(page); // rôle créateur par défaut
  await page.goto("/admin/copilot");
  await expect(page.getByText("Accès réservé aux administrateurs.")).toBeVisible();
});
