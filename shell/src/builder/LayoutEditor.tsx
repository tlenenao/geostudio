// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { DataSource, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { moveItemAt, nextFreePosition, type Breakpoint } from "./grid";
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
}: {
  items: WidgetItem[];
  onChange: (items: WidgetItem[]) => void;
  dataSources: DataSource[];
  breakpoint: Breakpoint;
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

  function handleRemove(id: string) {
    onChange(items.filter((i) => i.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  return (
    <div className="flex flex-col gap-2">
      <WidgetPalette onAdd={addWidget} exclude={NESTED_EXCLUDE} />
      <div className="h-48 overflow-auto border border-slate-200">
        <GridCanvas
          items={items}
          breakpoint={breakpoint}
          editable
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveItem={handleMove}
          onRemoveItem={handleRemove}
          renderItem={(item) => <WidgetHost item={item} mode="edit" />}
        />
      </div>
      <PropsPanel
        item={selected}
        dataSources={dataSources}
        onChange={updateSelectedProps}
        onVisibleWhenChange={updateSelectedVisibleWhen}
      />
    </div>
  );
}
