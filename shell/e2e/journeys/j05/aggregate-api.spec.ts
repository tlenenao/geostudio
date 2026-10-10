/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { expect, test } from "@playwright/test";
import { aggregate, apiFor, expectedByCat, type Api } from "./helpers";
import { getSeed, type Seed } from "./seed";

let seed: Seed;
let analyst: Api;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
  analyst = await apiFor("analyst");
});

const montants = () =>
  Array.from({ length: 60 }, (_, i) => (i % 7 === 0 ? null : i * 10)).filter(
    (v): v is number => v !== null,
  );

function quantileCont(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

test.describe("j05 agrégats — API", () => {
  test("groupBy + mesures : count/sum/median/percentile/stddev/countDistinct exacts", async () => {
    const exp = expectedByCat();
    const r = await aggregate(analyst, seed.ventes, {
      groupBy: "cat",
      measures: [
        { agg: "count", label: "n" },
        { agg: "sum", field: "montant", label: "s" },
        { agg: "median", field: "montant", label: "med" },
        { agg: "percentile", field: "montant", p: 90, label: "p90" },
        { agg: "countDistinct", field: "zone", label: "zones" },
      ],
    });
    expect(r.status).toBe(200);
    expect(r.body.categoryKey).toBe("cat");
    const rows = Object.fromEntries(r.body.rows.map((x: any) => [x.cat, x]));
    expect(rows.a.n).toBe(exp.a.n);
    expect(rows.b.s).toBe(exp.b.sum);
    // Médiane et p90 de la catégorie « c » recalculés indépendamment.
    const c = Array.from({ length: 60 }, (_, i) => i)
      .filter((i) => i % 10 !== 9 && i % 3 === 2 && i % 7 !== 0)
      .map((i) => i * 10)
      .sort((x, y) => x - y);
    expect(rows.c.med).toBeCloseTo(quantileCont(c, 0.5), 6);
    expect(rows.c.p90).toBeCloseTo(quantileCont(c, 0.9), 6);
    expect(rows.c.zones).toBe(1);
    const all = await aggregate(analyst, seed.ventes, { agg: "stddev", field: "montant" });
    const m = montants();
    const mean = m.reduce((a, b) => a + b, 0) / m.length;
    const sd = Math.sqrt(m.reduce((a, b) => a + (b - mean) ** 2, 0) / (m.length - 1));
    expect(all.body.rows[0].value).toBeCloseTo(sd, 6);
  });

  test("grains temporels : année et mois ventilent les 60 événements (2 x 30 par année)", async () => {
    const year = await aggregate(analyst, seed.ventes, {
      groupBy: "d",
      bucket: "year",
      agg: "count",
    });
    expect(year.status).toBe(200);
    expect(year.body.rows).toHaveLength(2);
    expect(year.body.rows.map((x: any) => x.value)).toEqual([30, 30]);
    const month = await aggregate(analyst, seed.ventes, {
      groupBy: "d",
      bucket: "month",
      agg: "count",
    });
    expect(month.body.rows.reduce((a: number, x: any) => a + x.value, 0)).toBe(60);
    expect(month.body.rows).toHaveLength(24);
    for (const g of ["hour", "day", "week", "quarter"]) {
      const r = await aggregate(analyst, seed.ventes, { groupBy: "d", bucket: g, agg: "count" });
      expect(r.status, g).toBe(200);
    }
  });

  test("histogramme et validations : bins somme au non-null, erreurs 400/422 structurées", async () => {
    const h = await aggregate(analyst, seed.ventes, { field: "montant", bins: 5 });
    expect(h.body.rows.reduce((a: number, x: any) => a + x.count, 0)).toBe(montants().length);
    const cases: [Record<string, unknown>, number][] = [
      [{ field: "montant", bins: 0 }, 400],
      [{ agg: "percentile", field: "montant" }, 400],
      [{ agg: "percentile", field: "montant", p: 100 }, 400],
      [{ groupBy: "cat", agg: "bogus", field: "montant" }, 400],
      [{ groupBy: "inexistant", agg: "count" }, 400],
      [{ groupBy: "cat", bucket: "decade" }, 422],
      [{ groupBy: ["cat", "cat"] }, 400],
    ];
    for (const [body, status] of cases) {
      const r = await aggregate(analyst, seed.ventes, body);
      expect(r.status, JSON.stringify(body)).toBe(status);
    }
  });

  // Finding j05-004 : aucune clause ORDER BY, les buckets sortent dans un ordre de hachage.
  test("j05-004 : les buckets temporels sont rendus en ordre chronologique", async () => {
    const r = await aggregate(analyst, seed.ventes, {
      groupBy: "d",
      bucket: "month",
      agg: "count",
    });
    const keys: string[] = r.body.rows.map((x: any) => x.d);
    expect(keys).toEqual([...keys].sort());
  });

  // Finding j05-005 : str(None) côté cœur -> la chaîne « None » pour un groupe NULL.
  test("j05-005 : un groupe NULL est rendu null, jamais la chaîne « None »", async () => {
    const r = await aggregate(analyst, seed.ventes, { groupBy: "cat", agg: "count" });
    expect(r.body.rows.map((x: any) => x.cat)).not.toContain("None");
  });

  // Finding j05-003 : d__lte « YYYY-MM-DD » compare à « YYYY-MM-DD hh:mm… » en texte.
  test("j05-003 : une plage temporelle d'un seul jour contient les événements de ce jour", async () => {
    // Le shell (derivePatch) envoie timeRange.from/to tels quels en d__gte / d__lte.
    const r = await aggregate(analyst, seed.ventes, {
      agg: "count",
      filters: { d__gte: "2025-01-15", d__lte: "2025-01-15" },
    });
    expect(r.body.rows[0]?.value).toBe(3);
  });

  // Finding j05-002 : la colonne géométrie du lac s'appelle « geometry », pas « geom ».
  test("j05-002 : un agrégat filtré par emprise ou intersection d'une collection importée répond 200", async () => {
    const bbox = await aggregate(analyst, seed.eventsCollection, {
      agg: "count",
      bbox: [0, 40, 5, 50],
    });
    expect(bbox.status).toBe(200);
    const inter = await aggregate(analyst, seed.eventsCollection, {
      agg: "count",
      geomIntersects: {
        type: "Polygon",
        coordinates: [
          [
            [0, 40],
            [5, 40],
            [5, 50],
            [0, 50],
            [0, 40],
          ],
        ],
      },
    });
    expect(inter.status).toBe(200);
  });

  // Finding j05-006 : erreur de conversion DuckDB non mappée en 400.
  test("j05-006 : un filtre numérique non convertible répond 400", async () => {
    const r = await aggregate(analyst, seed.ventes, {
      agg: "count",
      filters: { montant__gte: "abc" },
    });
    expect(r.status).toBe(400);
  });

  // Finding j05-007 : aucune ligne quand le filtre ne retient rien, même pour count.
  test("j05-007 : count sans groupBy sur un filtre vide renvoie 0", async () => {
    const r = await aggregate(analyst, seed.ventes, { agg: "count", filters: { cat: "zz" } });
    expect(r.body.rows[0]?.value).toBe(0);
  });

  // Finding j05-018 : cat__in découpe la valeur sur « , » (cross-filter multi-sélection).
  bug("j05-018 : un filtre __in accepte une valeur contenant une virgule", async () => {
    const value = '=1+1,"cité"\nligne2';
    const eq = await aggregate(analyst, seed.ventes, { agg: "count", filters: { note: value } });
    expect(eq.body.rows[0].value).toBe(1);
    const inn = await aggregate(analyst, seed.ventes, {
      agg: "count",
      filters: { note__in: value },
    });
    expect(inn.body.rows[0]?.value).toBe(1);
  });
});
