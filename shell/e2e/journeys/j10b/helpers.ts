/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { createReadStream, existsSync, mkdtempSync, readFileSync, statSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { apiFor, psql, type Api } from "../j10/seed";

export { apiFor, psql };
export type { Api };

const W = "geostudio-worker-1";
const MIME: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
};

function sh(cmd: string, args: string[]): string {
  return execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

export function appConfig(items: any[] = [], extra: any = {}) {
  return { version: 1, kind: "app", layout: { type: "grid", items }, ...extra };
}

export async function createApp(api: Api, title: string, config: any): Promise<string> {
  const r = await api.send("POST", "/v1/configs", { title, config });
  if (r.status !== 201) throw new Error(`app ${r.status} ${JSON.stringify(r.body)}`);
  return r.body.itemId as string;
}

export interface ExportRun {
  post: { status: number; body: any };
  jobId: string | null;
  result: { status: string; error: string | null; key: string | null } | null;
  dir: string | null;
  files: string[];
}

let installed = false;
function installRunner() {
  if (installed) return;
  sh("docker", [
    "cp",
    join(process.cwd(), "e2e/journeys/j10b/run_export.py"),
    `${W}:/tmp/run_export.py`,
  ]);
  installed = true;
}

// POST /v1/app-exports (500 AppNotOpen attendu : le job est créé puis jamais
// différé), puis rejoue la tâche dans le worker (patchCors=true : contourne
// put_bucket_cors, NotImplemented sur MinIO, j10b-002).
export async function runExport(
  api: Api,
  itemId: string,
  mode: string,
  patchCors = true,
): Promise<ExportRun> {
  installRunner();
  const post = await api.send("POST", "/v1/app-exports", { itemId, mode });
  const jobId =
    psql(
      `SELECT id FROM app_export_jobs WHERE item_id='${itemId}' AND mode='${mode}' ORDER BY created_at DESC LIMIT 1`,
    ).trim() || null;
  if (!jobId) return { post, jobId, result: null, dir: null, files: [] };
  const out = sh("docker", [
    "exec",
    "-w",
    "/app",
    "-e",
    "PYTHONPATH=/app",
    "-e",
    `PATCH_CORS=${patchCors ? "1" : "0"}`,
    W,
    "python",
    "/tmp/run_export.py",
    jobId,
  ]);
  const line = out.split("\n").find((l) => l.startsWith("RESULT="));
  const result = line ? JSON.parse(line.slice(7)) : null;
  let dir: string | null = null;
  let files: string[] = [];
  if (result?.key) {
    dir = mkdtempSync(join(tmpdir(), "j10b-"));
    sh("docker", ["cp", `${W}:/tmp/${jobId}.zip`, `${dir}/b.zip`]);
    sh("python3", ["-m", "zipfile", "-e", `${dir}/b.zip`, `${dir}/x`]);
    dir = `${dir}/x`;
    files = sh("python3", ["-m", "zipfile", "-l", `${dir}/../b.zip`])
      .split("\n")
      .slice(1)
      .map((l) => l.trim().split(/\s+/)[0])
      .filter(Boolean);
  }
  return { post, jobId, result, dir, files };
}

export function readBundleFile(run: ExportRun, name: string): any {
  const p = join(run.dir!, name);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : undefined;
}

export function serveDir(dir: string, port: number): Promise<Server> {
  return new Promise((resolve) => {
    const srv = createServer((req, res) => {
      const u = new URL(req.url ?? "/", "http://x").pathname;
      let f = join(dir, u === "/" ? "index.html" : u);
      if (!existsSync(f) || statSync(f).isDirectory()) f = join(dir, "index.html");
      res.setHeader("content-type", MIME[extname(f)] ?? "application/octet-stream");
      createReadStream(f).pipe(res);
    });
    srv.listen(port, "127.0.0.1", () => resolve(srv));
  });
}

export interface ColSeed {
  id: string;
  tableName: string;
}

// Collection à 1 point + champ sensible, rendue publique ou non (créée vide
// puis remplie en SQL : l'import est cassé, j03-002).
export async function makeCollection(
  api: Api,
  title: string,
  opts: { pub?: boolean; sensitive?: boolean; rows?: number } = {},
): Promise<ColSeed> {
  const c = await api.send("POST", "/v1/collections/empty", {
    title,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "secret", sqlType: "text" },
    ],
    geometryType: "Point",
    srid: 4326,
  });
  if (c.status !== 201) throw new Error(`col ${c.status} ${JSON.stringify(c.body)}`);
  const rows = opts.rows ?? 1;
  psql(
    `INSERT INTO public.${c.body.tableName} (tenant_id, nom, secret, geom) ` +
      `SELECT 'default','pub-'||g,'TOPSECRET-42',ST_SetSRID(ST_MakePoint(1,45),4326) FROM generate_series(1,${rows}) g`,
  );
  psql(`UPDATE collections SET feature_count=${rows} WHERE id='${c.body.id}'`);
  if (opts.sensitive) {
    const p = await api.send("PATCH", `/v1/collections/${c.body.id}`, {
      sensitiveFields: ["secret"],
    });
    if (p.status !== 200) throw new Error(`sensitive ${p.status}`);
  }
  if (opts.pub) {
    const s = await api.send("PUT", `/v1/collections/${c.body.id}/sharing`, {
      public: true,
      groups: [],
    });
    if (s.status !== 200) throw new Error(`share ${s.status}`);
  }
  return { id: c.body.id, tableName: c.body.tableName };
}

export function tableApp(colId: string, columns = ["nom", "secret"], extra: any = {}) {
  return appConfig(
    [
      {
        id: "tb",
        widget: "table",
        x: 0,
        y: 0,
        w: 12,
        h: 6,
        props: { dataSourceId: "d", columns },
      },
    ],
    {
      dataSources: [{ id: "d", type: "features", service: "core", layer: colId, query: {} }],
      ...extra,
    },
  );
}
