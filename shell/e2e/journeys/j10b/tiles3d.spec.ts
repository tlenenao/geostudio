import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { stamp } from "../_fixtures/env";
import { token } from "../j03/api";
import { apiFor, type Api } from "./helpers";

test.setTimeout(120_000);
const tag = stamp("j10b");
let creator: Api;
let reader: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
  reader = await apiFor("reader");
});

// L'envoi multipart est inutilisable (j10b-012) : on dépose le zip dans le
// bucket, on crée la ligne de job puis on rejoue finalize_tileset3d_task dans
// le worker (la config tileset3d ne peut être créée que par cette tâche).
function seedTileset(title: string, ownerId: string): { itemId: string; out: string } {
  const key = `default/${tag}/${title}.zip`;
  const out = execFileSync(
    "docker",
    ["exec", "-i", "-w", "/app", "-e", "PYTHONPATH=/app", "geostudio-worker-1", "python", "-"],
    {
      input: [
        "import io, os, zipfile",
        "from app.appexport.jobs import s3_client_from_env",
        "from app.db import request_scoped_session",
        "from app.tileset3d import repository as repo",
        "from app.tileset3d.jobs import finalize_tileset3d_task, _session_factory",
        "b = io.BytesIO()",
        "z = zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED)",
        'z.writestr(\'tileset.json\', \'{"asset":{"version":"1.0"},"geometricError":1,"root":{}}\')',
        "z.writestr('a.b3dm', b'b3dm-bytes')",
        "z.close()",
        "bucket = os.environ.get('S3_TILESET3D_BUCKET','geostudio-tileset3d')",
        `s3_client_from_env().put_object(Bucket=bucket, Key='${key}', Body=b.getvalue())`,
        "with request_scoped_session(_session_factory()) as s:",
        `    j = repo.create_job(s, tenant_id='default', created_by='${ownerId}', source_key='${key}', upload_id='x', filename='t.zip', title='${title}')`,
        "    jid = j.id",
        "finalize_tileset3d_task(jid, 'default')",
        "with request_scoped_session(_session_factory()) as s:",
        "    j = repo.get_job(s, tenant_id='default', job_id=jid)",
        "    print('ITEM=' + str(j.item_id), 'STATUS=' + str(j.status), 'ERR=' + str(getattr(j, 'error', None)))",
      ].join("\n"),
      encoding: "utf8",
    },
  );
  const m = /ITEM=(\S+)/.exec(out);
  if (!m || m[1] === "None") throw new Error(`tileset seed: ${out}`);
  return { itemId: m[1], out };
}

async function ownerId(): Promise<string> {
  return (await creator.get("/v1/me")).body.id as string;
}

test.describe("j10b tileset3d / terrain3d (capacités allumées)", () => {
  // FINDING j10b-012 : les routes d'upload 3D appellent ensure_uploads_bucket
  // (put_bucket_cors NotImplemented sur MinIO) : 500, donc aucun tileset ni
  // terrain ne peut être téléversé (même racine que j10b-002 / j03-002).
  test.fixme("j10b-012 : POST /v1/tileset3d/uploads crée un envoi multipart (201)", async () => {
    const r = await creator.send("POST", "/v1/tileset3d/uploads", {
      filename: "t.zip",
      title: `${tag}-up`,
    });
    expect(r.status).toBe(201);
  });

  test("droits : un lecteur (sans catalog.manage) reçoit 403 avant tout accès S3", async () => {
    const r = await reader.send("POST", "/v1/tileset3d/uploads", { filename: "t.zip", title: "x" });
    expect(r.status).toBe(403);
    expect((await creator.get("/v1/tileset3d/uploads/nope")).status).toBe(404);
    const tr = await reader.send("POST", "/v1/terrain3d/uploads/presign", {
      filename: "m.tif",
      contentType: "image/tiff",
    });
    expect(tr.status).toBe(403);
  });

  test("proxy : sert tileset.json et une tuile depuis le zip stocké ; 404 hors archive", async () => {
    const id = seedTileset(`${tag}-ts`, await ownerId()).itemId;
    const tok = await token("creator");
    const get = (p: string, h: Record<string, string> = { authorization: `Bearer ${tok}` }) =>
      fetch(`http://localhost:8200/v1/tileset3d/${id}/${p}`, { headers: h });
    const ok = await get("tileset.json");
    expect(ok.status).toBe(200);
    expect((await ok.json()).asset.version).toBe("1.0");
    expect(await (await get("a.b3dm")).text()).toBe("b3dm-bytes");
    expect((await get("absent.b3dm")).status).toBe(404);
    expect((await get("../../etc/passwd")).status).toBe(404);
    expect((await get("tileset.json", {})).status).toBe(401);
  });

  test("proxy : un lecteur ne voit pas un tileset privé (404) mais le voit une fois publié", async () => {
    const id = seedTileset(`${tag}-ts2`, await ownerId()).itemId;
    const tok = await token("reader");
    const url = `http://localhost:8200/v1/tileset3d/${id}/tileset.json`;
    expect((await fetch(url, { headers: { authorization: `Bearer ${tok}` } })).status).toBe(404);
    expect((await creator.send("PATCH", `/v1/items/${id}`, { isPublished: true })).status).toBe(
      200,
    );
    expect((await fetch(url, { headers: { authorization: `Bearer ${tok}` } })).status).toBe(200);
  });
});
