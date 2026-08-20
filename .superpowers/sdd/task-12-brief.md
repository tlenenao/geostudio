## Task 12: Shell — `CopilotPanel.tsx` + `AppBuilderPage.tsx` wiring

**Files:**
- Create: `shell/src/builder/copilot/CopilotPanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Create: `shell/src/builder/copilot/CopilotPanel.test.tsx`

**Interfaces:**
- Consumes: `useItemClient` (`../../api/ItemClientProvider`), `applyClientOp`/`RawClientOp` (Task 9), `buildClientToolSchemas` (Task 8), `useMcpToken` (Task 10), `Button` (`../../ui/button`).
- Produces: `CopilotPanel` component, mounted in `AppBuilderPage.tsx` gated on `copilotEnabled`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/copilot/CopilotPanel.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";
import { CopilotPanel } from "./CopilotPanel";

enableMockAuth();

function emptyConfig(): AppConfig {
  return {
    kind: "app", theme: {} as AppConfig["theme"], dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

function renderPanel(client: Partial<ItemClient>, setDraft: ReturnType<typeof vi.fn>) {
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <CopilotPanel itemId="1" config={emptyConfig()} activePageId="page-1" setDraft={setDraft} />
    </ItemClientProvider>,
  );
}

describe("CopilotPanel", () => {
  it("sends a message and shows the reply, without changing the draft when there are no clientOps", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockResolvedValue({ reply: "Ce dataset contient des incidents.", clientOps: [] });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(screen.getByText("Ce dataset contient des incidents.")).toBeInTheDocument());
    expect(setDraft).not.toHaveBeenCalled();
  });

  it("applies clientOps via a single setDraft call when present", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "J'ai ajouté un indicateur.",
      clientOps: [{ op: "addWidget", args: { type: "text" } }],
    });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Ajoute un widget texte");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(setDraft).toHaveBeenCalledTimes(1));
  });

  it("shows an error and does not crash when the request fails", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockRejectedValue(new Error("network"));
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx`
Expected: FAIL — `Cannot find module './CopilotPanel'`.

- [ ] **Step 3: Implement `CopilotPanel.tsx`**

Create `shell/src/builder/copilot/CopilotPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
// Panneau copilote du builder (SP-20) — propose des micro-actions
// (ajouter/modifier/retirer un widget, source de données, filtre) sur la
// config en cours d'édition. Chaque action passée par clientOps traverse
// setDraft (SP-19 undo) en un seul appel par tour : annulable via le
// bouton "Annuler" existant de la barre d'outils (AppBuilderPage.tsx),
// pas de bouton Annuler dédié ici — un seul et même undo stack.
import { useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AppConfig, CopilotMessage } from "../../api/types";
import { Button } from "../../ui/button";
import { applyClientOp, type RawClientOp } from "./applyClientOp";
import { buildClientToolSchemas } from "./clientTools";
import { useMcpToken } from "./useMcpToken";

const OP_LABELS: Record<string, string> = {
  addWidget: "Widget ajouté",
  updateWidgetProps: "Widget modifié",
  removeWidget: "Widget supprimé",
  addDataSource: "Source de données ajoutée",
  setFilter: "Filtre modifié",
};

export function CopilotPanel({
  itemId, config, activePageId, setDraft,
}: {
  itemId: string;
  config: AppConfig;
  activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  const [history, setHistory] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOpsSummary, setLastOpsSummary] = useState<string[]>([]);

  async function send() {
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    setError(null);
    const priorHistory = history;
    const nextHistory: CopilotMessage[] = [...priorHistory, { role: "user", content: message }];
    setHistory(nextHistory);
    try {
      const mcpToken = await getMcpToken();
      const result = await client.copilotTurn(itemId, {
        message, history: priorHistory, mcpToken, currentConfig: config,
        clientTools: buildClientToolSchemas(),
      });
      setHistory([...nextHistory, { role: "assistant", content: result.reply }]);
      if (result.clientOps.length > 0) {
        setLastOpsSummary(result.clientOps.map((o) => OP_LABELS[o.op] ?? `Action inconnue ignorée : ${o.op}`));
        setDraft((d) => {
          if (!d) return d;
          return (result.clientOps as RawClientOp[]).reduce(
            (acc, op) => applyClientOp(op, acc, activePageId), d,
          );
        });
      } else {
        setLastOpsSummary([]);
      }
    } catch {
      setError("Échec de la requête au copilote.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex max-h-64 flex-col gap-2 overflow-auto">
        {history.map((m, i) => (
          <p key={i} className={m.role === "user" ? "font-medium" : "text-slate-600"}>
            {m.content}
          </p>
        ))}
      </div>
      <label className="flex flex-col gap-1">
        <textarea
          aria-label="Message au copilote"
          className="min-h-16 rounded-md border border-slate-300 p-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
      </label>
      <Button size="sm" disabled={sending || !input.trim()} onClick={send}>
        Envoyer
      </Button>
      {lastOpsSummary.length > 0 && (
        <ul className="text-xs text-slate-500">
          {lastOpsSummary.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      )}
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Wire into `AppBuilderPage.tsx`**

Add the import (alphabetically, right after `import { AppExportPanel } from "../builder/appexport/AppExportPanel";`):
```ts
import { AppExportPanel } from "../builder/appexport/AppExportPanel";
import { CopilotPanel } from "../builder/copilot/CopilotPanel";
```

Add the flag derivation right after `const appExportEnabled = instanceQuery.data?.appExportEnabled === true;`:
```ts
  const appExportEnabled = instanceQuery.data?.appExportEnabled === true;
  const copilotEnabled = instanceQuery.data?.copilotEnabled === true;
```

Add the panel block right after the `appExportEnabled && (...)` block, still inside the left `<aside>`:

Change:
```tsx
              {appExportEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Export standalone</p>
                  <AppExportPanel itemId={pk} config={draft} />
                </>
              )}
            </aside>
```
to:
```tsx
              {appExportEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Export standalone</p>
                  <AppExportPanel itemId={pk} config={draft} />
                </>
              )}
              {copilotEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Copilote</p>
                  <CopilotPanel itemId={pk} config={draft} activePageId={activePage} setDraft={setDraft} />
                </>
              )}
            </aside>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx`
Expected: PASS (all 3).

Then the full shell suite + build:

Run: `cd shell && npm run build && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/copilot/CopilotPanel.tsx shell/src/builder/copilot/CopilotPanel.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): CopilotPanel — panneau de chat du builder (SP-20)

Monté dans AppBuilderPage.tsx, gated sur copilotEnabled. Applique les
clientOps en un seul setDraft (un tour = une entrée undo). Pas de bouton
Annuler dédié — réutilise le bouton Annuler existant de la barre d'outils
(un seul undo stack, SP-19).
EOF
)"
```

---

