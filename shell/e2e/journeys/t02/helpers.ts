import { test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { CORE_URL, type PersonaName } from "../_fixtures/env";
import { getA11ySeed, go, openAs, type A11ySeed } from "../t01/helpers";

export { getA11ySeed, go };
export type { A11ySeed };

// Les tests qui révèlent un bug sont `test.fixme` (ignorés) ; T02_VERIFY=1 les rejoue
// pour prouver qu'ils échouent bien sur l'assertion visée.
export const bug = process.env.T02_VERIFY ? test : test.fixme;

export interface Session {
  ctx: BrowserContext;
  page: Page;
}

export async function newSession(browser: Browser, persona: PersonaName): Promise<Session> {
  const ctx = await browser.newContext({ locale: "fr-FR" });
  const page = await ctx.newPage();
  page.setDefaultTimeout(10_000);
  await openAs(page, persona);
  return { ctx, page };
}

// Lectures du cœur hors profil / notifications / rôles (qui servent au chrome).
export const CORE_READS = (url: string, method: string): boolean =>
  method === "GET" &&
  url.startsWith(`${CORE_URL}/v1/`) &&
  !/\/v1\/(me|notifications|roles)/.test(url);

export function docker(...args: string[]): string {
  return execFileSync("docker", args, { stdio: ["ignore", "pipe", "pipe"] }).toString();
}

export function serviceHealth(service: "worker" | "martin"): string {
  return docker(
    "inspect",
    "-f",
    "{{.State.Status}}/{{.State.Health.Status}}",
    `geostudio-${service}-1`,
  ).trim();
}

// Redémarre le service nommé et attend son statut `healthy` (borné à 120 s).
export async function startAndAwaitHealthy(service: "worker" | "martin"): Promise<void> {
  docker("start", `geostudio-${service}-1`);
  const t0 = Date.now();
  while (serviceHealth(service) !== "running/healthy") {
    if (Date.now() - t0 > 120_000) throw new Error(`${service} non healthy après 120 s`);
    await new Promise((r) => setTimeout(r, 2000));
  }
}

// Exception encadrée à la règle 6 : arrêt puis redémarrage du SEUL service nommé, avec
// attente du statut `healthy` avant de rendre la main (même en cas d'échec de `body`).
export async function withServiceStopped<T>(
  service: "worker" | "martin",
  body: () => Promise<T>,
): Promise<T> {
  docker("stop", `geostudio-${service}-1`);
  let result: T | undefined;
  let failure: unknown;
  try {
    result = await body();
  } catch (err) {
    failure = err;
  }
  await startAndAwaitHealthy(service);
  if (failure !== undefined) throw failure;
  return result as T;
}
