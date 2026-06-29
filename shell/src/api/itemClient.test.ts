import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => token,
  });
}

test("listItems maps GeoNode resources to Items", async () => {
  const page = await makeClient().listItems();
  expect(page.total).toBe(2);
  expect(page.items[0]).toMatchObject({
    pk: "1",
    resourceType: "app",
    title: "Alpha",
    owner: "alice",
  });
});

test("listItems forwards the search term", async () => {
  const page = await makeClient().listItems({ q: "beta" });
  expect(page.items).toHaveLength(1);
  expect(page.items[0].title).toBe("Beta");
});

test("listItems sends the bearer token", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient("abc").listItems();
  expect(auth).toBe("Bearer abc");
});

test("listItems forwards the type filter param", async () => {
  let captured: URL | null = null;
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      captured = new URL(request.url);
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ type: "app" });
  expect(captured!.searchParams.get("filter{resource_type.in}")).toBe("app");
});

test("getItem maps a single resource", async () => {
  const item = await makeClient().getItem("7");
  expect(item.pk).toBe("7");
  expect(item.thumbnailUrl).toContain("/thumbs/7.png");
});

test("getItem throws on 404", async () => {
  await expect(makeClient().getItem("404")).rejects.toThrow(/404/);
});

test("getMe maps the current user", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
});
