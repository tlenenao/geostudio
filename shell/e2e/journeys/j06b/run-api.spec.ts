/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { apiFor, type Api, getGeoSeed } from "./seeds";
import { stamp } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import {
  createPipeline,
  createPlainCollection,
  edge,
  ensureExportsBucket,
  exportWriter,
  getPlainSeed,
  reader,
  runPipeline,
  s3Get,
  s3Put,
  waitRun,
  type PNode,
} from "./helpers";

// Exécution réelle de pipelines (CORE_ETL_ENABLED=true) : worker `etl`, DuckDB, MinIO.
const tag = stamp("j06b");
let creator: Api;
let plain: string;

test.beforeAll(async () => {
  creator = await apiFor("creator");
  plain = (await getPlainSeed()).collection;
  ensureExportsBucket();
});

async function runAndWait(itemId: string): Promise<any> {
  const run = await runPipeline(creator, itemId);
  expect(run.runId, JSON.stringify(run.body)).toBeTruthy();
  return waitRun(creator, itemId, run.runId!);
}

const filter = (expr: string, id = "f"): PNode => ({
  id,
  kind: "transform",
  op: "transform.filter",
  params: { expr },
});

test.describe("j06b exécution de pipelines", () => {
  // Finding j06b-001 (racine j03-001) : defer() hors app.open() → 500 alors que le run est créé.
  test("j06b-001 : POST /pipelines/{id}/run répond 202 avec le runId", async () => {
    const p = await createPipeline(
      creator,
      `${tag}-run202`,
      [reader(plain), exportWriter(`j06b/${tag}-202.csv`)],
      [edge("r", "w")],
    );
    const r = await creator.send("POST", `/v1/pipelines/${p.itemId}/run`);
    expect(r.status).toBe(202);
    expect(r.body.runId).toBeTruthy();
  });

  // Finding j06b-002 (miroir pipeline de j05-001) : reader.collection lit `geom`, le GeoParquet porte `geometry`.
  bug("j06b-002 : reader.collection lit une collection à géométrie importée", async () => {
    const geo = await getGeoSeed();
    const p = await createPipeline(
      creator,
      `${tag}-geo`,
      [reader(geo.pointsCollection), exportWriter(`j06b/${tag}-geo.csv`)],
      [edge("r", "w")],
    );
    const fin = await runAndWait(p.itemId!);
    expect(fin.error ?? "").not.toContain("geom");
    expect(fin.status).toBe("succeeded");
  });

  test("filter + derive → writer.export CSV : lignes attendues et nodeStats par nœud", async () => {
    const key = `j06b/${tag}-nominal.csv`;
    const p = await createPipeline(
      creator,
      `${tag}-nominal`,
      [
        reader(plain),
        filter("pop > 5"),
        {
          id: "d",
          kind: "transform",
          op: "transform.derive",
          params: { column: "pop2", expr: "pop * 2" },
        },
        exportWriter(key),
      ],
      [edge("r", "f"), edge("f", "d"), edge("d", "w")],
    );
    const fin = await runAndWait(p.itemId!);
    expect(fin.status, fin.error).toBe("succeeded");
    expect(Object.keys(fin.nodeStats).sort()).toEqual(["d", "f", "r", "w"]);
    expect(fin.nodeStats.r.rowCount).toBe(6);
    expect(fin.nodeStats.f.rowCount).toBe(4);
    const csv = s3Get(`default/pipelines/${key}`) ?? "";
    const lines = csv.trim().split(/\r?\n/);
    expect(lines).toHaveLength(5);
    expect(lines[0]).toContain("pop2");
    expect(csv).toContain(",80");
  });

  // Finding j06b-004 : la clé de writer.export n'est ni préfixée par le tenant ni restreinte.
  test("j06b-004 : writer.export n'écrase pas un objet étranger du bucket des exports", async () => {
    const victim = `renders/${tag}-victim.txt`;
    s3Put(victim, "ORIGINAL");
    const p = await createPipeline(
      creator,
      `${tag}-overwrite`,
      [reader(plain), exportWriter(victim)],
      [edge("r", "w")],
    );
    await runAndWait(p.itemId!);
    expect(s3Get(victim)).toBe("ORIGINAL");
  });

  test("schéma qui change : colonne supprimée après enregistrement → run failed + notification au propriétaire", async () => {
    const col = await createPlainCollection(creator, `${tag}-drop`, [
      ["a", 1],
      ["b", 7],
    ]);
    const p = await createPipeline(
      creator,
      `${tag}-drop`,
      [reader(col), filter("pop > 5"), exportWriter(`j06b/${tag}-drop.csv`)],
      [edge("r", "f"), edge("f", "w")],
    );
    expect((await runAndWait(p.itemId!)).status).toBe("succeeded");
    psql(`ALTER TABLE "${col}" DROP COLUMN pop`);
    const fin = await runAndWait(p.itemId!);
    expect(fin.status).toBe("failed");
    expect(fin.error).toContain("pop");
    const notes = await creator.get("/v1/notifications");
    const list: any[] = notes.body.notifications ?? notes.body.items ?? notes.body;
    expect(JSON.stringify(list)).toContain(`${tag}-drop`);
  });

  // Finding j06b-007 : l'erreur d'exécution est le texte brut de DuckDB (SQL interne, noms de vues).
  test("j06b-007 : l'erreur d'un run échoué est un message métier, pas du SQL DuckDB brut", async () => {
    const col = await createPlainCollection(creator, `${tag}-rawerr`, [["a", 1]]);
    const p = await createPipeline(
      creator,
      `${tag}-rawerr`,
      [reader(col), filter("colonne_inconnue > 5"), exportWriter(`j06b/${tag}-rawerr.csv`)],
      [edge("r", "f"), edge("f", "w")],
    );
    const fin = await runAndWait(p.itemId!);
    expect(fin.status).toBe("failed");
    expect(fin.error).not.toMatch(/erreur interne|LINE 1|node_f|Binder Error/);
  });

  // Finding j06b-008 : une colonne ajoutée à la table (DBA) n'existe pas dans le GeoParquet → reader en échec.
  bug(
    "j06b-008 : colonne ajoutée après l'écriture du GeoParquet → le run ne casse pas",
    async () => {
      const col = await createPlainCollection(creator, `${tag}-add`, [["a", 1]]);
      psql(`ALTER TABLE "${col}" ADD COLUMN extra text`);
      const p = await createPipeline(
        creator,
        `${tag}-add`,
        [reader(col), exportWriter(`j06b/${tag}-add.csv`)],
        [edge("r", "w")],
      );
      const fin = await runAndWait(p.itemId!);
      expect(fin.status, fin.error).toBe("succeeded");
    },
  );

  test("échecs de run lisibles : secret absent, SSRF 169.254.169.254, reader.file (flag éteint)", async () => {
    const W = exportWriter(`j06b/${tag}-fail.csv`);
    const rest = (params: Record<string, unknown>): PNode => ({
      id: "r",
      kind: "reader",
      op: "reader.connector.rest",
      params,
    });
    const mkAndRun = async (name: string, r: PNode) => {
      const p = await createPipeline(creator, `${tag}-${name}`, [r, W], [edge("r", "w")]);
      expect(p.status).toBe(201);
      return { id: p.itemId!, fin: await runAndWait(p.itemId!) };
    };
    const noSecret = await mkAndRun(
      "nosecret",
      rest({ baseUrl: "https://example.org", secretName: `${tag}-inexistant` }),
    );
    expect(noSecret.fin.status).toBe("failed");
    expect(noSecret.fin.error).toContain(`${tag}-inexistant`);
    expect(noSecret.fin.error).not.toMatch(/Traceback|File "/);

    const ssrf = await mkAndRun(
      "ssrf",
      rest({ baseUrl: "http://169.254.169.254", path: "/latest/meta-data/" }),
    );
    expect(ssrf.fin.status).toBe("failed");
    expect(ssrf.fin.error).toMatch(/egress|interdit|refus|blocked|private|not allowed/i);

    // Enregistrement accepté (registre brut), exécution et aperçu refusés sans lire le fichier.
    const file = await mkAndRun("file", {
      id: "r",
      kind: "reader",
      op: "reader.file",
      params: { path: "/etc/passwd" },
    });
    expect(file.fin.status).toBe("failed");
    expect(JSON.stringify(file.fin)).not.toContain("root:");
    const prev = await creator.send("POST", `/v1/pipelines/${file.id}/preview?upTo=r`);
    expect(prev.status).toBe(400);
    expect(JSON.stringify(prev.body)).not.toContain("root:");
  });

  // Finding j06b-005 : le service `worker` n'a pas CORE_SECRETS_MASTER_KEY (docker-compose.yml, bloc worker).
  test("j06b-005 : un run dont un reader référence un secret valide déchiffre ce secret dans le worker", async () => {
    const secretName = `${tag}-bearer`;
    const s = await creator.send("POST", "/v1/secrets", {
      name: secretName,
      payload: { kind: "bearer_token", token: "tok-j06b" },
    });
    expect(s.status).toBe(201);
    const p = await createPipeline(
      creator,
      `${tag}-secret`,
      [
        {
          id: "r",
          kind: "reader",
          op: "reader.connector.rest",
          params: { baseUrl: "https://example.org", secretName },
        },
        exportWriter(`j06b/${tag}-secret.csv`),
      ],
      [edge("r", "w")],
    );
    const fin = await runAndWait(p.itemId!);
    expect(fin.error ?? "").not.toContain("CORE_SECRETS_MASTER_KEY");
  });

  // Confirme j06-015 : deux /run successifs créent deux runs simultanés du même pipeline.
  bug("j06b-006 : un second /run pendant qu'un run est en cours est refusé (409)", async () => {
    const p = await createPipeline(
      creator,
      `${tag}-double`,
      [reader(plain), exportWriter(`j06b/${tag}-double.csv`)],
      [edge("r", "w")],
    );
    const a = await runPipeline(creator, p.itemId!);
    const b = await runPipeline(creator, p.itemId!);
    expect(a.runId).toBeTruthy();
    // b peut répondre 500 (j06b-001) APRÈS avoir créé son run : on compte donc les lignes.
    const n = psql(`SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id='${p.itemId}'`);
    expect(Number(n.trim()), JSON.stringify(b.body)).toBe(1);
  });
});
