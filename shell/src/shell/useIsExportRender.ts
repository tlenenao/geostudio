// SPDX-License-Identifier: Apache-2.0
import { useSearchParams } from "react-router-dom";

// True when the page was navigated to by the export worker (Task 6,
// core/app/export/jobs.py), which appends ?exportRender=1 to the runtime
// URL. Consumers use this to switch to a "nude" chrome (no builder UI, no
// navigation) so the Playwright capture is clean. Exact literal "1" only —
// no other truthy-looking value counts.
export function useIsExportRender(): boolean {
  const [params] = useSearchParams();
  return params.get("exportRender") === "1";
}
