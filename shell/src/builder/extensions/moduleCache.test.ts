// SPDX-License-Identifier: Apache-2.0
import { beforeEach, expect, test, vi } from "vitest";
import { _resetModuleCache, ensureModuleLoaded, whenElementDefined } from "./moduleCache";

beforeEach(() => _resetModuleCache());

test("calls the importer once and returns the same promise for two calls with the same URL", async () => {
  const importFn = vi.fn().mockResolvedValue({ ok: true });
  const p1 = ensureModuleLoaded("https://example.com/a.js", importFn);
  const p2 = ensureModuleLoaded("https://example.com/a.js", importFn);
  expect(p1).toBe(p2);
  await p1;
  expect(importFn).toHaveBeenCalledTimes(1);
});

test("does not share the cache across different URLs", async () => {
  const importFn = vi.fn().mockResolvedValue({ ok: true });
  await ensureModuleLoaded("https://example.com/a.js", importFn);
  await ensureModuleLoaded("https://example.com/b.js", importFn);
  expect(importFn).toHaveBeenCalledTimes(2);
});

test("a rejected import is not cached — a transient failure is retried (d24 #7)", async () => {
  const importFn = vi
    .fn()
    .mockRejectedValueOnce(new Error("network down"))
    .mockResolvedValueOnce({ ok: true });
  await expect(ensureModuleLoaded("https://example.com/flaky.js", importFn)).rejects.toThrow(
    "network down",
  );
  await expect(ensureModuleLoaded("https://example.com/flaky.js", importFn)).resolves.toEqual({
    ok: true,
  });
  expect(importFn).toHaveBeenCalledTimes(2);
});

test("the integrity is part of the cache key and is handed to the importer (AUD-109)", async () => {
  const importFn = vi.fn().mockResolvedValue({ ok: true });
  await ensureModuleLoaded("https://example.com/a.js", importFn, "sha384-AAA");
  await ensureModuleLoaded("https://example.com/a.js", importFn, "sha384-AAA");
  await ensureModuleLoaded("https://example.com/a.js", importFn, "sha384-BBB");
  expect(importFn).toHaveBeenCalledTimes(2);
  expect(importFn).toHaveBeenCalledWith("https://example.com/a.js", "sha384-AAA");
});

test("with an integrity the default loader injects a <script type=module integrity crossorigin>", async () => {
  const appended: HTMLScriptElement[] = [];
  const spy = vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
    appended.push(node as HTMLScriptElement);
    queueMicrotask(() => (node as HTMLScriptElement).onload?.(new Event("load")));
    return node;
  });
  await ensureModuleLoaded("https://example.com/sri.js", undefined, "sha384-AAA");
  spy.mockRestore();
  expect(appended).toHaveLength(1);
  expect(appended[0].type).toBe("module");
  expect(appended[0].integrity).toBe("sha384-AAA");
  expect(appended[0].crossOrigin).toBe("anonymous");
  expect(appended[0].src).toBe("https://example.com/sri.js");
});

test("a failing integrity check (script error) rejects with a readable message", async () => {
  const spy = vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
    queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event("error")));
    return node;
  });
  await expect(
    ensureModuleLoaded("https://example.com/tampered.js", undefined, "sha384-AAA"),
  ).rejects.toThrow(/integrity/);
  spy.mockRestore();
});

test("whenElementDefined resolves for a defined tag and rejects on timeout otherwise", async () => {
  customElements.define("l10-defined-widget", class extends HTMLElement {});
  await expect(whenElementDefined("l10-defined-widget")).resolves.toBeUndefined();
  await expect(whenElementDefined("l10-never-defined", 20)).rejects.toThrow(/not defined/);
});

test("defaults to a real dynamic import() when no importer is passed", async () => {
  await expect(ensureModuleLoaded("./__fixtures__/does-not-exist.ts")).rejects.toThrow();
});
