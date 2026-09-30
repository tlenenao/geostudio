import { test, expect } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor, psql, type Api } from "./helpers";
import { token } from "../j03/api";

// Troncature des tuiles vectorielles (MAX_TILE_FEATURES) : en-tête X-Tile-Truncated.
test.setTimeout(90_000);
let creator: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
});

async function collectionWith(n: number, title: string): Promise<string> {
  const c = await creator.send("POST", "/v1/collections/empty", {
    title,
    columns: [{ name: "nom", sqlType: "text" }],
    geometryType: "Point",
    srid: 4326,
  });
  expect(c.status).toBe(201);
  psql(
    `INSERT INTO public.${c.body.tableName} (tenant_id, nom, geom) SELECT 'default','n'||g, ST_SetSRID(ST_MakePoint(1+g*0.0001,45),4326) FROM generate_series(1,${n}) g`,
  );
  return c.body.id as string;
}

async function tile(id: string): Promise<Response> {
  const tok = await token("creator");
  return fetch(`${CORE_URL}/v1/collections/${id}/tiles/0/0/0.mvt`, {
    headers: { authorization: `Bearer ${tok}` },
  });
}

test.describe("j09 tuiles tronquées", () => {
  test("au-delà de 5000 entités la tuile est marquée tronquée", async () => {
    const id = await collectionWith(5001, "aud-j09-mvt-5001");
    const r = await tile(id);
    expect(r.status).toBe(200);
    expect(r.headers.get("x-tile-truncated")).toBe("true");
  });

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  test.fixme("j09-010 : exactement 5000 entités (aucune perdue) ne sont pas marquées tronquées", async () => {
    const id = await collectionWith(5000, "aud-j09-mvt-5000");
    const r = await tile(id);
    expect(r.status).toBe(200);
    expect(r.headers.get("x-tile-truncated")).toBeNull();
  });
});
