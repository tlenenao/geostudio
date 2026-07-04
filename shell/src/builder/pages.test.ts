import { expect, test } from "vitest";
import { getPages, getPageLayout, setPageLayout } from "./pages";
import type { AppConfig, AppLayout } from "../api/types";

const layout: AppLayout = { type: "grid", breakpoints: {}, items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {} }] };
const baseConfig: AppConfig = { kind: "app", theme: {}, dataSources: [], messages: [], layout };

test("getPages returns a single implicit page when config.pages is absent", () => {
  expect(getPages(baseConfig)).toEqual([{ id: "page-1", name: "Page 1", layout }]);
});

test("getPages returns the explicit pages array when present", () => {
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout }];
  expect(getPages({ ...baseConfig, pages })).toBe(pages);
});

test("getPageLayout resolves the matching page's layout", () => {
  const otherLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout: otherLayout }];
  expect(getPageLayout({ ...baseConfig, pages }, "p2")).toBe(otherLayout);
});

test("getPageLayout falls back to the base layout for an unknown pageId", () => {
  expect(getPageLayout(baseConfig, "nope")).toBe(layout);
});

test("setPageLayout on an implicit-page config only updates the top-level layout", () => {
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const next = setPageLayout(baseConfig, "page-1", newLayout);
  expect(next.layout).toBe(newLayout);
  expect(next.pages).toBeUndefined();
});

test("setPageLayout on an explicit-pages config updates only the matching page and mirrors pages[0] into layout", () => {
  const otherLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout: otherLayout }];
  const cfg = { ...baseConfig, pages };
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [{ id: "z", widget: "text", x: 1, y: 1, w: 1, h: 1, props: {} }] };
  const next = setPageLayout(cfg, "p2", newLayout);
  expect(next.pages![1].layout).toBe(newLayout);
  expect(next.pages![0].layout).toBe(layout); // untouched
  expect(next.layout).toBe(layout); // mirrors pages[0], unchanged since p1 wasn't edited
});

test("setPageLayout on an implicit-page config ignores an unrelated pageId", () => {
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const next = setPageLayout(baseConfig, "not-a-real-page", newLayout);
  expect(next).toBe(baseConfig);
});
