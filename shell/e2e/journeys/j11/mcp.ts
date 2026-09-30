/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON-RPC/REST du cœur, forme libre */
import { CORE_URL, PERSONAS, stamp, type PersonaName } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { psql } from "../j02/helpers";

export { apiFor, psql };
export type { Api };

const KC = process.env.KC_URL ?? "http://localhost:8180";

// Jeton d'audience MCP (`geostudio-mcp`) obtenu par grant password avec le
// client-scope optionnel geostudio-mcp-audience, comme le fait useMcpToken.ts.
export async function mcpToken(persona: PersonaName, scope = "openid geostudio-mcp-audience") {
  const { username, password } = PERSONAS[persona];
  const r = await fetch(`${KC}/realms/geostudio/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "password",
      client_id: "geostudio-shell",
      username,
      password,
      scope,
    }),
  });
  if (!r.ok) throw new Error(`token ${persona}: ${r.status}`);
  return ((await r.json()) as { access_token: string }).access_token;
}

export function jwtClaims(token: string): any {
  return JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
}

export interface ToolResult {
  isError: boolean;
  text: string;
  json: any;
}

export class McpClient {
  private sid: string | null = null;
  private n = 0;
  constructor(readonly token: string) {}

  static async as(persona: PersonaName): Promise<McpClient> {
    const c = new McpClient(await mcpToken(persona));
    await c.handshake();
    return c;
  }

  async post(method: string, params: unknown = {}, notify = false) {
    const headers: Record<string, string> = {
      authorization: `Bearer ${this.token}`,
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
    };
    if (this.sid) headers["mcp-session-id"] = this.sid;
    const body: any = { jsonrpc: "2.0", method, params };
    if (!notify) body.id = ++this.n;
    const r = await fetch(`${CORE_URL}/mcp`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    this.sid = r.headers.get("mcp-session-id") ?? this.sid;
    const text = await r.text();
    let rpc: any = null;
    for (const line of text.split("\n")) {
      if (line.startsWith("data:")) rpc = JSON.parse(line.slice(5));
    }
    return { status: r.status, rpc, raw: text };
  }

  async handshake() {
    const init = await this.post("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "aud-j11", version: "1" },
    });
    if (init.status !== 200) throw new Error(`initialize ${init.status}`);
    await this.post("notifications/initialized", {}, true);
  }

  async tools(): Promise<any[]> {
    return (await this.post("tools/list")).rpc.result.tools;
  }

  async call(name: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
    const { rpc, status, raw } = await this.post("tools/call", { name, arguments: args });
    if (!rpc?.result) throw new Error(`tools/call ${name}: ${status} ${raw.slice(0, 200)}`);
    const text: string = rpc.result.content?.[0]?.text ?? "";
    let json: any = null;
    try {
      json = JSON.parse(text);
    } catch {
      /* erreur d'outil : texte brut */
    }
    return { isError: rpc.result.isError === true, text, json };
  }
}

export interface Seed {
  tag: string;
  collectionId: string;
  tableName: string;
  datasetPk: string;
  appPk: string;
}

let cached: Promise<Seed> | undefined;

// Collection publique de 2 points (champ `secret` déclaré sensible), un dataset
// dessus et une app privée du créateur. Créée vide puis remplie en SQL : l'import
// est cassé sur cette stack (j03-001).
export function getSeed(): Promise<Seed> {
  cached ??= (async () => {
    const tag = stamp("j11");
    const creator = await apiFor("creator");
    const c = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-col`,
      columns: [
        { name: "nom", sqlType: "text" },
        { name: "val", sqlType: "integer" },
        { name: "secret", sqlType: "text" },
      ],
      geometryType: "Point",
      srid: 4326,
    });
    if (c.status !== 201) throw new Error(`collection ${c.status}`);
    const table = c.body.tableName as string;
    psql(
      `INSERT INTO public.${table} (tenant_id, nom, val, secret, geom) VALUES ` +
        `('default','A',1,'s1',ST_SetSRID(ST_MakePoint(1.5,45.2),4326)),` +
        `('default','B',2,'s2',ST_SetSRID(ST_MakePoint(1.6,45.3),4326))`,
    );
    psql(`UPDATE collections SET feature_count=2 WHERE id='${c.body.id}'`);
    const p = await creator.send("PATCH", `/v1/collections/${c.body.id}`, {
      sensitiveFields: ["secret"],
    });
    if (p.status !== 200) throw new Error(`sensitive ${p.status}`);
    await creator.send("PUT", `/v1/collections/${c.body.id}/sharing`, { public: true, groups: [] });
    const mcp = await McpClient.as("creator");
    const ds = await mcp.call("create_dataset", {
      title: `${tag}-ds`,
      source: "collection",
      collectionId: c.body.id,
    });
    const app = await creator.send("POST", "/v1/configs", {
      title: `${tag}-app`,
      config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
    });
    if (app.status !== 201) throw new Error(`app ${app.status}`);
    return {
      tag,
      collectionId: c.body.id,
      tableName: table,
      datasetPk: ds.json.pk,
      appPk: app.body.itemId,
    };
  })();
  return cached;
}
