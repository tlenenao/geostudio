// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
import { jobStatusLabel } from "../lib/jobStatusLabel";
import { fetchWithTimeout, parseErrorResponse, readBody } from "./base";

// REV-283e : `export/items` répond 202 `{jobId}` au-delà du seuil synchrone ;
// on sonde `.../export/jobs/{id}` jusqu'à `done`, puis on télécharge `resultUrl`
// (lien S3 présigné, sans Authorization). Abandon après 15 min.
const EXPORT_POLL_INTERVAL_MS = 2_000;
const EXPORT_POLL_DEADLINE_MS = 15 * 60_000;

export async function pollExportJob(
  accepted: Response,
  path: string,
  get: (path: string) => Promise<Response>,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
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
      throw new Error(t("exportJob.failed", { status: jobStatusLabel(job.status) }));
    if (job.status === "done" && job.resultUrl) {
      const file = await fetchWithTimeout(job.resultUrl, {}, 120_000);
      if (!file.ok) throw await parseErrorResponse(file);
      return { blob: await readBody(() => file.blob()), filename: job.filename ?? "export" };
    }
    if (Date.now() > deadline) throw new Error("export timed out");
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
