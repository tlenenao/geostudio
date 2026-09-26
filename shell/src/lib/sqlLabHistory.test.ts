// SPDX-License-Identifier: Apache-2.0
import { appendSqlHistory, findSqlHistoryEntry, readSqlHistory } from "./sqlLabHistory";

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
    appendSqlHistory({
      sql: "select 1",
      executedAt: "2026-08-03T10:00:00Z",
      status: "ok",
      rowCount: 1,
    });
    const after = appendSqlHistory({
      sql: "select 2",
      executedAt: "2026-08-03T10:01:00Z",
      status: "error",
    });
    expect(after).toHaveLength(2);
    expect(after[0]).toMatchObject({
      sql: "select 2",
      executedAt: "2026-08-03T10:01:00Z",
      status: "error",
    });
    expect(after[1]).toMatchObject({
      sql: "select 1",
      executedAt: "2026-08-03T10:00:00Z",
      status: "ok",
      rowCount: 1,
    });
    expect(after[0].id).toBeTruthy();
    expect(after[1].id).toBeTruthy();
    expect(after[0].id).not.toBe(after[1].id);
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

  test("attribue un id unique à chaque entrée ajoutée", () => {
    const history = appendSqlHistory({
      sql: "select 1",
      executedAt: "2026-09-26T00:00:00Z",
      status: "ok",
      rowCount: 1,
    });
    expect(history[0].id).toBeTruthy();
  });

  test("findSqlHistoryEntry retrouve une entrée par id", () => {
    const history = appendSqlHistory({
      sql: "select 1",
      executedAt: "2026-09-26T00:00:00Z",
      status: "ok",
      rowCount: 1,
    });
    expect(findSqlHistoryEntry(history[0].id)).toEqual(history[0]);
  });

  test("findSqlHistoryEntry renvoie undefined pour un id inconnu", () => {
    expect(findSqlHistoryEntry("inconnu")).toBeUndefined();
  });
});
