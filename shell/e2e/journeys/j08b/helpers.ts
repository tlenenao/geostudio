/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { CORE_URL } from "../_fixtures/env";
import { apiFor as apiForPersona } from "../j03/api";
import type { Api } from "../j03/api";
import { apiWithToken, makeUser, tokenFor, psql, PASSWORD, roleIdBySlug } from "../j08/helpers";

export { makeUser, tokenFor, psql, PASSWORD, roleIdBySlug, apiWithToken };
export type { Api };
export { apiForPersona as apiFor };

export const QUOTA_URL = "http://localhost:8201";
const NAME = "audit-core-quota";

function docker(args: string[], input?: Buffer | string): string {
  return execFileSync("docker", args, {
    encoding: "utf8",
    input,
    stdio: ["pipe", "pipe", "pipe"],
  });
}

// Un SECOND processus cœur (même image, même base, même réseau) avec des limites de
// quota basses : la stack d'audit n'est pas modifiée (limites larges 100000/10000).
export function startQuotaCore(limits: {
  items: number;
  collections: number;
  storage: number | null;
}): void {
  const env: string[] = JSON.parse(
    docker(["inspect", "geostudio-core-1", "--format", "{{json .Config.Env}}"]),
  );
  const keep = env.filter((e) =>
    /^(CORE_|S3_|DATABASE_URL|OTEL_|PUBLIC_BASE_URL|TITILER_URL)/.test(e),
  );
  const overrides = {
    CORE_QUOTAS_ENABLED: "true",
    CORE_QUOTA_MAX_ITEMS_PER_TENANT: String(limits.items),
    CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT: String(limits.collections),
    CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT: limits.storage === null ? "" : String(limits.storage),
  };
  const args = ["run", "-d", "--name", NAME, "--network", "geostudio_gis-net", "-p", "8201:8200"];
  for (const e of keep) {
    const k = e.split("=")[0];
    if (!(k in overrides)) args.push("-e", e);
  }
  for (const [k, v] of Object.entries(overrides)) args.push("-e", `${k}=${v}`);
  args.push("geostudio-core", "sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8200");
  stopQuotaCore();
  docker(args);
}

export function stopQuotaCore(): void {
  try {
    docker(["rm", "-f", NAME]);
  } catch {
    /* absent */
  }
}

export async function waitQuotaCore(): Promise<void> {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${QUOTA_URL}/v1/me`);
      if (r.status === 401) return;
    } catch {
      /* pas encore prêt */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("audit-core-quota ne démarre pas");
}

export function quotaApi(persona: "admin" | "creator"): Api {
  const username = persona === "admin" ? "audit-admin" : "audit-creator";
  return apiOn(QUOTA_URL, () => tokenFor(username));
}

export function apiOn(base: string, getToken: () => Promise<string>): Api {
  const send = async (method: string, path: string, body?: unknown) => {
    const tok = await getToken();
    const doFetch = () =>
      fetch(`${base}${path}`, {
        method,
        headers: {
          authorization: `Bearer ${tok}`,
          ...(body !== undefined ? { "content-type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
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

// Dépôt direct d'un objet dans un bucket tenant-préfixé (le présigné d'upload répond 500).
export function putObject(bucketEnv: string, name: string, size: number): string {
  const key = `default/audj08b-${Math.random().toString(16).slice(2)}-${name}`;
  const py =
    "import sys,boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY'])\n" +
    `c.put_object(Bucket=os.environ['${bucketEnv}'],Key=sys.argv[1],Body=sys.stdin.buffer.read())`;
  docker(["exec", "-i", "geostudio-core-1", "python", "-c", py, key], csvOfSize(size));
  return key;
}

export function deleteObject(bucketEnv: string, key: string): void {
  const py =
    "import sys,boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY'])\n" +
    `c.delete_object(Bucket=os.environ['${bucketEnv}'],Key=sys.argv[1])`;
  docker(["exec", "-i", "geostudio-core-1", "python", "-c", py, key]);
}

// CSV valide (nom,lat,lon) d'au moins `size` octets.
export function csvOfSize(size: number): string {
  let s = "nom,lat,lon\n";
  let i = 0;
  while (s.length < size) s += `p${i++},45.${String(i).padStart(3, "0")},1.5\n`;
  return s;
}

export function simulateLockout(tag: string): Record<string, any> {
  const code = readFileSync(join(process.cwd(), "e2e/journeys/j08b/lockout_sim.py"), "utf8");
  const out = execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-", tag], {
    input: code,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
  return JSON.parse(out.trim().split("\n").pop() as string);
}

export const APP_CONFIG = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
};

export { CORE_URL };
