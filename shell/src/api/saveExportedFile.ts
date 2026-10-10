// SPDX-License-Identifier: Apache-2.0
import type { ExportedFile } from "./base";

// Enregistre un export : ancre `download` sur l'URL présignée (Content-Disposition
// attachment côté S3) ou, pour une réponse synchrone, sur un Blob éphémère.
export function saveExportedFile(file: ExportedFile): void {
  const href = file.url ?? URL.createObjectURL(file.blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = file.filename;
  a.click();
  if (!file.url) URL.revokeObjectURL(href);
}
