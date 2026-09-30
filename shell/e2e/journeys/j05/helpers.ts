import { CORE_URL, type PersonaName } from "../_fixtures/env";
import { apiFor, token, type Api } from "../j03/api";

export type { Api };
export { apiFor };

export async function sql(api: Api, query: string) {
  return api.send("POST", "/v1/analytics/sql", { sql: query });
}

export async function aggregate(api: Api, collectionId: string, body: Record<string, unknown>) {
  return api.send("POST", `/v1/collections/${collectionId}/aggregate`, body);
}

// Récupère un export binaire (CSV/XLSX/GPKG/GeoJSON) avec le jeton d'une persona.
export async function download(
  persona: PersonaName | null,
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<{ status: number; type: string; disposition: string; buf: Buffer }> {
  const headers: Record<string, string> = {};
  if (persona) headers.authorization = `Bearer ${await token(persona)}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  const doFetch = () =>
    fetch(`${CORE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  const r = await doFetch().catch(() => doFetch());
  return {
    status: r.status,
    type: r.headers.get("content-type") ?? "",
    disposition: r.headers.get("content-disposition") ?? "",
    buf: Buffer.from(await r.arrayBuffer()),
  };
}

// Valeurs attendues des 60 événements de seed.ts (montant = i*10, null si i%7==0,
// cat = a/b/c ou null si i%10==9).
export function expectedByCat(): Record<string, { n: number; sum: number }> {
  const out: Record<string, { n: number; sum: number }> = {};
  for (let i = 0; i < 60; i++) {
    const cat = i % 10 === 9 ? "∅" : ["a", "b", "c"][i % 3];
    out[cat] ??= { n: 0, sum: 0 };
    out[cat].n += 1;
    out[cat].sum += i % 7 === 0 ? 0 : i * 10;
  }
  return out;
}
