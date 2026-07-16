// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import type { ActionBus, BusHandler } from "./ActionBus";

const ActionBusContext = createContext<ActionBus | null>(null);

export function ActionBusProvider({ bus, children }: { bus: ActionBus; children: ReactNode }) {
  return <ActionBusContext.Provider value={bus}>{children}</ActionBusContext.Provider>;
}

export function useActionBus(): ActionBus | null {
  return useContext(ActionBusContext);
}

// Register a widget action for the widget's lifetime. The handler is kept in a
// ref so re-renders don't churn the registration but the latest closure runs.
export function useBusAction(
  bus: ActionBus | null | undefined,
  widgetId: string | undefined,
  action: string,
  handler: BusHandler,
): void {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => {
    if (!bus || !widgetId) return;
    return bus.register(widgetId, action, (p) => ref.current(p));
  }, [bus, widgetId, action]);
}
