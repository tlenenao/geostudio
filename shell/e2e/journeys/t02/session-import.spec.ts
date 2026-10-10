import { expect, test, type Page } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { go, newSession } from "./helpers";

test("t02 UI : la session survit à l'expiration du jeton d'accès (5 min) grâce au renouvellement silencieux", async ({
  browser,
}) => {
  test.setTimeout(480_000);
  const s = await newSession(browser, "creator");
  const statuses: { t: number; url: string; status: number }[] = [];
  const t0 = Date.now();
  s.page.on("response", (r) => {
    if (r.url().startsWith(`${CORE_URL}/v1/`)) {
      statuses.push({ t: Math.round((Date.now() - t0) / 1000), url: r.url(), status: r.status() });
    }
  });
  await s.page.waitForTimeout(345_000);
  await go(s.page, "/bookmarks", 3000);
  const late = statuses.filter((x) => x.t > 300);
  expect(late.length).toBeGreaterThan(0);
  expect(late.filter((x) => x.status === 401)).toEqual([]);
  expect(statuses.filter((x) => x.status >= 500)).toEqual([]);
  await s.ctx.close();
});

// Simule un import dont le job n'avance jamais (worker arrêté) : le pré-signé, le PUT et la
// création du job sont simulés, seul le sondage de statut est piloté par le test.
async function stubUploadPipeline(
  page: Page,
  status: (n: number) => "pending" | "running" | "done" | "abort",
): Promise<{ polls: () => number }> {
  let polls = 0;
  await page.route(`${CORE_URL}/v1/uploads/presign`, (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        uploadUrl: `${CORE_URL}/__t02_put`,
        key: "default/t02-key-points.csv",
      }),
    }),
  );
  await page.route(`${CORE_URL}/__t02_put`, (r) =>
    r.fulfill({ status: 200, headers: { "access-control-allow-origin": "*" }, body: "" }),
  );
  await page.route(`${CORE_URL}/v1/uploads`, (r) =>
    r.request().method() === "POST"
      ? r.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({ jobId: "t02job" }),
        })
      : r.continue(),
  );
  await page.route(`${CORE_URL}/v1/uploads/t02job`, (r) => {
    polls++;
    const st = status(polls);
    if (st === "abort") return r.abort("connectionrefused");
    return r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: st,
        errorMessage: null,
        collectionId: st === "done" ? "incidents" : null,
        itemId: null,
      }),
    });
  });
  return { polls: () => polls };
}

async function startImport(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "points.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("nom,latitude,longitude\na,46.2,2.5\n"),
  });
  await page.getByLabel("Titre de la collection").fill("aud-t02-import");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
}

test.describe("t02 UI : import de fichier sous file de jobs à l'arrêt ou instable", () => {
  test("un import dont le job reste « pending » affiche « Import en cours… » et verrouille l'annulation", async ({
    browser,
  }) => {
    test.setTimeout(90_000);
    const s = await newSession(browser, "creator");
    await go(s.page, "/", 1500);
    await stubUploadPipeline(s.page, () => "pending");
    await startImport(s.page);
    await expect(s.page.getByRole("button", { name: "Import en cours…" })).toBeVisible();
    await s.page.waitForTimeout(20_000);
    await expect(s.page.getByRole("button", { name: "Import en cours…" })).toBeDisabled();
    await expect(s.page.getByRole("button", { name: "Annuler", exact: true })).toBeDisabled();
    // L'issue de secours existe depuis D6 : « Annuler l'import » reste actif (t02-010).
    await expect(s.page.getByRole("button", { name: "Annuler l'import" })).toBeEnabled();
    await s.ctx.close();
  });

  // Finding t02-010 : le sondage n'a ni plafond de durée ni issue de secours ; le tiroir reste verrouillé.
  test("t02-010 : un import en attente prolongée offre une sortie (annulation ou avertissement)", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const s = await newSession(browser, "creator");
    await go(s.page, "/", 1500);
    await stubUploadPipeline(s.page, () => "pending");
    await startImport(s.page);
    await s.page.waitForTimeout(60_000);
    const cancelEnabled = await s.page
      .getByRole("button", { name: "Annuler l'import" })
      .isEnabled();
    const hint = await s.page.getByRole("dialog").innerText();
    expect(cancelEnabled || /toujours en cours|plus long|en attente|arrière-plan/i.test(hint)).toBe(
      true,
    );
    await s.ctx.close();
  });

  // Finding t02-011 : une seule erreur réseau du sondage est présentée comme un échec de l'import.
  test("t02-011 : un raté ponctuel du sondage n'affiche pas « Échec de l'import. »", async ({
    browser,
  }) => {
    test.setTimeout(60_000);
    const s = await newSession(browser, "creator");
    await go(s.page, "/", 1500);
    await stubUploadPipeline(s.page, (n) => (n === 2 ? "abort" : n >= 4 ? "done" : "running"));
    await startImport(s.page);
    await s.page.waitForTimeout(6000);
    expect(await s.page.locator("[role=alert]").allTextContents()).not.toContain(
      "Échec de l'import.",
    );
    await s.ctx.close();
  });
});
