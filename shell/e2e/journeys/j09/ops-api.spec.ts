/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { CORE_URL, instanceFlag } from "../_fixtures/env";
import { alertConfig, apiFor, getAlertSeed, waitEvaluation, type Api } from "./helpers";

// Journal des tâches (/usage), état d'instance, passerelle /admin-tools et rapports planifiés.
test.setTimeout(150_000);
let admin: Api;
let creator: Api;
let analyst: Api;
let reader: Api;

test.beforeAll(async () => {
  admin = await apiFor("admin");
  creator = await apiFor("creator");
  analyst = await apiFor("analyst");
  reader = await apiFor("reader");
});

test.describe("j09 journal des tâches (/usage)", () => {
  test("matrice de droits : lecteur 403, créateur/analyste 200, résumé réservé à tasks.view_all", async () => {
    expect((await reader.get("/v1/usage/tasks")).status).toBe(403);
    expect((await creator.get("/v1/usage/tasks")).status).toBe(200);
    expect((await analyst.get("/v1/usage/tasks")).status).toBe(200);
    expect((await admin.get("/v1/usage/tasks")).status).toBe(200);
    expect((await creator.get("/v1/usage/summary")).status).toBe(403);
    expect((await admin.get("/v1/usage/summary")).status).toBe(200);
  });

  test("j09-008 : le propriétaire d'une règle d'alerte retrouve ses évaluations dans son journal de tâches", async () => {
    const s = await getAlertSeed();
    const r = await s.creator.send("POST", "/v1/configs", {
      title: `${s.tag}-usage`,
      config: alertConfig(s.datasetId),
    });
    const id = r.body.itemId as string;
    await s.creator.send("POST", `/v1/alerts/${id}/evaluate`);
    const list = await s.creator.get(`/v1/alerts/${id}/evaluations`);
    const evalId = list.body[0].id as string;
    await waitEvaluation(s.creator, id, evalId);
    const mine = await s.creator.get("/v1/usage/tasks?pageSize=200");
    const rows = mine.body.tasks.filter((t: any) => t.objectId === id);
    expect(rows.map((t: any) => t.action)).toContain("alert.evaluate");
  });
});

test.describe("j09 instance et passerelle /admin-tools", () => {
  test("passerelle éteinte : lancement, session et verify sont introuvables, même pour l'administrateur", async () => {
    test.skip(
      await instanceFlag("adminToolsEnabled"),
      "stack avec CORE_ADMIN_TOOLS_ENABLED=true : parcours « passerelle éteinte » sans objet",
    );
    for (const tool of ["martin", "titiler", "grafana"]) {
      expect((await admin.send("POST", `/v1/admin-tools/launch/${tool}`)).status).toBe(404);
      const session = await fetch(`${CORE_URL}/v1/admin-tools/session/${tool}?_at=x`, {
        redirect: "manual",
      });
      expect(session.status).toBe(404);
    }
    const verify = await fetch(`${CORE_URL}/v1/admin-tools/verify`);
    expect(verify.status).toBe(404);
  });
});

test.describe("j09 rapports planifiés", () => {
  test("la création d'un rapport est refusée en 403 quand l'export est désactivé", async () => {
    test.skip(
      await instanceFlag("exportEnabled"),
      "stack avec CORE_EXPORT_ENABLED=true : parcours « export éteint » sans objet",
    );
    const app = await creator.send("POST", "/v1/configs", {
      title: "j09-app",
      config: {
        version: 1,
        kind: "app",
        theme: {},
        dataSources: [],
        messages: [],
        layout: { type: "grid", breakpoints: {}, items: [] },
      },
    });
    const bm = await creator.send("POST", "/v1/configs", {
      title: "j09-bm",
      config: { version: 1, kind: "bookmark", bookmark: { appId: app.body.itemId, pageId: "p1" } },
    });
    expect(bm.status).toBe(201);
    const rep = await creator.send("POST", "/v1/configs", {
      title: "j09-rep",
      config: {
        version: 1,
        kind: "report",
        report: {
          bookmarkItemId: bm.body.itemId,
          refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
          channels: [{ kind: "webhook", url: "https://example.test/h" }],
        },
      },
    });
    expect(rep.status).toBe(403);
  });
});
