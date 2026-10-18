// SPDX-License-Identifier: Apache-2.0
// AUD-019 / D8 : mécanisme de langue + parité du catalogue anglais.
import { afterEach, describe, expect, it } from "vitest";
import { compareText, formatBytes, formatDateTime, formatNumber } from "../lib/format";
import { allMessages } from "./domains/all";
import { enMessages } from "./en/all";
import { activateLocale, detectLocale, getLocale, plural, t } from "./index";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

afterEach(async () => {
  localStorage.clear();
  await activateLocale("fr");
});

describe("catalogue anglais", () => {
  it("couvre exactement les clés du français, mêmes {paramètres}", () => {
    expect(Object.keys(enMessages).sort()).toEqual(Object.keys(allMessages).sort());
    const bad = Object.entries(allMessages).filter(
      ([k, v]) => JSON.stringify(placeholders(v)) !== JSON.stringify(placeholders(enMessages[k])),
    );
    expect(bad.map(([k]) => k)).toEqual([]);
  });
});

describe("locale active", () => {
  it("t() suit la locale, repli fr sur clé absente, lang posé sur <html>", async () => {
    expect(getLocale()).toBe("fr");
    const fr = t("actions.edit");
    await activateLocale("en");
    expect(t("actions.edit")).toBe(enMessages["actions.edit"]);
    expect(t("actions.edit")).not.toBe(fr);
    expect(document.documentElement.lang).toBe("en");
  });

  it("plural suit Intl.PluralRules en anglais, la règle fr (0 singulier) en français", async () => {
    expect(plural(0, "actions.edit", "actions.menu")).toBe("actions.edit");
    await activateLocale("en");
    expect(plural(0, "actions.edit", "actions.menu")).toBe("actions.menu");
    expect(plural(1, "actions.edit", "actions.menu")).toBe("actions.edit");
  });

  it("detectLocale : préférence stockée, sinon navigateur, sinon fr", () => {
    localStorage.setItem("gs.locale", "en");
    expect(detectLocale()).toBe("en");
    localStorage.setItem("gs.locale", "fr");
    expect(detectLocale()).toBe("fr");
    localStorage.clear();
    expect(detectLocale()).toBe("en"); // jsdom : navigator.language = en-US
  });

  it("les formats suivent la langue (nombre, octets, tri accentué)", async () => {
    expect(formatNumber(1234.5)).toBe("1 234,5");
    expect(formatBytes(2048)).toBe("2 Ko");
    await activateLocale("en");
    expect(formatNumber(1234.5)).toBe("1,234.5");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatDateTime("2026-07-01T00:30:00+02:00")).toContain("01/07/2026");
    expect(["Zone", "Étage", "abc"].sort(compareText)).toEqual(["abc", "Étage", "Zone"]);
  });
});
