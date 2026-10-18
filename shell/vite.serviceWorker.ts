// SPDX-License-Identifier: Apache-2.0
// L8 : émet `dist/sw.js` à partir de `sw/sw.template.js` avec l'identifiant de build et la liste de
// précache : le graphe STATIQUE de l'entrée (démarrage du shell) + celui de la page de collecte
// publique (`/collect/:token`, lazy), seule route qui doit s'ouvrir hors-ligne dès la première
// visite. Les autres chunks sont mis en cache à l'usage (cf. le modèle). `apply: "build"` : jamais
// de SW en `vite dev`.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import type { Plugin, Rollup } from "vite";

const OPTIONAL = ["/env-config.js", "/manifest.webmanifest", "/icons/icon.svg"];
const COLLECT_PAGE = "/src/pages/CollectPage.tsx";
// Chargés à la demande par le fournisseur de file : doivent exister hors-ligne dès la première visite.
const OFFLINE_MODULES = [
  "/src/offline/outbox.ts",
  "/src/offline/sync.ts",
  "/src/offline/transport.ts",
];

export function buildServiceWorker(
  template: string,
  critical: string[],
  optional: string[],
  seed: string,
): string {
  const id = createHash("sha256")
    .update(seed)
    .update(critical.join("\n"))
    .digest("hex")
    .slice(0, 12);
  return template
    .replace("__BUILD_ID__", id)
    .replace("__PRECACHE_CRITICAL__", JSON.stringify(critical))
    .replace("__PRECACHE_OPTIONAL__", JSON.stringify(optional));
}

export function serviceWorkerPlugin(): Plugin {
  return {
    name: "gs-service-worker",
    apply: "build",
    generateBundle(_options, bundle) {
      const chunks = Object.values(bundle).filter(
        (o): o is Rollup.OutputChunk => o.type === "chunk",
      );
      const byFile = new Map(chunks.map((c) => [c.fileName, c]));
      const files = new Set<string>();
      const walk = (fileName: string) => {
        if (files.has(fileName)) return;
        const chunk = byFile.get(fileName);
        if (!chunk) return;
        files.add(fileName);
        chunk.imports.forEach(walk);
        for (const css of chunk.viteMetadata?.importedCss ?? []) files.add(css);
      };
      const entry = chunks.find((c) => c.isEntry);
      const collect = chunks.find((c) =>
        Object.keys(c.modules).some((m) => m.replaceAll("\\", "/").endsWith(COLLECT_PAGE)),
      );
      if (!entry || !collect) {
        this.error("service worker : entrée ou page de collecte introuvable dans le bundle");
      }
      walk(entry.fileName);
      walk(collect.fileName);
      const isOffline = (c: Rollup.OutputChunk) =>
        Object.keys(c.modules).some((m) =>
          OFFLINE_MODULES.some((o) => m.replaceAll("\\", "/").endsWith(o)),
        );
      for (const c of chunks) if (isOffline(c)) walk(c.fileName);
      // Chunks-façades (aucun module propre : simple réexport) du même import dynamique.
      for (const c of chunks)
        for (const d of c.dynamicImports) {
          const t = byFile.get(d);
          if (t && Object.keys(t.modules).length === 0 && t.imports.some((i) => files.has(i)))
            walk(d);
        }
      const index = bundle["index.html"];
      const indexSource = index && index.type === "asset" ? String(index.source) : "";
      const critical = ["/index.html", ...[...files].sort().map((f) => `/${f}`)];
      this.emitFile({
        type: "asset",
        fileName: "sw.js",
        source: buildServiceWorker(
          readFileSync(new URL("./sw/sw.template.js", import.meta.url), "utf-8"),
          critical,
          OPTIONAL,
          indexSource,
        ),
      });
    },
  };
}
