// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { posFor, styleForPos, moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";

const baseItem = { id: "a", widget: "text", x: 2, y: 3, w: 4, h: 2, props: {} };

test("posFor returns the base position at lg", () => {
  expect(posFor(baseItem, "lg")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("posFor falls back to the base position when a breakpoint has no override", () => {
  expect(posFor(baseItem, "sm")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("posFor uses the per-breakpoint override when present", () => {
  const item = { ...baseItem, layouts: { sm: { x: 0, y: 5, w: 12, h: 2 } } };
  expect(posFor(item, "sm")).toEqual({ x: 0, y: 5, w: 12, h: 2 });
  expect(posFor(item, "lg")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("styleForPos maps a position to grid CSS", () => {
  expect(styleForPos({ x: 2, y: 3, w: 4, h: 2 })).toEqual({
    gridColumn: "3 / span 4",
    gridRow: "4 / span 2",
  });
});

test("moveItemAt writes the base position at lg", () => {
  const moved = moveItemAt(baseItem, "lg", 1, -1);
  expect(moved.x).toBe(3);
  expect(moved.y).toBe(2);
  expect(moved.layouts).toBeUndefined();
});

test("moveItemAt writes a per-breakpoint override at sm and keeps the base intact", () => {
  const moved = moveItemAt(baseItem, "sm", 1, 0);
  expect(moved.x).toBe(2); // base untouched
  expect(moved.layouts?.sm).toEqual({ x: 3, y: 3, w: 4, h: 2 });
});

test("moveItemAt preserves other breakpoints' overrides", () => {
  const item = { ...baseItem, layouts: { md: { x: 1, y: 1, w: 6, h: 2 } } };
  const moved = moveItemAt(item, "sm", 1, 0);
  expect(moved.layouts?.md).toEqual({ x: 1, y: 1, w: 6, h: 2 });
  expect(moved.layouts?.sm).toEqual({ x: 3, y: 3, w: 4, h: 2 });
});

test("moveItemAt clamps within the grid", () => {
  const moved = moveItemAt(baseItem, "lg", 100, -100);
  expect(moved.x).toBe(12 - 4); // GRID_COLS - w
  expect(moved.y).toBe(0);
});

test("breakpointForWidth maps widths to breakpoints", () => {
  expect(breakpointForWidth(1280)).toBe<Breakpoint>("lg");
  expect(breakpointForWidth(1024)).toBe<Breakpoint>("lg");
  expect(breakpointForWidth(800)).toBe<Breakpoint>("md");
  expect(breakpointForWidth(640)).toBe<Breakpoint>("md");
  expect(breakpointForWidth(500)).toBe<Breakpoint>("sm");
});
