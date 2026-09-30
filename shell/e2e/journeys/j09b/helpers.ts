/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { alertConfig, waitEvaluation } from "../j09/helpers";
import type { Api } from "../j09/helpers";

export { apiFor, psql, openAs, spaGoto, corePython } from "../j09/helpers";
export { alertConfig, getAlertSeed, waitEvaluation, deferEvaluation } from "../j09/helpers";
export type { Api };

export const RECV = "audit-j09b-recv";
const NET = "audit-j09b-pub";
// Sous-réseau ROUTABLE (hors RFC1918) : la garde d'egress des webhooks refuse toute cible interne,
// y compris loopback/privée ; un conteneur jetable sur 11.77.0.0/24 est donc la seule façon de
// livrer un webhook réel sans modifier la stack.
export const PUB_IP = "11.77.0.10";
export const HOOK = `http://${PUB_IP}:8080`;

function docker(args: string[], input?: string): string {
  return execFileSync("docker", args, {
    encoding: "utf8",
    input,
    stdio: ["pipe", "pipe", "pipe"],
  });
}

// Conteneur jetable (image du cœur, env du cœur) : récepteur webhook+SMTP ET exécuteur
// d'évaluation d'alerte sur le réseau routable. Créé et supprimé par les specs.
export function startHarness(): void {
  stopHarness();
  const env: string[] = JSON.parse(
    docker(["inspect", "geostudio-core-1", "--format", "{{json .Config.Env}}"]),
  );
  const keep = env.filter((e) => /^(CORE_|S3_|DATABASE_URL|TITILER_URL)/.test(e));
  docker(["network", "create", "--subnet", "11.77.0.0/24", NET]);
  const args = ["run", "-d", "--name", RECV, "--network", "geostudio_gis-net"];
  for (const e of keep) args.push("-e", e);
  args.push("geostudio-core", "sleep", "infinity");
  docker(args);
  docker(["network", "connect", "--ip", PUB_IP, NET, RECV]);
  docker(["cp", join(process.cwd(), "e2e/journeys/j09b/recv.py"), `${RECV}:/tmp/recv.py`]);
  docker(["exec", "-d", RECV, "python", "/tmp/recv.py"]);
  for (let i = 0; i < 20; i++) {
    try {
      docker([
        "exec",
        RECV,
        "python",
        "-c",
        `import socket;socket.create_connection(("${PUB_IP}",8080),1)`,
      ]);
      return;
    } catch {
      execFileSync("sleep", ["0.5"]);
    }
  }
  throw new Error("récepteur j09b injoignable");
}

export function stopHarness(): void {
  for (const cmd of [
    ["rm", "-f", RECV],
    ["network", "rm", NET],
  ]) {
    try {
      docker(cmd);
    } catch {
      /* absent */
    }
  }
}

export function recvLog(name: "http" | "smtp" | "smtp_auth_fail"): any[] {
  try {
    const out = docker(["exec", RECV, "cat", `/tmp/recv/${name}.jsonl`]);
    return out
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}

// Exécute la tâche d'évaluation (son corps) dans le conteneur jetable : mêmes fonctions que le
// worker, mais avec un chemin réseau vers le récepteur routable.
export function runnerEvaluate(evaluationId: string): string {
  return docker(
    ["exec", "-i", RECV, "python", "-"],
    [
      "from app.alerts.jobs import evaluate_alert_task",
      `evaluate_alert_task.func(evaluation_id="${evaluationId}", tenant_id="default")`,
    ].join("\n"),
  );
}

// Crée la ligne d'évaluation pending via la route REST (dont le déféré échoue en 500, j09-001).
export async function newEvaluation(api: Api, itemId: string): Promise<string> {
  await api.send("POST", `/v1/alerts/${itemId}/evaluate`);
  const list = await api.get(`/v1/alerts/${itemId}/evaluations`);
  const pending = (list.body as any[]).find((e) => e.state === "pending");
  if (!pending) throw new Error("aucune évaluation pending");
  return pending.id as string;
}

export async function mkRule(
  api: Api,
  datasetId: string,
  title: string,
  over: any = {},
): Promise<string> {
  const r = await api.send("POST", "/v1/configs", {
    title,
    config: alertConfig(datasetId, over),
  });
  if (r.status !== 201) throw new Error(`rule ${r.status} ${JSON.stringify(r.body)}`);
  return r.body.itemId as string;
}

export async function evalWith(
  api: Api,
  itemId: string,
  how: "runner" | "worker",
  defer?: (id: string) => void,
): Promise<any> {
  const id = await newEvaluation(api, itemId);
  if (how === "runner") runnerEvaluate(id);
  else defer!(id);
  return waitEvaluation(api, itemId, id);
}
