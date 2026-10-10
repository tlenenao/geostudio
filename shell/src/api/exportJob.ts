// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
import { jobStatusLabel } from "../lib/jobStatusLabel";
import { parseErrorResponse, type ExportedFile } from "./base";
import "../i18n/domains/widgets";

// REV-283e : `export/items` répond 202 `{jobId}` au-delà du seuil synchrone ;
// on sonde `.../export/jobs/{id}` jusqu'à `done`, puis on renvoie `resultUrl`
// (lien S3 présigné) : le navigateur le télécharge par navigation, jamais par fetch
// (CSP connect-src, pas de Blob en mémoire). Abandon du sondage après 15 min :
// le serveur laisse tourner le job jusqu'à 60 min et notifie à la fin.

/** Échec ou abandon d'un export : le message est déjà en français, à afficher tel quel. */
export class ExportJobError extends Error {}

const EXPORT_POLL_INTERVAL_MS = 2_000;
const EXPORT_POLL_DEADLINE_MS = 15 * 60_000;

export async function pollExportJob(
  accepted: Response,
  path: string,
  get: (path: string) => Promise<Response>,
  signal?: AbortSignal,
): Promise<ExportedFile> {
  const { jobId } = (await accepted.json()) as { jobId: string };
  const statusPath = `${path.split("/export")[0]}/export/jobs/${jobId}`;
  const deadline = Date.now() + EXPORT_POLL_DEADLINE_MS;
  const aborted = () => new DOMException("export aborted", "AbortError");
  for (;;) {
    if (signal?.aborted) throw aborted();
    const res = await get(statusPath);
    if (signal?.aborted) throw aborted();
    if (!res.ok) throw await parseErrorResponse(res);
    const job = (await res.json()) as {
      status: string;
      resultUrl?: string | null;
      filename?: string | null;
      error?: string | null;
    };
    if (job.status === "failed")
      throw new ExportJobError(
        `${t("exportJob.failed", { status: jobStatusLabel(job.status) })}${job.error ? ` ${job.error}` : ""}`,
      );
    if (job.status === "done" && job.resultUrl) {
      return { url: job.resultUrl, filename: job.filename ?? "export" };
    }
    if (Date.now() > deadline) throw new ExportJobError(t("exportJob.timeout"));
    await new Promise<void>((resolve) => {
      const timer = setTimeout(done, EXPORT_POLL_INTERVAL_MS);
      function done() {
        clearTimeout(timer);
        signal?.removeEventListener("abort", done);
        resolve();
      }
      signal?.addEventListener("abort", done);
    });
  }
}
