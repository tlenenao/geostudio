// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { ApiError } from "./ApiError";
import { apiErrorMessage } from "./apiErrorMessage";

describe("apiErrorMessage : quota-exceeded (P26.09)", () => {
  it("rend un message traduit et actionnable, jamais le texte brut du cœur", () => {
    const e = new ApiError(409, {
      detail: "quota d'items du tenant dépassé : 30/30",
      problemType: "quota-exceeded",
      quota: { kind: "items", current: 30, limit: 30 },
    });
    const msg = apiErrorMessage(e, "x");
    expect(msg).toContain("30/30");
    expect(msg).toContain("administrateur");
  });
  it("formate le stockage en unités lisibles", () => {
    const e = new ApiError(413, {
      problemType: "quota-exceeded",
      quota: { kind: "storage", current: 2048, limit: 1024 },
    });
    expect(apiErrorMessage(e, "x")).toContain("2 Ko/1 Ko");
  });
});

describe("apiErrorMessage : errors[] du problem+json (REV-278e)", () => {
  it("affiche les erreurs par champ plutôt que le detail générique", () => {
    const e = new ApiError(400, {
      detail: "validation failed",
      errors: [
        { field: "url", code: "invalid", message: "url must be an http(s) URL" },
        { field: "", code: "x", message: "titre manquant" },
      ],
    });
    expect(apiErrorMessage(e, "x")).toBe("url : url must be an http(s) URL ; titre manquant");
  });
  it("retombe sur le detail sans errors[]", () => {
    expect(apiErrorMessage(new ApiError(409, { detail: "déjà existant" }), "x")).toBe(
      "déjà existant",
    );
  });
});
