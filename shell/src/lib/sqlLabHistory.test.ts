// SPDX-License-Identifier: Apache-2.0
import { appendSqlHistory, readSqlHistory } from "./sqlLabHistory";

beforeEach(() => localStorage.clear());

describe("sqlLabHistory", () => {
  test("readSqlHistory returns an empty list when nothing is stored", () => {
    expect(readSqlHistory()).toEqual([]);
  });

  test("readSqlHistory returns an empty list when the stored value is corrupted JSON", () => {
    localStorage.setItem("geostudio.sqlLab.history", "{not json");
    expect(readSqlHistory()).toEqual([]);
  });

  test("appendSqlHistory prepends the newest entry and persists it", () => {
    appendSqlHistory({ sql: "select 1", executedAt: "2026-08-03T10:00:00Z", status: "ok", rowCount: 1 });
    const after = appendSqlHistory({ sql: "select 2", executedAt: "2026-08-03T10:01:00Z", status: "error" });
    expect(after).toEqual([
      { sql: "select 2", executedAt: "2026-08-03T10:01:00Z", status: "error" },
      { sql: "select 1", executedAt: "2026-08-03T10:00:00Z", status: "ok", rowCount: 1 },
    ]);
    expect(readSqlHistory()).toEqual(after);
  });

  test("appendSqlHistory caps the list at 20 entries, dropping the oldest", () => {
    for (let i = 0; i < 20; i++) {
      appendSqlHistory({ sql: `select ${i}`, executedAt: `t${i}`, status: "ok" });
    }
    const result = appendSqlHistory({ sql: "select 20", executedAt: "t20", status: "ok" });
    expect(result).toHaveLength(20);
    expect(result[0].sql).toBe("select 20");
    expect(result.find((e) => e.sql === "select 0")).toBeUndefined();
  });
});
