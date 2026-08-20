// SPDX-License-Identifier: Apache-2.0
import { beforeEach, expect, test, vi } from "vitest";
import { _resetModuleCache, ensureModuleLoaded } from "./moduleCache";

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

test("caches a rejected import too — a second call does not retry", async () => {
  const importFn = vi.fn().mockRejectedValue(new Error("network down"));
  await expect(ensureModuleLoaded("https://example.com/broken.js", importFn)).rejects.toThrow(
    "network down",
  );
  await expect(ensureModuleLoaded("https://example.com/broken.js", importFn)).rejects.toThrow(
    "network down",
  );
  expect(importFn).toHaveBeenCalledTimes(1);
});

test("defaults to a real dynamic import() when no importer is passed", async () => {
  await expect(ensureModuleLoaded("./__fixtures__/does-not-exist.ts")).rejects.toThrow();
});
