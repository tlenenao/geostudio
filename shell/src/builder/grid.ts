// SPDX-License-Identifier: Apache-2.0
import type { CSSProperties } from "react";
import type { WidgetItem } from "../api/types";

export const GRID_COLS = 12;

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

// Effective positions of all items at a breakpoint. At `sm`, items without an explicit
// `layouts.sm` stack full width (reading order: y, then x) instead of staying side by
// side on a phone; items with an explicit override keep it.
export function positionsFor(items: WidgetItem[], bp: Breakpoint): Map<string, Pos> {
  const out = new Map<string, Pos>();
  if (bp !== "sm") {
    for (const it of items) out.set(it.id, posFor(it, bp));
    return out;
  }
  let y = 0;
  const auto = items.filter((it) => !it.layouts?.sm).sort((a, b) => a.y - b.y || a.x - b.x);
  for (const it of items) if (it.layouts?.sm) out.set(it.id, it.layouts.sm);
  for (const it of auto) {
    out.set(it.id, { x: 0, y, w: GRID_COLS, h: it.h });
    y += it.h;
  }
  return out;
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
export function moveItemAt(
  item: WidgetItem,
  bp: Breakpoint,
  dxCells: number,
  dyCells: number,
): WidgetItem {
  const cur = posFor(item, bp);
  const x = Math.max(0, Math.min(GRID_COLS - cur.w, cur.x + dxCells));
  const y = Math.max(0, cur.y + dyCells);
  if (bp === "lg") return { ...item, x, y };
  return { ...item, layouts: { ...item.layouts, [bp]: { ...cur, x, y } } };
}

// Resize an item within a breakpoint (same lg/override rule as moveItemAt). Width is
// clamped to the grid (x + w <= GRID_COLS), height to >= 1.
export function resizeItemAt(
  item: WidgetItem,
  bp: Breakpoint,
  dwCells: number,
  dhCells: number,
): WidgetItem {
  const cur = posFor(item, bp);
  const w = Math.max(1, Math.min(GRID_COLS - cur.x, cur.w + dwCells));
  const h = Math.max(1, cur.h + dhCells);
  if (bp === "lg") return { ...item, w, h };
  return { ...item, layouts: { ...item.layouts, [bp]: { ...cur, w, h } } };
}

// Copy of an item with a fresh id, placed below all existing items.
export function duplicateItem(item: WidgetItem, items: WidgetItem[]): WidgetItem {
  const { x, y } = nextFreePosition(items);
  return {
    ...structuredClone(item),
    id: crypto.randomUUID(),
    x,
    y,
    layouts: undefined,
  };
}

// Position for a newly added widget: stack it below all existing items (at
// the base/`lg` breakpoint) so it never overlaps a widget already on the
// canvas. Without this, every new item would default to (0, 0) and sit on
// top of whatever's already there — invisible/unclickable underneath in
// preview and runtime.
export function nextFreePosition(items: WidgetItem[]): { x: number; y: number } {
  const maxY = items.reduce((max, item) => Math.max(max, item.y + item.h), 0);
  return { x: 0, y: maxY };
}

export function breakpointForWidth(width: number): Breakpoint {
  if (width >= 1024) return "lg";
  if (width >= 640) return "md";
  return "sm";
}
