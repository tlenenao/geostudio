import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { corePython } from "../j06/helpers";
import { apiFor, psql, type Api } from "./seed";

test.setTimeout(90_000);
const tag = stamp("j10");
let creator: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
});

test.describe("j10 export d'apps : capacité éteinte", () => {
  test("l'instance annonce appExportEnabled=false et les routes /app-exports sont absentes", async () => {
    const inst = await creator.get("/v1/instance");
    expect(inst.body.appExportEnabled).toBe(false);
    expect(inst.body.exportEnabled).toBe(false);
    const cfg = await creator.send("POST", "/v1/configs", {
      title: `${tag}-exp`,
      config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
    });
    for (const mode of ["static", "connected", "standalone"]) {
      const r = await creator.send("POST", "/v1/app-exports", { itemId: cfg.body.itemId, mode });
      expect(r.status, mode).toBe(404);
    }
    expect((await creator.get("/v1/app-exports/jobs/x")).status).toBe(404);
  });

  test("impression : printLayout est validé (format de page) et relu tel quel", async () => {
    const base = { version: 1, kind: "app", layout: { type: "grid", items: [] } };
    const bad = await creator.send("POST", "/v1/configs", {
      title: `${tag}-pl-ko`,
      config: { ...base, printLayout: { pageSize: "a0" } },
    });
    expect(bad.status).toBe(422);
    const ok = await creator.send("POST", "/v1/configs", {
      title: `${tag}-pl`,
      config: {
        ...base,
        printLayout: { pageSize: "a3", orientation: "landscape", title: "T", cartouche: "C" },
      },
    });
    expect(ok.status).toBe(201);
    const back = (await creator.get(`/v1/configs/by-item/${ok.body.itemId}`)).body.config;
    expect(back.printLayout).toMatchObject({
      pageSize: "a3",
      orientation: "landscape",
      title: "T",
    });
  });

  // FINDING j10-007 : le gel du mode Statique (et l'instantané Autoporté) lit la
  // table avec rls_scope() non masqué : une collection publique dont des champs
  // sont sensibles les embarque en clair dans le bundle. Exécuté ici en
  // appelant directement freeze_config dans le conteneur cœur (la route est éteinte).
  test.fixme("j10-007 : le gel d'export statique n'embarque pas les champs sensibles", async () => {
    const c = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-sens`,
      columns: [
        { name: "nom", sqlType: "text" },
        { name: "secret", sqlType: "text" },
      ],
      geometryType: "Point",
      srid: 4326,
    });
    expect(c.status).toBe(201);
    psql(
      `INSERT INTO public.${c.body.tableName} (tenant_id, nom, secret, geom) VALUES ('default','pub','TOPSECRET-42',ST_SetSRID(ST_MakePoint(1,45),4326))`,
    );
    expect(
      (await creator.send("PATCH", `/v1/collections/${c.body.id}`, { sensitiveFields: ["secret"] }))
        .status,
    ).toBe(200);
    expect(
      (
        await creator.send("PUT", `/v1/collections/${c.body.id}/sharing`, {
          public: true,
          groups: [],
        })
      ).status,
    ).toBe(200);
    // Référence : la lecture anonyme masque bien le champ.
    const anon = await fetch(`http://localhost:8200/v1/collections/${c.body.id}/items`);
    expect(JSON.stringify(await anon.json())).not.toContain("TOPSECRET-42");
    const out = corePython(
      [
        "import json",
        "from app.appexport.freeze import freeze_config",
        "from app.configs.schemas import BuilderConfig",
        "from app.db import request_scoped_session",
        "from app.jobs.common import session_factory",
        "cfg = BuilderConfig(kind='app', layout={'type':'grid','items':[]}, dataSources=[{'id':'d','type':'features','service':'core','layer':'" +
          c.body.id +
          "','query':{}}])",
        "with request_scoped_session(session_factory()) as s:",
        "    print('FROZEN=' + json.dumps(freeze_config(s, tenant_id='default', config=cfg).model_dump()['dataSources']))",
      ].join("\n"),
    );
    expect(out).not.toContain("TOPSECRET-42");
  });
});
