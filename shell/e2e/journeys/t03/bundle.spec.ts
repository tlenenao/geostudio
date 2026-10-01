/* eslint-disable @typescript-eslint/no-explicit-any -- manifeste Vite, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { SHELL_URL, loginOidc } from "../_fixtures/env";
import { netLog } from "./helpers";

// Charge JS/CSS initiale du build servi (même définition que
// scripts/check-bundle-size.mjs : entrée + imports statiques, pas de dynamicImports).
async function initialFiles(request: any): Promise<{ manifest: any; files: string[] }> {
  const res = await request.get(`${SHELL_URL}/.vite/manifest.json`);
  expect(res.status()).toBe(200);
  const manifest = await res.json();
  const entry = Object.keys(manifest).find((k) => manifest[k].isEntry) as string;
  const seen = new Set<string>();
  const files = new Set<string>();
  const walk = (k: string) => {
    if (seen.has(k) || !manifest[k]) return;
    seen.add(k);
    files.add(manifest[k].file);
    (manifest[k].css ?? []).forEach((c: string) => files.add(c));
    (manifest[k].imports ?? []).forEach(walk);
  };
  walk(entry);
  return { manifest, files: [...files] };
}

test.describe("t03 bundle et livraison statique", () => {
  test("charge initiale JS/CSS dans le seuil (.bundle-size-threshold), marge mesurée", async ({
    request,
  }, testInfo) => {
    const { files } = await initialFiles(request);
    let raw = 0;
    let gz = 0;
    for (const f of files) {
      const body = Buffer.from(await (await request.get(`${SHELL_URL}/${f}`)).body());
      raw += body.length;
      gz += gzipSync(body).length;
    }
    const threshold = Number(readFileSync("./.bundle-size-threshold", "utf8").trim());
    testInfo.annotations.push({
      type: "mesure",
      description: `initial brut ${(raw / 1024).toFixed(1)} Ko / gzip ${(gz / 1024).toFixed(1)} Ko / seuil ${threshold} Ko`,
    });
    console.log(`T03 initial raw=${raw} gzip=${gz} threshold=${threshold}KB files=${files.length}`);
    // Le seuil du dépôt est calculé sur les octets bruts.
    expect(raw / 1024).toBeLessThanOrEqual(threshold);
  });

  // Le seuil (730 Ko) garde ~5 % de marge sur le mesuré (694,8 Ko).
  bug("t03-006 : la charge initiale garde 5 % de marge sous le seuil", async ({ request }) => {
    const { files } = await initialFiles(request);
    let raw = 0;
    for (const f of files)
      raw += Buffer.from(await (await request.get(`${SHELL_URL}/${f}`)).body()).length;
    const threshold = Number(readFileSync("./.bundle-size-threshold", "utf8").trim());
    expect(raw / 1024).toBeLessThan(threshold * 0.95);
  });

  test("les chunks lourds (carte, SQL Lab, pipelines) ne sont pas dans la charge initiale", async ({
    request,
  }) => {
    const { manifest, files } = await initialFiles(request);
    const heavy = Object.values<any>(manifest)
      .filter((e) =>
        /MapView|SqlLab|PipelineBuilder|vendor-map|vendor-echarts|AppBuilder/.test(e.file),
      )
      .map((e) => e.file);
    expect(heavy.length).toBeGreaterThan(3);
    for (const h of heavy) expect(files, h).not.toContain(h);
  });

  test("catalogue : aucune charge des chunks d'éditeurs, transfert mesuré", async ({
    page,
  }, testInfo) => {
    const log = await netLog(page);
    await loginOidc(page, "creator");
    await page.waitForTimeout(2500);
    const s = await log.stop();
    const shell = s.byUrl.filter((r) => r.url.startsWith(SHELL_URL));
    const kb = Math.round(shell.reduce((a, r) => a + r.kb, 0));
    testInfo.annotations.push({
      type: "mesure",
      description: `${shell.length} fichiers shell, ${kb} Ko transférés (gzip)`,
    });
    console.log("T03 catalogue shell", shell.length, kb, JSON.stringify(shell.slice(0, 6)));
    for (const r of shell)
      expect(r.url).not.toMatch(
        /MapView|SqlLab|PipelineBuilder|AppBuilder|LayersPanel|vendor-echarts/,
      );
  });

  // CatalogSpatialFilter monte une vraie carte MapLibre (WebGL + worker) dans le
  // panneau de filtres de la page d'accueil, chargeant vendor-map (932 Ko bruts + 83 Ko CSS).
  bug("t03-005 : le catalogue ne charge pas MapLibre à l'ouverture", async ({ page }) => {
    const log = await netLog(page);
    await loginOidc(page, "creator");
    await page.waitForTimeout(2500);
    const s = await log.stop();
    expect(s.byUrl.map((r) => r.url).join("\n")).not.toMatch(/vendor-map/);
  });

  // Aucun Cache-Control sur /assets/* : chaque visite revalide (If-None-Match) les
  // ~110 chunks à hachage de contenu au lieu de les servir depuis le cache.
  bug(
    "t03-001 : les assets à hachage de contenu sont servis en Cache-Control immutable",
    async ({ request }) => {
      const { files } = await initialFiles(request);
      const js = files.find((f) => f.endsWith(".js")) as string;
      const res = await request.get(`${SHELL_URL}/${js}`);
      expect(res.headers()["cache-control"] ?? "").toMatch(/immutable|max-age=\d{6,}/);
    },
  );

  // Le worker MapLibre est en octet-stream (j12-001) donc hors gzip_types : 482 Ko bruts.
  bug("t03-002 : maplibre-gl-shared.mjs est servi compressé", async ({ request }) => {
    const res = await request.get(`${SHELL_URL}/assets/maplibre-gl-shared.mjs`, {
      headers: { "accept-encoding": "gzip" },
    });
    expect(res.headers()["content-encoding"]).toBe("gzip");
  });

  // try_files ... /index.html : un chunk absent (déploiement pendant une session)
  // reçoit index.html en 200 au lieu d'un 404.
  bug("t03-003 : un asset hachagé inexistant répond 404, pas index.html", async ({ request }) => {
    const res = await request.get(`${SHELL_URL}/assets/CatalogPage-inexistant.js`);
    expect(res.status()).toBe(404);
  });

  bug(
    "t03-004 : ni manifeste de build ni fixtures de test dans l'image de production",
    async ({ request }) => {
      const m = await request.get(`${SHELL_URL}/.vite/manifest.json`);
      const f = await request.get(`${SHELL_URL}/fixtures/gauge-extension-widget.js`);
      expect([m.status(), f.status()]).toEqual([404, 404]);
    },
  );
});
