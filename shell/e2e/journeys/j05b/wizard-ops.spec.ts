import { bug } from "../_fixtures/verify";
import { expect, test } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import { fillWizard, getSeed, psql, rowsOf, submitWizard, type Seed } from "./helpers";

let seed: Seed;
test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

test.describe("j05b requête visuelle — opérateurs, métriques, schéma", () => {
  // Finding j05b-002 : la collection de sortie créée par l'assistant (POST /collections/empty)
  // refuse toute écriture par writer.dataset (tenant_id « required »), cf. j02-003.
  bug(
    "j05b-002 : Créer produit un dataset rempli sans contournement SQL de la table de sortie",
    async ({ page }) => {
      test.setTimeout(240_000);
      const title = stamp("j05b");
      await loginOidc(page, "creator");
      await page.waitForTimeout(800);
      await fillWizard(page, { title, base: seed.ventes });
      const res = await submitWizard(page, title, { patch: false });
      expect(res.run.status).toBe("succeeded");
    },
  );

  test("« contient » : enrobé de %, mais sensible à la casse et jokers non échappés", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    const count = async (value: string) => {
      const title = stamp("j05b");
      await fillWizard(page, {
        title,
        base: seed.ventes,
        filters: [{ column: "note", op: "contains", value }],
      });
      const r = await submitWizard(page, title);
      expect(r.run.status).toBe("succeeded");
      return Number(rowsOf(r.outCollection, "count(*)", "1")[0][0]);
    };
    expect(await count("n1")).toBe(10); // n10..n19 (E0/E1 portent des notes spéciales)
    // Attendu par un auteur no-code : « N1 » retrouve « n1 » ; « _ » (souligné littéral) ne retient rien.
    expect(await count("N1")).toBe(0); // sensible à la casse (constaté)
    expect(await count("_")).toBe(60); // joker LIKE non échappé : tout passe (constaté)
  });

  // Finding j05b-003 : constaté ci-dessus (casse + jokers) ; le test correspond au comportement
  // attendu par l'auteur. Confirme j05-023 (hypothèse de 1re passe, à nuancer : l'enrobage % existe).
  bug(
    "j05b-003 : « contient » ignore la casse et traite % et _ comme des caractères littéraux",
    async ({ page }) => {
      test.setTimeout(240_000);
      await loginOidc(page, "creator");
      await page.waitForTimeout(800);
      const title = stamp("j05b");
      await fillWizard(page, {
        title,
        base: seed.ventes,
        filters: [{ column: "note", op: "contains", value: "_" }],
      });
      const r = await submitWizard(page, title);
      expect(Number(rowsOf(r.outCollection, "count(*)", "1")[0][0])).toBe(0);
    },
  );

  test("filtre sur colonne date (timestamptz) et sur colonne numérique", async ({ page }) => {
    test.setTimeout(300_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    const t1 = stamp("j05b");
    await fillWizard(page, {
      title: t1,
      base: seed.ventes,
      filters: [{ column: "d", op: "gte", value: "2026-01-01" }],
    });
    const a = await submitWizard(page, t1);
    expect(a.run.status).toBe("succeeded");
    expect(rowsOf(a.outCollection, "count(*)", "1")[0][0]).toBe("30");
    const t2 = stamp("j05b");
    await fillWizard(page, {
      title: t2,
      base: seed.ventes,
      filters: [
        { column: "montant", op: "gt", value: "100" },
        { column: "montant", op: "lt", value: "200" },
      ],
    });
    const b = await submitWizard(page, t2);
    expect(b.run.status).toBe("succeeded");
    // i = 11..19 sauf i%7==0 (14) : 9 valeurs -> 8 lignes (montant 110..190 hors 140).
    expect(rowsOf(b.outCollection, "count(*)", "1")[0][0]).toBe("8");
  });

  test("toutes les métriques (count, distinct, somme, moyenne, médiane, centile, écart-type, min, max)", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.ventes,
      summary: {
        groupBy: ["zone"],
        metrics: [
          { fn: "count" },
          { fn: "countDistinct", column: "cat" },
          { fn: "sum", column: "montant" },
          { fn: "avg", column: "montant" },
          { fn: "median", column: "montant" },
          { fn: "percentile", column: "montant", p: "90" },
          { fn: "stddev", column: "montant" },
          { fn: "min", column: "montant" },
          { fn: "max", column: "qte" },
        ],
      },
    });
    const r = await submitWizard(page, title);
    expect(r.run.status).toBe("succeeded");
    const rows = rowsOf(
      r.outCollection,
      "zone,metrique_1,metrique_2,metrique_3,round(metrique_4::numeric,2),metrique_5,metrique_6,round(metrique_7::numeric,2),metrique_8,metrique_9",
      "zone",
    );
    // zone z1 : i = 0,3,6,...,57 (20 lignes) ; montant = i*10 sauf i%7==0.
    const z1 = Array.from({ length: 20 }, (_, k) => k * 3);
    const m = z1.filter((i) => i % 7 !== 0).map((i) => i * 10);
    const sum = m.reduce((a, b) => a + b, 0);
    expect(rows[0].slice(0, 4)).toEqual([
      "z1",
      "20",
      String(new Set(z1.map((i) => (i % 10 === 9 ? null : ["a", "b", "c"][i % 3]))).size - 1),
      String(sum),
    ]);
    expect(Number(rows[0][4])).toBeCloseTo(sum / m.length, 1);
    expect(Number(rows[0][8])).toBe(Math.min(...m));
    expect(rows).toHaveLength(3);
  });

  test("schéma de sortie : types des colonnes et collection de sortie sans géométrie", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const title = stamp("j05b");
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await fillWizard(page, {
      title,
      base: seed.ventes,
      summary: { groupBy: ["cat"], metrics: [{ fn: "count" }, { fn: "avg", column: "qte" }] },
    });
    const r = await submitWizard(page, title);
    expect(r.run.status).toBe("succeeded");
    const cols = psql(
      `SELECT column_name||':'||data_type FROM information_schema.columns WHERE table_name='${psql(`SELECT table_name FROM collections WHERE id='${r.outCollection}'`).trim()}' ORDER BY ordinal_position`,
    )
      .trim()
      .split("\n");
    expect(cols).toEqual([
      "id:integer",
      "tenant_id:text",
      "cat:text",
      "metrique_1:integer",
      "metrique_2:double precision",
    ]);
  });
});
