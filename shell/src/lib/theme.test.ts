// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import {
  applyThemePreference,
  onThemeChange,
  readThemePreference,
  saveThemePreference,
} from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test("auto par défaut : aucun attribut data-theme", () => {
  applyThemePreference(readThemePreference());
  expect(readThemePreference()).toBe("auto");
  expect(document.documentElement.dataset.theme).toBeUndefined();
});

test("sombre : persisté et appliqué au rechargement", () => {
  saveThemePreference("dark");
  delete document.documentElement.dataset.theme; // simule un nouveau chargement
  applyThemePreference(readThemePreference());
  expect(document.documentElement.dataset.theme).toBe("dark");
});

test("retour à auto : efface le réglage et l'attribut", () => {
  saveThemePreference("light");
  saveThemePreference("auto");
  expect(localStorage.getItem("gs-theme")).toBeNull();
  expect(document.documentElement.dataset.theme).toBeUndefined();
});

test("un stockage qui lève ne casse ni la lecture ni l'écriture", () => {
  const spy = Object.getPrototypeOf(localStorage);
  const get = spy.getItem;
  const set = spy.setItem;
  spy.getItem = () => {
    throw new Error("blocked");
  };
  spy.setItem = () => {
    throw new Error("blocked");
  };
  try {
    expect(readThemePreference()).toBe("auto");
    saveThemePreference("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  } finally {
    spy.getItem = get;
    spy.setItem = set;
  }
});

test("onThemeChange : notifie quand data-theme change, puis plus après désabonnement (REV-285 e)", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ addEventListener: () => {}, removeEventListener: () => {} }),
  );
  try {
    const cb = vi.fn();
    const off = onThemeChange(cb);
    document.documentElement.dataset.theme = "dark";
    await new Promise((r) => setTimeout(r, 0));
    expect(cb).toHaveBeenCalledTimes(1);
    off();
    document.documentElement.dataset.theme = "light";
    await new Promise((r) => setTimeout(r, 0));
    expect(cb).toHaveBeenCalledTimes(1);
  } finally {
    vi.unstubAllGlobals();
    delete document.documentElement.dataset.theme;
  }
});

test("onThemeChange : suit prefers-color-scheme en « auto » et se désabonne (REV-323)", () => {
  const listeners = new Set<() => void>();
  const add = vi.fn((_: string, l: () => void) => listeners.add(l));
  const remove = vi.fn((_: string, l: () => void) => listeners.delete(l));
  const mm = vi.fn().mockReturnValue({ addEventListener: add, removeEventListener: remove });
  vi.stubGlobal("matchMedia", mm);
  try {
    const cb = vi.fn();
    const off = onThemeChange(cb);
    expect(mm).toHaveBeenCalledWith("(prefers-color-scheme: dark)");
    listeners.forEach((l) => l()); // l'OS bascule clair/sombre
    expect(cb).toHaveBeenCalledTimes(1);
    off();
    expect(remove).toHaveBeenCalledWith("change", expect.any(Function));
    expect(listeners.size).toBe(0);
  } finally {
    vi.unstubAllGlobals();
  }
});
