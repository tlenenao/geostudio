// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
import type { ItemClient } from "../api/types";
import type { BlobRecord, OutboxEntry } from "./db";

const submitPublic = vi.fn();
vi.mock("../api/domains/publicSubmit", () => ({
  submitPublic: (...a: unknown[]) => submitPublic(...a),
}));

import { privateTransport, publicTransport } from "./transport";

const entry: OutboxEntry = {
  opId: "00000000-0000-4000-8000-000000000001",
  ownerKey: "t1:alice",
  collectionId: "c1",
  kind: "feature",
  payload: { properties: { nom: "x" }, geometry: { type: "Point", coordinates: [1, 2] } },
  createdAt: Date.UTC(2026, 9, 18, 8, 0, 0),
  updatedAt: 0,
  state: "queued",
  attempts: 0,
  lastError: null,
  nextTryAt: 0,
};
const blob: BlobRecord = {
  blobId: "b1",
  opId: entry.opId,
  ownerKey: entry.ownerKey,
  fieldKey: "photo",
  kind: "image",
  name: "a.jpg",
  type: "image/jpeg",
  size: 3,
  blob: new Blob([new Uint8Array(3)]),
  clientOpId: "11111111-1111-4111-8111-111111111111",
  uploaded: false,
};

test("transport connecté : opId en Idempotency-Key, horodatage hors-ligne, puis presign → PUT → confirm idempotent", async () => {
  const calls: string[] = [];
  const client = {
    createFeature: vi.fn(async () => {
      calls.push("create");
      return { id: 42 };
    }),
    presignAttachmentUpload: vi.fn(async () => {
      calls.push("presign");
      return { uploadUrl: "https://s3/put", key: "k1" };
    }),
    uploadToPresignedUrl: vi.fn(async () => {
      calls.push("put");
    }),
    confirmAttachmentUpload: vi.fn(async () => {
      calls.push("confirm");
    }),
  } as unknown as ItemClient;
  const t = privateTransport(client);
  const { fid } = await t.create(entry, [], "2026-10-18T08:00:00.000Z");
  expect(fid).toBe("42");
  expect(client.createFeature).toHaveBeenCalledWith(
    "c1",
    { type: "Feature", properties: { nom: "x" }, geometry: entry.payload.geometry },
    { idempotencyKey: entry.opId, offlineCreatedAt: "2026-10-18T08:00:00.000Z" },
  );
  await t.uploadBlob!(entry, "42", blob);
  expect(calls).toEqual(["create", "presign", "put", "confirm"]);
  expect(client.presignAttachmentUpload).toHaveBeenCalledWith("c1", "42", {
    fieldKey: "photo",
    filename: "a.jpg",
    contentType: "image/jpeg",
    size: 3,
  });
  expect(client.confirmAttachmentUpload).toHaveBeenCalledWith(
    "c1",
    "42",
    { key: "k1", fieldKey: "photo", filename: "a.jpg", contentType: "image/jpeg" },
    { idempotencyKey: blob.clientOpId },
  );
});

test("transport public : un seul envoi multipart avec clientOpId = opId et tous les fichiers", async () => {
  const t = publicTransport("https://core/v1", "tok");
  await t.create(entry, [blob], "x");
  expect(submitPublic).toHaveBeenCalledTimes(1);
  const [url, token, sub] = submitPublic.mock.calls[0];
  expect([url, token]).toEqual(["https://core/v1", "tok"]);
  expect(sub.clientOpId).toBe(entry.opId);
  expect(sub.files).toHaveLength(1);
  expect(sub.files[0]).toMatchObject({ fieldKey: "photo" });
  expect(sub.files[0].file.name).toBe("a.jpg");
});
