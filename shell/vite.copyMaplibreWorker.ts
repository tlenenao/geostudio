// SPDX-License-Identifier: Apache-2.0
// maplibre-gl v6 resolves its worker script at runtime relative to its own
// bundled chunk's `import.meta.url` (`new URL("./maplibre-gl-worker.mjs",
// import.meta.url)`, inside maplibre-gl's own minified source) — a pattern
// Vite's static asset analysis never sees, since it's not literally present
// in our source. Vite therefore never bundles/copies `maplibre-gl-worker.mjs`
// into the build output, so that URL 404s in a built app; the library
// swallows the failed `new Worker(...)` (try/catch, console.warn only), and
// every operation depending on the worker — tile parsing, and with it
// "load"/"idle" — hangs forever. Confirmed by e2e (map canvas renders, style
// loads, but no vector tile is ever requested and popups never open) before
// this plugin existed.
//
// A plain `?url` import of just the worker file is not enough either: the
// worker script's own first line imports `./maplibre-gl-shared.mjs` by a
// fixed relative path (not parameterisable) — Vite's `?url` handling would
// hash-rename that sibling if imported separately, breaking the reference.
// Both files must land, byte-for-byte, unhashed, next to each other, inside
// the SAME output directory as the chunk that calls `setWorkerUrl` (see
// src/map/maplibreWorkerSetup.ts, which resolves the runtime URL the same
// way maplibre-gl resolves its own: `new URL(name, import.meta.url)`, so it
// automatically respects each build's `base` — "/" here, "./" in
// vite.export.config.ts for a bundle unzipped under an arbitrary sub-path).
import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import type { Plugin } from "vite";

const WORKER_FILES = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

function copyInto(outDir: string): void {
  const srcDir = fileURLToPath(new URL("./node_modules/maplibre-gl/dist/", import.meta.url));
  mkdirSync(outDir, { recursive: true });
  for (const file of WORKER_FILES) copyFileSync(resolve(srcDir, file), resolve(outDir, file));
}

/** `assetsDir` must match each config's own `build.assetsDir` (default
 * "assets", unchanged by either shell config) — same directory Vite puts
 * every hashed JS/CSS chunk in, which is where `import.meta.url`-relative
 * resolution from a compiled chunk lands. */
export function copyMaplibreWorkerPlugin(assetsDir = "assets"): Plugin {
  let outDir = "";
  return {
    name: "copy-maplibre-worker",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir, assetsDir);
    },
    closeBundle() {
      copyInto(outDir);
    },
  };
}
