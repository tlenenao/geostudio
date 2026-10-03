import { test, expect } from "@playwright/test";
import { openAs, spaGoto } from "../j06/helpers";

test.setTimeout(120_000);

async function openInfra(page: import("@playwright/test").Page): Promise<void> {
  await openAs(page, "admin");
  await spaGoto(page, "/settings");
  await page.getByRole("link", { name: "Outils d'infrastructure →" }).click();
  await expect(page.getByRole("heading", { name: "Outils d'infrastructure" })).toBeVisible();
}

test("outils activés : trois boutons Martin/Titiler/Grafana, plus de mention « Non activé »", async ({
  page,
}) => {
  await openInfra(page);
  for (const name of ["Martin", "Titiler", "Grafana"]) {
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByText(/Non activé sur cette instance/)).toHaveCount(0);
  await expect(page.getByText(/Stockage : .*pas de limite configurée/)).toBeVisible();
});

test("un clic sur Grafana demande un lancement au cœur et ouvre l'URL de session dans un nouvel onglet", async ({
  page,
  context,
}) => {
  await openInfra(page);
  const launch = page.waitForResponse(
    (r) => r.url().endsWith("/v1/admin-tools/launch/grafana") && r.request().method() === "POST",
  );
  const popupPromise = context.waitForEvent("page");
  await page.getByRole("button", { name: "Grafana", exact: true }).click();
  expect((await launch).status()).toBe(200);
  const popup = await popupPromise;
  await popup.waitForLoadState("commit");
  expect(popup.url()).toMatch(/\/admin\/grafana\/|\/v1\/admin-tools\/session\/grafana/);
  await popup.close();
});

test("échec du lancement (403) : le bouton affiche une alerte « Échec de l'ouverture de l'outil. »", async ({
  page,
}) => {
  await openInfra(page);
  await page.route("**/v1/admin-tools/launch/martin", (route) =>
    route.fulfill({ status: 403, contentType: "application/json", body: '{"detail":"forbidden"}' }),
  );
  await page.getByRole("button", { name: "Martin", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Échec de l'ouverture de l'outil.");
});

// Finding j08b-009 : le lien « Console MinIO » n'est affiché que si le port 9001 est publié
// (indiqué par GET /instance/status) ; en production il est masqué plutôt que mort.
test("j08b-009 : la console MinIO n'est proposée que si son port est publié", async ({ page }) => {
  const status = page.waitForResponse((r) => r.url().includes("/instance/status"));
  await openInfra(page);
  const published = (await (await status).json()).minioConsolePublished === true;
  await expect(page.getByRole("link", { name: /Console MinIO/ })).toHaveCount(published ? 1 : 0);
});
