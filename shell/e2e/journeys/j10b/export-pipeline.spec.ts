/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { stamp } from "../_fixtures/env";
import {
  apiFor,
  appConfig,
  createApp,
  makeCollection,
  psql,
  readBundleFile,
  runExport,
  tableApp,
  type Api,
} from "./helpers";

test.setTimeout(240_000);
const tag = stamp("j10b");
let creator: Api;
let reader: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
  reader = await apiFor("reader");
});

function grep(dir: string, needle: string): string {
  return spawnSync("grep", ["-rl", needle, dir], { encoding: "utf8" }).stdout.trim();
}

test.describe("j10b export d'apps : pipeline API -> job -> zip", () => {
  // FINDING j10b-001 : POST /v1/app-exports répond 500 (AppNotOpen sur .defer())
  // après avoir committé le job : il reste « pending » pour toujours.
  test("j10b-001 : POST /v1/app-exports met le job en file (202)", async () => {
    const id = await createApp(creator, `${tag}-q`, appConfig());
    const r = await creator.send("POST", "/v1/app-exports", { itemId: id, mode: "static" });
    expect(r.status).toBe(202);
    const job = await creator.get(`/v1/app-exports/jobs/${r.body.jobId}`);
    await new Promise((res) => setTimeout(res, 8000));
    const again = await creator.get(`/v1/app-exports/jobs/${r.body.jobId}`);
    expect(["done", "running"]).toContain(again.body.status ?? job.body.status);
  });

  // FINDING j10b-002 : ensure_uploads_bucket() appelle put_bucket_cors, que
  // MinIO ne supporte pas (NotImplemented) : même avec la file rejouée à la
  // main, chaque job d'export d'app finit en erreur (racine de j03-002).
  test("j10b-002 : le worker termine un export sans échouer sur PutBucketCors", async () => {
    const id = await createApp(creator, `${tag}-cors`, appConfig());
    const run = await runExport(creator, id, "static", false);
    expect(run.result?.status).toBe("done");
  });

  test("static : zip = runtime + config gelée, sans geostudio-connection.json", async () => {
    const col = await makeCollection(creator, `${tag}-s1`, { pub: true, rows: 3 });
    const id = await createApp(creator, `${tag}-st`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "static");
    expect(run.result?.status).toBe("done");
    expect(run.files).toContain("index.html");
    expect(run.files).toContain("geostudio-app-config.json");
    expect(run.files.some((f) => f.startsWith("assets/"))).toBe(true);
    expect(run.files).not.toContain("geostudio-connection.json");
    const cfg = readBundleFile(run, "geostudio-app-config.json");
    const d = cfg.dataSources[0];
    expect(d.type).toBe("static");
    expect(d.query.records).toHaveLength(3);
  });

  test("connected : embarque l'URL du cœur et garde la source features d'origine", async () => {
    const col = await makeCollection(creator, `${tag}-c1`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-co`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "connected");
    expect(run.result?.status).toBe("done");
    expect(readBundleFile(run, "geostudio-connection.json")).toEqual({
      coreUrl: "http://localhost:8200",
    });
    const cfg = readBundleFile(run, "geostudio-app-config.json");
    expect(cfg.dataSources[0]).toMatchObject({ type: "features", layer: col.id });
  });

  test("standalone : data/ + manifeste + instantané GeoParquet + docker-compose", async () => {
    const col = await makeCollection(creator, `${tag}-a1`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-sa`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "standalone");
    expect(run.result?.status).toBe("done");
    expect(run.files).toEqual(
      expect.arrayContaining([
        "data/geostudio-app-config.json",
        "data/manifest.json",
        "docker-compose.yml",
        "README.md",
      ]),
    );
    expect(run.files.some((f) => f.endsWith("data.parquet"))).toBe(true);
    const manifest = readBundleFile(run, "data/manifest.json");
    expect(manifest.collections.map((c: any) => c.id)).toContain(col.id);
  });

  test("garde : collection non publique refusée dans les trois modes", async () => {
    const col = await makeCollection(creator, `${tag}-p1`, { pub: false });
    const id = await createApp(creator, `${tag}-priv`, tableApp(col.id, ["nom"]));
    for (const mode of ["static", "connected", "standalone"]) {
      const run = await runExport(creator, id, mode);
      expect(run.result?.status, mode).toBe("error");
      expect(run.result?.error, mode).toContain("n'est pas partagée publiquement");
    }
  });

  // Confirme j10-009 (probable en 1re passe) : variableInput est un widget
  // intégré (SP-52) mais absent de l'allowlist du garde.
  test("j10b-003 : widget intégré variableInput accepté en export statique (confirme j10-009)", async () => {
    const id = await createApp(
      creator,
      `${tag}-vi`,
      appConfig([{ id: "v", widget: "variableInput", x: 0, y: 0, w: 4, h: 2, props: {} }]),
    );
    const run = await runExport(creator, id, "static");
    expect(run.result?.status).toBe("done");
  });

  // Confirme j10-008 : la garde ne parcourt pas les widgets imbriqués.
  bug(
    "j10b-004 : widget tiers imbriqué dans tabs refusé en statique (confirme j10-008)",
    async () => {
      const id = await createApp(
        creator,
        `${tag}-nest`,
        appConfig([
          {
            id: "tabs",
            widget: "tabs",
            x: 0,
            y: 0,
            w: 12,
            h: 6,
            props: {
              tabs: [
                {
                  id: "t1",
                  label: "A",
                  items: [{ id: "g", widget: "acme-gauge", x: 0, y: 0, w: 4, h: 2, props: {} }],
                },
              ],
            },
          },
        ]),
      );
      const run = await runExport(creator, id, "static");
      expect(run.result?.status).toBe("error");
    },
  );

  // Confirme j10-010 : troncature silencieuse à 50 000 enregistrements.
  bug(
    "j10b-005 : le gel signale une collection de plus de 50 000 lignes (confirme j10-010)",
    async () => {
      const col = await makeCollection(creator, `${tag}-big`, { pub: true, rows: 50_001 });
      const id = await createApp(creator, `${tag}-bigapp`, tableApp(col.id, ["nom"]));
      const run = await runExport(creator, id, "static");
      const n = readBundleFile(run, "geostudio-app-config.json").dataSources[0].query.records
        .length;
      expect(n).toBe(50_001);
    },
  );

  // Confirme j10-007 de bout en bout (job réel + zip), modes static et standalone.
  test("j10b-006 : les champs sensibles ne sont pas écrits dans les bundles (confirme j10-007)", async () => {
    const col = await makeCollection(creator, `${tag}-sens`, { pub: true, sensitive: true });
    const anon = await fetch(`http://localhost:8200/v1/collections/${col.id}/items`);
    expect(JSON.stringify(await anon.json())).not.toContain("TOPSECRET-42");
    const id = await createApp(creator, `${tag}-sensapp`, tableApp(col.id));
    for (const mode of ["static", "standalone"]) {
      const run = await runExport(creator, id, mode);
      expect(run.result?.status, mode).toBe("done");
      expect(grep(run.dir!, "TOPSECRET-42"), mode).toBe("");
    }
  });

  test("droits : un lecteur ne peut exporter ni lire le job d'un item privé (404)", async () => {
    const id = await createApp(creator, `${tag}-own`, appConfig());
    expect(
      (await creator.send("POST", "/v1/app-exports", { itemId: id, mode: "zip" })).status,
    ).toBe(422);
    expect(
      (await creator.send("POST", "/v1/app-exports", { itemId: "nope", mode: "static" })).status,
    ).toBe(404);
    expect((await creator.get("/v1/app-exports/jobs/nope")).status).toBe(404);
    expect(
      (await reader.send("POST", "/v1/app-exports", { itemId: id, mode: "static" })).status,
    ).toBe(404);
    const jobId = psql(`SELECT id FROM app_export_jobs WHERE item_id='${id}' LIMIT 1`).trim();
    expect(jobId).toBe("");
    const run = await runExport(creator, id, "static");
    expect((await reader.get(`/v1/app-exports/jobs/${run.jobId}`)).status).toBe(404);
  });

  // FINDING j10b-007 : aucun contrôle du kind : n'importe quel item lisible
  // (site, alerte, pipeline…) est « exporté » en bundle d'app.
  bug("j10b-007 : l'export refuse un item qui n'est pas une app", async () => {
    const r = await creator.send("POST", "/v1/configs", {
      title: `${tag}-site`,
      config: { version: 1, kind: "site", layout: { type: "grid", items: [] } },
    });
    expect(r.status).toBe(201);
    const run = await runExport(creator, r.body.itemId, "static");
    expect(run.result?.status).toBe("error");
  });
});
