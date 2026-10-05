// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { DataSource, Variable, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import {
  duplicateItem,
  moveItemAt,
  nextFreePosition,
  nextOrdinal,
  resizeItemAt,
  type Breakpoint,
} from "./grid";
import { WidgetPalette } from "./WidgetPalette";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { PropsPanel } from "./PropsPanel";

const NESTED_EXCLUDE = ["tabs", "modal", "drawer"];

export function LayoutEditor({
  items,
  onChange,
  dataSources,
  breakpoint,
  variables,
}: {
  items: WidgetItem[];
  onChange: (items: WidgetItem[]) => void;
  dataSources: DataSource[];
  breakpoint: Breakpoint;
  variables?: Variable[];
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find((i) => i.id === selectedId) ?? null;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def) return;
    const { x, y } = nextFreePosition(items);
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x,
      y,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
      ordinal: nextOrdinal(items, type),
    };
    onChange([...items, item]);
    setSelectedId(item.id);
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    onChange(items.map((i) => (i.id === selectedId ? { ...i, props } : i)));
  }

  function updateSelectedVisibleWhen(expr: string) {
    onChange(
      items.map((i) => (i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i)),
    );
  }

  function handleMove(id: string, dx: number, dy: number) {
    onChange(items.map((i) => (i.id === id ? moveItemAt(i, breakpoint, dx, dy) : i)));
  }

  function handleResize(id: string, dw: number, dh: number) {
    onChange(items.map((i) => (i.id === id ? resizeItemAt(i, breakpoint, dw, dh) : i)));
  }

  function handleDuplicate(id: string) {
    const src = items.find((i) => i.id === id);
    if (!src) return;
    const copy = duplicateItem(src, items);
    onChange([...items, copy]);
    setSelectedId(copy.id);
  }

  function handleRemove(id: string) {
    onChange(items.filter((i) => i.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  return (
    <div className="flex flex-col gap-2">
      <WidgetPalette onAdd={addWidget} exclude={NESTED_EXCLUDE} />
      <div className="h-48 overflow-auto border border-rule">
        <GridCanvas
          items={items}
          breakpoint={breakpoint}
          editable
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveItem={handleMove}
          onRemoveItem={handleRemove}
          onResizeItem={handleResize}
          onDuplicateItem={handleDuplicate}
          renderItem={(item) => <WidgetHost item={item} mode="edit" />}
        />
      </div>
      <PropsPanel
        key={selected?.id ?? "none"}
        item={selected}
        dataSources={dataSources}
        variables={variables ?? []}
        onChange={updateSelectedProps}
        onVisibleWhenChange={updateSelectedVisibleWhen}
      />
    </div>
  );
}
