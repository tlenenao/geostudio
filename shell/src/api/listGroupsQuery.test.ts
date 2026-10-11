// SPDX-License-Identifier: Apache-2.0
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";

test("listGroups(q) transmet la recherche à GET /groups (REV-277)", async () => {
  let q: string | null = null;
  server.use(
    http.get("https://core.test/v1/groups", ({ request }) => {
      q = new URL(request.url).searchParams.get("q");
      return HttpResponse.json([]);
    }),
  );
  await createItemClient({ coreUrl: "https://core.test", getToken: () => "t" }).listGroups(
    "équ ipe",
  );
  expect(q).toBe("équ ipe");
});
