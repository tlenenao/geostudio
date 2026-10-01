// SPDX-License-Identifier: Apache-2.0
// P07.07/P07.08 : historiques cloisonnés par compte, purgés à la déconnexion.
import { appendCopilotHistory, readCopilotHistory } from "./copilotHistory";
import { appendSqlHistory, readSqlHistory } from "./sqlLabHistory";
import { purgeLocalHistories, setStorageUser } from "./userStorage";

beforeEach(() => {
  localStorage.clear();
  setStorageUser(undefined);
});

test("le SQL Lab d'un compte n'est pas lisible par un autre", () => {
  setStorageUser("alice");
  appendSqlHistory({ sql: "select secret", executedAt: "2026-01-01T00:00:00Z", status: "ok" });
  setStorageUser("bob");
  expect(readSqlHistory()).toEqual([]);
  setStorageUser("alice");
  expect(readSqlHistory()).toHaveLength(1);
});

test("l'historique copilote est cloisonné par compte ET par item", () => {
  setStorageUser("alice");
  appendCopilotHistory({ message: "m", opsCount: 0, status: "ok" }, "item-1");
  expect(readCopilotHistory("item-1")).toHaveLength(1);
  expect(readCopilotHistory("item-2")).toEqual([]);
  setStorageUser("bob");
  expect(readCopilotHistory("item-1")).toEqual([]);
});

test("purgeLocalHistories vide tous les comptes et l'ancienne clé non scopée", () => {
  setStorageUser("alice");
  appendSqlHistory({ sql: "x", executedAt: "2026-01-01T00:00:00Z", status: "ok" });
  appendCopilotHistory({ message: "m", opsCount: 0, status: "ok" }, "item-1");
  localStorage.setItem("geostudio.sqlLab.history", "[]");
  localStorage.setItem("autre", "garde");
  purgeLocalHistories();
  expect(Object.keys(localStorage)).toEqual(["autre"]);
});
