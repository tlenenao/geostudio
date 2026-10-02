/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { bug } from "../_fixtures/verify";
import {
  apiFor,
  createPipeline,
  edge,
  ensureExportsBucket,
  exportWriter,
  getPlainBig,
  reader,
  runAndTime,
  runPipeline,
  s3Lines,
  stamp,
  timed,
  waitRun,
  withPeakMem,
  type Api,
  type PNode,
} from "./helpers";

const tag = stamp("t03b");
let creator: Api;
let p50k: { id: string };
let p500k: { id: string };

const runMs = (run: any) => Date.parse(run.finishedAt) - Date.parse(run.startedAt);
const filter = (expr: string): PNode => ({
  id: "f",
  kind: "transform",
  op: "transform.filter",
  params: { expr },
});

// Collection de sortie vide typée .
async function outCollection(name: string): Promise<string> {
  const out = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-${name}`,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "cat", sqlType: "text" },
      { name: "val", sqlType: "integer" },
    ],
  });
  return out.body.id as string;
}
const collWriter = (id: string): PNode => ({
  id: "c",
  kind: "writer",
  op: "writer.collection",
  params: { collectionId: id, mode: "append" },
});

test.beforeAll(async () => {
  test.setTimeout(600_000);
  ensureExportsBucket();
  creator = await apiFor("creator");
  p50k = await getPlainBig(50_000);
  p500k = await getPlainBig(500_000);
});

test.describe("t03b exécution de pipeline sur gros volumes (ETL allumé)", () => {
  test("500 000 lignes : reader.collection -> writer.export CSV en moins de 15 s, mémoire worker < 1 Go", async () => {
    const key = `t03b/${tag}-500k.csv`;
    const m = await withPeakMem("geostudio-worker-1", () =>
      runAndTime(
        creator,
        `${tag}-exp500k`,
        [reader(p500k.id), exportWriter(key)],
        [edge("r", "w")],
      ),
    );
    const run = m.value.run;
    console.log(
      "T03B pipe500kCsv",
      run.status,
      runMs(run),
      "ms worker",
      m.startMb,
      "->",
      m.peakMb,
      "Mo",
    );
    expect(run.status, run.error).toBe("succeeded");
    expect(run.nodeStats.w.rowCount).toBe(500_000);
    expect(runMs(run)).toBeLessThan(15_000);
    expect(m.peakMb).toBeLessThan(1024);
    expect(s3Lines(key)).toBe(500_001);
  });

  test("500 000 lignes : filtre + agrégat (8 groupes) -> export en moins de 15 s", async () => {
    const r = await runAndTime(
      creator,
      `${tag}-agg500k`,
      [
        reader(p500k.id),
        filter("val > 500"),
        {
          id: "a",
          kind: "transform",
          op: "transform.aggregate",
          params: { groupBy: ["cat"], metrics: { n: "count(*)", s: "sum(val)" } },
        },
        exportWriter(`t03b/${tag}-agg500k.csv`),
      ],
      [edge("r", "f"), edge("f", "a"), edge("a", "w")],
    );
    console.log(
      "T03B pipe500kAgg",
      r.run.status,
      runMs(r.run),
      "ms",
      JSON.stringify(r.run.nodeStats),
      r.run.error ?? "",
    );
    expect(r.run.status, r.run.error).toBe("succeeded");
    expect(runMs(r.run)).toBeLessThan(15_000);
    expect(r.run.nodeStats.a.rowCount).toBe(8);
  });

  test("500 000 lignes : writer.export GeoJSON (corps construit en mémoire), pic mémoire worker < 1,5 Go", async () => {
    const key = `t03b/${tag}-500k.geojson`;
    const m = await withPeakMem("geostudio-worker-1", () =>
      runAndTime(
        creator,
        `${tag}-gj500k`,
        [reader(p500k.id), exportWriter(key, "geojson")],
        [edge("r", "w")],
      ),
    );
    const run = m.value.run;
    console.log(
      "T03B pipe500kGeojson",
      run.status,
      runMs(run),
      "ms worker",
      m.startMb,
      "->",
      m.peakMb,
      "Mo",
      run.error ?? "",
    );
    expect(run.status, run.error).toBe("succeeded");
    expect(m.peakMb).toBeLessThan(1536);
  });

  test("aperçu de pipeline sur 500 000 lignes (POST /preview) : 50 lignes en moins de 5 s", async () => {
    const p = await createPipeline(
      creator,
      `${tag}-prev500k`,
      [reader(p500k.id), filter("val > 990"), exportWriter(`t03b/${tag}-prev.csv`)],
      [edge("r", "f"), edge("f", "w")],
    );
    const r = await timed("creator", `/v1/pipelines/${p.itemId}/preview?upTo=f`, {
      method: "POST",
    });
    console.log("T03B preview500k", r.status, r.ms, "ms", r.bytes, "o");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(5000);
  });

  bug(
    "t03b-001 : writer.collection écrit 50 000 lignes en moins de 10 s (>= 5 000 lignes/s)",
    async () => {
      // Constat : _write_collection valide et INSERT ligne par ligne (validate_feature + insert_feature) :
      // ~2 000 lignes/s, soit 24,8 s pour 50k et 243,6 s pour 500k.
      const out = await outCollection("w50k");
      const r = await runAndTime(
        creator,
        `${tag}-w50k`,
        [reader(p50k.id), collWriter(out)],
        [edge("r", "c")],
      );
      console.log("T03B writer50k", r.run.status, runMs(r.run), "ms", r.run.error ?? "");
      expect(r.run.status, r.run.error).toBe("succeeded");
      expect(runMs(r.run)).toBeLessThan(10_000);
    },
  );

  bug("t03b-001 (500k) : writer.collection écrit 500 000 lignes en moins de 60 s", async () => {
    test.setTimeout(900_000);
    const out = await outCollection("w500k");
    const r = await runAndTime(
      creator,
      `${tag}-w500k`,
      [reader(p500k.id), collWriter(out)],
      [edge("r", "c")],
      800_000,
    );
    console.log("T03B writer500k", r.run.status, runMs(r.run), "ms");
    expect(r.run.status, r.run.error).toBe("succeeded");
    expect(runMs(r.run)).toBeLessThan(60_000);
  });

  bug(
    "t03b-002 : un export de 50k lignes n'attend pas la fin d'un writer.collection de 50k lignes (worker à concurrence 1)",
    async () => {
      test.setTimeout(240_000);
      const out = await outCollection("hol");
      const slow = await createPipeline(
        creator,
        `${tag}-hol-slow`,
        [reader(p50k.id), collWriter(out)],
        [edge("r", "c")],
      );
      const fast = await createPipeline(
        creator,
        `${tag}-hol-fast`,
        [reader(p50k.id), exportWriter(`t03b/${tag}-hol.csv`)],
        [edge("r", "w")],
      );
      const rs = await runPipeline(creator, slow.itemId!);
      await new Promise((r) => setTimeout(r, 4000));
      const rf = await runPipeline(creator, fast.itemId!);
      const fastRun = await waitRun(creator, fast.itemId!, rf.runId!, 180_000);
      const slowRun = await waitRun(creator, slow.itemId!, rs.runId!, 180_000);
      const startedFast = Date.parse(fastRun.startedAt);
      const finishedSlow = Date.parse(slowRun.finishedAt);
      console.log("T03B headOfLine fast start", fastRun.startedAt, "slow end", slowRun.finishedAt);
      expect(startedFast).toBeLessThan(finishedSlow - 5000);
    },
  );
});
