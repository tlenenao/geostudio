/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { stamp } from "../_fixtures/env";
import { apiFor, fixture, ingest } from "./api";

export interface Seed {
  tag: string;
  pointsItem: string;
  pointsCollection: string;
}

const CACHE = join(tmpdir(), "aud-j03-seed.json");

// Import d'une carte de points (12 entités, champs nom/cat/val/pop) partagé par
// les specs UI/API de j03. Mis en cache disque : un import coûte ~10 s (rattrapage
// du défaut j03-001, cf. api.ts).
export async function getSeed(): Promise<Seed> {
  const creator = await apiFor("creator");
  if (existsSync(CACHE)) {
    const cached = JSON.parse(readFileSync(CACHE, "utf8")) as Seed;
    const r = await creator.get(`/v1/items/${cached.pointsItem}`);
    if (r.status === 200) return cached;
  }
  const tag = stamp("j03");
  const res = await ingest(creator, "points.geojson", fixture("points.geojson"), {
    collectionTitle: `${tag}-points`,
  });
  if (res.job?.status !== "done") throw new Error(`seed ingest: ${JSON.stringify(res)}`);
  const seed: Seed = {
    tag,
    pointsItem: res.job.itemId,
    pointsCollection: res.job.collectionId,
  };
  writeFileSync(CACHE, JSON.stringify(seed));
  return seed;
}

export async function mapConfig(api: Awaited<ReturnType<typeof apiFor>>, pk: string): Promise<any> {
  return (await api.get(`/v1/configs/by-item/${pk}`)).body;
}
