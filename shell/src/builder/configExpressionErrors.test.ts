// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { getConfigExpressionErrors } from "./configExpressionErrors";
import type { AppConfig } from "../api/types";

function config(items: AppConfig["layout"]["items"], messages: AppConfig["messages"] = []): AppConfig {
  return { kind: "app", theme: {}, dataSources: [], messages, layout: { type: "grid", breakpoints: {}, items } };
}

test("returns no errors for a config with no expressions", () => {
  expect(getConfigExpressionErrors(config([{ id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {} }]))).toEqual([]);
});

test("returns no errors when visibleWhen and a calculated column are valid", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "vars.x == 'a'" },
    { id: "w2", widget: "table", x: 0, y: 2, w: 2, h: 2, props: { columns: ["nom", { label: "C", expr: "1 + 1" }] } },
  ];
  expect(getConfigExpressionErrors(config(items))).toEqual([]);
});

test("reports an invalid visibleWhen with the widget id", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "vars.x ==" },
  ];
  const errors = getConfigExpressionErrors(config(items));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("w1");
});

test("reports an invalid calculated column expression with the widget id and column label", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w2", widget: "table", x: 0, y: 0, w: 2, h: 2, props: { columns: [{ label: "Mauvaise", expr: "1 +" }] } },
  ];
  const errors = getConfigExpressionErrors(config(items));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("w2");
  expect(errors[0]).toContain("Mauvaise");
});

test("does not throw when a calculated column's expr is not a string (corrupted config)", () => {
  const items: AppConfig["layout"]["items"] = [
    {
      id: "w3",
      widget: "table",
      x: 0,
      y: 0,
      w: 2,
      h: 2,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      props: { columns: [{ label: "Mauvaise", expr: 42 } as any] },
    },
  ];
  expect(() => getConfigExpressionErrors(config(items))).not.toThrow();
  expect(Array.isArray(getConfigExpressionErrors(config(items)))).toBe(true);
});

test("returns no errors when a message's condition is valid", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop", when: "vars.x == 'a'" }];
  expect(getConfigExpressionErrors(config([], messages))).toEqual([]);
});

test("ignores a message without a condition", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop" }];
  expect(getConfigExpressionErrors(config([], messages))).toEqual([]);
});

test("reports an invalid message condition with the message id", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop", when: "vars.x ==" }];
  const errors = getConfigExpressionErrors(config([], messages));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("m1");
});

test("does not throw when a message's when is not a string (corrupted config)", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop", when: 42 as any }];
  expect(() => getConfigExpressionErrors(config([], messages))).not.toThrow();
  expect(getConfigExpressionErrors(config([], messages))).toEqual([]);
});

test("reports an invalid when condition on a page onEnter message", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1", name: "Intro",
        layout: { type: "grid", breakpoints: {}, items: [] },
        onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.(" }],
      },
    ],
  };
  const errors = getConfigExpressionErrors(config);
  expect(errors.some((e) => e.includes("Intro") && e.includes("oe1"))).toBe(true);
});

test("accepts a valid when condition on a page onEnter message", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1", name: "Intro",
        layout: { type: "grid", breakpoints: {}, items: [] },
        onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.ready" }],
      },
    ],
  };
  expect(getConfigExpressionErrors(config)).toEqual([]);
});

test("accepts a visibleWhen expression referencing the ctx.* analytics prefix (cel-js parse is syntax-only)", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "ctx.timeRange != null" },
    ] },
  };
  expect(getConfigExpressionErrors(config)).toEqual([]);
});
