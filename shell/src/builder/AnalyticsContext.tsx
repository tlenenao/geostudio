// SPDX-License-Identifier: Apache-2.0
export const EXTENT_DEBOUNCE_MS = 500;

export type CrossFilterEntry = { field: string; value: string | string[]; originSourceId: string };

export type AnalyticsContextState = {
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, CrossFilterEntry | undefined>;
};

export const EMPTY_ANALYTICS_CONTEXT: AnalyticsContextState = { timeRange: null, extent: null, crossFilter: {} };

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type SetTimeRange = (range: { from: string; to: string } | null) => void;
type SetExtent = (bbox: [number, number, number, number] | null) => void;
type SetCrossFilter = (datasetId: string, field: string, value: string | string[], originSourceId: string) => void;

const AnalyticsStateContext = createContext<AnalyticsContextState>(EMPTY_ANALYTICS_CONTEXT);
const AnalyticsSettersContext = createContext<{ setTimeRange: SetTimeRange; setExtent: SetExtent; setCrossFilter: SetCrossFilter }>({
  setTimeRange: () => {}, setExtent: () => {}, setCrossFilter: () => {},
});

function sameCrossFilterValue(a: CrossFilterEntry["value"], b: CrossFilterEntry["value"]): boolean {
  return Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a) === JSON.stringify(b) : a === b;
}

export function AnalyticsContextProvider({
  interactions, initialState, onStateChange, children,
}: {
  interactions?: "auto" | "manual";
  initialState?: AnalyticsContextState;
  onStateChange?: (state: AnalyticsContextState) => void;
  children: ReactNode;
}) {
  const active = interactions === "auto";
  const [state, setState] = useState<AnalyticsContextState>(initialState ?? EMPTY_ANALYTICS_CONTEXT);
  const extentTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onStateChangeRef = useRef(onStateChange);
  useEffect(() => { onStateChangeRef.current = onStateChange; }, [onStateChange]);
  useEffect(() => { onStateChangeRef.current?.(state); }, [state]);
  useEffect(() => () => { if (extentTimer.current) clearTimeout(extentTimer.current); }, []);

  const setTimeRange = useCallback<SetTimeRange>((range) => {
    if (!active) return;
    setState((prev) => ({ ...prev, timeRange: range }));
  }, [active]);

  const setExtent = useCallback<SetExtent>((bbox) => {
    if (!active) return;
    if (extentTimer.current) clearTimeout(extentTimer.current);
    extentTimer.current = setTimeout(() => {
      setState((prev) => ({ ...prev, extent: bbox }));
    }, EXTENT_DEBOUNCE_MS);
  }, [active]);

  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const setters = useMemo(() => ({ setTimeRange, setExtent, setCrossFilter }), [setTimeRange, setExtent, setCrossFilter]);

  return (
    <AnalyticsSettersContext.Provider value={setters}>
      <AnalyticsStateContext.Provider value={state}>{children}</AnalyticsStateContext.Provider>
    </AnalyticsSettersContext.Provider>
  );
}

export function useAnalyticsContext(): AnalyticsContextState {
  return useContext(AnalyticsStateContext);
}
export function useSetTimeRange(): SetTimeRange {
  return useContext(AnalyticsSettersContext).setTimeRange;
}
export function useSetExtent(): SetExtent {
  return useContext(AnalyticsSettersContext).setExtent;
}
export function useSetCrossFilter(): SetCrossFilter {
  return useContext(AnalyticsSettersContext).setCrossFilter;
}
