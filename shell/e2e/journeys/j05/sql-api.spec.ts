/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { expect, test } from "@playwright/test";
import { aggregate, apiFor, sql, type Api } from "./helpers";
import { getSeed, type Seed } from "./seed";

let seed: Seed;
let analyst: Api;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

// Le limiteur SQL (10 requêtes / 60 s) est clé sur l'en-tête Authorization : un jeton
// neuf par test garde chaque test dans son propre budget.
test.beforeEach(async () => {
  analyst = await apiFor("analyst");
});

test.describe("j05 SQL Lab — API", () => {
  test("SELECT agrégé sur une table tabulaire : lignes et types corrects", async () => {
    const r = await sql(
      analyst,
      `select cat, count(*) n, sum(montant) s from ${seed.ventes} group by cat order by cat`,
    );
    expect(r.status).toBe(200);
    expect(r.body.columns).toEqual(["cat", "n", "s"]);
    expect(r.body.truncated).toBe(false);
    const byCat = Object.fromEntries(r.body.rows.map((x: any[]) => [String(x[0]), x]));
    expect(byCat.a[1]).toBe(18);
    expect(byCat.null[1]).toBe(6);
  });

  test("jointure de deux collections lisibles et sous-requête", async () => {
    const r = await sql(
      analyst,
      `select z.label, count(*) n from ${seed.ventes} v join ${seed.zonesRef} z on z.zone = v.zone ` +
        `where v.zone in (select zone from ${seed.zonesRef} where habitants > 1500) group by 1 order by 1`,
    );
    expect(r.status).toBe(200);
    expect(r.body.rows.map((x: any[]) => x[0])).toEqual(["Zone 2", "Zone 3"]);
  });

  test("droits : Lecteur et Créateur reçoivent 403, anonyme 401", async () => {
    for (const p of ["reader", "creator"] as const) {
      const api = await apiFor(p);
      const r = await sql(api, "select 1");
      expect(r.status).toBe(403);
    }
    const anon = await fetch(
      `${process.env.CORE_URL ?? "http://localhost:8200"}/v1/analytics/sql`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sql: "select 1" }),
      },
    );
    expect(anon.status).toBe(401);
  });

  test("bac à sable : DML, multi-instructions, fichiers, S3 et ATTACH sont refusés", async () => {
    const attempts = [
      `insert into ${seed.ventes} (cat) values ('x')`,
      "select 1; select 2",
      "select * from read_csv('/etc/passwd')",
      "select * from read_parquet('s3://geostudio-cdc/cdc/**')",
      "attach ':memory:' as x",
      "copy (select 1) to '/tmp/x.csv'",
      "install httpfs",
    ];
    for (const q of attempts) {
      const r = await sql(analyst, q);
      expect(r.status, q).toBe(400);
      expect(r.body.errors[0].field).toBe("sql");
    }
  });

  test("bac à sable : une requête trop longue est interrompue à ~10 s (400)", async () => {
    test.setTimeout(60_000);
    const t0 = Date.now();
    const r = await sql(
      analyst,
      "select count(*) from range(30000) a, range(30000) b, range(30) c where (a.range*b.range+c.range) % 7 = 3",
    );
    expect(r.status).toBe(400);
    expect(r.body.errors[0].message).toMatch(/time limit/);
    expect(Date.now() - t0).toBeLessThan(20_000);
  });

  test("plafond de lignes : 10 001 lignes demandées, 10 000 rendues et truncated", async () => {
    const r = await sql(analyst, "select * from range(10001)");
    expect(r.status).toBe(200);
    expect(r.body.rows).toHaveLength(10_000);
    expect(r.body.truncated).toBe(true);
  });

  test("SQL vide ou invalide : 400 avec erreur structurée, 422 sans champ sql", async () => {
    const empty = await sql(analyst, "");
    expect(empty.status).toBe(400);
    const bad = await sql(analyst, "select from where");
    expect(bad.status).toBe(400);
    expect(bad.body.errors[0].code).toBe("sql_error");
    const missing = await analyst.send("POST", "/v1/analytics/sql", {});
    expect(missing.status).toBe(422);
  });

  test("champ sensible : masqué en select *, absent des colonnes candidates", async () => {
    const admin = await apiFor("admin");
    const on = await admin.send("PATCH", `/v1/collections/${seed.ventes}`, {
      sensitiveFields: ["note"],
    });
    expect(on.status).toBe(200);
    try {
      const star = await sql(analyst, `select * from ${seed.ventes} limit 1`);
      expect(star.status).toBe(200);
      expect(star.body.columns).not.toContain("note");
      const direct = await sql(analyst, `select note from ${seed.ventes}`);
      expect(direct.status).toBe(400);
      const asAdmin = await sql(admin, `select note from ${seed.ventes} limit 1`);
      expect(asAdmin.status).toBe(200);
    } finally {
      await admin.send("PATCH", `/v1/collections/${seed.ventes}`, { sensitiveFields: [] });
    }
  });

  test("limiteur : la 11e requête SQL d'un même jeton reçoit 429 avec Retry-After", async () => {
    let last: Response | null = null;
    const url = `${process.env.CORE_URL ?? "http://localhost:8200"}/v1/analytics/sql`;
    const { token } = await import("../j03/api");
    const tok = await token("analyst");
    const statuses: number[] = [];
    for (let i = 0; i < 11; i++) {
      last = await fetch(url, {
        method: "POST",
        headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
        body: JSON.stringify({ sql: "select 1" }),
      });
      statuses.push(last.status);
    }
    expect(statuses.slice(0, 10).every((s) => s === 200)).toBe(true);
    expect(last!.status).toBe(429);
    expect(last!.headers.get("retry-after")).toBe("60");
  });

  // Finding j05-001 : le GeoParquet nomme la colonne « geometry », la table PostGIS « geom ».
  test.fixme("j05-001 : SQL Lab lit une collection à géométrie importée", async () => {
    const r = await sql(analyst, `select count(*) from ${seed.eventsCollection}`);
    expect(r.status).toBe(200);
    expect(r.body.rows[0][0]).toBe(60);
  });

  // Finding j05-008 : inf/NaN ne sont pas sérialisables en JSON -> 500.
  test.fixme("j05-008 : une division par zéro (inf) est rendue sans erreur serveur", async () => {
    const r = await sql(analyst, "select 1/0 as x");
    expect(r.status).toBeLessThan(500);
  });

  // Finding j05-012 : les colonnes date/timestamptz sont exposées en VARCHAR par le lac.
  test.fixme("j05-012 : une colonne timestamptz reste un TIMESTAMP dans SQL Lab", async () => {
    const r = await sql(analyst, `select typeof(d) from ${seed.ventes} limit 1`);
    expect(r.body.rows[0][0]).toMatch(/TIMESTAMP/);
  });

  // Finding j05-020 : une collection non encore répliquée dans le lac.
  test.fixme("j05-020 : agrégat sur une collection non répliquée signale l'attente", async () => {
    test.setTimeout(60_000);
    const creator = await apiFor("creator");
    const created = await creator.send("POST", "/v1/collections/empty", {
      title: `${seed.tag}-fresh-${Date.now().toString(36)}`,
      columns: [{ name: "v", sqlType: "integer" }],
    });
    expect(created.status).toBe(201);
    const id = created.body.id as string;
    const { psql } = await import("../j02/helpers");
    psql(`INSERT INTO ${id} (tenant_id, v) VALUES ('default', 1),('default', 2),('default', 3)`);
    await creator.send("PUT", `/v1/collections/${id}/sharing`, { public: true, groups: [] });
    const r = await aggregate(analyst, id, { agg: "count" });
    // 3 lignes existent en base : soit le lac les a déjà, soit la réponse doit le dire.
    const ok = r.body?.rows?.[0]?.value === 3 || r.status !== 200 || r.body?.pending === true;
    expect(ok).toBe(true);
  });
});
