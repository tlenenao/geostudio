/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import {
  anon,
  apiFor,
  appConfig,
  mapConfigOn,
  meId,
  mkCollection,
  mkGroup,
  mkItem,
  share,
  TAG,
  type Api,
} from "./helpers";

// Partage d'items, groupes, publication et liens à échéance vus depuis l'API
// du cœur, jetons Keycloak réels des 4 personas.
let creator: Api, analyst: Api, reader: Api, admin: Api;
let readerId: string, analystId: string;

test.beforeAll(async () => {
  [creator, analyst, reader, admin] = await Promise.all([
    apiFor("creator"),
    apiFor("analyst"),
    apiFor("reader"),
    apiFor("admin"),
  ]);
  readerId = await meId(reader);
  analystId = await meId(analyst);
});

test.describe("j13 matrice rôle × kind (création de config)", () => {
  test("création par kind : Lecteur 403 partout, Analyste seulement bookmark, Créateur app/map/dataset/site/dashboard/bookmark", async () => {
    const col = await mkCollection(creator, `${TAG}-mx-col`);
    const target = await mkItem(creator, `${TAG}-mx-app`);
    const configs: Record<string, any> = {
      app: appConfig(),
      dashboard: { ...appConfig(), kind: "dashboard" },
      site: { version: 1, kind: "site", layout: { type: "grid", items: [] } },
      map: mapConfigOn(col),
      dataset: {
        version: 1,
        kind: "dataset",
        dataset: { source: "collection", collectionId: col },
      },
      bookmark: { version: 1, kind: "bookmark", bookmark: { appId: target.pk, pageId: "p1" } },
    };
    // Le bookmark cible une app que l'appelant doit pouvoir lire : on la partage publiquement.
    expect(await share(creator, target.pk, [], true)).toBe(204);
    const expected: Record<string, Record<string, number>> = {
      creator: { app: 201, dashboard: 201, site: 201, map: 201, dataset: 201, bookmark: 201 },
      analyst: { app: 403, dashboard: 403, site: 403, map: 403, dataset: 403, bookmark: 201 },
      reader: { app: 403, dashboard: 403, site: 403, map: 403, dataset: 403, bookmark: 403 },
    };
    const got: Record<string, Record<string, number>> = {};
    for (const [who, api] of [
      ["creator", creator],
      ["analyst", analyst],
      ["reader", reader],
    ] as const) {
      got[who] = {};
      for (const [kind, config] of Object.entries(configs)) {
        const r = await api.send("POST", "/v1/configs", {
          title: `${TAG}-mx-${who}-${kind}`,
          config,
        });
        got[who][kind] = r.status;
      }
    }
    expect(got).toEqual(expected);
  });

  test("un Lecteur ne peut ni créer un groupe ni une collection vide ; un Analyste non plus", async () => {
    for (const api of [reader, analyst]) {
      expect((await api.send("POST", "/v1/groups", { name: `${TAG}-g-denied` })).status).toBe(403);
      const c = await api.send("POST", "/v1/collections/empty", {
        title: `${TAG}-col-denied`,
        columns: [{ name: "nom", sqlType: "text" }],
        geometryType: "Point",
        srid: 4326,
      });
      expect(c.status).toBe(403);
    }
  });
});

test.describe("j13 rôle de partage viewer / editor", () => {
  test("viewer via groupe : lecture 200 ; métadonnées, publication, partage, config et suppression refusés (403)", async () => {
    const it = await mkItem(creator, `${TAG}-viewer`);
    const g = await mkGroup(creator, `${TAG}-gv`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    const item = await reader.get(`/v1/items/${it.pk}`);
    expect(item.status).toBe(200);
    expect(item.body.permissions).toEqual({
      read: true,
      write: false,
      delete: false,
      share: false,
    });
    expect((await reader.send("PATCH", `/v1/items/${it.pk}`, { title: "x" })).status).toBe(403);
    expect((await reader.send("PATCH", `/v1/items/${it.pk}`, { isPublished: true })).status).toBe(
      403,
    );
    expect(
      (await reader.send("PUT", `/v1/items/${it.pk}/sharing`, { public: true, groups: [] })).status,
    ).toBe(403);
    expect((await reader.send("PUT", `/v1/configs/by-item/${it.pk}`, appConfig())).status).toBe(
      403,
    );
    expect((await reader.send("DELETE", `/v1/items/${it.pk}`)).status).toBe(403);
    expect(
      (await reader.send("POST", `/v1/items/${it.pk}/share-links`, { ttlDays: 1 })).status,
    ).toBe(403);
  });

  test("retirer le groupe du partage retire l'accès (404, pas 403)", async () => {
    const it = await mkItem(creator, `${TAG}-unshare`);
    const g = await mkGroup(creator, `${TAG}-gu`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    expect((await reader.get(`/v1/items/${it.pk}`)).status).toBe(200);
    expect(await share(creator, it.pk, [])).toBe(204);
    expect((await reader.get(`/v1/items/${it.pk}`)).status).toBe(404);
    expect((await reader.get(`/v1/configs/${it.configId}`)).status).toBe(404);
    expect((await reader.get(`/v1/configs/${it.configId}/revisions`)).status).toBe(404);
  });

  // Finding j13-002 : la garde de privilège ne couvre que l'écriture de config ;
  // un Lecteur (0 privilège) éditeur par groupe publie, rend public et re-partage.
  bug(
    "j13-002 : un Lecteur éditeur par groupe ne peut ni publier (anonyme), ni rendre public, ni créer de lien",
    async () => {
      const it = await mkItem(creator, `${TAG}-editor-reader`);
      const g = await mkGroup(creator, `${TAG}-ge`, [readerId]);
      expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
      // Contrôle : l'écriture de config, elle, est bien refusée au Lecteur.
      expect((await reader.send("PUT", `/v1/configs/by-item/${it.pk}`, appConfig())).status).toBe(
        403,
      );
      expect((await reader.send("PATCH", `/v1/items/${it.pk}`, { isPublished: true })).status).toBe(
        403,
      );
      expect(await anon(`/v1/public/configs/by-item/${it.pk}`)).toBe(404);
      expect(
        (await reader.send("PUT", `/v1/items/${it.pk}/sharing`, { public: true, groups: [] }))
          .status,
      ).toBe(403);
    },
  );

  test("constat j13-002 : le Lecteur éditeur publie l'app, qui devient lisible par un anonyme", async () => {
    const it = await mkItem(creator, `${TAG}-editor-reader-obs`);
    const g = await mkGroup(creator, `${TAG}-geo`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    expect((await reader.send("PUT", `/v1/configs/by-item/${it.pk}`, appConfig())).status).toBe(
      403,
    );
    const renamed = await reader.send("PATCH", `/v1/items/${it.pk}`, {
      title: `${TAG}-renomme-par-lecteur`,
      isPublished: true,
    });
    expect(renamed.status).toBe(200);
    expect(await anon(`/v1/public/configs/by-item/${it.pk}`)).toBe(200);
    // Il peut aussi rendre l'item visible de tout le tenant.
    expect(
      (
        await reader.send("PUT", `/v1/items/${it.pk}/sharing`, {
          public: true,
          groups: [{ groupId: g, role: "editor" }],
        })
      ).status,
    ).toBe(204);
  });

  test("un éditeur par groupe peut accorder « editor » à un autre groupe (rôle = co-propriétaire)", async () => {
    // Constat (j13-012) : pas de rôle intermédiaire « modifier sans re-partager ».
    const it = await mkItem(creator, `${TAG}-coowner`);
    const g = await mkGroup(creator, `${TAG}-gco`, [analystId]);
    const other = await mkGroup(creator, `${TAG}-gco2`);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    expect(
      await share(analyst, it.pk, [
        { groupId: g, role: "editor" },
        { groupId: other, role: "editor" },
      ]),
    ).toBe(204);
    const sh = await creator.get(`/v1/items/${it.pk}/sharing`);
    expect(sh.body.groups).toHaveLength(2);
  });
});

test.describe("j13 groupes de partage", () => {
  test("seul le créateur d'un groupe y ajoute un membre (404 pour les autres, y compris l'Administrateur)", async () => {
    const g = await mkGroup(creator, `${TAG}-gown`);
    for (const api of [analyst, admin]) {
      const r = await api.send("POST", `/v1/groups/${g}/members`, { userId: analystId });
      expect(r.status).toBe(404);
    }
    const bogus = await creator.send("POST", `/v1/groups/${g}/members`, { userId: "nope" });
    expect(bogus.status).toBe(404);
  });

  // Finding j13-004 : aucune route pour retirer un membre, lister les membres,
  // renommer ou supprimer un groupe.
  bug(
    "j13-004 : le créateur d'un groupe peut lister ses membres, en retirer un et supprimer le groupe",
    async () => {
      const g = await mkGroup(creator, `${TAG}-gmgmt`, [readerId]);
      const members = await creator.get(`/v1/groups/${g}/members`);
      expect(members.status).toBe(200);
      expect((await creator.send("DELETE", `/v1/groups/${g}/members/${readerId}`)).status).toBe(
        204,
      );
      expect((await creator.send("DELETE", `/v1/groups/${g}`)).status).toBe(204);
    },
  );

  test("constat j13-004 : un membre ajouté par erreur ne peut être retiré que par… rien (routes absentes)", async () => {
    const it = await mkItem(creator, `${TAG}-stuck`);
    const g = await mkGroup(creator, `${TAG}-gstuck`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    for (const [m, p] of [
      ["GET", `/v1/groups/${g}/members`],
      ["DELETE", `/v1/groups/${g}/members/${readerId}`],
      ["DELETE", `/v1/groups/${g}`],
      ["PATCH", `/v1/groups/${g}`],
    ] as const) {
      const r = await creator.send(m, p, m === "PATCH" ? { name: "x" } : undefined);
      expect([404, 405]).toContain(r.status);
    }
    expect((await reader.get(`/v1/items/${it.pk}`)).status).toBe(200);
  });

  test("partage vers un groupe inconnu → 404, groupe dupliqué → 422, rien n'est modifié", async () => {
    const it = await mkItem(creator, `${TAG}-badgroups`);
    const g = await mkGroup(creator, `${TAG}-gbad`);
    expect(await share(creator, it.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    expect(await share(creator, it.pk, [{ groupId: "0".repeat(32), role: "viewer" }])).toBe(404);
    expect(
      await share(creator, it.pk, [
        { groupId: g, role: "viewer" },
        { groupId: g, role: "editor" },
      ]),
    ).toBe(422);
    expect(await share(creator, it.pk, [{ groupId: g, role: "owner" as any }])).toBe(422);
    const sh = await creator.get(`/v1/items/${it.pk}/sharing`);
    expect(sh.body.groups).toEqual([{ groupId: g, role: "viewer" }]);
  });
});

test.describe("j13 « public » vs « publié »", () => {
  test("partage public = visible des comptes du tenant seulement ; publication = anonyme", async () => {
    const it = await mkItem(creator, `${TAG}-pubflag`);
    expect(await share(creator, it.pk, [], true)).toBe(204);
    expect((await reader.get(`/v1/items/${it.pk}`)).status).toBe(200);
    expect(await anon(`/v1/public/configs/by-item/${it.pk}`)).toBe(404);
    expect(await anon(`/v1/public/items/${it.pk}`)).toBe(404);
    expect((await creator.send("PATCH", `/v1/items/${it.pk}`, { isPublished: true })).status).toBe(
      200,
    );
    expect(await anon(`/v1/public/configs/by-item/${it.pk}`)).toBe(200);
  });
});

test.describe("j13 partage d'une carte et de ses données", () => {
  // Finding j13-008 : partager une carte à un groupe ne donne pas accès à sa collection.
  bug(
    "j13-008 : un membre du groupe à qui l'on partage une carte lit aussi les entités de sa couche",
    async () => {
      const col = await mkCollection(creator, `${TAG}-mapcol`);
      const m = await mkItem(creator, `${TAG}-sharedmap`, mapConfigOn(col));
      const g = await mkGroup(creator, `${TAG}-gmap`, [readerId]);
      expect(await share(creator, m.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
      expect((await reader.get(`/v1/configs/by-item/${m.pk}`)).status).toBe(200);
      expect((await reader.get(`/v1/collections/${col}/items`)).status).toBe(200);
    },
  );

  test("constat j13-008 : config lisible, collection 404 tant que le propriétaire ne la partage pas à part (API seule)", async () => {
    const col = await mkCollection(creator, `${TAG}-mapcol2`);
    const m = await mkItem(creator, `${TAG}-sharedmap2`, mapConfigOn(col));
    const g = await mkGroup(creator, `${TAG}-gmap2`, [readerId]);
    expect(await share(creator, m.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    expect((await reader.get(`/v1/configs/by-item/${m.pk}`)).status).toBe(200);
    expect((await reader.get(`/v1/collections/${col}/items`)).status).toBe(404);
    const sh = await creator.send("PUT", `/v1/collections/${col}/sharing`, {
      public: false,
      groups: [{ groupId: g, role: "viewer" }],
    });
    expect(sh.status).toBe(200);
    expect((await reader.get(`/v1/collections/${col}/items`)).status).toBe(200);
  });
});

test.describe("j13 suppression et références", () => {
  // Finding j13-003 : DELETE /configs/{id} ne vérifie pas les références inverses.
  bug(
    "j13-003 : supprimer un dataset référencé par une alerte est refusé (409) sur les trois routes de suppression",
    async () => {
      const col = await mkCollection(creator, `${TAG}-refcol`);
      const d = await mkItem(creator, `${TAG}-refds`, {
        version: 1,
        kind: "dataset",
        dataset: { source: "collection", collectionId: col },
      });
      await mkItem(creator, `${TAG}-refalert`, alertOn(d.pk));
      expect((await creator.send("DELETE", `/v1/items/${d.pk}`)).status).toBe(409);
      expect((await creator.send("DELETE", `/v1/configs/by-item/${d.pk}`)).status).toBe(409);
      expect((await creator.send("DELETE", `/v1/configs/${d.configId}`)).status).toBe(409);
    },
  );

  test("constat j13-003 : DELETE /configs/{id} supprime le dataset référencé (204) et laisse l'alerte orpheline", async () => {
    const col = await mkCollection(creator, `${TAG}-refcol2`);
    const d = await mkItem(creator, `${TAG}-refds2`, {
      version: 1,
      kind: "dataset",
      dataset: { source: "collection", collectionId: col },
    });
    const a = await mkItem(creator, `${TAG}-refalert2`, alertOn(d.pk));
    expect((await creator.send("DELETE", `/v1/items/${d.pk}`)).status).toBe(409);
    expect((await creator.send("DELETE", `/v1/configs/${d.configId}`)).status).toBe(204);
    expect((await creator.get(`/v1/items/${d.pk}`)).status).toBe(404);
    const orphan = await creator.get(`/v1/configs/by-item/${a.pk}`);
    expect(orphan.status).toBe(200);
    expect(orphan.body.config.alert.datasetItemId).toBe(d.pk);
  });
});

test.describe("j13 administration et modération", () => {
  // Finding j13-009 : l'Administrateur ne voit ni ne modère les items privés d'autrui.
  bug(
    "j13-009 : l'Administrateur peut dépublier un item publié par un autre utilisateur",
    async () => {
      const it = await mkItem(creator, `${TAG}-moderate`);
      expect(
        (await creator.send("PATCH", `/v1/items/${it.pk}`, { isPublished: true })).status,
      ).toBe(200);
      expect((await admin.send("PATCH", `/v1/items/${it.pk}`, { isPublished: false })).status).toBe(
        200,
      );
    },
  );

  test("constat j13-009 : Administrateur 403 sur la dépublication, 404 sur un item privé d'autrui", async () => {
    const pub = await mkItem(creator, `${TAG}-moderate-obs`);
    expect((await creator.send("PATCH", `/v1/items/${pub.pk}`, { isPublished: true })).status).toBe(
      200,
    );
    expect((await admin.send("PATCH", `/v1/items/${pub.pk}`, { isPublished: false })).status).toBe(
      403,
    );
    expect((await admin.send("DELETE", `/v1/items/${pub.pk}`)).status).toBe(403);
    const priv = await mkItem(creator, `${TAG}-private-obs`);
    expect((await admin.get(`/v1/items/${priv.pk}`)).status).toBe(404);
    expect((await admin.send("DELETE", `/v1/items/${priv.pk}`)).status).toBe(404);
  });
});

test.describe("j13 liens de partage à échéance", () => {
  // Finding j13-001 : CORE_SHARE_LINK_TOKEN_SECRET vide (jamais généré) → 500.
  bug(
    "j13-001 : le propriétaire crée un lien de partage (201) et un anonyme le résout",
    async () => {
      const it = await mkItem(creator, `${TAG}-link`);
      const r = await creator.send("POST", `/v1/items/${it.pk}/share-links`, { ttlDays: 7 });
      expect(r.status).toBe(201);
      expect(await anon(`/v1/share-links/${r.body.token}`)).toBe(200);
    },
  );

  test("constat j13-001 : POST share-links répond 500 sans laisser de lien en base", async () => {
    const it = await mkItem(creator, `${TAG}-link-obs`);
    const r = await creator.send("POST", `/v1/items/${it.pk}/share-links`, { ttlDays: 7 });
    expect(r.status).toBe(500);
    const list = await creator.get(`/v1/items/${it.pk}/share-links`);
    expect(list.status).toBe(200);
    expect(list.body).toEqual([]);
  });

  test("bornes du TTL (0 et 31 jours → 422), jeton invalide → 401, lien d'un item non partageable → 403", async () => {
    const it = await mkItem(creator, `${TAG}-ttl`);
    for (const ttlDays of [0, 31, -1]) {
      const r = await creator.send("POST", `/v1/items/${it.pk}/share-links`, { ttlDays });
      expect(r.status).toBe(422);
    }
    expect(await anon("/v1/share-links/pas-un-jeton")).toBe(401);
    expect(await share(creator, it.pk, [], true)).toBe(204);
    expect((await reader.get(`/v1/items/${it.pk}/share-links`)).status).toBe(403);
    expect((await reader.send("DELETE", `/v1/items/${it.pk}/share-links/abc`)).status).toBe(403);
  });
});

function alertOn(datasetItemId: string) {
  return {
    version: 1,
    kind: "alert",
    alert: {
      datasetItemId,
      query: { agg: "count" },
      condition: { expr: "value > 2" },
      refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: "http://127.0.0.1:9/hook" }],
    },
  };
}
