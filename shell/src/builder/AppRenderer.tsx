import { useEffect, useMemo, useRef, useState } from "react";
import type { AppConfig, RenderMode } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider } from "./ActionBusContext";
import { themeToCssVars } from "./theme";

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
  breakpoint,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  breakpoint?: Breakpoint;
}) {
  const editable = mode === "edit";
  const bus = useMemo(() => new ActionBus(), []);
  useEffect(() => {
    bus.configure(config.messages);
  }, [bus, config.messages]);

  // When no breakpoint is controlled (runtime/preview without a switcher),
  // auto-detect from the container width. jsdom has no ResizeObserver → keep lg.
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoBp, setAutoBp] = useState<Breakpoint>("lg");
  useEffect(() => {
    if (breakpoint) return;
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const update = () => setAutoBp(breakpointForWidth(el.clientWidth));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [breakpoint]);
  const bp = breakpoint ?? autoBp;

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    onChange({
      ...config,
      layout: {
        ...config.layout,
        items: config.layout.items.map((it) => (it.id === id ? moveItemAt(it, bp, dx, dy) : it)),
      },
    });
  }

  return (
    <div ref={containerRef} className="h-full w-full bg-[var(--gs-color-background)] font-[var(--gs-font)]" style={themeToCssVars(config.theme)}>
      <ActionBusProvider bus={bus}>
        <DataProvider sources={config.dataSources}>
          <GridCanvas
            items={config.layout.items}
            breakpoint={bp}
            editable={editable}
            selectedId={selectedId}
            onSelect={(id) => onSelect?.(id)}
            onMoveItem={handleMove}
            renderItem={(item) => <WidgetHost item={item} mode={mode} />}
          />
        </DataProvider>
      </ActionBusProvider>
    </div>
  );
}
