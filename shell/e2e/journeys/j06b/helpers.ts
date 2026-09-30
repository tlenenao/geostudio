/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { loginOidc, type PersonaName } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import type { Api } from "../j03/api";
import { getSeed } from "../j03/seed";

export { getSeed };

export async function spaGoto(page: Page, path: string): Promise<void> {
  await page.evaluate((p) => {
    history.pushState({}, "", p);
    dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

export async function openAs(page: Page, persona: PersonaName): Promise<void> {
  await loginOidc(page, persona);
  await page.getByRole("navigation", { name: /domaines/i }).waitFor();
}

export function corePython(code: string): string {
  return execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-"], {
    input: code,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
}

export interface PNode {
  id: string;
  kind: "reader" | "transform" | "writer";
  op: string;
  params?: Record<string, unknown>;
  x?: number;
  y?: number;
}
export interface PEdge {
  id: string;
  from: string;
  to: string;
  role?: "primary" | "secondary";
}

export const reader = (collectionId: string, id = "r"): PNode => ({
  id,
  kind: "reader",
  op: "reader.collection",
  params: { collectionId },
});
export const exportWriter = (key: string, format = "csv", id = "w"): PNode => ({
  id,
  kind: "writer",
  op: "writer.export",
  params: { format, key },
});
export const edge = (from: string, to: string, id = `${from}-${to}`): PEdge => ({ id, from, to });

export async function createPipeline(
  api: Api,
  title: string,
  nodes: PNode[],
  edges: PEdge[],
  extra: Record<string, unknown> = {},
): Promise<{ status: number; body: any; itemId?: string }> {
  const r = await api.send("POST", "/v1/configs", {
    title,
    config: { version: 1, kind: "pipeline", pipeline: { nodes, edges, ...extra } },
  });
  return { ...r, itemId: r.body?.itemId };
}

export async function waitRun(
  api: Api,
  itemId: string,
  runId: string,
  timeoutMs = 90_000,
): Promise<any> {
  const t0 = Date.now();
  for (;;) {
    const r = await api.get(`/v1/pipelines/${itemId}/runs`);
    const run = (r.body as any[]).find((x) => x.id === runId);
    if (run && (run.status === "succeeded" || run.status === "failed" || run.status === "done"))
      return run;
    if (Date.now() - t0 > timeoutMs) return { status: "timeout", ...run };
    await new Promise((res) => setTimeout(res, 1000));
  }
}

// POST /run (et /trigger) répondent 500 (AppNotOpen, cf. j03-001/j06b-001) APRÈS avoir commité
// le run : on retrouve la ligne et on défère la tâche depuis le worker pour auditer la suite.
export async function runPipeline(
  api: Api,
  itemId: string,
  { rescue = true }: { rescue?: boolean } = {},
): Promise<{ status: number; runId?: string; body: any }> {
  const before = new Set(
    psql(`SELECT id FROM pipeline_runs WHERE pipeline_item_id='${itemId}'`).split("\n"),
  );
  const r = await api.send("POST", `/v1/pipelines/${itemId}/run`);
  return rescueRun(r, itemId, before, rescue);
}

export function rescueRun(
  r: { status: number; body: any },
  itemId: string,
  before: Set<string>,
  rescue = true,
): { status: number; runId?: string; body: any } {
  if (r.status === 202) return { ...r, runId: r.body.runId };
  if (r.status !== 500 || !rescue) return r;
  const ids = psql(`SELECT id FROM pipeline_runs WHERE pipeline_item_id='${itemId}'`)
    .split("\n")
    .filter((x) => x && !before.has(x));
  if (!ids.length) return r;
  deferRun(ids[0]);
  return { ...r, runId: ids[0] };
}

export function deferRun(runId: string): void {
  execFileSync(
    "docker",
    [
      "exec",
      "geostudio-worker-1",
      "python",
      "-c",
      "import sys\nfrom app.jobs import app\nfrom app.pipelines.jobs import run_pipeline_task\nwith app.open():\n run_pipeline_task.defer(run_id=sys.argv[1],tenant_id='default')",
      runId,
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
}

// Collection SANS géométrie (nogeom.csv) : reader.collection ne sait pas lire une colonne `geom`
// (j06b-002), seule une collection sans géométrie est exécutable de bout en bout.
export async function getPlainSeed(): Promise<{ collection: string; item: string }> {
  const { apiFor } = await import("../j03/api");
  const { stamp } = await import("../_fixtures/env");
  const creator = await apiFor("creator");
  const cache = join(tmpdir(), "aud-j06b-plain.json");
  if (existsSync(cache)) {
    const c = JSON.parse(readFileSync(cache, "utf8")) as { collection: string; item: string };
    const agg = await creator.send("POST", `/v1/collections/${c.collection}/aggregate`, {
      aggregates: [{ fn: "count", as: "n" }],
    });
    if (agg.status === 200 && agg.body?.rows?.[0]?.value === 6) return c;
  }
  const id = await createPlainCollection(creator, `${stamp("j06b")}-plain`, [
    ["a", 1],
    ["b", 5],
    ["c", 10],
    ["d", 20],
    ["e", 30],
    ["f", 40],
  ]);
  const seed = { collection: id, item: "" };
  writeFileSync(cache, JSON.stringify(seed));
  return seed;
}

const S3_PY =
  "import sys,boto3,os,json;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
  "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
  "b=os.environ['S3_EXPORTS_BUCKET']\n";

// Ce que fait le premier export « classique » (app.export.jobs : ensure_uploads_bucket) ; writer.export ne le fait pas.
export function ensureExportsBucket(): void {
  execFileSync(
    "docker",
    [
      "exec",
      "geostudio-core-1",
      "python",
      "-c",
      S3_PY + "try: c.create_bucket(Bucket=b)\nexcept Exception: pass",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
}

export function exportsBucketExists(): boolean {
  const out = execFileSync(
    "docker",
    [
      "exec",
      "geostudio-core-1",
      "python",
      "-c",
      S3_PY + "print('yes' if b in [x['Name'] for x in c.list_buckets()['Buckets']] else 'no')",
    ],
    { encoding: "utf8" },
  );
  return out.trim() === "yes";
}

export function s3Put(key: string, body: string): void {
  execFileSync(
    "docker",
    [
      "exec",
      "-i",
      "geostudio-core-1",
      "python",
      "-c",
      S3_PY + "c.put_object(Bucket=b,Key=sys.argv[1],Body=sys.stdin.buffer.read())",
      key,
    ],
    { input: body, stdio: ["pipe", "ignore", "pipe"] },
  );
}

export function s3Get(key: string): string | null {
  try {
    return execFileSync(
      "docker",
      [
        "exec",
        "geostudio-core-1",
        "python",
        "-c",
        S3_PY + "sys.stdout.write(c.get_object(Bucket=b,Key=sys.argv[1])['Body'].read().decode())",
        key,
      ],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    );
  } catch {
    return null;
  }
}

// Collection sans géométrie dédiée à un test (schéma modifiable sans gêner les autres).
export async function createPlainCollection(
  api: Api,
  title: string,
  rows: Array<[string, number]>,
): Promise<string> {
  const col = await api.send("POST", "/v1/collections/empty", {
    title,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "pop", sqlType: "integer" },
    ],
  });
  if (col.status !== 201) throw new Error(`collection: ${JSON.stringify(col)}`);
  const id = col.body.id as string;
  psql(
    `INSERT INTO "${id}" (tenant_id, nom, pop) VALUES ` +
      rows.map(([n, p]) => `('default','${n}',${p})`).join(","),
  );
  const t0 = Date.now();
  for (;;) {
    const agg = await api.send("POST", `/v1/collections/${id}/aggregate`, {
      aggregates: [{ fn: "count", as: "n" }],
    });
    if (agg.body?.rows?.[0]?.value === rows.length) return id;
    if (Date.now() - t0 > 60_000) throw new Error("CDC timeout");
    await new Promise((r) => setTimeout(r, 1500));
  }
}
