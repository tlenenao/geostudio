// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { jobStatusLabel } from "./jobStatusLabel";

describe("jobStatusLabel", () => {
  it("traduit chaque statut connu du vocabulaire pipeline (PipelineRunStatus)", () => {
    expect(jobStatusLabel("queued")).toBe("En attente");
    expect(jobStatusLabel("running")).toBe("En cours");
    expect(jobStatusLabel("succeeded")).toBe("Terminé");
    expect(jobStatusLabel("failed")).toBe("Échoué");
  });

  it("traduit chaque statut connu du vocabulaire rapport (ReportRunStatus)", () => {
    expect(jobStatusLabel("pending")).toBe("En attente");
    expect(jobStatusLabel("running")).toBe("En cours");
    expect(jobStatusLabel("done")).toBe("Terminé");
    expect(jobStatusLabel("error")).toBe("Échoué");
    expect(jobStatusLabel("unknown")).toBe("Inconnu");
  });

  it("traduit le statut cancelled (brief SP-B10a, pas encore émis par le cœur)", () => {
    expect(jobStatusLabel("cancelled")).toBe("Annulé");
  });

  it("retombe sur le statut brut pour une valeur inconnue", () => {
    expect(jobStatusLabel("weird")).toBe("weird");
  });
});
