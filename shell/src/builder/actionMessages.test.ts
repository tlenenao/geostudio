// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { ActionMessage } from "../api/types";
import { pruneMessagesForIds } from "./actionMessages";

function msg(over: Partial<ActionMessage>): ActionMessage {
  return { id: "m1", from: "w1", event: "clicked", to: "w2", action: "reset", ...over };
}

test("removes a message whose `from` references a removed id", () => {
  const messages = [msg({ id: "m1", from: "w1" })];
  expect(pruneMessagesForIds(messages, ["w1"])).toEqual([]);
});

test("removes a message whose `to` references a removed id", () => {
  const messages = [msg({ id: "m1", to: "w2" })];
  expect(pruneMessagesForIds(messages, ["w2"])).toEqual([]);
});

test("keeps a message that references none of the removed ids", () => {
  const messages = [msg({ id: "m1", from: "w1", to: "w2" })];
  expect(pruneMessagesForIds(messages, ["w3"])).toEqual(messages);
});

test("works with the var: prefix used for variable receivers", () => {
  const messages = [msg({ id: "m1", from: "w1", to: "var:v1" })];
  expect(pruneMessagesForIds(messages, ["var:v1"])).toEqual([]);
});

test("an empty removedIds list is a no-op (identity, not a copy)", () => {
  const messages = [msg({ id: "m1" })];
  expect(pruneMessagesForIds(messages, [])).toBe(messages);
});

test("removing several ids at once prunes every affected message", () => {
  const messages = [
    msg({ id: "m1", from: "w1", to: "w2" }),
    msg({ id: "m2", from: "w3", to: "w4" }),
    msg({ id: "m3", from: "w5", to: "w6" }),
  ];
  expect(pruneMessagesForIds(messages, ["w2", "w5"]).map((m) => m.id)).toEqual(["m2"]);
});
