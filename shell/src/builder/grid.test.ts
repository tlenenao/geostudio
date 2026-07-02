import { expect, test } from "vitest";
import { GRID_COLS, moveItem, resizeItem, styleFor } from "./grid";
import type { WidgetItem } from "../api/types";

const base: WidgetItem = { id: "a", widget: "text", x: 2, y: 2, w: 4, h: 2, props: {} };

test("moveItem shifts by cells and clamps to the grid", () => {
  expect(moveItem(base, 1, 1)).toMatchObject({ x: 3, y: 3 });
  expect(moveItem(base, -5, -5)).toMatchObject({ x: 0, y: 0 });
  expect(moveItem(base, 100, 0).x).toBe(GRID_COLS - base.w);
});

test("resizeItem changes size with min 1 and right-edge clamp", () => {
  expect(resizeItem(base, 2, 1)).toMatchObject({ w: 6, h: 3 });
  expect(resizeItem(base, -10, -10)).toMatchObject({ w: 1, h: 1 });
  expect(resizeItem({ ...base, x: 10 }, 100, 0).w).toBe(GRID_COLS - 10);
});

test("styleFor maps to CSS grid placement", () => {
  expect(styleFor(base)).toMatchObject({
    gridColumn: "3 / span 4",
    gridRow: "3 / span 2",
  });
});
