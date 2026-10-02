import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder, fixme } from "./helpers";

test.setTimeout(90_000);
const text = (id: string, t: string, y = 0) => ({
  id,
  widget: "text",
  x: 0,
  y,
  w: 6,
  h: 2,
  props: { text: t },
});

async function shareToReader(
  s: Awaited<ReturnType<typeof getSeed>>,
  id: string,
  role: "viewer" | "editor",
) {
  const me = await s.reader.get("/v1/me");
  const g = await s.creator.send("POST", "/v1/groups", {
    name: `${s.tag}-${role}-${Date.now().toString(36)}`,
  });
  await s.creator.send("POST", `/v1/groups/${g.body.id}/members`, { userId: me.body.id });
  const r = await s.creator.send("PUT", `/v1/items/${id}/sharing`, {
    public: false,
    groups: [{ groupId: g.body.id, role }],
  });
  expect(r.status).toBe(204);
}

test.describe("j04 droits, historique, concurrence", () => {
  test("lecteur (viewer) : le builder s'ouvre mais Enregistrer est verrouillé avec explication", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("viewer-builder", baseApp({ layout: grid([text("a", "A")]) }));
    await shareToReader(s, id, "viewer");
    await openBuilder(page, id, "reader");
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  });

  test("lecteur : PUT direct de la config d'une app en lecture seule est refusé", async () => {
    const s = await getSeed();
    const id = await s.mkApp("viewer-put", baseApp({ layout: grid([text("a", "A")]) }));
    await shareToReader(s, id, "viewer");
    const r = await s.reader.send(
      "PUT",
      `/v1/configs/by-item/${id}`,
      baseApp({ layout: grid([text("a", "pirate")]) }),
    );
    expect([403, 404]).toContain(r.status);
  });

  test("lecteur sans partage : le builder affiche « introuvable », pas de contenu", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "prive-builder",
      baseApp({ layout: grid([text("a", "SecretPrive")]) }),
    );
    await openBuilder(page, id, "reader");
    await expect(page.getByText("Application introuvable.")).toBeVisible();
    await expect(page.getByText("SecretPrive")).toHaveCount(0);
  });

  test("analyste sans droit d'édition sur l'app d'un autre : PUT refusé", async () => {
    const s = await getSeed();
    const id = await s.mkApp("analyst-put", baseApp());
    const { apiFor } = await import("./api");
    const analyst = await apiFor("analyst");
    const r = await analyst.send(
      "PUT",
      `/v1/configs/by-item/${id}`,
      baseApp({ layout: grid([text("a", "x")]) }),
    );
    expect([403, 404]).toContain(r.status);
  });

  // finding j04-008
  fixme(
    "j04-008 : deux sessions d'édition concurrentes — la seconde sauvegarde est refusée ou fusionnée (pas d'écrasement silencieux)",
    async () => {
      const s = await getSeed();
      const id = await s.mkApp("concurrence", baseApp({ layout: grid([text("a", "V1")]) }));
      const first = await s.creator.get(`/v1/configs/by-item/${id}`);
      const v = first.body.version;
      const cfgA = { ...first.body.config, layout: grid([text("a", "Edition A")]) };
      const cfgB = { ...first.body.config, layout: grid([text("a", "Edition B")]) };
      const ra = await s.creator.send("PUT", `/v1/configs/by-item/${id}`, { ...cfgA, version: v });
      const rb = await s.creator.send("PUT", `/v1/configs/by-item/${id}`, { ...cfgB, version: v });
      expect(ra.status).toBe(200);
      // Attendu : 409/412 sur la version périmée. Observé : 200 et l'édition A est perdue.
      expect(rb.status).toBeGreaterThanOrEqual(409);
    },
  );

  test("historique : restaurer une version antérieure remplace le brouillon sans enregistrer", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("histo", baseApp({ layout: grid([text("a", "Version un")]) }));
    await s.creator.send(
      "PUT",
      `/v1/configs/by-item/${id}`,
      baseApp({ layout: grid([text("a", "Version deux")]) }),
    );
    await openBuilder(page, id);
    await expect(page.getByText("Version deux")).toBeVisible();
    await expect(page.getByText(/Version 1 —/)).toBeVisible();
    await page
      .getByRole("button", { name: /Restaurer/ })
      .first()
      .click();
    const confirm = page.getByRole("button", { name: /Restaurer|Confirmer/ }).last();
    if (await page.getByRole("dialog").count()) await confirm.click();
    await page.waitForTimeout(2000);
    await expect(page.getByText("Version un")).toBeVisible();
  });

  // finding j04-009
  test("j04-009 : le créateur peut redimensionner un widget (largeur/hauteur) depuis l'éditeur", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("resize", baseApp({ layout: grid([text("a", "A")]) }));
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner widget-a" }).click();
    const controls =
      (await page
        .getByRole("button", { name: /(Redimensionner|Élargir|Agrandir|Largeur|Hauteur)/i })
        .count()) + (await page.getByLabel(/(Largeur|Hauteur|Taille)/i).count());
    expect(controls).toBeGreaterThan(0);
  });

  test("déplacement : deux widgets peuvent être superposés sans avertissement", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "overlap",
      baseApp({ layout: grid([text("a", "A", 0), text("b", "B", 2)]) }),
    );
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner widget-b" }).click();
    await page.getByRole("button", { name: "Déplacer widget-b en haut" }).click();
    await page.getByRole("button", { name: "Déplacer widget-b en haut" }).click();
    const rows = await page
      .locator("[data-col]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-row")));
    expect(new Set(rows).size).toBe(1); // superposés : comportement observé (documenté, pas un échec)
  });
});
