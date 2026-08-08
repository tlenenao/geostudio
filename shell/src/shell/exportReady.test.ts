// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from "vitest";
import { markExportReady } from "./exportReady";

afterEach(() => {
  delete document.body.dataset.exportReady;
});

describe("markExportReady", () => {
  it("sets data-export-ready=\"true\" on document.body — the exact selector Task 6's worker waits for", () => {
    markExportReady();
    // Assert against the actual DOM attribute (not just "didn't throw"): this
    // is the literal string Playwright's page.wait_for_selector(
    // '[data-export-ready="true"]') matches against.
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
    expect(document.body.dataset.exportReady).toBe("true");
  });

  it("is idempotent: calling it twice does not throw and leaves the same attribute", () => {
    markExportReady();
    expect(() => markExportReady()).not.toThrow();
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
  });
});
