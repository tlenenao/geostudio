// SPDX-License-Identifier: Apache-2.0
import { http, HttpResponse } from "msw";

const CORE = "https://core.test";

function item(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resourceType: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: "alice",
    thumbnailUrl: `${CORE}/items/${pk}/thumbnail`,
    date: "2026-01-01T00:00:00Z",
    configId: null,
    isPublished: false,
    permissions: { read: true, write: true, delete: true, share: true },
  };
}

export const handlers = [
  http.get(`${CORE}/items`, () =>
    HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 }),
  ),
  http.get(`${CORE}/items/:pk`, ({ params }) => {
    if (params.pk === "404") return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(item(String(params.pk)));
  }),
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1",
      username: "alice",
      firstName: "Alice",
      lastName: "Martin",
      email: "alice@example.com",
      tenantId: "t1",
      role: { id: "role-creator", name: "Créateur", slug: "creator" },
      privileges: ["catalog.manage", "maps.manage", "data.view", "data.manage"],
      version: "0.1.0",
      tenantSlug: "demo",
    }),
  ),
  http.get(`${CORE}/instance`, () => HttpResponse.json({ readOnly: false })),
  http.post(`${CORE}/configs`, async ({ request }) => {
    const body = (await request.json()) as { title: string; config: { kind: string } };
    return HttpResponse.json(
      { id: "cfg-1", itemId: "99", kind: body.config.kind, version: 1, config: body.config },
      { status: 201 },
    );
  }),
  http.patch(`${CORE}/items/:pk`, async ({ params, request }) => {
    const patch = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...item(String(params.pk)), ...patch });
  }),
  http.post(`${CORE}/items/:pk/thumbnail`, () => new HttpResponse(null, { status: 204 })),
  http.delete(`${CORE}/configs/by-item/:pk`, () => new HttpResponse(null, { status: 204 })),
  http.get(`${CORE}/groups`, () =>
    HttpResponse.json([
      { id: "10", name: "Équipe A" },
      { id: "11", name: "Équipe B" },
    ]),
  ),
  http.get(`${CORE}/items/:pk/sharing`, () =>
    HttpResponse.json({ public: true, groups: [{ groupId: "10", role: "editor" }] }),
  ),
  http.put(`${CORE}/items/:pk/sharing`, () => new HttpResponse(null, { status: 204 })),
];
