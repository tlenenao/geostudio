import { test, expect } from "@playwright/test";
import { CORE_URL, etlEnabled, stamp } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";

// Comportement du cœur quand CORE_ETL_ENABLED est faux (cas de la stack d'audit) :
// les routes /v1/pipelines/* ne sont pas montées et la création de config
// kind="pipeline" est refusée.
const tag = stamp("j06");
let admin: Api;
let creator: Api;
let reader: Api;

test.beforeAll(async () => {
  test.skip(
    await etlEnabled(),
    "stack avec CORE_ETL_ENABLED=true : parcours « ETL éteint » sans objet",
  );
  [admin, creator, reader] = await Promise.all([
    apiFor("admin"),
    apiFor("creator"),
    apiFor("reader"),
  ]);
});

const pipeline = {
  nodes: [
    { id: "r", kind: "reader", op: "reader.collection", params: { collectionId: "x" } },
    { id: "w", kind: "writer", op: "writer.collection", params: { collectionId: "x" } },
  ],
  edges: [{ id: "e", from: "r", to: "w" }],
};

test.describe("j06 ETL désactivé — API", () => {
  test("/v1/instance et /v1/me annoncent etlEnabled=false", async () => {
    const inst = await creator.get("/v1/instance");
    expect(inst.status).toBe(200);
    expect(inst.body.etlEnabled).toBe(false);
    const me = await creator.get("/v1/me");
    expect(me.body.capabilities.etlEnabled).toBe(false);
  });

  test("les routes pipelines ne sont pas montées (404)", async () => {
    for (const [m, p] of [
      ["GET", "/v1/pipelines/ops"],
      ["GET", "/v1/pipelines/next-run?cron=*/5%20*%20*%20*%20*"],
      ["POST", "/v1/pipelines/abc/run"],
      ["GET", "/v1/pipelines/abc/runs"],
      ["POST", "/v1/pipelines/abc/preview?upTo=r"],
      ["POST", "/v1/pipelines/abc/webhook-tokens"],
    ] as const) {
      expect((await admin.send(m, p)).status, `${m} ${p}`).toBe(404);
    }
  });

  test("le déclencheur webhook entrant est introuvable sans jeton comme avec un jeton", async () => {
    const bare = await fetch(`${CORE_URL}/v1/pipelines/abc/trigger`, { method: "POST" });
    expect(bare.status).toBe(404);
    const withTok = await fetch(`${CORE_URL}/v1/pipelines/abc/trigger`, {
      method: "POST",
      headers: { authorization: "Bearer inconnu" },
    });
    expect(withTok.status).toBe(404);
  });

  test("créer une config pipeline valide : 403 « ETL capability disabled » (même pour l'admin)", async () => {
    for (const api of [admin, creator]) {
      const r = await api.send("POST", "/v1/configs", {
        title: `${tag}-pipe`,
        config: { kind: "pipeline", pipeline },
      });
      expect(r.status).toBe(403);
      expect(JSON.stringify(r.body)).toContain("ETL capability disabled");
    }
  });

  test("lecteur : refus pour privilège manquant, avant la garde de capacité", async () => {
    const r = await reader.send("POST", "/v1/configs", {
      title: `${tag}-pipe-reader`,
      config: { kind: "pipeline", pipeline },
    });
    expect(r.status).toBe(403);
    expect(JSON.stringify(r.body)).toContain("automation.manage");
  });

  test("un pipeline structurellement invalide est rejeté en 422 avant toute garde", async () => {
    const r = await creator.send("POST", "/v1/configs", {
      title: `${tag}-pipe-vide`,
      config: { kind: "pipeline", pipeline: { nodes: [], edges: [] } },
    });
    expect(r.status).toBe(422);
  });

  test("le catalogue ne contient aucun item de type pipeline", async () => {
    const r = await admin.get("/v1/items?type=pipeline");
    expect(r.status).toBe(200);
    const rows = Array.isArray(r.body) ? r.body : (r.body.items ?? r.body.results ?? []);
    expect(rows).toHaveLength(0);
  });
});
