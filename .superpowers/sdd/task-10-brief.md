## Task 10: Shell — `useMcpToken.ts`

**Files:**
- Modify: `shell/src/auth/useAuth.ts` (export `isMockMode()`)
- Create: `shell/src/builder/copilot/useMcpToken.ts`
- Create: `shell/src/builder/copilot/useMcpToken.test.tsx`

**Interfaces:**
- Consumes: `useAuth as useOidcAuth` from `react-oidc-context`, `isMockMode` from `../../auth/useAuth`.
- Produces: `useMcpToken(): () => Promise<string>`. Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Add `isMockMode()` to `useAuth.ts`**

In `shell/src/auth/useAuth.ts`, add right after `enableMockAuth`:

Change:
```ts
let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}
```
to:
```ts
let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}
export function isMockMode(): boolean {
  return mockMode;
}
```

- [ ] **Step 2: Write the failing tests**

Create `shell/src/builder/copilot/useMcpToken.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    signinSilent: vi.fn().mockResolvedValue({ access_token: "real-mcp-token" }),
  }),
}));

describe("useMcpToken", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("returns a fixed mock token synchronously in mock mode", async () => {
    enableMockAuth();
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const token = await result.current();
    expect(token).toBe("mock-mcp-token");
  });
});
```

Note: since `enableMockAuth()` sets a module-level flag with no reset function, this test file must run in isolation from `useMcpToken`'s non-mock behavior — cover the real-mode path (`signinSilent` called with the right scope, caching across calls) in a **separate** test file that never calls `enableMockAuth()`:

Create `shell/src/builder/copilot/useMcpTokenOidc.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const signinSilent = vi.fn().mockResolvedValue({ access_token: "real-mcp-token" });
vi.mock("react-oidc-context", () => ({ useAuth: () => ({ signinSilent }) }));

describe("useMcpToken (real OIDC mode)", () => {
  it("calls signinSilent with the geostudio-mcp-audience scope and caches the result", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const first = await result.current();
    expect(first).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledWith({ scope: "openid profile email geostudio-mcp-audience" });

    const second = await result.current();
    expect(second).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledTimes(1); // cached, not called again
  });

  it("throws a readable error when signinSilent resolves without a token", async () => {
    signinSilent.mockResolvedValueOnce(null);
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/copilot/useMcpToken.test.tsx src/builder/copilot/useMcpTokenOidc.test.tsx`
Expected: FAIL — `Cannot find module './useMcpToken'`.

- [ ] **Step 4: Implement**

Create `shell/src/builder/copilot/useMcpToken.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Jeton d'audience MCP distincte pour le copilote (SP-20) — obtenu via un
// second signinSilent() demandant le client-scope optionnel
// geostudio-mcp-audience (déjà provisionné dans le realm, Task 1), jamais
// via un paramètre resource ni token-exchange. Contourne délibérément le
// useAuth() de l'app (../../auth/useAuth), qui n'expose pas signinSilent —
// importe react-oidc-context directement, comme AuthProvider.tsx le fait
// déjà pour construire son propre <AuthProvider>. Le jeton ne vit qu'en
// mémoire (état React), jamais localStorage — même garantie que le jeton
// REST normal (cf. AuthProvider.tsx, InMemoryStore).
import { useCallback, useRef } from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { isMockMode } from "../../auth/useAuth";

const MCP_SCOPE = "openid profile email geostudio-mcp-audience";

export function useMcpToken(): () => Promise<string> {
  const cachedRef = useRef<string | null>(null);

  if (isMockMode()) {
    // mockMode est un drapeau au niveau module, fixé une fois avant tout
    // rendu (enableMockAuth() dans AuthProvider) — jamais togglé en cours
    // de vie de l'app, donc ce retour anticipé avant l'appel conditionnel
    // ci-dessous respecte quand même les rules-of-hooks en pratique, même
    // patron que useAuth.ts.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    return useCallback(async () => "mock-mcp-token", []);
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const oidc = useOidcAuth();
  return useCallback(async () => {
    if (cachedRef.current) return cachedRef.current;
    const user = await oidc.signinSilent({ scope: MCP_SCOPE });
    if (!user?.access_token) {
      throw new Error("Impossible d'obtenir un jeton MCP (signinSilent a échoué).");
    }
    cachedRef.current = user.access_token;
    return user.access_token;
  }, [oidc]);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/useMcpToken.test.tsx src/builder/copilot/useMcpTokenOidc.test.tsx`
Expected: PASS (all 3).

- [ ] **Step 6: Commit**

```bash
git add shell/src/auth/useAuth.ts shell/src/builder/copilot/useMcpToken.ts shell/src/builder/copilot/useMcpToken.test.tsx shell/src/builder/copilot/useMcpTokenOidc.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): useMcpToken — second signinSilent pour l'audience MCP (SP-20)

Demande le scope geostudio-mcp-audience (Task 1) via react-oidc-context
directement (useAuth() de l'app n'expose pas signinSilent). Jeton en
mémoire uniquement, mis en cache pour la session du panneau.
EOF
)"
```

---

