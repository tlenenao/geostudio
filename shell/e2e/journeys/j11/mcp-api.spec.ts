/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON-RPC/REST du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor, getSeed, jwtClaims, McpClient, mcpToken, psql } from "./mcp";

test.setTimeout(90_000);

const KC = process.env.KC_URL ?? "http://localhost:8180";

test.describe("j11 MCP : authentification et découverte OAuth", () => {
  test("sans jeton, jeton bidon ou jeton d'audience REST seule : 401 + métadonnées de ressource", async () => {
    const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    const headers = {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
    };
    const restOnly = await mcpToken("creator", "openid");
    expect(jwtClaims(restOnly).aud).not.toContain("geostudio-mcp");
    for (const bearer of [null, "abc.def.ghi", restOnly]) {
      const r = await fetch(`${CORE_URL}/mcp`, {
        method: "POST",
        headers: { ...headers, ...(bearer ? { authorization: `Bearer ${bearer}` } : {}) },
        body,
      });
      expect(r.status).toBe(401);
      expect(r.headers.get("www-authenticate")).toContain(
        `resource_metadata="${CORE_URL}/.well-known/oauth-protected-resource/mcp"`,
      );
    }
    const meta = await (await fetch(`${CORE_URL}/.well-known/oauth-protected-resource/mcp`)).json();
    expect(meta.resource).toBe(`${CORE_URL}/mcp`);
    expect(meta.authorization_servers).toEqual([`${KC}/realms/geostudio`]);
    const oidc = await (
      await fetch(`${KC}/realms/geostudio/.well-known/openid-configuration`)
    ).json();
    expect(oidc.code_challenge_methods_supported).toContain("S256");
    expect(oidc.registration_endpoint).toBeTruthy();
  });

  test("un jeton d'audience MCP ouvre la session et whoami suit /v1/me pour chaque persona", async () => {
    for (const persona of ["admin", "creator", "analyst", "reader"] as const) {
      const mcp = await McpClient.as(persona);
      expect(jwtClaims(mcp.token).aud).toContain("geostudio-mcp");
      const who = await mcp.call("whoami");
      const me = await (await apiFor(persona)).get("/v1/me");
      expect(who.json.username).toBe(me.body.username);
      expect(who.json.tenantId).toBe(me.body.tenantId);
    }
  });

  test("inventaire des outils : les outils de la liste blanche du copilote existent, ETL éteint masque les outils pipeline", async () => {
    const mcp = await McpClient.as("creator");
    const names = (await mcp.tools()).map((t) => t.name);
    for (const n of [
      "search_catalog",
      "list_items",
      "explain_dataset",
      "run_analytics_query",
      "create_item",
      "create_form_app",
      "generate_sql_query",
      "generate_visual_query",
    ]) {
      expect(names).toContain(n);
    }
    // Capacité ETL éteinte : aucun outil de pipeline exposé.
    expect(names.filter((n) => /pipeline/.test(n))).toEqual([]);
    // Les outils d'écriture destructifs ne sont pas exposés.
    expect(names).not.toContain("delete_item");
  });
});

test.describe("j11 MCP : permissions de l'utilisateur et parité REST", () => {
  test("list_items MCP voit exactement ce que GET /v1/items voit, pour chaque persona", async () => {
    const seed = await getSeed();
    for (const persona of ["creator", "reader"] as const) {
      const mcp = await McpClient.as(persona);
      const api = await apiFor(persona);
      const viaMcp = await mcp.call("list_items", { pageSize: 100 });
      const viaRest = await api.get("/v1/items?pageSize=100");
      const pks = (r: any) => r.items.map((i: any) => i.pk).sort();
      expect(pks(viaMcp.json)).toEqual(pks(viaRest.body));
      expect(viaMcp.json.total).toBe(viaRest.body.total);
      const sees = pks(viaMcp.json).includes(seed.appPk);
      expect(sees).toBe(persona === "creator");
    }
  });

  test("droits d'écriture : lecteur et analyste refusés, créateur autorisé, mêmes règles que REST", async () => {
    const seed = await getSeed();
    const cfg = { version: 1, kind: "app", layout: { type: "grid", items: [] } };
    const denied: Record<string, string> = {};
    for (const persona of ["reader", "analyst"] as const) {
      const mcp = await McpClient.as(persona);
      const r = await mcp.call("create_item", {
        kind: "app",
        title: "aud-j11-denied",
        config: cfg,
      });
      expect(r.isError).toBe(true);
      denied[persona] = r.text;
      const rest = await (
        await apiFor(persona)
      ).send("POST", "/v1/configs", {
        title: "aud-j11-denied",
        config: cfg,
      });
      expect(rest.status).toBe(403);
      expect((await mcp.call("create_form_app", { collectionId: seed.collectionId })).isError).toBe(
        true,
      );
    }
    expect(denied.reader).toContain("apps.manage");
    const reader = await McpClient.as("reader");
    expect((await reader.call("create_group", { name: "aud-j11-g" })).text).toContain(
      "catalog.manage",
    );
    const creator = await McpClient.as("creator");
    const ok = await creator.call("create_item", {
      kind: "app",
      title: `${seed.tag}-mcp`,
      config: cfg,
    });
    expect(ok.isError).toBe(false);
    expect(ok.json.owner).toBe("audit-creator");
  });

  test("un non-propriétaire ne peut ni lire, ni enregistrer, ni partager un item privé (même 404 que REST)", async () => {
    const seed = await getSeed();
    const cfg = { version: 1, kind: "app", layout: { type: "grid", items: [] } };
    for (const persona of ["reader", "analyst", "admin"] as const) {
      const mcp = await McpClient.as(persona);
      for (const [tool, args] of [
        ["get_item", { itemId: seed.appPk }],
        ["get_app_config", { itemId: seed.appPk }],
        ["get_sharing", { itemId: seed.appPk }],
        ["save_app_config", { itemId: seed.appPk, config: cfg }],
        ["set_sharing", { itemId: seed.appPk, sharing: { public: true, groups: [] } }],
      ] as const) {
        const r = await mcp.call(tool, args as any);
        expect(r.isError, `${persona} ${tool}`).toBe(true);
        expect(r.text).toContain("item not found");
      }
      const rest = await (await apiFor(persona)).get(`/v1/items/${seed.appPk}`);
      expect(rest.status).toBe(404);
    }
  });

  test("query_features masque le champ sensible comme la route REST et refuse d'y filtrer", async () => {
    const seed = await getSeed();
    for (const persona of ["creator", "reader"] as const) {
      const mcp = await McpClient.as(persona);
      const r = await mcp.call("query_features", { collectionId: seed.collectionId });
      expect(r.isError).toBe(false);
      expect(r.json.numberReturned).toBe(2);
      const rest = await (await apiFor(persona)).get(`/v1/collections/${seed.collectionId}/items`);
      const props = (f: any) => Object.keys(f.properties).sort();
      expect(props(r.json.features[0])).toEqual(props(rest.body.features[0]));
      expect(props(r.json.features[0])).not.toContain("secret");
      const f = await mcp.call("query_features", {
        collectionId: seed.collectionId,
        filters: { secret: "s1" },
      });
      expect(f.isError).toBe(true);
      expect(f.text).toContain("unknown filter field");
    }
  });

  test("les écritures MCP sont journalisées en actor_kind=agent, les écritures REST en user", async () => {
    const seed = await getSeed();
    const creator = await McpClient.as("creator");
    const title = `${seed.tag}-audit`;
    const made = await creator.call("create_item", {
      kind: "app",
      title,
      config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
    });
    await (
      await apiFor("creator")
    ).send("POST", "/v1/configs", {
      title: `${title}-rest`,
      config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
    });
    const mcpRows = psql(
      `SELECT DISTINCT actor_kind || ':' || action FROM audit_log WHERE object_id='${made.json.pk}' OR payload->>'title'='${title}'`,
    );
    expect(mcpRows).toContain("agent:item.create");
    const restRows = psql(
      `SELECT DISTINCT actor_kind || ':' || action FROM audit_log WHERE payload->>'title'='${title}-rest'`,
    );
    expect(restRows).toContain("user:");
    expect(restRows).not.toContain("agent:");
  });
});

test.describe("j11 MCP : défauts constatés", () => {
  // FINDING j11-002 : une valeur hors bornes atteint PostgreSQL et l'erreur
  // brute (SQL complet, nom de table physique, paramètres) est renvoyée à l'agent.
  test(
    "j11-002 : query_features avec limit négatif renvoie une erreur d'outil propre, sans SQL",
    async () => {
      const seed = await getSeed();
      const mcp = await McpClient.as("creator");
      const r = await mcp.call("query_features", { collectionId: seed.collectionId, limit: -1 });
      expect(r.isError).toBe(true);
      expect(r.text).not.toMatch(/SELECT|psycopg|FROM public\./);
      expect(r.text).not.toContain(seed.tableName);
    },
  );

  // FINDING j11-001 : CORE_LLM_PROVIDER vaut "" sur cette stack ; is_copilot_enabled()
  // le traite comme éteint mais get_llm_provider() lève « unknown CORE_LLM_PROVIDER: ».
  test(
    "j11-001 : generate_sql_query sans fournisseur LLM répond un message d'indisponibilité lisible",
    async () => {
      const seed = await getSeed();
      const mcp = await McpClient.as("analyst");
      const r = await mcp.call("generate_sql_query", {
        collectionId: seed.collectionId,
        question: "total par nom",
      });
      expect(r.isError).toBe(true);
      expect(r.text).not.toContain("unknown CORE_LLM_PROVIDER");
      expect(r.text.toLowerCase()).toMatch(/indisponible|non configur|unavailable|not configured/);
    },
  );

  // FINDING j11-003 : run_alert_rule commite une évaluation « pending » puis échoue au
  // defer (AppNotOpen, cf. j09-001) ; l'évaluation orpheline masque ensuite tout nouveau
  // déclenchement (202 created:false, aucun job déféré) pendant la fenêtre de reprise.
  bug(
    "j11-003 : après un échec de defer, un nouveau déclenchement ne réutilise pas une évaluation orpheline",
    async () => {
      const seed = await getSeed();
      const mcp = await McpClient.as("creator");
      const made = await mcp.call("create_alert_rule", {
        title: `${seed.tag}-alert`,
        datasetItemId: seed.datasetPk,
        query: { agg: "count" },
        condition: { expr: "value > 2" },
        refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
        channels: [{ kind: "webhook", url: "http://127.0.0.1:9/hook" }],
      });
      expect(made.isError).toBe(false);
      const pk = made.json.pk as string;
      const first = await mcp.call("run_alert_rule", { alertRuleId: pk });
      const jobsBefore = Number(
        psql(
          `SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE '%evaluate_alert%' AND args->>'tenant_id'='default'`,
        ).trim(),
      );
      const second = await (await apiFor("creator")).send("POST", `/v1/alerts/${pk}/evaluate`);
      const jobsAfter = Number(
        psql(
          `SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE '%evaluate_alert%' AND args->>'tenant_id'='default'`,
        ).trim(),
      );
      // Soit le premier appel a réussi, soit le second doit réessayer réellement.
      if (first.isError) {
        expect(second.body.created).toBe(true);
        expect(jobsAfter).toBeGreaterThan(jobsBefore);
      }
    },
  );

  // FINDING j11-004 : POST /mcp partage le budget « llm » (20 requêtes/60 s/jeton) ; une
  // poignée de main (initialize + initialized + tools/list) en coûte 3, un tour de copilote
  // ouvre une session neuve, donc ~6 tours par minute épuisent le jeton (429).
  test(
    "j11-004 : 7 tours de copilote successifs (poignée de main + 1 appel d'outil) ne sont pas limités",
    async () => {
      const token = await mcpToken("reader");
      const statuses: number[] = [];
      for (let turn = 0; turn < 7; turn++) {
        const c = new McpClient(token);
        const init = await c.post("initialize", {
          protocolVersion: "2025-06-18",
          capabilities: {},
          clientInfo: { name: "geostudio-copilot", version: "0" },
        });
        statuses.push(init.status);
        statuses.push((await c.post("notifications/initialized", {}, true)).status);
        statuses.push((await c.post("tools/list")).status);
        statuses.push((await c.post("tools/call", { name: "whoami", arguments: {} })).status);
      }
      expect(statuses.filter((s) => s === 429)).toEqual([]);
    },
  );
});
