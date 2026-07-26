## Task 1: `ExplorerContext` — open/close state and gating

**Files:**
- Create: `shell/src/builder/ExplorerContext.tsx`
- Test: `shell/src/builder/ExplorerContext.test.tsx`

**Interfaces:**
- Produces (consumed by every later task):
  - `type ExplorerTarget = { datasetId: string; dataSourceId: string } | null`
  - `function ExplorerProvider({ enabled, children }: { enabled?: boolean; children: ReactNode })`
  - `function useExplorerTarget(): ExplorerTarget`
  - `function useExplorerEnabled(): boolean`
  - `function useOpenExplorer(): (target: { datasetId: string; dataSourceId: string }) => void`
  - `function useCloseExplorer(): () => void`

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/ExplorerContext.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { ExplorerProvider, useCloseExplorer, useExplorerEnabled, useExplorerTarget, useOpenExplorer } from "./ExplorerContext";

function Probe() {
  const target = useExplorerTarget();
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const close = useCloseExplorer();
  return (
    <div>
      <p>enabled:{String(enabled)}</p>
      <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>
      <button onClick={() => open({ datasetId: "ds1", dataSourceId: "src1" })}>open</button>
      <button onClick={() => open({ datasetId: "ds2", dataSourceId: "src2" })}>open-other</button>
      <button onClick={close}>close</button>
    </div>
  );
}

test("openExplorer is a silent no-op when the provider is disabled", async () => {
  render(<ExplorerProvider enabled={false}><Probe /></ExplorerProvider>);
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("openExplorer sets the target when enabled", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  expect(screen.getByText("enabled:true")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("opening a second target while one is open replaces it (last one wins)", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("open-other"));
  expect(screen.getByText("target:ds2/src2")).toBeInTheDocument();
});

test("closeExplorer clears the target", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("close"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("hooks work with no provider mounted at all (default disabled, no-op)", async () => {
  render(<Probe />);
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/ExplorerContext.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerContext"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/ExplorerContext.tsx`:

```tsx
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/ExplorerContext.test.tsx`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/ExplorerContext.tsx shell/src/builder/ExplorerContext.test.tsx
git commit -m "feat(shell): ExplorerContext — open/close state for the analytics drill panel (SP-14d)"
```

---

