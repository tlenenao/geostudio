// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
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

test("uploadToPresignedUrl envoie application/octet-stream quand File.type est vide", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  try {
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await client.uploadToPresignedUrl("https://s3.test/u", new File(["x"], "a.gpkg", { type: "" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "https://s3.test/u",
      expect.objectContaining({
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test("uploadToPresignedUrl conserve le type du fichier quand il est renseigné", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  try {
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await client.uploadToPresignedUrl(
      "https://s3.test/u",
      new File(["x"], "a.json", { type: "application/json" }),
    );
    expect(fetchMock.mock.calls[0]![1].headers).toEqual({ "Content-Type": "application/json" });
  } finally {
    vi.unstubAllGlobals();
  }
});
