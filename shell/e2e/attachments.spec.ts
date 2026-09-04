// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// Navigation : même patron qu'incident-form.spec.ts (widget Formulaire déjà
// exercé en E2E) — gabarit "application-de-saisie", pré-câblé sur la
// collection "incidents" (INCIDENT_APP_DATA_SOURCES, shell/src/builder/
// templates.ts). On réutilise cette collection déjà entièrement mockée par
// mockCore() (schéma, CRUD en mémoire) plutôt que d'inventer une collection
// "col1" qu'aucun gabarit ne sait câbler sans passer par le sélecteur de
// source de données (hors périmètre de ce spec) — seul le schéma est
// surchargé ci-dessous pour y ajouter un champ "photos" de type
// "attachment".
test("ajouter, lister et supprimer une pièce jointe depuis le widget Formulaire", async ({
  page,
}) => {
  await mockCore(page);

  // Surcharge posée APRÈS mockCore : Playwright privilégie la route la plus
  // récemment enregistrée qui matche (même remarque qu'incident-form.spec.ts
  // ligne 57-59) — ce schéma l'emporte sur "**/collections/incidents/schema"
  // déjà enregistré par mockCore, en ajoutant un champ "photos" de type
  // "attachment" à côté des champs "titre"/"gravite" existants.
  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents",
        pk: "id",
        geometry: null,
        fields: [
          { name: "titre", type: "string", required: true, maxLength: 120 },
          { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
          { name: "photos", type: "attachment", required: false, label: "Photos" },
        ],
      },
    });
  });

  let confirmed = false;
  await page.route("**/collections/incidents/items/1/attachments/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "http://localhost/upload", key: "t/incidents/1/x-a.jpg" },
    });
  });
  await page.route("http://localhost/upload", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/collections/incidents/items/1/attachments*", async (route) => {
    if (route.request().method() === "POST") {
      confirmed = true;
      await route.fulfill({
        status: 201,
        json: {
          id: "att1",
          fieldKey: "photos",
          filename: "a.jpg",
          contentType: "image/jpeg",
          byteSize: 10,
          createdAt: "2026-01-01T00:00:00Z",
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        attachments: confirmed
          ? [
              {
                id: "att1",
                fieldKey: "photos",
                filename: "a.jpg",
                contentType: "image/jpeg",
                byteSize: 10,
                createdAt: "2026-01-01T00:00:00Z",
              },
            ]
          : [],
      },
    });
  });
  await page.route("**/collections/incidents/items/1/attachments/att1", async (route) => {
    confirmed = false;
    await route.fulfill({ status: 204, body: "" });
  });
  // Preuve de sortie de C1 (revue finale de branche) : le fichier n'est plus
  // servi par un `<a href>` nu (jamais authentifié) mais par un fetch réel —
  // ce mock permet de vérifier que la requête déclenchée par le clic aboutit
  // bien en 200, pas seulement que le bouton est visible.
  await page.route("**/collections/incidents/items/1/attachments/att1/file", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      body: Buffer.from("x"),
      headers: { "Content-Disposition": 'attachment; filename="a.jpg"' },
    });
  });

  // Créer l'app depuis le gabarit, sans code (patron incident-form.spec.ts).
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Pièces jointes");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Sélectionner le widget Formulaire pré-câblé et charger son schéma (avec
  // le champ "photos" désormais servi par la surcharge ci-dessus).
  await page.getByRole("button", { name: "Sélectionner widget-tpl-incident-form" }).click();
  await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
  await expect(page.getByLabel("Label du champ titre")).toBeVisible();

  // Enregistrer la configuration du builder (bouton du builder, distinct du
  // bouton de soumission du Formulaire).
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : créer une entité (fid="1" — id retourné par le mock CRUD
  // "incidents" de mockCore()).
  await page.goto("/apps/9");
  await page.getByLabel("titre").fill("Fuite d'eau");
  await page.getByLabel("gravite").selectOption("haute");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();
  await expect(page.getByText("Fuite d'eau")).toBeVisible();

  // Modifier depuis la sélection Table → Formulaire (même patron
  // qu'incident-form.spec.ts) : atteint fid="1" en mode édition, où le champ
  // "photos" (type "attachment") devient exploitable.
  await page.getByText("Fuite d'eau").click();
  await expect(page.getByText(/Modification de l'enregistrement #1/)).toBeVisible();

  await expect(page.getByLabel("Ajouter des fichiers")).toBeVisible();
  await page
    .getByLabel("Ajouter des fichiers")
    .setInputFiles({ name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("x") });

  // `exact: true` : Playwright fait un matching par sous-chaîne par défaut sur
  // `name`, contrairement à Testing Library — "a.jpg" matcherait aussi le
  // bouton "Supprimer a.jpg" juste à côté sans cette option.
  const downloadButton = page.getByRole("button", { name: "a.jpg", exact: true });
  await expect(downloadButton).toBeVisible();

  // Le clic déclenche un fetch authentifié réel (plus un `<a href>` nu) —
  // vérifié via la réponse effective, pas seulement la visibilité du bouton.
  const [fileResponse] = await Promise.all([
    page.waitForResponse((res) => res.url().includes("/attachments/att1/file")),
    downloadButton.click(),
  ]);
  expect(fileResponse.status()).toBe(200);

  await page.getByRole("button", { name: "Supprimer a.jpg" }).click();
  await expect(page.getByRole("button", { name: "a.jpg", exact: true })).toHaveCount(0);
});
