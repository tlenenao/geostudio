import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readLines, rel, sourceFiles } from "./helpers";

// Les trois garde-fous de tokens/i18n du dépôt passent bien : preuve que le « vert » de
// `npm run lint` est réel avant de chercher ce qu'ils ne voient pas.
test.describe("garde-fous de tokens et d'i18n (sources)", () => {
  test("les trois scripts de garde sortent en succès et aucune couleur arbitraire ne subsiste hors kit/map", () => {
    for (const script of [
      "check-raw-colors.mjs",
      "check-arbitrary-text-size.mjs",
      "check-i18n-coverage.mjs",
    ]) {
      const out = execFileSync("node", [`scripts/${script}`], { cwd: process.cwd() }).toString();
      expect(out, script).toMatch(/^OK/);
    }
    const bad: string[] = [];
    for (const f of sourceFiles([".tsx"])) {
      if (/src\/(ui\/kit|map)\//.test(f)) continue;
      readLines(f).forEach((l, i) => {
        if (l.includes("gs-raw-color-ok")) return;
        if (/\b(bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]/.test(l)) {
          bad.push(`${rel(f)}:${i + 1}`);
        }
      });
    }
    expect(bad).toEqual([]);
  });

  // Finding t04-018 : check-i18n-coverage.mjs ne lit que les .tsx et ne reconnaît pas les
  // gabarits (backticks) : du français d'interface vit hors catalogue sans alerter la CI.
  test("t04-018 : aucun libellé français d'interface hors du catalogue i18n", () => {
    const accent = /[àâäéèêëïîôöùûüçÀÂÉÈÊÎÔÙÛÇ]/;
    const skip = /console\.|throw new Error|^\s*(\/\/|\*|\/\*)|localStorage|description:/;
    const offenders: string[] = [];
    for (const f of sourceFiles([".ts", ".tsx"])) {
      // TriptychLayout (prose de commentaire JSX) et SqlLabPage (console.warn multiligne) : faux positifs.
      if (/src\/(builder\/copilot|test)\/|TriptychLayout|SqlLabPage/.test(f)) continue;
      const lines = readLines(f);
      // Exemptions justifiées du détecteur (`i18n-ok-file` / `i18n-ok`), comme check-i18n-coverage.mjs.
      if (lines.some((x) => x.includes("i18n-ok-file"))) continue;
      lines.forEach((l, i) => {
        if (skip.test(l) || /i18n-ok/.test(l) || /i18n-ok/.test(lines[i - 1] ?? "")) return;
        const literals = [...l.matchAll(/`([^`]*)`|"([^"\\]*)"/g)].map((m) => m[1] ?? m[2] ?? "");
        if (literals.some((v) => accent.test(v))) offenders.push(`${rel(f)}:${i + 1}`);
      });
    }
    // Observé : aggregates.ts, chartOption.ts, resourceTypes.ts, templates.ts, pipeline/validation.ts,
    // GridCanvas.tsx, api/domains/*.ts, CoreUnreachableError.ts...
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});
