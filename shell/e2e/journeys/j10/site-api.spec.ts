/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, createSite, getDatasetSeed, richItem, siteConfig, type Api } from "./seed";

test.setTimeout(90_000);
const tag = stamp("j10");
let creator: Api;
let reader: Api;
let analyst: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
  reader = await apiFor("reader");
  analyst = await apiFor("analyst");
});

const anon = async (path: string) => {
  const r = await fetch(`${CORE_URL}${path}`);
  const text = await r.text();
  let body: any = text;
  try {
    body = JSON.parse(text);
  } catch {
    /* corps non JSON */
  }
  return { status: r.status, body, headers: r.headers };
};

test.describe("j10 sites : API", () => {
  test("le slug est dérivé du titre (accents, ponctuation) et suffixé en cas de collision", async () => {
    const a = await createSite(creator, `${tag} Été à Ünïcode !`, siteConfig());
    expect(a.slug).toMatch(/^aud-j10-[a-z0-9]+-ete-a-unicode$/);
    const b = await creator.send("POST", "/v1/configs", {
      title: `${tag} Été à Ünïcode !`,
      config: siteConfig(),
    });
    expect(b.status).toBe(201);
    const item = (await creator.get(`/v1/items/${b.body.itemId}`)).body;
    expect(item.slug).toBe(`${a.slug}-2`);
  });

  test("un slug explicite invalide ou déjà pris est refusé (422 / 409)", async () => {
    const s = await createSite(creator, `${tag}-slugs`, siteConfig(), { slug: `${tag}-fixe` });
    const dup = await creator.send("POST", "/v1/configs", {
      title: "autre",
      slug: s.slug,
      config: siteConfig(),
    });
    expect(dup.status).toBe(409);
    for (const bad of ["Bad Slug", "a--b", "-a", "é"]) {
      const r = await creator.send("POST", "/v1/configs", {
        title: "autre",
        slug: bad,
        config: siteConfig(),
      });
      expect(r.status, bad).toBe(422);
    }
    const patch = await creator.send("PATCH", `/v1/items/${s.pk}`, { slug: "" });
    expect(patch.status).toBe(422);
  });

  test("un site non publié est introuvable en public ; publier puis dépublier le rend puis le retire", async () => {
    const s = await createSite(creator, `${tag}-cycle`, siteConfig([richItem("r", "# ok")]));
    expect((await anon(`/v1/public/sites/${s.slug}`)).status).toBe(404);
    expect((await anon(`/v1/public/configs/by-item/${s.pk}`)).status).toBe(404);
    expect((await anon(`/v1/public/sites/${s.slug}/social-preview`)).status).toBe(404);

    await creator.send("PATCH", `/v1/items/${s.pk}`, { isPublished: true });
    const pub = await anon(`/v1/public/sites/${s.slug}`);
    expect(pub.status).toBe(200);
    expect(pub.body.permissions).toBeDefined();
    expect((await anon(`/v1/public/configs/by-item/${s.pk}`)).status).toBe(200);
    const sitemap = await anon("/v1/public/sitemap.xml");
    expect(sitemap.body).toContain(`/sites/${s.slug}<`);

    await creator.send("PATCH", `/v1/items/${s.pk}`, { isPublished: false });
    expect((await anon(`/v1/public/sites/${s.slug}`)).status).toBe(404);
    expect((await anon("/v1/public/sitemap.xml")).body).not.toContain(`/sites/${s.slug}<`);
  });

  test("changer le slug d'un site publié libère l'ancienne URL publique", async () => {
    const s = await createSite(creator, `${tag}-mv`, siteConfig(), { publish: true });
    const next = `${s.slug}-v2`;
    const r = await creator.send("PATCH", `/v1/items/${s.pk}`, { slug: next });
    expect(r.status).toBe(200);
    expect((await anon(`/v1/public/sites/${s.slug}`)).status).toBe(404);
    expect((await anon(`/v1/public/sites/${next}`)).status).toBe(200);
  });

  test("sitemap, robots.txt et aperçu social échappent le HTML/XML du titre", async () => {
    const s = await createSite(creator, `${tag} <b>&"x"`, siteConfig(), { publish: true });
    await creator.send("PATCH", `/v1/items/${s.pk}`, { abstract: 'desc "<script>"' });
    const prev = await anon(`/v1/public/sites/${s.slug}/social-preview`);
    expect(prev.status).toBe(200);
    expect(prev.body).not.toContain("<script>");
    expect(prev.body).toContain("&lt;b&gt;");
    expect(prev.body).toContain(
      `<link rel="canonical" href="http://localhost:8300/sites/${s.slug}">`,
    );
    const robots = await anon("/v1/public/robots.txt");
    expect(robots.body).toContain("Sitemap: http://localhost:8300/sitemap.xml");
    const sm = await anon("/v1/public/sitemap.xml");
    expect(sm.headers.get("content-type")).toContain("xml");
  });

  test("droits : lecteur et analyste ne peuvent ni créer un site ni modifier celui d'un autre", async () => {
    const s = await createSite(creator, `${tag}-droits`, siteConfig(), { publish: true });
    for (const who of [reader, analyst]) {
      const c = await who.send("POST", "/v1/configs", { title: "x", config: siteConfig() });
      expect(c.status).toBe(403);
      expect((await who.send("PATCH", `/v1/items/${s.pk}`, { title: "piraté" })).status).toBe(403);
      expect((await who.send("PUT", `/v1/configs/by-item/${s.pk}`, siteConfig())).status).toBe(403);
      expect((await who.send("DELETE", `/v1/items/${s.pk}`)).status).toBe(403);
    }
    const item = (await creator.get(`/v1/items/${s.pk}`)).body;
    expect(item.title).toBe(`${tag}-droits`);
  });

  // FINDING j10-001 : GET /public/configs/by-item/{id} sert la config de N'IMPORTE
  // QUEL item publié (alerte, pipeline…), donc l'URL de webhook d'une alerte publiée.
  test.fixme("j10-001 : la config publique d'une alerte publiée ne divulgue pas ses canaux", async () => {
    const ds = await getDatasetSeed();
    const a = await creator.send("POST", "/v1/configs", {
      title: `${tag}-alert`,
      config: {
        version: 1,
        kind: "alert",
        alert: {
          datasetItemId: ds.datasetItemId,
          query: { agg: "count" },
          condition: { expr: "value > 2" },
          refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
          channels: [{ kind: "webhook", url: "https://hooks.example.com/SECRETTOKEN123" }],
        },
      },
    });
    expect(a.status).toBe(201);
    await creator.send("PATCH", `/v1/items/${a.body.itemId}`, { isPublished: true });
    const pub = await anon(`/v1/public/configs/by-item/${a.body.itemId}`);
    expect(JSON.stringify(pub.body)).not.toContain("SECRETTOKEN123");
  });

  // FINDING j10-004 : la liste publique et le widget galerie exposent tous les
  // types d'items publiés, y compris alertes et jeux de données techniques.
  test.fixme("j10-004 : /public/items?type= filtre, mais sans filtre les alertes publiées sont listées", async () => {
    const ds = await getDatasetSeed();
    const a = await creator.send("POST", "/v1/configs", {
      title: `${tag}-alert-liste`,
      config: {
        version: 1,
        kind: "alert",
        alert: {
          datasetItemId: ds.datasetItemId,
          query: { agg: "count" },
          condition: { expr: "value > 2" },
          refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
          channels: [{ kind: "webhook", url: "https://hooks.example.com/x" }],
        },
      },
    });
    await creator.send("PATCH", `/v1/items/${a.body.itemId}`, { isPublished: true });
    const list = await anon("/v1/public/items?pageSize=200");
    expect(list.body.items.map((i: any) => i.resourceType)).not.toContain("alert");
  });
});
