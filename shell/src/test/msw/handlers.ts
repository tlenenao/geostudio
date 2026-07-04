import { http, HttpResponse } from "msw";

const GEONODE = "https://geonode.test";

function resource(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resource_type: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: { username: "alice" },
    thumbnail_url: `${GEONODE}/thumbs/${pk}.png`,
    date: "2026-01-01T00:00:00Z",
    is_published: false,
  };
}

export const handlers = [
  http.get(`${GEONODE}/api/v2/resources`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search");
    const all = [resource("1", "app", "Alpha"), resource("2", "dashboard", "Beta")];
    const filtered = search
      ? all.filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
      : all;
    return HttpResponse.json({
      total: filtered.length,
      page: Number(url.searchParams.get("page") ?? "1"),
      page_size: Number(url.searchParams.get("page_size") ?? "12"),
      resources: filtered,
    });
  }),

  http.get(`${GEONODE}/api/v2/resources/:pk`, ({ params }) => {
    const pk = String(params.pk);
    if (pk === "404") return new HttpResponse(null, { status: 404 });
    return HttpResponse.json({ resource: resource(pk) });
  }),

  http.get(`${GEONODE}/api/v2/users/me`, () =>
    HttpResponse.json({
      user: { username: "alice", first_name: "Alice", last_name: "Martin" },
    }),
  ),

  http.post("https://builder.test/configs", async ({ request }) => {
    const body = (await request.json()) as { config: { kind: string } };
    return HttpResponse.json({
      id: "cfg-1",
      kind: body.config.kind,
      itemId: "99",
      version: 1,
      config: body.config,
    });
  }),

  http.patch(`${GEONODE}/api/v2/resources/:pk`, async ({ params, request }) => {
    const patch = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      resource: {
        pk: String(params.pk),
        resource_type: "app",
        title: (patch.title as string) ?? "Item",
        abstract: (patch.abstract as string) ?? "",
        owner: { username: "alice" },
        thumbnail_url: null,
        date: "2026-01-01T00:00:00Z",
        is_published: (patch.is_published as boolean) ?? false,
      },
    });
  }),

  http.put(`${GEONODE}/api/v2/resources/:pk/set_thumbnail`, () =>
    new HttpResponse(null, { status: 200 }),
  ),

  http.delete("https://builder.test/configs/by-item/:pk", () =>
    new HttpResponse(null, { status: 204 }),
  ),

  http.get(`${GEONODE}/api/v2/groups`, () =>
    HttpResponse.json({
      group_profiles: [
        { pk: 10, title: "Équipe A" },
        { pk: 11, title: "Équipe B" },
      ],
    }),
  ),

  http.get(`${GEONODE}/api/v2/resources/:pk/permissions`, () =>
    HttpResponse.json({
      groups: [
        { id: "anonymous", permissions: "view" },
        { id: "10", permissions: "edit" },
      ],
    }),
  ),

  http.put(`${GEONODE}/api/v2/resources/:pk/permissions`, () =>
    new HttpResponse(null, { status: 200 }),
  ),
];
