/* eslint-disable @typescript-eslint/no-explicit-any -- sortie JSON de la sonde, forme libre */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor } from "./mcp";

test.setTimeout(90_000);

// Le routeur /v1/copilot/turn n'est monté que si CORE_LLM_PROVIDER est renseigné
// (éteint sur cette stack, non modifiable) : la sonde monte ce routeur seul dans le
// conteneur cœur, avec un LLM et une session MCP factices.
const PROBE = join(process.cwd(), "../docs/revue/audit-2026-09-29/j11/probes/copilot_probe.py");

let probe: Record<string, any>;

test.beforeAll(() => {
  const out = execFileSync(
    "docker",
    ["exec", "-i", "-w", "/app", "-e", "PYTHONPATH=/app", "geostudio-core-1", "python", "-"],
    { input: readFileSync(PROBE), encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] },
  );
  probe = JSON.parse(out.trim().split("\n").pop() as string);
});

test.describe("j11 copilote : capacité éteinte", () => {
  test("sans CORE_LLM_PROVIDER : copilotEnabled=false et POST /v1/copilot/turn n'existe pas (404)", async () => {
    const creator = await apiFor("creator");
    const inst = await creator.get("/v1/instance");
    expect(inst.body.copilotEnabled).toBe(false);
    const turn = await creator.send("POST", "/v1/copilot/turn", {
      message: "bonjour",
      mcpToken: "x",
      currentConfig: {},
    });
    expect(turn.status).toBe(404);
    const res = await fetch(`${CORE_URL}/v1/copilot/turn`, { method: "POST" });
    expect([401, 404]).toContain(res.status);
  });
});

test.describe("j11 copilote : routeur /copilot/turn (sonde dans le conteneur)", () => {
  test("bornes d'entrée : 40 messages d'historique passent, 41, message > 4000 et config > 64000 sont refusés (422)", async () => {
    expect(probe.history_40[0]).toBe(200);
    expect(probe.history_41[0]).toBe(422);
    expect(probe.message_4001[0]).toBe(422);
    expect(probe.history_message_8001[0]).toBe(422);
    expect(probe.config_64500[0]).toBe(422);
  });

  test("le rôle system est refusé dans l'historique et un outil hors liste blanche n'est jamais exécuté côté serveur", async () => {
    expect(probe.role_system_in_history[0]).toBe(422);
    const ops = JSON.parse(probe.non_allowlisted_tool[1].replace(/…$/, "") || "{}");
    expect(ops.clientOps.map((o: any) => o.op)).toEqual(["save_app_config"]);
    // save_app_config est renvoyé au shell comme opération client ; seul search_catalog
    // (liste blanche) a été appelé sur la session MCP.
    expect(probe.server_tools_called).toEqual(["search_catalog"]);
  });

  // FINDING j11-005 : seule EgressBlockedError est traduite ; un 429/5xx du fournisseur,
  // un délai dépassé ou une réponse mal formée remontent en 500 opaque.
  test.fixme("j11-005 : une panne du fournisseur LLM répond 502/504 et non 500", async () => {
    for (const k of [
      "llm_http_429",
      "llm_http_500",
      "llm_timeout",
      "llm_connect_error",
      "llm_bad_payload",
    ]) {
      expect([502, 503, 504], k).toContain(probe[k][0]);
    }
  });

  // FINDING j11-009 / j11-013 : l'historique et la config partent sans plafond côté
  // shell alors que le cœur refuse > 40 messages / > 64000 caractères de config.
  test("la sonde restitue les motifs de refus des bornes (40 messages, 64000 caractères)", async () => {
    expect(probe.history_41[1]).toContain("at most 40 items");
    expect(probe.config_64500[1]).toContain("64000");
  });
});
