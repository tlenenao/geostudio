// SPDX-License-Identifier: Apache-2.0
// Companion to vite.copyMaplibreWorker.ts (see that file for the full
// explanation) — this module supplies the runtime half: point maplibre-gl at
// the worker file the build copied alongside this module's own compiled
// chunk. Resolved the same way maplibre-gl resolves its own default worker
// URL (`new URL(name, import.meta.url)`), so it automatically respects
// whichever `base` the current build used, and lands in the same flat
// `assets/` directory as the copied `maplibre-gl-worker.mjs` +
// `maplibre-gl-shared.mjs`.
//
// The filename is built from two literals precisely so this does NOT look
// like the `new URL("./literal.ext", import.meta.url)` shape Vite's static
// asset analysis pattern-matches on: it must stay a plain runtime URL
// computation, or Vite would try to resolve "maplibre-gl-worker.mjs"
// against this file's own directory at build time (where it doesn't exist)
// instead of leaving the string alone for the build plugin's copy to serve.
import * as maplibregl from "maplibre-gl";

const WORKER_FILENAME = ["maplibre-gl-worker", ".mjs"].join("");

maplibregl.setWorkerUrl(new URL(WORKER_FILENAME, import.meta.url).href);
