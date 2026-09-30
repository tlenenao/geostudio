/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { CORE_URL, type PersonaName } from "../_fixtures/env";
import { getA11ySeed, go, openAs, type A11ySeed } from "../t01/helpers";

export { getA11ySeed, go };
export type { A11ySeed };

// Les tests qui révèlent un bug sont `test.fixme` (ignorés) ; T04_VERIFY=1 les rejoue
// pour prouver qu'ils échouent bien sur l'assertion visée.
export const bug = process.env.AUDIT_VERIFY || process.env.T04_VERIFY ? test : test.fixme;

export interface Session {
  ctx: BrowserContext;
  page: Page;
}

export async function newSession(
  browser: Browser,
  persona: PersonaName,
  locale = "en-US",
  beforeLogin?: (page: Page) => Promise<void>,
): Promise<Session> {
  const ctx = await browser.newContext({ locale });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  if (beforeLogin) await beforeLogin(page);
  await openAs(page, persona);
  return { ctx, page };
}

// Toute lecture du cœur (hors profil, notifications et catalogue de rôles) répond 500.
export async function failCoreReads(page: Page): Promise<void> {
  await page.route(`${CORE_URL}/v1/**`, (route) => {
    const url = route.request().url();
    if (route.request().method() !== "GET" || /\/v1\/(me|notifications|roles\/catalog)/.test(url)) {
      return route.continue();
    }
    return route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    });
  });
}

// Toute lecture du cœur (mêmes exceptions) est retardée de `ms`.
export async function slowCoreReads(page: Page, ms: number): Promise<void> {
  await page.route(`${CORE_URL}/v1/**`, async (route) => {
    const url = route.request().url();
    if (route.request().method() !== "GET" || /\/v1\/(me|notifications|roles\/catalog)/.test(url)) {
      return route.continue();
    }
    await new Promise((r) => setTimeout(r, ms));
    return route.continue();
  });
}

export interface StateSnap {
  alerts: string[];
  status: { tag: string; spinner: boolean; text: string }[];
  retry: boolean;
  text: string;
}

export async function stateSnap(page: Page): Promise<StateSnap> {
  return page.evaluate(() => {
    const alerts = [...document.querySelectorAll("[role=alert]")].map((e) =>
      (e.textContent ?? "").trim().slice(0, 120),
    );
    const status = [...document.querySelectorAll("[role=status]")].map((e) => ({
      tag: e.tagName.toLowerCase(),
      spinner: e.querySelector(".animate-spin") !== null,
      text: (e.textContent ?? "").trim().slice(0, 60),
    }));
    const retry = [...document.querySelectorAll("button")].some((b) =>
      /réessayer/i.test(b.textContent ?? ""),
    );
    return { alerts, status, retry, text: document.body.innerText.slice(0, 2000) };
  });
}

// Parcours récursif des sources du shell (hors tests, code généré et catalogue).
export function sourceFiles(exts: string[]): string[] {
  const root = join(process.cwd(), "src");
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of readdirSync(dir)) {
      const full = join(dir, e);
      if (statSync(full).isDirectory()) {
        if (e === "generated" || e === "test") continue;
        walk(full);
      } else if (exts.some((x) => e.endsWith(x)) && !/\.test\.tsx?$/.test(e)) {
        out.push(full);
      }
    }
  };
  walk(root);
  return out.filter((f) => !/i18n\/catalog|ui\/kit\/testUtils/.test(f));
}

export function rel(f: string): string {
  return relative(process.cwd(), f);
}

export function readLines(f: string): string[] {
  return readFileSync(f, "utf8").split("\n");
}

export async function createApp(api: any, title: string, config: any): Promise<string> {
  const r = await api.send("POST", "/v1/configs", { title, config });
  if (r.status !== 201) throw new Error(`app ${r.status} ${JSON.stringify(r.body)}`);
  return r.body.itemId as string;
}
