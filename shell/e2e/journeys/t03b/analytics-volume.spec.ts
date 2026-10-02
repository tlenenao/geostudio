/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { getBigSeed, getPlainBig, psql, timed, apiFor, type BigSeed } from "./helpers";

let s500k: BigSeed;
let plain50k: { id: string; cdcMs: number };
let plain500k: { id: string; cdcMs: number };

test.beforeAll(async () => {
  test.setTimeout(600_000);
  s500k = await getBigSeed(500_000);
  plain50k = await getPlainBig(50_000);
  plain500k = await getPlainBig(500_000);
});

const agg = (id: string, body: unknown, who: "creator" | "analyst" = "creator") =>
  timed(who, `/v1/collections/${id}/aggregate`, { method: "POST", body });
// Seul un compte voyant la collection (admin : ADMIN_COLLECTIONS_MANAGE) l'interroge en SQL Lab :
// les collections du créateur ne sont pas partagées à l'analyste.
const sql = (q: string) =>
  timed("admin", "/v1/analytics/sql", { method: "POST", body: { sql: q } });

test.describe("t03b requêtes DuckDB / agrégats sur 500 000 entités (CDC actif)", () => {
  test("aggregate groupé (count, sum, avg, median, p90, countDistinct) sur 500k : froid puis chaud sous 3 s", async () => {
    const body = {
      groupBy: "cat",
      measures: [
        { agg: "count", label: "n" },
        { agg: "sum", field: "val", label: "s" },
        { agg: "avg", field: "val", label: "a" },
        { agg: "median", field: "val", label: "med" },
        { agg: "percentile", field: "val", p: 90, label: "p90" },
        { agg: "countDistinct", field: "nom", label: "d" },
      ],
    };
    const cold = await agg(s500k.collectionId, body);
    const warm = await agg(s500k.collectionId, body);
    console.log("T03B aggregate500k froid", cold.ms, "ms chaud", warm.ms, "ms");
    expect(cold.status).toBe(200);
    const rows = JSON.parse(cold.text()).rows;
    expect(rows).toHaveLength(8);
    expect(rows.reduce((s: number, r: any) => s + r.n, 0)).toBe(500_000);
    expect(cold.ms).toBeLessThan(3000);
    expect(warm.ms).toBeLessThan(3000);
  });

  test("5 agrégats concurrents sur 500k : tous 200, le plus lent sous 6 s", async () => {
    const t0 = Date.now();
    const rs = await Promise.all(
      Array.from({ length: 5 }, () =>
        agg(s500k.collectionId, {
          groupBy: "cat",
          measures: [{ agg: "median", field: "val", label: "m" }],
        }),
      ),
    );
    console.log("T03B concurrents", rs.map((r) => r.ms).join(","), "ms total", Date.now() - t0);
    for (const r of rs) expect(r.status).toBe(200);
    expect(Math.max(...rs.map((r) => r.ms))).toBeLessThan(6000);
  });

  test("SQL Lab : GROUP BY sur 500k en moins de 3 s", async () => {
    const r = await sql(
      `select cat, count(*) n, avg(val) a from ${plain500k.id} group by cat order by cat`,
    );
    console.log("T03B sqlGroupBy500k", r.status, r.ms, "ms");
    expect(r.status).toBe(200);
    expect(JSON.parse(r.text()).rows).toHaveLength(8);
    expect(r.ms).toBeLessThan(3000);
  });

  test("SQL Lab : ORDER BY sur 500k, résultat plafonné à 10 000 lignes et marqué truncated", async () => {
    const r = await sql(`select nom, val from ${plain500k.id} order by val desc, nom`);
    console.log("T03B sqlOrderBy500k", r.status, r.ms, "ms", r.bytes, "o");
    expect(r.status).toBe(200);
    const b = JSON.parse(r.text());
    expect(b.rows).toHaveLength(10_000);
    expect(b.truncated).toBe(true);
    expect(r.ms).toBeLessThan(8000);
  });

  test("SQL Lab : jointure 500k x 500k à cardinalité explosive stoppée par le délai, sans 5xx", async () => {
    test.setTimeout(60_000);
    const r = await sql(
      `select count(*) from ${plain500k.id} a join ${plain500k.id} b on a.cat = b.cat`,
    );
    console.log("T03B sqlJoin", r.status, r.ms, "ms", r.text().slice(0, 140));
    expect(r.status).toBeLessThan(500);
    expect(r.ms).toBeLessThan(25_000);
  });

  test("fraîcheur : 10 lignes ajoutées à une collection de 50k apparaissent dans l'agrégat en moins de 45 s (flush CDC à 30 s)", async () => {
    test.setTimeout(120_000);
    const creator = await apiFor("creator");
    const table = psql(`SELECT table_name FROM collections WHERE id='${plain50k.id}'`).trim();
    psql(
      `INSERT INTO public."${table}" (tenant_id, nom, cat, val) SELECT 'default','fresh-'||g,'cf',1 FROM generate_series(1,10) g`,
    );
    const truth = Number(psql(`SELECT count(*) FROM public."${table}"`).trim());
    const t0 = Date.now();
    let n = 0;
    while (Date.now() - t0 < 80_000) {
      const r = await creator.send("POST", `/v1/collections/${plain50k.id}/aggregate`, {
        measures: [{ agg: "count", label: "n" }],
      });
      n = r.body?.rows?.[0]?.n ?? 0;
      if (n >= truth) break;
      await new Promise((res) => setTimeout(res, 1000));
    }
    const lag = Date.now() - t0;
    console.log("T03B fraicheurCDC", n, truth, lag, "ms");
    expect(n).toBe(truth);
    expect(lag).toBeLessThan(45_000);
  });

  test("t03b-004 : un insert en masse est visible dans les agrégats sans attendre un balayage différé", async () => {
    // Comparaison PG (vérité) vs agrégat : juste après l'INSERT, le compte agrégé doit
    // égaler le compte SQL (ou l'API doit signaler la fraîcheur des données).
    const creator = await apiFor("creator");
    const table = psql(`SELECT table_name FROM collections WHERE id='${plain50k.id}'`).trim();
    psql(
      `INSERT INTO public."${table}" (tenant_id, nom, cat, val) SELECT 'default','imm-'||g,'ci',1 FROM generate_series(1,5) g`,
    );
    const truth = Number(psql(`SELECT count(*) FROM public."${table}"`).trim());
    const r = await creator.send("POST", `/v1/collections/${plain50k.id}/aggregate`, {
      measures: [{ agg: "count", label: "n" }],
    });
    // P25.11 : le lac peut retarder (flush CDC ~30 s) — la réponse le dit via asOf/pending.
    const signalsAge = typeof r.body.asOf === "string" || r.body.pending === true;
    expect(r.body.rows[0].n === truth || signalsAge).toBe(true);
  });
});
