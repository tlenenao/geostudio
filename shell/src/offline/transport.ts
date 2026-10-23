// SPDX-License-Identifier: Apache-2.0
// L8 : les deux transports du moteur de synchronisation — utilisateur connecté (ItemClient) et
// page publique (jeton de lien).
import { submitPublic } from "../api/domains/publicSubmit";
import type { ItemClient } from "../api/types";
import { blobToFile, type SyncTransport } from "./sync";

export function privateTransport(client: ItemClient): SyncTransport {
  return {
    mode: "separate",
    async create(entry, _blobs, offlineCreatedAt) {
      const { id } = await client.createFeature(
        entry.collectionId,
        {
          type: "Feature",
          properties: entry.payload.properties,
          geometry: entry.payload.geometry,
        },
        { idempotencyKey: entry.opId, offlineCreatedAt },
      );
      return { fid: String(id) };
    },
    async uploadBlob(entry, fid, blob) {
      const file = blobToFile(blob);
      const { uploadUrl, key } = await client.presignAttachmentUpload(entry.collectionId, fid, {
        fieldKey: blob.fieldKey,
        filename: blob.name,
        contentType: blob.type,
        size: blob.size,
      });
      await client.uploadToPresignedUrl(uploadUrl, file);
      await client.confirmAttachmentUpload(
        entry.collectionId,
        fid,
        { key, fieldKey: blob.fieldKey, filename: blob.name, contentType: blob.type },
        { idempotencyKey: blob.clientOpId },
      );
    },
  };
}

export function publicTransport(coreV1: string, token: string): SyncTransport {
  return {
    mode: "single",
    async create(entry, blobs) {
      await submitPublic(coreV1, token, {
        feature: {
          type: "Feature",
          properties: entry.payload.properties,
          geometry: entry.payload.geometry,
        },
        files: blobs.map((b) => ({ fieldKey: b.fieldKey, file: blobToFile(b) })),
        clientOpId: entry.opId,
        honeypot: "",
      });
      return {};
    },
  };
}
