// SPDX-License-Identifier: Apache-2.0
// L8 : les en-têtes de la collecte hors-ligne partent réellement sur le fil (msw), pas seulement
// dans les doublures de ItemClient.
import { expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../itemClient";

const client = () => createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });

test("createFeature : Idempotency-Key et X-GS-Offline-Created-At, absents sans option", async () => {
  const seen: Headers[] = [];
  server.use(
    http.post("https://core.test/v1/collections/c1/items", ({ request }) => {
      seen.push(request.headers);
      return HttpResponse.json({ id: 7 }, { status: 201 });
    }),
  );
  const f = { type: "Feature" as const, properties: {}, geometry: null };
  await client().createFeature("c1", f);
  await client().createFeature("c1", f, {
    idempotencyKey: "00000000-0000-4000-8000-000000000001",
    offlineCreatedAt: "2026-10-18T08:00:00.000Z",
  });
  expect(seen[0].get("idempotency-key")).toBeNull();
  expect(seen[1].get("idempotency-key")).toBe("00000000-0000-4000-8000-000000000001");
  expect(seen[1].get("x-gs-offline-created-at")).toBe("2026-10-18T08:00:00.000Z");
});

test("confirmAttachmentUpload : Idempotency-Key transmise", async () => {
  let key: string | null = "unset";
  server.use(
    http.post("https://core.test/v1/collections/c1/items/9/attachments", ({ request }) => {
      key = request.headers.get("idempotency-key");
      return HttpResponse.json({ id: "a1" }, { status: 201 });
    }),
  );
  await client().confirmAttachmentUpload(
    "c1",
    "9",
    { key: "k", fieldKey: "photo", filename: "a.jpg", contentType: "image/jpeg" },
    { idempotencyKey: "11111111-1111-4111-8111-111111111111" },
  );
  expect(key).toBe("11111111-1111-4111-8111-111111111111");
});

test("getCollectKit : If-None-Match entre guillemets, 304 -> null", async () => {
  let inm: string | null = null;
  server.use(
    http.get("https://core.test/v1/collections/c1/collect-kit", ({ request }) => {
      inm = request.headers.get("if-none-match");
      return new HttpResponse(null, { status: 304 });
    }),
  );
  expect(await client().getCollectKit!("c1", "abc")).toBeNull();
  expect(inm).toBe('"abc"');
});
