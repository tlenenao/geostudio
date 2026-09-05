// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, AttachmentSummary } from "../types";
import type { ItemClientBase } from "../base";
import { requestBlob } from "../base";

type AttachmentsMethods = Pick<
  ItemClient,
  | "presignAttachmentUpload"
  | "confirmAttachmentUpload"
  | "listAttachments"
  | "deleteAttachment"
  | "attachmentFileUrl"
  | "downloadAttachment"
>;

export function createAttachmentsMethods(base: ItemClientBase): AttachmentsMethods {
  const { request, coreUrl, getToken } = base;
  return {
    async presignAttachmentUpload(
      collectionId: string,
      fid: string,
      input: { fieldKey: string; filename: string; contentType: string },
    ): Promise<{ uploadUrl: string; key: string }> {
      return request<{ uploadUrl: string; key: string }>(
        "POST",
        `/collections/${collectionId}/items/${fid}/attachments/presign`,
        input,
      );
    },

    async confirmAttachmentUpload(
      collectionId: string,
      fid: string,
      input: { key: string; fieldKey: string; filename: string; contentType: string },
    ): Promise<AttachmentSummary> {
      return request<AttachmentSummary>(
        "POST",
        `/collections/${collectionId}/items/${fid}/attachments`,
        input,
      );
    },

    async listAttachments(
      collectionId: string,
      fid: string,
      fieldKey?: string,
    ): Promise<AttachmentSummary[]> {
      const qs = fieldKey ? `?fieldKey=${encodeURIComponent(fieldKey)}` : "";
      const data = await request<{ attachments: AttachmentSummary[] }>(
        "GET",
        `/collections/${collectionId}/items/${fid}/attachments${qs}`,
      );
      return data.attachments;
    },

    async deleteAttachment(collectionId: string, fid: string, attachmentId: string): Promise<void> {
      await request<void>(
        "DELETE",
        `/collections/${collectionId}/items/${fid}/attachments/${attachmentId}`,
      );
    },

    attachmentFileUrl(collectionId: string, fid: string, attachmentId: string): string {
      return `${coreUrl}/collections/${collectionId}/items/${fid}/attachments/${attachmentId}/file`;
    },

    async downloadAttachment(
      collectionId: string,
      fid: string,
      attachmentId: string,
    ): Promise<{ blob: Blob; filename: string }> {
      return requestBlob(
        coreUrl,
        getToken,
        "GET",
        `/collections/${collectionId}/items/${fid}/attachments/${attachmentId}/file`,
      );
    },
  };
}
