import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { getSeed } from "./seed";

test.describe("j02 lecteur — recherche, pièces jointes, écriture de données", () => {
  test("recherche : un titre partagé est trouvé, jamais un item privé", async () => {
    const s = await getSeed();
    const found = await s.reader.get(
      `/v1/items?q=${encodeURIComponent(`${s.tag}-carte`)}&pageSize=50`,
    );
    expect(found.status).toBe(200);
    const titles: string[] = found.body.items.map((i: { title: string }) => i.title);
    expect(titles).toContain(`${s.tag}-carte`);
    expect(titles).not.toContain(`${s.tag}-carte-privee`);
    const priv = await s.reader.get(
      `/v1/items?q=${encodeURIComponent(`${s.tag}-ds-prive`)}&pageSize=50`,
    );
    expect((priv.body.items as { title: string }[]).map((i) => i.title)).not.toContain(
      `${s.tag}-ds-prive`,
    );
  });

  test("recherche : caractères spéciaux et requêtes limites répondent 200 sans erreur", async () => {
    const s = await getSeed();
    for (const q of [
      "%",
      "_",
      "'; drop table items;--",
      "\\",
      "é",
      "<script>alert(1)</script>",
      "a".repeat(3000),
    ]) {
      const r = await s.reader.get(`/v1/items?q=${encodeURIComponent(q)}`);
      expect(r.status, q.slice(0, 20)).toBe(200);
    }
    expect((await s.reader.get("/v1/items?pageSize=0")).status).toBe(422);
    expect((await s.reader.get("/v1/items?bbox=1,2")).status).toBe(422);
    const beyond = await s.reader.get("/v1/items?page=9999");
    expect(beyond.body.items).toEqual([]);
  });

  test("pièces jointes : le lecteur liste (vide) mais ne peut pas déposer (403)", async () => {
    const s = await getSeed();
    const list = await s.reader.get(`/v1/collections/${s.sharedCol}/items/1/attachments`);
    expect(list.status).toBe(200);
    expect(list.body.attachments).toEqual([]);
    const presign = await s.reader.send(
      "POST",
      `/v1/collections/${s.sharedCol}/items/1/attachments/presign`,
      {
        fieldKey: "photo",
        filename: "a.png",
        contentType: "image/png",
      },
    );
    expect(presign.status).toBe(403);
  });

  // j02-002 : le présigné d'upload appelle put_bucket_cors, non implémenté par le MinIO reconstruit.
  bug("j02-002 : le propriétaire peut obtenir une URL présignée de pièce jointe", async () => {
    const s = await getSeed();
    const presign = await s.creator.send(
      "POST",
      `/v1/collections/${s.sharedCol}/items/1/attachments/presign`,
      {
        fieldKey: "photo",
        filename: "a.png",
        contentType: "image/png",
      },
    );
    expect(presign.status).toBe(200);
    expect(presign.body.uploadUrl).toBeTruthy();
    const up = await s.creator.send("POST", "/v1/uploads/presign", {
      filename: "aud.geojson",
      contentType: "application/geo+json",
    });
    expect(up.status).toBe(200);
  });

  // j02-003 : une collection créée vide refuse toute entité (tenant_id « requis »).
  test("j02-003 : une collection créée vide accepte une première entité via OGC API", async () => {
    const s = await getSeed();
    const col = await s.creator.send("POST", "/v1/collections/empty", {
      title: `${s.tag}-vide`,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    expect(col.status).toBe(201);
    const feat = await s.creator.send("POST", `/v1/collections/${col.body.id}/items`, {
      type: "Feature",
      geometry: { type: "Point", coordinates: [1.5, 45.2] },
      properties: { nom: "Alpha" },
    });
    expect(feat.status).toBe(201);
  });
});
