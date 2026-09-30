/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { psql } from "../j02/helpers";
import { CORE_URL, PERSONAS, type PersonaName } from "../_fixtures/env";

const KC = process.env.KC_URL ?? "http://localhost:8180";
export const FX = join(process.cwd(), "e2e/journeys/j03/fixtures");

export async function token(persona: PersonaName): Promise<string> {
  const { username, password } = PERSONAS[persona];
  const r = await fetch(`${KC}/realms/geostudio/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "password",
      client_id: "geostudio-shell",
      username,
      password,
    }),
  });
  if (!r.ok) throw new Error(`token ${persona}: ${r.status}`);
  return ((await r.json()) as { access_token: string }).access_token;
}

export interface Api {
  get(path: string): Promise<{ status: number; body: any }>;
  send(method: string, path: string, body?: unknown): Promise<{ status: number; body: any }>;
}

export async function apiFor(persona: PersonaName): Promise<Api> {
  const tok = await token(persona);
  const send = async (method: string, path: string, body?: unknown) => {
    const doFetch = () =>
      fetch(`${CORE_URL}${path}`, {
        method,
        headers: {
          authorization: `Bearer ${tok}`,
          ...(body !== undefined ? { "content-type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    // undici réutilise une connexion que uvicorn a déjà fermée (keep-alive) : un seul rejeu.
    const r = await doFetch().catch(() => doFetch());
    const text = await r.text();
    let parsed: any = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* corps non JSON */
    }
    return { status: r.status, body: parsed };
  };
  return { get: (p) => send("GET", p), send };
}

// Le présigné d'upload répond 500 sur cette stack (cf. j03-001) : on dépose
// l'objet directement dans le bucket via le conteneur core (boto3), à la clé
// que /uploads/presign aurait produite (`<tenant>/<uuid>-<nom>`).
export function putUpload(name: string, data: Buffer): string {
  const key = `default/${Math.random().toString(16).slice(2)}${Date.now().toString(16)}-${name}`;
  const py =
    "import sys,boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
    "b=os.environ['S3_UPLOADS_BUCKET']\n" +
    "try: c.create_bucket(Bucket=b)\nexcept Exception: pass\n" +
    "c.put_object(Bucket=b,Key=sys.argv[1],Body=sys.stdin.buffer.read())";
  execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-c", py, key], {
    input: data,
    stdio: ["pipe", "ignore", "pipe"],
  });
  return key;
}

export function fixture(name: string): Buffer {
  return readFileSync(join(FX, name));
}

export async function ingest(
  api: Api,
  file: string,
  data: Buffer,
  extra: Record<string, unknown> = {},
  timeoutMs = 90_000,
  rescue = true,
): Promise<{ create: { status: number; body: any }; job?: any }> {
  const key = putUpload(file, data);
  const create = await api.send("POST", "/v1/uploads", {
    key,
    filename: file,
    collectionTitle: `aud-j03 ${file}`,
    ...extra,
  });
  let jobId: string | undefined = create.body?.jobId;
  if (create.status !== 201) {
    // Défaut j03-001 : POST /uploads répond 500 (AppNotOpen) APRÈS avoir commité
    // le job. `rescue` (défaut) le rattrape : on le défère depuis le worker pour
    // pouvoir auditer la suite du parcours ; `rescue: false` rend le 500 brut.
    if (!rescue || create.status !== 500) return { create };
    jobId = psql(`SELECT id FROM ingestion_jobs WHERE source_key='${key}'`).trim();
    if (!jobId) return { create };
    execFileSync(
      "docker",
      [
        "exec",
        "geostudio-worker-1",
        "python",
        "-c",
        "import sys\nfrom app.jobs import app\nfrom app.ingestion.tasks import run_ingestion_task\nwith app.open():\n run_ingestion_task.defer(job_id=sys.argv[1],tenant_id='default')",
        jobId,
      ],
      { stdio: ["ignore", "ignore", "pipe"] },
    );
  }
  const t0 = Date.now();
  for (;;) {
    const j = await api.get(`/v1/uploads/${jobId}`);
    if (j.body?.status === "done" || j.body?.status === "error") return { create, job: j.body };
    if (Date.now() - t0 > timeoutMs) return { create, job: { status: "timeout", ...j.body } };
    await new Promise((r) => setTimeout(r, 1000));
  }
}
