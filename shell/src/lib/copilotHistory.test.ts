// SPDX-License-Identifier: Apache-2.0
import { appendCopilotHistory, readCopilotHistory } from "./copilotHistory";

beforeEach(() => localStorage.clear());

describe("copilotHistory", () => {
  test("readCopilotHistory returns an empty list when nothing is stored", () => {
    expect(readCopilotHistory()).toEqual([]);
  });

  test("readCopilotHistory returns an empty list when the stored value is corrupted JSON", () => {
    localStorage.setItem("geostudio.copilot.history", "{not json");
    expect(readCopilotHistory()).toEqual([]);
  });

  test("appendCopilotHistory prepends the newest entry and persists it", () => {
    appendCopilotHistory({ message: "ajoute une carte", opsCount: 1, status: "ok" });
    const after = appendCopilotHistory({
      message: "corrige la requête",
      opsCount: 0,
      status: "error",
    });
    expect(after).toHaveLength(2);
    expect(after[0]).toMatchObject({
      message: "corrige la requête",
      opsCount: 0,
      status: "error",
    });
    expect(after[1]).toMatchObject({
      message: "ajoute une carte",
      opsCount: 1,
      status: "ok",
    });
    expect(after[0].id).toBeTruthy();
    expect(after[1].id).toBeTruthy();
    expect(after[0].id).not.toBe(after[1].id);
    expect(after[0].executedAt).toBeTruthy();
    expect(readCopilotHistory()).toEqual(after);
  });

  test("appendCopilotHistory caps the list at 20 entries, dropping the oldest", () => {
    for (let i = 0; i < 25; i++) {
      appendCopilotHistory({ message: `m${i}`, opsCount: 0, status: "ok" });
    }
    const result = readCopilotHistory();
    expect(result).toHaveLength(20);
    expect(result[0].message).toBe("m24");
    expect(result.find((e) => e.message === "m0")).toBeUndefined();
  });

  test("attribue un id unique à chaque entrée ajoutée", () => {
    const history = appendCopilotHistory({
      message: "ajoute une carte",
      opsCount: 1,
      status: "ok",
    });
    expect(history[0].id).toBeTruthy();
  });
});
