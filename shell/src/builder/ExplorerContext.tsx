// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type ExplorerTarget = { datasetId: string; dataSourceId: string } | null;

type OpenExplorer = (target: { datasetId: string; dataSourceId: string }) => void;
type CloseExplorer = () => void;

const ExplorerTargetContext = createContext<ExplorerTarget>(null);
const ExplorerEnabledContext = createContext<boolean>(false);
const ExplorerSettersContext = createContext<{ open: OpenExplorer; close: CloseExplorer }>({
  open: () => {}, close: () => {},
});

export function ExplorerProvider({
  enabled = false, children,
}: {
  enabled?: boolean;
  children: ReactNode;
}) {
  const [target, setTarget] = useState<ExplorerTarget>(null);

  const open = useCallback<OpenExplorer>((next) => {
    if (!enabled) return;
    setTarget(next);
  }, [enabled]);

  const close = useCallback<CloseExplorer>(() => {
    setTarget(null);
  }, []);

  const setters = useMemo(() => ({ open, close }), [open, close]);

  return (
    <ExplorerEnabledContext.Provider value={enabled}>
      <ExplorerSettersContext.Provider value={setters}>
        <ExplorerTargetContext.Provider value={target}>{children}</ExplorerTargetContext.Provider>
      </ExplorerSettersContext.Provider>
    </ExplorerEnabledContext.Provider>
  );
}

export function useExplorerTarget(): ExplorerTarget {
  return useContext(ExplorerTargetContext);
}
export function useExplorerEnabled(): boolean {
  return useContext(ExplorerEnabledContext);
}
export function useOpenExplorer(): OpenExplorer {
  return useContext(ExplorerSettersContext).open;
}
export function useCloseExplorer(): CloseExplorer {
  return useContext(ExplorerSettersContext).close;
}
