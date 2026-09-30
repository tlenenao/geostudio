import AxeBuilder from "@axe-core/playwright";
import { test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { loginOidc, type PersonaName } from "../_fixtures/env";
import { spaGo } from "../j02/helpers";
import { getA11ySeed, type A11ySeed } from "../t01/helpers";

export { getA11ySeed };
export type { A11ySeed };

// Les tests qui révèlent un bug sont `test.fixme` ; T01B_VERIFY=1 les rejoue pour prouver
// qu'ils échouent bien sur l'assertion visée.
export const bug = process.env.AUDIT_VERIFY || process.env.T01B_VERIFY ? test : test.fixme;

export interface Session {
  ctx: BrowserContext;
  page: Page;
}

export async function session(
  browser: Browser,
  persona: PersonaName,
  colorScheme: "light" | "dark" = "light",
): Promise<Session> {
  const ctx = await browser.newContext({ colorScheme });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  await loginOidc(page, persona);
  await page.waitForTimeout(800);
  return { ctx, page };
}

export async function go(page: Page, path: string, settleMs = 2000): Promise<void> {
  await spaGo(page, path, settleMs);
}

// Violations axe graves (critical/serious) ; `region`, `landmark-one-main` et
// `page-has-heading-one` sont « moderate » et déjà couverts par t01-001/003.
export async function seriousViolations(page: Page): Promise<string[]> {
  const r = await new AxeBuilder({ page }).analyze();
  return r.violations
    .filter((v) => v.impact === "critical" || v.impact === "serious")
    .map((v) => `${v.id} x${v.nodes.length}: ${v.nodes[0]?.target.join(" ")}`);
}

export async function focusDesc(page: Page): Promise<string> {
  return page.evaluate(() => {
    const a = document.activeElement as HTMLElement | null;
    if (!a || a === document.body) return "body";
    return `${a.tagName.toLowerCase()}|${a.getAttribute("role") ?? ""}|${(a.getAttribute("aria-label") || a.textContent || "").trim().slice(0, 40)}`;
  });
}
