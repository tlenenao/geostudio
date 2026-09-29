/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { CORE_URL, PERSONAS, type PersonaName } from "../_fixtures/env";

const KC = process.env.KC_URL ?? "http://localhost:8180";

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
    const r = await fetch(`${CORE_URL}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${tok}`,
        ...(body !== undefined ? { "content-type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
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
