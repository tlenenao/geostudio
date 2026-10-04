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

import { sanitizeDanglingMessages } from "./actionMessages";
import type { AppConfig } from "../api/types";

function cfg(over: Partial<AppConfig>): AppConfig {
  return {
    kind: "app",
    theme: {} as AppConfig["theme"],
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "text", x: 0, y: 0, w: 1, h: 1, props: {} },
        {
          id: "w2",
          widget: "modal",
          x: 0,
          y: 0,
          w: 1,
          h: 1,
          props: { items: [{ id: "w3", widget: "text", x: 0, y: 0, w: 1, h: 1, props: {} }] },
        },
      ],
    },
    ...over,
  };
}

test("sanitizeDanglingMessages drops dangling from/to, keeps nested widgets and var targets", () => {
  const c = cfg({
    variables: [{ id: "v1", name: "v", initialValue: null }],
    messages: [
      msg({ id: "ok1", from: "w1", to: "w3" }),
      msg({ id: "ok2", from: "w1", to: "var:v1" }),
      msg({ id: "badTo", from: "w1", to: "gone" }),
      msg({ id: "badFrom", from: "gone", to: "w1" }),
      msg({ id: "badVar", from: "w1", to: "var:nope" }),
    ],
  });
  expect(sanitizeDanglingMessages(c).messages.map((m) => m.id)).toEqual(["ok1", "ok2"]);
});

test("sanitizeDanglingMessages returns same ref when clean and prunes page onEnter", () => {
  const clean = cfg({ messages: [msg({ from: "w1", to: "w2" })] });
  expect(sanitizeDanglingMessages(clean)).toBe(clean);
  const withPage = cfg({
    pages: [
      {
        id: "p1",
        name: "p",
        layout: { type: "grid", breakpoints: {}, items: [] },
        onEnter: [msg({ id: "e1", to: "gone" }), msg({ id: "e2", to: "w1" })],
      },
    ],
  });
  expect(sanitizeDanglingMessages(withPage).pages![0].onEnter!.map((m) => m.id)).toEqual(["e2"]);
});
