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
