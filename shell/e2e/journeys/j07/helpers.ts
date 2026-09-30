/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { stamp } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import { apiFor, fixture, ingest, type Api } from "../j03/api";

export { apiFor, psql };
export type { Api };

export interface PublicSeed {
  tag: string;
  collectionId: string;
  table: string;
}

const CACHE = join(tmpdir(), "aud-j07-seed.json");

// Collection de 12 points (nom/cat/val/pop), rendue publique, avec "pop" déclaré sensible
// et des métadonnées ouvertes complètes. Importée via le rattrapage de j03 (POST /uploads → 500).
export async function getPublicSeed(): Promise<PublicSeed> {
  const creator = await apiFor("creator");
  if (existsSync(CACHE)) {
    const cached = JSON.parse(readFileSync(CACHE, "utf8")) as PublicSeed;
    if ((await creator.get(`/v1/collections/${cached.collectionId}`)).status === 200) {
      return cached;
    }
  }
  const tag = stamp("j07");
  const res = await ingest(creator, "points.geojson", fixture("points.geojson"), {
    collectionTitle: `${tag}-points`,
  });
  if (res.job?.status !== "done") throw new Error(`seed ingest: ${JSON.stringify(res)}`);
  const collectionId = res.job.collectionId as string;
  const patch = await creator.send("PATCH", `/v1/collections/${collectionId}`, {
    isPublic: true,
    sensitiveFields: ["pop"],
    license: "cc-by-4.0",
    licenseUri: "https://example.org/licence",
    producer: "Producteur j07",
    contact: "steward@example.org",
    updateFrequency: "daily",
    lineage: "Import de test j07",
    language: "fr",
    version: "1.0",
    temporalStart: "2020-01-01",
    temporalEnd: "2020-12-31",
  });
  if (patch.status !== 200) throw new Error(`seed patch: ${JSON.stringify(patch)}`);
  const seed: PublicSeed = { tag, collectionId, table: patch.body.tableName };
  writeFileSync(CACHE, JSON.stringify(seed));
  return seed;
}

// Exécute run_harvest_task dans le conteneur worker (la file `harvest` n'y est consommée par
// personne, cf. j07-001) : équivalent fonctionnel de ce que ferait un worker correctement câblé.
export function runHarvestInWorker(sourceId: string): void {
  execFileSync(
    "docker",
    [
      "exec",
      "geostudio-worker-1",
      "python",
      "-c",
      "import sys\nfrom app.harvest.jobs import run_harvest_task\nrun_harvest_task.func(source_id=sys.argv[1],tenant_id='default')",
      sourceId,
    ],
    { stdio: ["ignore", "ignore", "ignore"] },
  );
}

export async function createSource(api: Api, body: Record<string, unknown>): Promise<any> {
  const r = await api.send("POST", "/v1/harvest/sources", body);
  if (r.status !== 201) throw new Error(`create source: ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}

// Défère run_harvest_task depuis le conteneur worker (comme le ferait la route POST …/run si elle
// fonctionnait) et rend l'état procrastinate du job après `waitMs`.
export async function deferHarvestAndPoll(sourceId: string, waitMs = 20_000): Promise<string> {
  execFileSync(
    "docker",
    [
      "exec",
      "geostudio-worker-1",
      "python",
      "-c",
      "import sys\nfrom app.jobs import app\nfrom app.harvest.jobs import run_harvest_task\nwith app.open():\n run_harvest_task.defer(source_id=sys.argv[1],tenant_id='default')",
      sourceId,
    ],
    { stdio: ["ignore", "ignore", "ignore"] },
  );
  const sql = `SELECT status FROM procrastinate_jobs WHERE task_name='app.harvest.jobs.run_harvest_task' AND args->>'source_id'='${sourceId}'`;
  const t0 = Date.now();
  let status = psql(sql).trim();
  while (status === "todo" && Date.now() - t0 < waitMs) {
    await new Promise((r) => setTimeout(r, 1000));
    status = psql(sql).trim();
  }
  return status;
}
