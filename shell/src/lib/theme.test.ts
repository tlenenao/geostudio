// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test } from "vitest";
import { applyThemePreference, readThemePreference, saveThemePreference } from "./theme";

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
