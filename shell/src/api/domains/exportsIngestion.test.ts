// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../itemClient";

test("runAnalyticsSql jette une ApiError sur un statut serveur non-400", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json(
        { type: "about:blank", title: "Internal Server Error", status: 500, detail: "boom" },
        { status: 500 },
      ),
    ),
  );
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  await expect(client.runAnalyticsSql("select 1")).rejects.toMatchObject({
    name: "ApiError",
    status: 500,
    detail: "boom",
  });
});

test("runAnalyticsSql jette toujours SqlQueryError sur un 400 (comportement inchangé)", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json(
        { errors: [{ field: "sql", code: "sql_error", message: "Parser Error: x" }] },
        { status: 400 },
      ),
    ),
  );
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  await expect(client.runAnalyticsSql("select x")).rejects.toMatchObject({
    name: "SqlQueryError",
    message: "Parser Error: x",
  });
});
