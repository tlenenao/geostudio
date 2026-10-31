// SPDX-License-Identifier: Apache-2.0
export const EXTENT_DEBOUNCE_MS = 500;

export type CrossFilterValue = string | string[] | { from: string; to: string };
export type CrossFilterEntry = {
  field: string;
  value: CrossFilterValue;
  originSourceId: string;
  geometry?: unknown;
};

export type AnalyticsContextState = {
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  // AUD-059 : une entrée par dataset ET par widget émetteur (`originSourceId`).
  crossFilter: Record<string, Record<string, CrossFilterEntry>>;
};

/** Lecture tolérante de l'ancienne forme `{dataset: entrée}` (URL, signets). */
export function normalizeCrossFilter(raw: unknown): AnalyticsContextState["crossFilter"] {
  const out: AnalyticsContextState["crossFilter"] = {};
  if (!raw || typeof raw !== "object") return out;
  for (const [ds, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!v || typeof v !== "object") continue;
    const e = v as Partial<CrossFilterEntry>;
    if (typeof e.field === "string" && typeof e.originSourceId === "string")
      out[ds] = { [e.originSourceId]: e as CrossFilterEntry };
    else out[ds] = v as Record<string, CrossFilterEntry>;
  }
  return out;
}

export const EMPTY_ANALYTICS_CONTEXT: AnalyticsContextState = {
  timeRange: null,
  extent: null,
  crossFilter: {},
};

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type SetTimeRange = (range: { from: string; to: string } | null) => void;
type SetExtent = (bbox: [number, number, number, number] | null) => void;
type SetCrossFilter = (
  datasetId: string,
  field: string,
  value: CrossFilterValue,
  originSourceId: string,
  geometry?: unknown,
) => void;
type ClearCrossFilter = (datasetId: string, originSourceId?: string) => void;

const AnalyticsStateContext = createContext<AnalyticsContextState>(EMPTY_ANALYTICS_CONTEXT);
const AnalyticsSettersContext = createContext<{
  setTimeRange: SetTimeRange;
  setExtent: SetExtent;
  setCrossFilter: SetCrossFilter;
  clearCrossFilter: ClearCrossFilter;
}>({
  setTimeRange: () => {},
  setExtent: () => {},
  setCrossFilter: () => {},
  clearCrossFilter: () => {},
});

function sameCrossFilterValue(a: CrossFilterValue, b: CrossFilterValue): boolean {
  return typeof a === "string" && typeof b === "string"
    ? a === b
    : JSON.stringify(a) === JSON.stringify(b);
}

export function AnalyticsContextProvider({
  interactions,
  initialState,
  onStateChange,
  children,
}: {
  interactions?: "auto" | "manual";
  initialState?: AnalyticsContextState;
  onStateChange?: (state: AnalyticsContextState) => void;
  children: ReactNode;
}) {
  const active = interactions === "auto";
  const [state, setState] = useState<AnalyticsContextState>(
    initialState ?? EMPTY_ANALYTICS_CONTEXT,
  );
  const extentTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onStateChangeRef = useRef(onStateChange);
  useEffect(() => {
    onStateChangeRef.current = onStateChange;
  }, [onStateChange]);
  useEffect(() => {
    onStateChangeRef.current?.(state);
  }, [state]);
  useEffect(
    () => () => {
      if (extentTimer.current) clearTimeout(extentTimer.current);
    },
    [],
  );

  const setTimeRange = useCallback<SetTimeRange>(
    (range) => {
      if (!active) return;
      setState((prev) => ({ ...prev, timeRange: range }));
    },
    [active],
  );

  const setExtent = useCallback<SetExtent>(
    (bbox) => {
      if (!active) return;
      if (extentTimer.current) clearTimeout(extentTimer.current);
      extentTimer.current = setTimeout(() => {
        setState((prev) => ({ ...prev, extent: bbox }));
      }, EXTENT_DEBOUNCE_MS);
    },
    [active],
  );

  const setCrossFilter = useCallback<SetCrossFilter>(
    (datasetId, field, value, originSourceId, geometry) => {
      if (!active) return;
      setState((prev) => {
        const current = prev.crossFilter[datasetId]?.[originSourceId];
        const isToggleOff =
          Boolean(current) &&
          current!.field === field &&
          sameCrossFilterValue(current!.value, value);
        const entries = { ...prev.crossFilter[datasetId] };
        if (isToggleOff) delete entries[originSourceId];
        else entries[originSourceId] = { field, value, originSourceId, geometry };
        const nextCrossFilter = { ...prev.crossFilter, [datasetId]: entries };
        if (Object.keys(entries).length === 0) delete nextCrossFilter[datasetId];
        return { ...prev, crossFilter: nextCrossFilter };
      });
    },
    [active],
  );

  const clearCrossFilter = useCallback<ClearCrossFilter>(
    (datasetId, originSourceId) => {
      if (!active) return;
      setState((prev) => {
        const entries = prev.crossFilter[datasetId];
        if (!entries) return prev;
        if (originSourceId !== undefined && !entries[originSourceId]) return prev;
        const nextCrossFilter = { ...prev.crossFilter };
        const rest = { ...entries };
        if (originSourceId !== undefined) delete rest[originSourceId];
        if (originSourceId === undefined || Object.keys(rest).length === 0)
          delete nextCrossFilter[datasetId];
        else nextCrossFilter[datasetId] = rest;
        return { ...prev, crossFilter: nextCrossFilter };
      });
    },
    [active],
  );

  const setters = useMemo(
    () => ({ setTimeRange, setExtent, setCrossFilter, clearCrossFilter }),
    [setTimeRange, setExtent, setCrossFilter, clearCrossFilter],
  );

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
export function useClearCrossFilter(): ClearCrossFilter {
  return useContext(AnalyticsSettersContext).clearCrossFilter;
}
