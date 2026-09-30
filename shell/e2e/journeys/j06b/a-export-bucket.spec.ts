import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { apiFor } from "../j03/api";
import { stamp } from "../_fixtures/env";
import {
  createPipeline,
  edge,
  exportWriter,
  getPlainSeed,
  reader,
  runPipeline,
  waitRun,
} from "./helpers";

// Doit tourner AVANT tout autre fichier : le bucket des exports n'existe pas sur une stack
// neuve et seul un export « classique » (app.export.jobs) le crée (les autres specs appellent
// ensureExportsBucket()).
test.describe("j06b writer.export sur stack neuve", () => {
  // Finding j06b-003 : writer.export ne crée pas le bucket → NoSuchBucket au premier run.
  bug("j06b-003 : le premier run d'un writer.export réussit sur un MinIO neuf", async () => {
    const creator = await apiFor("creator");
    const seed = await getPlainSeed();
    const p = await createPipeline(
      creator,
      `${stamp("j06b")}-bucket`,
      [reader(seed.collection), exportWriter("j06b/bucket.csv")],
      [edge("r", "w")],
    );
    const run = await runPipeline(creator, p.itemId!);
    const fin = await waitRun(creator, p.itemId!, run.runId!);
    expect(fin.error ?? "").not.toContain("NoSuchBucket");
    expect(fin.status).toBe("succeeded");
  });
});
