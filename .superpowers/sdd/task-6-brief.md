## Task 6: `ErrorBoundary` applicatif (3.5c)

**Files:**
- Create: `shell/src/AppErrorBoundary.tsx`
- Create: `shell/src/AppErrorBoundary.test.tsx`
- Modify: `shell/src/App.tsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed by later tasks.

**Context:** `shell/src/builder/WidgetHost.tsx:14-30` already has `WidgetErrorBoundary`, a per-widget class component — that one stays untouched (it's scoped intentionally to isolate one widget crash from the rest of a page). `shell/src/App.tsx` is the actual root: `App()` renders `<AuthProvider><QueryClientProvider><AppShell /></QueryClientProvider></AuthProvider>`, and `AppShell()` renders `<ItemClientProvider><BrowserRouter><AppRoutes /></BrowserRouter></ItemClientProvider>`. The new boundary wraps `<AppShell />` (inside the providers, so it still has query client / auth context for its own fallback UI if needed, but outside the router so it also catches any router-level crash).

- [ ] **Step 1: Write the failing test**

Create `shell/src/AppErrorBoundary.test.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppErrorBoundary } from "./AppErrorBoundary";

function Boom(): never {
  throw new Error("kaboom");
}

describe("AppErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <AppErrorBoundary>
        <div>hello</div>
      </AppErrorBoundary>,
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("renders a fallback instead of crashing when a child throws", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    );
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
    expect(screen.getByText(/une erreur est survenue/i)).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd shell
npx vitest run src/AppErrorBoundary.test.tsx
```

Expected: FAILS — `./AppErrorBoundary` doesn't exist yet.

- [ ] **Step 3: Implement**

Create `shell/src/AppErrorBoundary.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

// Distinct de WidgetErrorBoundary (builder/WidgetHost.tsx), qui isole un
// widget individuel — celui-ci est au niveau racine de l'app (App.tsx) et
// attrape tout ce qui n'est PAS un widget : chrome du builder, pages,
// panneaux (I12, revue de projet 2026-08-20 — un seul ErrorBoundary
// existait, scopé par widget, donc toute exception de rendu ailleurs
// produisait un écran blanc).
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(err: unknown) {
    console.error("AppErrorBoundary: unhandled render error", err);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4 bg-slate-50 text-center">
          <p className="text-lg font-medium text-slate-800">Une erreur est survenue.</p>
          <p className="text-sm text-slate-500">
            Rechargez la page ; si le problème persiste, contactez votre administrateur.
          </p>
          <button
            type="button"
            className="rounded bg-slate-800 px-4 py-2 text-sm text-white"
            onClick={() => window.location.reload()}
          >
            Recharger
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 4: Wire it into `App.tsx`**

Edit `shell/src/App.tsx`:

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { buildExportAwareToken } from "./auth/exportAwareToken";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppRoutes } from "./shell/routes";
import { AppErrorBoundary } from "./AppErrorBoundary";

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
const queryClient = new QueryClient();

function AppShell() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: config.coreUrl,
        getToken: buildExportAwareToken(getAccessToken),
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AuthProvider config={config}>
        <QueryClientProvider client={queryClient}>
          <AppShell />
        </QueryClientProvider>
      </AuthProvider>
    </AppErrorBoundary>
  );
}
```

(Placed outside `AuthProvider` rather than inside `AppShell`, so it also catches a crash in `AuthProvider`/`QueryClientProvider` setup itself, not just inside the router tree.)

- [ ] **Step 5: Run the new test and the existing `App.test.tsx`**

```bash
cd shell
npx vitest run src/AppErrorBoundary.test.tsx src/App.test.tsx
```

Expected: all pass. If `App.test.tsx` snapshot-tests the exact render tree structure, it may need a small update to account for the new wrapper — check its content first with `cat src/App.test.tsx` before assuming no change is needed.

- [ ] **Step 6: Run the full shell suite**

```bash
cd shell
npx vitest run
npm run lint && npm run format:check && npm run build
```

Expected: 161+2 = 163 files (2 new: `AppErrorBoundary.tsx` isn't a test file itself, only `AppErrorBoundary.test.tsx` counts — verify the exact delta against the vitest summary rather than assuming), no regressions.

- [ ] **Step 7: Commit**

```bash
git add shell/src/AppErrorBoundary.tsx shell/src/AppErrorBoundary.test.tsx shell/src/App.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ErrorBoundary applicatif à la racine

Le seul ErrorBoundary existant est scopé par widget (WidgetHost.tsx) —
toute exception de rendu ailleurs (chrome builder, pages, panneaux)
produisait un écran blanc (I12, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

