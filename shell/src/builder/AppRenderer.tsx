import { useEffect, useMemo } from "react";
import type { AppConfig, RenderMode } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItem } from "./grid";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider } from "./ActionBusContext";

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
}) {
  const editable = mode === "edit";
  const bus = useMemo(() => new ActionBus(), []);
  useEffect(() => {
    bus.configure(config.messages);
  }, [bus, config.messages]);

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    onChange({
      ...config,
      layout: {
        ...config.layout,
        items: config.layout.items.map((it) => (it.id === id ? moveItem(it, dx, dy) : it)),
      },
    });
  }

  return (
    <ActionBusProvider bus={bus}>
      <DataProvider sources={config.dataSources}>
        <GridCanvas
          items={config.layout.items}
          editable={editable}
          selectedId={selectedId}
          onSelect={(id) => onSelect?.(id)}
          onMoveItem={handleMove}
          renderItem={(item) => <WidgetHost item={item} mode={mode} />}
        />
      </DataProvider>
    </ActionBusProvider>
  );
}
