/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor, download, getSeed, psql, type Seed } from "./helpers";

let seed: Seed;
let bigCollection: string;
let bigTable: string;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
  const creator = await apiFor("creator");
  const c = await creator.send("POST", "/v1/collections/empty", {
    title: `${stamp("j05b")}-big`,
    columns: [
      { name: "n", sqlType: "integer" },
      { name: "txt", sqlType: "text" },
    ],
    geometryType: "Point",
    srid: 4326,
  });
  if (c.status !== 201) throw new Error(`big ${c.status} ${JSON.stringify(c.body)}`);
  bigCollection = c.body.id;
  bigTable = c.body.tableName;
  psql(
    `INSERT INTO public.${bigTable} (tenant_id, n, txt, geom) SELECT 'default', g, 'ligne ' || g, ST_SetSRID(ST_MakePoint(1 + (g % 100) / 100.0, 45 + (g / 100) / 1000.0), 4326) FROM generate_series(1,100001) g`,
  );
});

test.describe("j05b exports — plafond, GPKG, tâche /v1/export (flags allumés)", () => {
  // REV-283e : au-delà de CORE_EXPORT_SYNC_MAX (100 000) l'export devient asynchrone (202 + jobId) ;
  // le 413 n'intervient plus qu'au-delà de CORE_EXPORT_JOB_MAX (500 000).
  test("GET export/items : 100 001 entités → 202 asynchrone ; un filtre ramène sous le plafond synchrone", async () => {
    test.setTimeout(240_000);
    const creator = await apiFor("creator");
    const path = `/v1/collections/${bigCollection}/export/items`;
    const over = await creator.send("GET", `${path}?format=csv`);
    expect(over.status).toBe(202);
    expect(over.body.jobId).toBeTruthy();
    const exact = await download("creator", "GET", `${path}?format=csv&n__lte=1000`);
    expect(exact.status).toBe(200);
    expect(exact.buf.toString().split("\n").filter(Boolean)).toHaveLength(1001); // en-tête + 1 000
  });

  test("GPKG : fichier SQLite valide, table d'entités, nombre de lignes et géométries", async () => {
    test.setTimeout(120_000);
    const r = await download(
      "creator",
      "GET",
      `/v1/collections/${seed.eventsCollection}/export/items?format=gpkg`,
    );
    expect(r.status).toBe(200);
    const dir = mkdtempSync(join(tmpdir(), "aud-j05b-"));
    const file = join(dir, "out.gpkg");
    writeFileSync(file, r.buf);
    const py = `
import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1])
out={}
out['appid']=c.execute('pragma application_id').fetchone()[0]
out['contents']=c.execute('select table_name,data_type,srs_id from gpkg_contents').fetchall()
out['geomcols']=c.execute('select table_name,column_name,geometry_type_name,srs_id from gpkg_geometry_columns').fetchall()
t=out['contents'][0][0]
out['n']=c.execute(f'select count(*) from "{t}"').fetchone()[0]
cols=[r[1] for r in c.execute(f'pragma table_info("{t}")')]
out['cols']=cols
g=[r[1] for r in c.execute(f'pragma table_info("{t}")') if r[1] in ('geom','geometry')]
out['nullgeom']=c.execute(f'select count(*) from "{t}" where {g[0]} is null').fetchone()[0] if g else -1
out['hdr']=c.execute(f'select hex(substr({g[0]},1,4)) from "{t}" limit 1').fetchone()[0] if g else ''
print(json.dumps(out))
`;
    const out = JSON.parse(execFileSync("python3", ["-c", py, file], { encoding: "utf8" }));
    expect(out.appid).toBe(0x47504b47); // "GPKG"
    expect(out.n).toBe(60);
    expect(["POINT", "GEOMETRY"]).toContain(out.geomcols[0][2]);
    expect(out.geomcols[0][3]).toBe(4326);
    expect(out.nullgeom).toBe(0);
    expect(out.hdr.startsWith("4750")).toBe(true); // magic "GP"
  });

  test("GeoJSON : FeatureCollection, 60 entités, propriétés typées, coordonnées [lon, lat]", async () => {
    const r = await download(
      "creator",
      "GET",
      `/v1/collections/${seed.eventsCollection}/export/items?format=geojson`,
    );
    expect(r.status).toBe(200);
    const fc = JSON.parse(r.buf.toString());
    expect(fc.type).toBe("FeatureCollection");
    expect(fc.features).toHaveLength(60);
    const f = fc.features.find((x: any) => x.properties.nom === "E10");
    expect(f.properties.montant).toBe(100);
    expect(f.geometry.type).toBe("Point");
    expect(f.geometry.coordinates[0]).toBeCloseTo(2, 5);
    expect(f.geometry.coordinates[1]).toBeCloseTo(46.1, 5);
  });

  test("POST /v1/export : format hors png/pdf → 422, item inconnu → 404, item privé d'autrui → 404", async () => {
    const creator = await apiFor("creator");
    const reader = await apiFor("reader");
    const bad = await creator.send("POST", "/v1/export", {
      itemId: seed.eventsItem,
      format: "csv",
    });
    expect(bad.status).toBe(422);
    const unknown = await creator.send("POST", "/v1/export", { itemId: "nope", format: "png" });
    expect(unknown.status).toBe(404);
    const priv = await creator.send("POST", "/v1/configs", {
      title: `${stamp("j05b")}-privee`,
      config: {
        version: 1,
        kind: "app",
        theme: {},
        dataSources: [],
        messages: [],
        layout: { type: "grid", breakpoints: {}, items: [] },
      },
    });
    expect(priv.status).toBe(201);
    const denied = await reader.send("POST", "/v1/export", {
      itemId: priv.body.itemId,
      format: "png",
    });
    expect(denied.status).toBe(404);
    const audit = psql(
      `SELECT count(*) FROM export_jobs WHERE item_id='${priv.body.itemId}'`,
    ).trim();
    expect(audit).toBe("0");
  });

  // Finding j05b-005 : AppNotOpen (comme j03-001) sur POST /v1/export : la ligne export_jobs est
  // commitée « pending » puis le différé échoue en 500 ; le job ne s'exécutera jamais.
  test("j05b-005 : POST /v1/export valide répond 202 et le job quitte l'état pending", async () => {
    test.setTimeout(60_000);
    const creator = await apiFor("creator");
    const r = await creator.send("POST", "/v1/export", { itemId: seed.eventsItem, format: "png" });
    expect(r.status).toBe(202);
    await new Promise((res) => setTimeout(res, 8000));
    const job = await creator.get(`/v1/export/jobs/${r.body.jobId}`);
    expect(job.body.status).not.toBe("pending");
  });

  // Finding j05b-006 : le job déféré à la main s'exécute mais échoue après 30 s avec une trace
  // Playwright brute (le shell embarque VITE_CORE_URL=http://localhost:8200, injoignable depuis
  // export-worker, contrainte documentée dans .env.example mais sans détection ni message).
  bug(
    "j05b-006 : un export qui ne peut pas joindre le cœur échoue vite avec un message exploitable",
    async () => {
      test.setTimeout(150_000);
      const creator = await apiFor("creator");
      const before = new Set(psql("SELECT id FROM export_jobs").split("\n"));
      await creator.send("POST", "/v1/export", { itemId: seed.eventsItem, format: "png" });
      const id = psql("SELECT id FROM export_jobs ORDER BY created_at DESC LIMIT 1").trim();
      expect(before.has(id)).toBe(false);
      execFileSync(
        "docker",
        [
          "exec",
          "geostudio-export-worker-1",
          "python",
          "-c",
          "import sys\nfrom app.jobs import app\nfrom app.export.jobs import render_export_task\nwith app.open():\n render_export_task.defer(job_id=sys.argv[1],tenant_id='default')",
          id,
        ],
        { stdio: ["ignore", "ignore", "pipe"] },
      );
      let job: any;
      for (let k = 0; k < 40; k++) {
        await new Promise((res) => setTimeout(res, 3000));
        job = (await creator.get(`/v1/export/jobs/${id}`)).body;
        if (job.status === "done" || job.status === "error") break;
      }
      expect(job.status).toBe("done");
      expect(job.error ?? "").not.toMatch(/wait_for_selector|Call log/);
    },
  );

  test("GET /v1/export/jobs/{id} : invisible pour un lecteur sans accès à l'item, 404 sur id inconnu", async () => {
    const creator = await apiFor("creator");
    const reader = await apiFor("reader");
    const started = await creator.send("POST", "/v1/export", {
      itemId: seed.eventsItem,
      format: "png",
    });
    expect(started.status).toBe(202);
    const id = started.body.jobId;
    expect((await creator.get(`/v1/export/jobs/${id}`)).status).toBe(200);
    expect((await reader.get(`/v1/export/jobs/${id}`)).status).toBe(404);
    expect((await creator.get(`/v1/export/jobs/inconnu`)).status).toBe(404);
  });
});
