import { expect, test } from "vitest";
import { getConfigExpressionErrors } from "./configExpressionErrors";
import type { AppConfig } from "../api/types";

function config(items: AppConfig["layout"]["items"]): AppConfig {
  return { kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", breakpoints: {}, items } };
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
