import { expect, test } from "vitest";
import { TEMPLATES, getTemplate } from "./templates";

test("exposes exactly one app template and one dashboard template", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(1);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(1);
});

test("every template has at least one layout item", () => {
  for (const t of TEMPLATES) {
    expect(t.layout.items.length).toBeGreaterThan(0);
  }
});

test("getTemplate resolves a template by id", () => {
  const first = TEMPLATES[0];
  expect(getTemplate(first.id)).toBe(first);
});

test("getTemplate returns undefined for an unknown id", () => {
  expect(getTemplate("nope")).toBeUndefined();
});
