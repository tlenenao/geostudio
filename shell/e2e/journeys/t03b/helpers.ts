/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFile, execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, token, type Api } from "../j03/api";
import { psql } from "../j02/helpers";
import {
  createPipeline,
  edge,
  ensureExportsBucket,
  exportWriter,
  reader,
  runPipeline,
  waitRun,
  type PNode,
} from "../j06b/helpers";
import { getBigSeed, FR } from "../t03/helpers";

export {
  apiFor,
  token,
  psql,
  createPipeline,
  edge,
  ensureExportsBucket,
  exportWriter,
  reader,
  runPipeline,
  waitRun,
  getBigSeed,
  FR,
  stamp,
};
export type { Api, PNode };

export const dockerMem = (c: string): string =>
  execFileSync("docker", ["stats", "--no-stream", "--format", "{{.MemUsage}}", c], {
    encoding: "utf8",
  }).trim();

export interface Timed {
  status: number;
  ms: number;
  bytes: number;
  headers: Headers;
  text: () => string;
  buf: Buffer;
}

export async function timed(
  persona: "admin" | "creator" | "analyst" | "reader",
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<Timed> {
  const tok = await token(persona);
  const t0 = performance.now();
  const r = await fetch(`${CORE_URL}${path}`, {
    method: init.method ?? "GET",
    headers: {
      authorization: `Bearer ${tok}`,
      ...(init.body ? { "content-type": "application/json" } : {}),
    },
    body: init.body ? JSON.stringify(init.body) : undefined,
  });
  const buf = Buffer.from(await r.arrayBuffer());
  return {
    status: r.status,
    ms: Math.round(performance.now() - t0),
    bytes: buf.length,
    headers: r.headers,
    text: () => buf.toString("utf8"),
    buf,
  };
}

// Collection SANS géométrie de `n` lignes (nom/cat/val), créée via l'API du produit puis
// remplie par SQL dans sa seule table. On attend que le CDC ait rendu les `n` lignes
// visibles côté lakehouse (aggregate), condition de tout reader.collection.
export async function getPlainBig(n: number): Promise<{ id: string; cdcMs: number }> {
  const creator = await apiFor("creator");
  const cache = join(tmpdir(), `aud-t03b-plain-${n}.json`);
  if (existsSync(cache)) {
    const c = JSON.parse(readFileSync(cache, "utf8")) as { id: string; cdcMs: number };
    if ((await creator.get(`/v1/collections/${c.id}`)).status === 200) return c;
  }
  const r = await creator.send("POST", "/v1/collections/empty", {
    title: `${stamp("t03b")}-plain-${n}`,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "cat", sqlType: "text" },
      { name: "val", sqlType: "integer" },
    ],
  });
  if (r.status !== 201) throw new Error(`collection ${r.status} ${JSON.stringify(r.body)}`);
  const id = r.body.id as string;
  const table = r.body.tableName as string;
  psql(
    `INSERT INTO public."${table}" (tenant_id, nom, cat, val) ` +
      `SELECT 'default', 'pt-' || g, 'c' || (g % 8), (g % 1000) FROM generate_series(1, ${n}) g`,
  );
  const t0 = Date.now();
  for (;;) {
    const agg = await creator.send("POST", `/v1/collections/${id}/aggregate`, {
      aggregates: [{ fn: "count", as: "n" }],
    });
    if (agg.body?.rows?.[0]?.value === n) break;
    if (Date.now() - t0 > 240_000) throw new Error("CDC timeout");
    await new Promise((res) => setTimeout(res, 2000));
  }
  const out = { id, cdcMs: Date.now() - t0 };
  writeFileSync(cache, JSON.stringify(out));
  return out;
}

export async function runAndTime(
  api: Api,
  title: string,
  nodes: PNode[],
  edges: ReturnType<typeof edge>[],
  timeoutMs = 600_000,
): Promise<{ wallMs: number; run: any; itemId: string }> {
  const p = await createPipeline(api, title, nodes, edges);
  if (p.status !== 201) throw new Error(`pipeline ${p.status} ${JSON.stringify(p.body)}`);
  const t0 = Date.now();
  const run = await runPipeline(api, p.itemId!);
  if (!run.runId) throw new Error(`run ${run.status} ${JSON.stringify(run.body)}`);
  const fin = await waitRun(api, p.itemId!, run.runId, timeoutMs);
  return { wallMs: Date.now() - t0, run: fin, itemId: p.itemId! };
}

// Pic de mémoire d'un conteneur pendant `fn` (échantillonnage asynchrone en continu).
export async function withPeakMem<T>(
  container: string,
  fn: () => Promise<T>,
): Promise<{ value: T; peakMb: number; startMb: number }> {
  const toMb = (full: string) => {
    const m = full.split(" / ")[0];
    const v = parseFloat(m);
    return m.includes("GiB") ? v * 1024 : m.includes("KiB") ? v / 1024 : v;
  };
  const startMb = toMb(dockerMem(container));
  let peak = startMb;
  let stop = false;
  const sampler = (async () => {
    while (!stop) {
      const out = await new Promise<string>((res) =>
        execFile(
          "docker",
          ["stats", "--no-stream", "--format", "{{.MemUsage}}", container],
          { encoding: "utf8" },
          (_e, so) => res(String(so)),
        ),
      );
      if (out.trim()) peak = Math.max(peak, toMb(out.trim()));
    }
  })();
  try {
    const value = await fn();
    return { value, peakMb: Math.round(peak), startMb: Math.round(startMb) };
  } finally {
    stop = true;
    await sampler;
  }
}

// Nombre de lignes d'un objet du bucket des exports, compté dans le conteneur (execFileSync
// plafonne stdout à 1 Mo : s3Get() rend "" sur un gros objet). `key` est la clé du writer :
// le cœur la range sous `<tenant>/pipelines/` (P03.03).
export function s3Lines(key: string): number {
  const py =
    "import sys,boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
    "b=os.environ['S3_EXPORTS_BUCKET'];" +
    "print(sum(1 for _ in c.get_object(Bucket=b,Key=sys.argv[1])['Body'].iter_lines()))";
  return Number(
    execFileSync(
      "docker",
      ["exec", "geostudio-core-1", "python", "-c", py, `default/pipelines/${key}`],
      {
        encoding: "utf8",
      },
    ).trim(),
  );
}
