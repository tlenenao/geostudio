import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("déclarer un incident : créer sans code, créer/voir/modifier/supprimer une entité", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");

  // Créer l'app depuis le gabarit, sans code.
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Déclarer un incident");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Sélectionner le widget Formulaire pré-câblé et charger son schéma.
  await page.getByRole("button", { name: "Sélectionner widget-tpl-incident-form" }).click();
  await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
  await expect(page.getByLabel("Label du champ titre")).toBeVisible();

  // Enregistrer la configuration du builder (bouton du builder, distinct du
  // bouton de soumission du Formulaire — cf. Global Constraints).
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : créer une entité.
  await page.goto("/apps/9");
  await page.getByLabel("titre").fill("Fuite d'eau");
  await page.getByLabel("gravite").selectOption("haute");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();

  // Apparaît dans la Table (rafraîchissement après écriture, SP-4a §5).
  await expect(page.getByText("Fuite d'eau")).toBeVisible();

  // Modifier depuis la sélection Table → Formulaire.
  await page.getByText("Fuite d'eau").click();
  await expect(page.getByText(/Modification de l'enregistrement #1/)).toBeVisible();
  const titreInput = page.getByLabel("titre");
  await titreInput.fill("Fuite d'eau (résolue)");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();
  await expect(page.getByText("Fuite d'eau (résolue)")).toBeVisible();
  await expect(page.getByText("Fuite d'eau", { exact: true })).toBeHidden();

  // Supprimer (confirmation native auto-acceptée).
  page.on("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByText("Fuite d'eau (résolue)")).toBeHidden();
  await expect(page.getByText(/Modification de l'enregistrement/)).toBeHidden();
});

test("un viewer ne voit pas les boutons d'écriture ; une écriture forcée est refusée (403)", async ({
  page,
}) => {
  await mockCore(page);
  // Surcharge posée APRÈS mockCore : Playwright privilégie la route la plus
  // récemment enregistrée qui matche, donc ceci l'emporte sur le
  // "**/collections/incidents" (permissions.write:true) déjà enregistré par mockCore.
  await page.route("**/collections/incidents", async (route) => {
    await route.fulfill({
      json: {
        id: "incidents",
        title: "Incidents",
        description: "",
        tableName: "incidents",
        isPublic: true,
        editable: true,
        geometryType: null,
        srid: null,
        pkColumn: "id",
        permissions: { read: true, write: false, delete: false, share: false },
      },
    });
  });
  await page.route("**/collections/incidents/items*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 403, json: { detail: "write access required" } });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Déclarer un incident (viewer)");
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
      body: JSON.stringify({
        type: "Feature",
        properties: { titre: "Forcé", gravite: "haute" },
        geometry: null,
      }),
    });
    return res.status;
  });
  expect(status).toBe(403);
});
