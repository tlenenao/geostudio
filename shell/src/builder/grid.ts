import type { CSSProperties } from "react";
import type { WidgetItem } from "../api/types";

export const GRID_COLS = 12;

export function moveItem(item: WidgetItem, dxCells: number, dyCells: number): WidgetItem {
  const x = Math.max(0, Math.min(GRID_COLS - item.w, item.x + dxCells));
  const y = Math.max(0, item.y + dyCells);
  return { ...item, x, y };
}

export function resizeItem(item: WidgetItem, dwCells: number, dhCells: number): WidgetItem {
  const w = Math.max(1, Math.min(GRID_COLS - item.x, item.w + dwCells));
  const h = Math.max(1, item.h + dhCells);
  return { ...item, w, h };
}

export function styleFor(item: WidgetItem): CSSProperties {
  return {
    gridColumn: `${item.x + 1} / span ${item.w}`,
    gridRow: `${item.y + 1} / span ${item.h}`,
  };
}

export const BREAKPOINTS = ["sm", "md", "lg"] as const;
export type Breakpoint = (typeof BREAKPOINTS)[number];
export type Pos = { x: number; y: number; w: number; h: number };

function basePos(item: WidgetItem): Pos {
  return { x: item.x, y: item.y, w: item.w, h: item.h };
}

// Effective position of an item at a breakpoint. `lg` is the base position
// (x/y/w/h); md/sm use their override if present, else fall back to the base.
export function posFor(item: WidgetItem, bp: Breakpoint): Pos {
  if (bp === "lg") return basePos(item);
  return item.layouts?.[bp] ?? basePos(item);
}

export function styleForPos(pos: Pos): CSSProperties {
  return {
    gridColumn: `${pos.x + 1} / span ${pos.w}`,
    gridRow: `${pos.y + 1} / span ${pos.h}`,
  };
}

// Move an item within a breakpoint: writes the base position at `lg`, or the
// per-breakpoint override at md/sm (leaving the base and other breakpoints
// untouched). Clamps to the grid.
export function moveItemAt(item: WidgetItem, bp: Breakpoint, dxCells: number, dyCells: number): WidgetItem {
  const cur = posFor(item, bp);
  const x = Math.max(0, Math.min(GRID_COLS - cur.w, cur.x + dxCells));
  const y = Math.max(0, cur.y + dyCells);
  if (bp === "lg") return { ...item, x, y };
  return { ...item, layouts: { ...item.layouts, [bp]: { ...cur, x, y } } };
}

export function breakpointForWidth(width: number): Breakpoint {
  if (width >= 1024) return "lg";
  if (width >= 640) return "md";
  return "sm";
}
