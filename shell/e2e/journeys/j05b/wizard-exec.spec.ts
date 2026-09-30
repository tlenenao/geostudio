import { bug } from "../_fixtures/verify";
import { expect, test } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import { fillWizard, getSeed, psql, rowsOf, submitWizard, type Seed } from "./helpers";

let seed: Seed;
test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

// Les 60 lignes de `ventes` : cat a/b/c (null si i%10==9), montant i*10 (null si i%7==0).
const ventes = Array.from({ length: 60 }, (_, i) => ({
  i,
  cat: i % 10 === 9 ? null : ["a", "b", "c"][i % 3],
  zone: `z${(i % 3) + 1}`,
  montant: i % 7 === 0 ? null : i * 10,
}));

test.describe("j05b requête visuelle — exécution réelle (ETL allumé)", () => {
  test("Créer : la requête est exécutée et le dataset de sortie est rempli", async ({ page }) => {
    test.setTimeout(240_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.ventes,
      filters: [{ column: "montant", op: "gte", value: "100" }],
      summary: {
        groupBy: ["cat"],
        metrics: [{ fn: "sum", column: "montant" }, { fn: "count" }],
      },
    });
    const res = await submitWizard(page, title);
    expect(res.run.status).toBe("succeeded");
    const got = rowsOf(res.outCollection, "cat,metrique_1,metrique_2", "cat NULLS LAST");
    const exp: Record<string, [number, number]> = {};
    for (const v of ventes) {
      if (v.montant === null || v.montant < 100) continue;
      const k = v.cat ?? "∅";
      exp[k] ??= [0, 0];
      exp[k][0] += v.montant;
      exp[k][1] += 1;
    }
    const gotMap = Object.fromEntries(got.map((r) => [r[0], [Number(r[1]), Number(r[2])]]));
    expect(gotMap).toEqual(exp);
  });

  // Finding j05b-001 : le POST /run du wizard répond 500 (AppNotOpen, j06b-001) après avoir créé
  // collection + dataset + pipeline ; l'utilisateur voit « internal server error » et un nouvel
  // essai crée un second jeu d'objets identiques.
  bug(
    "j05b-001 : un échec du lancement ne laisse ni objets orphelins ni doublon au nouvel essai",
    async ({ page }) => {
      test.setTimeout(120_000);
      const title = stamp("j05b");
      await loginOidc(page, "creator");
      await page.waitForTimeout(800);
      await fillWizard(page, { title, base: seed.ventes });
      const create = page.getByRole("button", { name: "Créer", exact: true });
      await create.click();
      await expect(page.getByRole("alert")).toBeVisible();
      await create.click();
      await page.waitForTimeout(3000);
      const n = psql_count(
        `SELECT count(*) FROM items WHERE resource_type='pipeline' AND title='Requête — ${title}'`,
      );
      expect(n).toBeLessThanOrEqual(1);
    },
  );

  test("Jointure interne puis gauche : lignes et colonnes de sortie", async ({ page }) => {
    test.setTimeout(240_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    const inner = stamp("j05b");
    await fillWizard(page, {
      title: inner,
      base: seed.zonesRef,
      join: { collection: seed.ventes, on: "zone", how: "inner" },
    });
    const a = await submitWizard(page, inner);
    expect(a.run.status).toBe("succeeded");
    expect(rowsOf(a.outCollection, "count(*)", "1")[0][0]).toBe("60");
    const left = stamp("j05b");
    await fillWizard(page, {
      title: left,
      base: seed.zonesRef,
      join: { collection: seed.ventes, on: "zone", how: "left" },
    });
    const b = await submitWizard(page, left);
    expect(b.run.status).toBe("succeeded");
    // z4 n'a aucune vente : la jointure gauche garde une ligne orpheline.
    expect(rowsOf(b.outCollection, "count(*)", "1")[0][0]).toBe("61");
  });

  test("Relancer le pipeline remplace la sortie (pas de doublon)", async ({ page }) => {
    test.setTimeout(240_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, { title, base: seed.zonesRef });
    const a = await submitWizard(page, title);
    expect(a.run.status).toBe("succeeded");
    const { runPipeline, waitRun, apiFor } = await import("./helpers");
    const creator = await apiFor("creator");
    const again = await runPipeline(creator, a.pipelineItem);
    const run2 = await waitRun(creator, a.pipelineItem, again.runId!);
    expect(run2.status).toBe("succeeded");
    expect(rowsOf(a.outCollection, "count(*)", "1")[0][0]).toBe("4");
  });
});

function psql_count(sql: string): number {
  return Number(psql(sql).trim());
}
