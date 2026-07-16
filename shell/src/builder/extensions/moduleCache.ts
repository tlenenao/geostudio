// SPDX-License-Identifier: Apache-2.0
const cache = new Map<string, Promise<unknown>>();

function defaultImport(url: string): Promise<unknown> {
  return import(/* @vite-ignore */ url);
}

export function ensureModuleLoaded(
  url: string,
  importFn: (url: string) => Promise<unknown> = defaultImport,
): Promise<unknown> {
  let p = cache.get(url);
  if (!p) {
    p = importFn(url);
    cache.set(url, p);
  }
  return p;
}

export function _resetModuleCache(): void {
  cache.clear();
}
