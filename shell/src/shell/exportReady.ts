// SPDX-License-Identifier: Apache-2.0

// DOM signal the Playwright export worker (core/app/export/jobs.py) waits
// for via page.wait_for_selector('[data-export-ready="true"]', state="attached")
// before capturing a screenshot/PDF. Setting `document.body.dataset.exportReady`
// to the string "true" is what produces the HTML attribute
// data-export-ready="true" that selector matches — do not change the target
// element, attribute name, or value without updating Task 6's worker too.
// Idempotent: safe to call more than once (e.g. a MapView "idle" firing
// again after the first capture-ready moment).
export function markExportReady(): void {
  document.body.dataset.exportReady = "true";
}
