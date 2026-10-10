import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor } from "../j03/api";
import { psql } from "../j02/helpers";
import { bug, docker, go, newSession, serviceHealth, withServiceStopped } from "./helpers";

// Exception à la règle 6 (prompt t02) : docker stop/start des SEULS services `worker` et `martin`,
// avec confirmation `healthy` avant de rendre la main (cf. withServiceStopped).

test.describe.configure({ mode: "serial" });

async function putCsv(name: string, csv: string): Promise<string> {
  const key = `default/${Math.random().toString(16).slice(2)}${Date.now().toString(16)}-${name}`;
  const py =
    "import sys,boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
    "b=os.environ['S3_UPLOADS_BUCKET']\n" +
    "try: c.create_bucket(Bucket=b)\nexcept Exception: pass\n" +
    "c.put_object(Bucket=b,Key=sys.argv[1],Body=sys.stdin.buffer.read())";
  execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-c", py, key], {
    input: Buffer.from(csv),
    stdio: ["pipe", "ignore", "pipe"],
  });
  return key;
}

test.afterAll(() => {
  // Filet : jamais de service laissé arrêté en fin de fichier.
  for (const svc of ["worker", "martin"] as const) {
    if (serviceHealth(svc).startsWith("exited")) docker("start", `geostudio-${svc}-1`);
  }
});

test.describe("t02 : worker arrêté", () => {
  test("le cœur et le shell restent utilisables, un job en file attend puis se termine au redémarrage", async ({
    browser,
  }) => {
    test.setTimeout(300_000);
    const creator = await apiFor("creator");
    const s = await newSession(browser, "creator");
    const tag = stamp("t02");
    let jobId = "";
    const during = await withServiceStopped("worker", async () => {
      // Le cœur défère lui-même le job (P01) : on crée l'import worker arrêté, sinon le worker le
      // consomme avant son arrêt.
      const key = await putCsv(`${tag}.csv`, "nom,latitude,longitude\na,46.2,2.5\nb,46.3,2.6\n");
      const create = await creator.send("POST", "/v1/uploads", {
        key,
        filename: `${tag}.csv`,
        collectionTitle: `${tag}-worker`,
      });
      jobId =
        create.body?.jobId ??
        psql(`SELECT id FROM ingestion_jobs WHERE source_key='${key}'`).trim();
      expect(jobId).toBeTruthy();
      await go(s.page, "/", 2000);
      const catalog = await creator.get("/v1/items");
      const health = await fetch(`${CORE_URL}/health`);
      await new Promise((r) => setTimeout(r, 12_000));
      const job = await creator.get(`/v1/uploads/${jobId}`);
      const queued = psql(
        `SELECT status FROM procrastinate_jobs WHERE task_name LIKE '%run_ingestion_task' AND args->>'job_id'='${jobId}'`,
      ).trim();
      const banner = await s.page.getByText(/Connexion au serveur perdue/).count();
      return {
        catalogStatus: catalog.status,
        health: health.status,
        job: job.body.status,
        queued,
        banner,
      };
    });
    expect(during.catalogStatus).toBe(200);
    expect(during.health).toBe(200);
    expect(during.job).toBe("pending");
    expect(during.queued).toBe("todo");
    expect(during.banner).toBe(0);
    expect(serviceHealth("worker")).toBe("running/healthy");

    // Après redémarrage, le job en file est consommé sans intervention.
    let final = "";
    for (let i = 0; i < 60 && final !== "done" && final !== "error"; i++) {
      final = (await creator.get(`/v1/uploads/${jobId}`)).body.status;
      if (final !== "done" && final !== "error") await new Promise((r) => setTimeout(r, 1000));
    }
    expect(final).toBe("done");
    await s.ctx.close();
  });

  // Finding t02-013 : rien n'expose l'arrêt du worker (health statique, /instance muet, aucune bannière).
  bug(
    "t02-013 : l'arrêt du worker est observable par un exploitant (health ou instance)",
    async () => {
      const admin = await apiFor("admin");
      const before = await (await fetch(`${CORE_URL}/health`)).json();
      const res = await withServiceStopped("worker", async () => {
        await new Promise((r) => setTimeout(r, 5000));
        const health = await (await fetch(`${CORE_URL}/health`)).json();
        const inst = await admin.get("/v1/instance");
        return { health, inst: inst.body };
      });
      const mentionsWorker = JSON.stringify([res.health, res.inst]).match(
        /worker|queue|file|jobs/i,
      );
      expect(before).toEqual({ status: "ok" });
      expect(res.health).not.toEqual({ status: "ok" }); // ou exposer l'état de la file
      expect(mentionsWorker).not.toBeNull();
    },
  );
});

test.describe("t02 : martin arrêté", () => {
  test("les tuiles vectorielles du cœur et le catalogue ne dépendent pas de martin", async ({
    browser,
  }) => {
    test.setTimeout(240_000);
    const creator = await apiFor("creator");
    const cols = await creator.get("/v1/collections");
    const id = cols.body.collections[0].id as string;
    const s = await newSession(browser, "creator");
    const res = await withServiceStopped("martin", async () => {
      await go(s.page, "/", 2500);
      const tile = await fetch(`${CORE_URL}/v1/collections/${id}/tiles/0/0/0.mvt`, {
        headers: { authorization: `Bearer ${await (await import("../j03/api")).token("creator")}` },
      });
      const health = await fetch(`${CORE_URL}/health`);
      const banner = await s.page.getByText(/Connexion au serveur perdue/).count();
      const listed = await s.page.locator("body").innerText();
      // Le healthcheck Docker finit par constater l'arrêt (conteneur « exited »).
      const state = serviceHealth("martin");
      return {
        tile: tile.status,
        health: health.status,
        banner,
        listedOk: listed.length > 100,
        state,
      };
    });
    expect(res.tile).toBe(200);
    expect(res.health).toBe(200);
    expect(res.banner).toBe(0);
    expect(res.listedOk).toBe(true);
    expect(res.state).toMatch(/^exited/);
    expect(serviceHealth("martin")).toBe("running/healthy");
    await s.ctx.close();
  });
});
