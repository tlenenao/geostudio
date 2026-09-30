import { expect, test } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import { spaGo } from "../j04/helpers";
import { apiFor, fillWizard, getSeed, psql, submitWizard, waitRun, type Seed } from "./helpers";

let seed: Seed;
test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

test.describe("j05b requête visuelle — géométrie, réouverture, droits", () => {
  // Finding j05b-004 : reader.collection ne sait pas relire une collection à géométrie (j06b-002) ;
  // l'assistant propose pourtant toute collection de la liste et le run échoue avec une erreur brute.
  test.fixme("j05b-004 : une requête visuelle sur une collection à géométrie s'exécute", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.eventsCollection,
      filters: [{ column: "cat", op: "eq", value: "a" }],
    });
    const r = await submitWizard(page, title);
    expect(r.run.status).toBe("succeeded");
  });

  test("Modifier la requête : l'état (filtre, jointure, résumé, centile) est restitué", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.ventes,
      filters: [{ column: "note", op: "contains", value: "n" }],
      summary: {
        groupBy: ["zone"],
        metrics: [{ fn: "percentile", column: "montant", p: "75" }, { fn: "count" }],
      },
    });
    const r = await submitWizard(page, title);
    expect(r.run.status).toBe("succeeded");
    await spaGo(page, `/datasets/visual-query/${r.pipelineItem}/edit`, 3000);
    await expect(page.getByLabel("Collection de base")).toHaveValue(seed.ventes);
    await expect(page.getByLabel("Valeur du filtre 1")).toHaveValue("n");
    await expect(page.getByLabel("Regrouper par zone")).toBeChecked();
    await expect(page.getByLabel("Fonction de la métrique 1")).toHaveValue("percentile");
    await expect(page.getByLabel("Centile de la métrique 1")).toHaveValue("75");
    await expect(page.getByLabel("Titre", { exact: true })).toHaveValue(title);
  });

  test("Analyste (sans automation.manage) : l'assistant n'offre pas de création qui échouerait", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const title = stamp("j05b");
    const before = Number(psql("SELECT count(*) FROM items WHERE resource_type='dataset'").trim());
    await loginOidc(page, "analyst");
    await page.waitForTimeout(800);
    await spaGo(page, "/datasets/visual-query/new", 2500);
    // Constat : la page s'ouvre, le formulaire se remplit et « Créer » est actif (seul le garde
    // serveur refuse), cf. j05-022 pour le Lecteur. On vérifie au moins l'absence d'objet orphelin.
    await page.getByLabel("Titre", { exact: true }).fill(title);
    await page.getByLabel("Collection de base").selectOption(seed.ventes);
    const create = page.getByRole("button", { name: "Créer", exact: true });
    if (await create.isEnabled()) {
      await create.click();
      await page.waitForTimeout(3000);
    }
    const after = Number(psql("SELECT count(*) FROM items WHERE resource_type='dataset'").trim());
    const orphanColl = Number(
      psql(`SELECT count(*) FROM collections WHERE title='${title} (données)'`).trim(),
    );
    expect(after).toBe(before);
    expect(orphanColl).toBe(0);
  });

  test("API : un Analyste ne peut pas enregistrer ni lancer un pipeline ; un Lecteur non plus", async () => {
    for (const persona of ["analyst", "reader"] as const) {
      const api = await apiFor(persona);
      const r = await api.send("POST", "/v1/configs", {
        title: stamp("j05b"),
        config: {
          version: 1,
          kind: "pipeline",
          pipeline: {
            nodes: [
              {
                id: "r",
                kind: "reader",
                op: "reader.collection",
                params: { collectionId: seed.ventes },
              },
              {
                id: "w",
                kind: "writer",
                op: "writer.export",
                params: { format: "csv", key: "x.csv" },
              },
            ],
            edges: [{ id: "e", from: "r", to: "w" }],
          },
        },
      });
      expect([401, 403]).toContain(r.status);
      const ops = await api.get("/v1/pipelines/ops");
      expect(ops.status).toBe(200);
    }
  });

  test("le dataset de sortie est lisible par l'agrégat et par SQL Lab après réplication CDC", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.ventes,
      summary: { groupBy: ["zone"], metrics: [{ fn: "count" }] },
    });
    const r = await submitWizard(page, title);
    expect(r.run.status).toBe("succeeded");
    const creator = await apiFor("creator");
    await creator.send("PUT", `/v1/collections/${r.outCollection}/sharing`, {
      public: true,
      groups: [],
    });
    const table = psql(`SELECT table_name FROM collections WHERE id='${r.outCollection}'`).trim();
    let n: unknown;
    for (let k = 0; k < 40; k++) {
      const a = await creator.send("POST", `/v1/collections/${r.outCollection}/aggregate`, {
        agg: "count",
      });
      n = a.body?.rows?.[0]?.value;
      if (n === 3) break;
      await new Promise((res) => setTimeout(res, 2000));
    }
    expect(n).toBe(3);
    const analyst = await apiFor("analyst");
    const sql = await analyst.send("POST", "/v1/analytics/sql", {
      sql: `SELECT zone, metrique_1 FROM ${table} ORDER BY zone`,
    });
    expect(sql.status).toBe(200);
    expect(sql.body.rows).toHaveLength(3);
    void waitRun;
  });
});
