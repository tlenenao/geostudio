/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { apiFor, download } from "../j05/helpers";
import { getSeed, type Seed } from "../j05/seed";
import {
  createPipeline,
  deferRun,
  edge,
  exportWriter,
  reader,
  runPipeline,
  waitRun,
  type PEdge,
  type PNode,
} from "../j06b/helpers";
import { psql } from "../j02/helpers";

export {
  apiFor,
  download,
  getSeed,
  createPipeline,
  deferRun,
  edge,
  exportWriter,
  reader,
  runPipeline,
  waitRun,
  psql,
};
export type { Seed, PNode, PEdge };

export type Api = Awaited<ReturnType<typeof apiFor>>;

// Collection de sortie vide typée, comme le fait l'assistant avant d'écrire le pipeline.
export async function emptyOut(
  api: Api,
  title: string,
  columns: { name: string; sqlType: string }[],
): Promise<string> {
  const r = await api.send("POST", "/v1/collections/empty", { title, columns });
  if (r.status !== 201) throw new Error(`empty: ${JSON.stringify(r)}`);
  return r.body.id as string;
}

// Nom de table physique d'une collection (vérité terrain lisible en SQL direct).
export function tableOf(collectionId: string): string {
  return psql(`SELECT table_name FROM collections WHERE id='${collectionId}'`).trim();
}

// Lignes d'une table de sortie, triées, en tableaux de chaînes (NULL -> "∅").
export function rowsOf(collectionId: string, cols: string, order: string): string[][] {
  const out = psql(`SELECT ${cols} FROM ${tableOf(collectionId)} ORDER BY ${order}`).trim();
  return out === ""
    ? []
    : out.split("\n").map((l) => l.split("|").map((c) => (c === "" ? "∅" : c)));
}

import type { Page } from "@playwright/test";
import { spaGo } from "../j04/helpers";

export interface WizardSpec {
  title: string;
  base: string;
  filters?: { column: string; op: string; value: string }[];
  join?: { collection: string; on: string; how?: "inner" | "left" };
  summary?: {
    groupBy: string[];
    metrics: { fn: string; column?: string; p?: string }[];
  };
}

export async function fillWizard(page: Page, w: WizardSpec): Promise<void> {
  await spaGo(page, "/datasets/visual-query/new", 2500);
  await page.getByLabel("Titre", { exact: true }).fill(w.title);
  await page.getByLabel("Collection de base").selectOption(w.base);
  let n = 0;
  for (const f of w.filters ?? []) {
    n += 1;
    await page.getByRole("button", { name: "Ajouter un filtre" }).click();
    await page.getByLabel(`Colonne du filtre ${n}`).selectOption(f.column);
    await page.getByLabel(`Opérateur du filtre ${n}`).selectOption(f.op);
    await page.getByLabel(`Valeur du filtre ${n}`).fill(f.value);
  }
  if (w.join) {
    await page.getByRole("button", { name: "Ajouter une jointure" }).click();
    await page.getByLabel("Collection à joindre").selectOption(w.join.collection);
    await page.getByLabel("Colonne de jointure").selectOption(w.join.on);
    if (w.join.how) await page.getByLabel("Type de jointure").selectOption(w.join.how);
  }
  if (w.summary) {
    await page.getByRole("button", { name: "Ajouter un résumé" }).click();
    for (const g of w.summary.groupBy) await page.getByLabel(`Regrouper par ${g}`).check();
    let m = 0;
    for (const metric of w.summary.metrics) {
      m += 1;
      await page.getByRole("button", { name: "Ajouter une métrique" }).click();
      await page.getByLabel(`Fonction de la métrique ${m}`).selectOption(metric.fn);
      if (metric.column)
        await page.getByLabel(`Colonne de la métrique ${m}`).selectOption(metric.column);
      if (metric.p) await page.getByLabel(`Centile de la métrique ${m}`).fill(metric.p);
    }
  }
}

export interface WizardResult {
  pipelineItem: string;
  datasetItem: string;
  outCollection: string;
  runId: string;
  run: any;
  httpStatus: number;
}

// Clique « Créer », constate le 500 d'AppNotOpen (j06b-001), puis défère le run depuis le worker
// (contournement des agents précédents) et attend sa fin.
export async function submitWizard(
  page: Page,
  title: string,
  { patch = true }: { patch?: boolean } = {},
): Promise<WizardResult> {
  const creator = await apiFor("creator");
  const resp = page.waitForResponse(
    (r) => /\/v1\/pipelines\/[0-9a-f]+\/run$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  const r = await resp;
  const pipelineItem = /pipelines\/([0-9a-f]+)\/run/.exec(r.url())![1];
  const runs = psql(
    `SELECT id FROM pipeline_runs WHERE pipeline_item_id='${pipelineItem}' ORDER BY created_at DESC`,
  )
    .trim()
    .split("\n");
  const runId = runs[0];
  const outCollection = psql(
    `SELECT id FROM collections WHERE title='${title} (données)' ORDER BY created_at DESC LIMIT 1`,
  ).trim();
  // Contournement de j02-003 : la table de sortie (POST /collections/empty) exige tenant_id côté
  // validate_feature ; un DEFAULT la rend non « required » et laisse le writer écrire.
  if (patch)
    psql(`ALTER TABLE ${tableOf(outCollection)} ALTER COLUMN tenant_id SET DEFAULT 'default'`);
  if (r.status() !== 202) deferRun(runId);
  const run = await waitRun(creator, pipelineItem, runId);
  const datasetItem = psql(
    `SELECT id FROM items WHERE resource_type='dataset' AND title='${title}' ORDER BY created_at DESC LIMIT 1`,
  ).trim();
  return { pipelineItem, datasetItem, outCollection, runId, run, httpStatus: r.status() };
}
