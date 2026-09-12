// SPDX-License-Identifier: Apache-2.0
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { resolveShareLink } from "./resolveShareLink";

test("resolveShareLink returns the resolved metadata on success", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/tok-1", () =>
      HttpResponse.json({
        itemId: "app-1",
        title: "Mon App",
        resourceType: "app",
        expiresAt: "2026-10-01",
      }),
    ),
  );
  const resolved = await resolveShareLink("https://core.test", "tok-1");
  expect(resolved).toEqual({
    itemId: "app-1",
    title: "Mon App",
    resourceType: "app",
    expiresAt: "2026-10-01",
  });
});

test("resolveShareLink throws on a 401 (invalid or expired token)", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/bad", () =>
      HttpResponse.json({ detail: "invalid or expired share link" }, { status: 401 }),
    ),
  );
  await expect(resolveShareLink("https://core.test", "bad")).rejects.toThrow();
});
