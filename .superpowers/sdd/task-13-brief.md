## Task 13: E2E — copilot panel presence + explain/add-widget flows

**Files:**
- Create: `shell/e2e/copilot.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`./mocks`), the existing app-creation flow (mirrors `shell/e2e/app-builder.spec.ts`).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/copilot.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("copilot panel is absent without copilotEnabled", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await expect(page.getByLabel("Message au copilote")).toHaveCount(0);
});

test("copilot: explain prompt makes no changes, add-widget prompt adds and is undoable", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  await page.route("https://core.test/copilot/turn", async (route) => {
    const body = route.request().postDataJSON() as { message: string };
    if (body.message.includes("indicateur")) {
      await route.fulfill({
        json: {
          reply: "J'ai ajouté un indicateur.",
          clientOps: [{ op: "addWidget", args: { type: "indicator" } }],
        },
      });
    } else {
      await route.fulfill({ json: { reply: "Ce dataset contient des incidents.", clientOps: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Explique — pas de changement de canevas.
  await page.getByLabel("Message au copilote").fill("Explique ce dataset");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("Ce dataset contient des incidents.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);

  // Ajoute un widget — apparaît sur le canevas, annulable via le bouton
  // Annuler de la barre d'outils (pas de bouton dédié dans le panneau).
  await page.getByLabel("Message au copilote").fill("Ajoute un indicateur");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("J'ai ajouté un indicateur.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();

  await page.getByRole("button", { name: "Annuler" }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);
});
```

- [ ] **Step 2: Run the spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/copilot.spec.ts`
Expected: PASS (both tests).

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS (all specs, including the new one — 19 specs total).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/copilot.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): panneau copilote — absence sans capacité, explication puis ajout de widget annulable (SP-20)
EOF
)"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-08-05-copilote-embarque-design.md`, as amended during the spec-verification pass):
- §2 architecture (shell → core → MCP loopback → clientOps back to shell): Tasks 4, 5, 9, 12.
- §2.1 MCP-audience bridge: Task 1 (realm), Task 10 (`useMcpToken`) — implemented as a client-scope grant, not `resource`/token-exchange, per the revised decision recorded in this session.
- §3 core components (`llm_provider.py`, `mcp_loopback.py`, `tools_allowlist.py`, `routes.py`, `GET /instance`): Tasks 2–5.
- §3 shell components (`CopilotPanel.tsx`, `useMcpToken.ts`, `clientTools.ts`, `applyClientOp.ts`): Tasks 8–12.
- §4 security (allowlist enforcement, no direct DB mutation, read-only-mode inheritance, in-memory-only token): Task 5 (allowlist check + read-only-guard exemption), Task 10 (in-memory token).
- §5 governance (off by default, no quota): Task 2 (`is_copilot_enabled`), Task 6 (env wiring).
- §6 out of scope: respected — no persistence beyond the browser session, no quotas, no full-dashboard generation, no runtime-mode copilot, no second LLM provider, no SQL Lab exposure beyond `run_analytics_query`.
- §7 risks: max-iteration guard (Task 5, tested), hallucinated-tool-argument mitigation (Task 9's `configSchema`-based coercion), SP-19 dependency (already shipped, confirmed at spec-verification time).
- §8 acceptance criteria: criterion 1 (Task 2 + `AppBuilderPage.tsx` gating), criterion 2 (Task 13 E2E "explain"), criterion 3 (Task 13 E2E "add widget", undoable via existing SP-19 button), criterion 4 (Task 5's read-only-guard exemption — MCP tools self-gate writes, matches `is_read_only_mode` already blocking `create_item`/`create_form_app` server-side), criterion 5 (Task 5's allowlist check, tested), criterion 6 (Task 5's max-iterations fallback, tested).

**Corrections made relative to the original design doc during this planning pass** (all grounded in reading the real code, not assumption):
1. §2.1's `resource` param / implied token-exchange replaced with a plain OIDC optional-scope grant (`geostudio-mcp-audience`, already provisioned in the realm) — simpler, no Keycloak preview feature required, confirmed against `deploy/keycloak/geostudio-realm.json`.
2. §3's "CopilotPanel is a tab, dedicated Annuler button calling `undo()` from a `UndoContext`" replaced with: CopilotPanel is a stacked always-visible panel (same as every other builder panel), and it has **no** dedicated Annuler button — it shares the single global undo stack via the toolbar's existing button, avoiding a duplicate-label collision.
3. `clientTools.ts`'s premise ("a new widget becomes automatically editable") required adding a new `configSchema` field to `WidgetDefinition` and backfilling all 22 builtin widgets (Task 7) — the registry previously had no declarative prop schema for builtin widgets, only for SP-8 WC/extension widgets.
4. `POST /copilot/turn` added to the read-only-mode middleware's exemption list (Task 5) — without this, acceptance criterion 4 (search/explain works in demo mode) would 403 before the handler ever ran.
5. `docker-compose.yml`/`​.env.example` wiring made an explicit task (Task 6) rather than assumed — `CORE_EMBEDDING_PROVIDER` (SP-7) never got this wiring and is silently inert in the packaged stack; not repeating that.

**Placeholder scan:** none found — every step has complete code, exact file paths, and expected command output. The one intentionally-flagged-and-then-corrected placeholder in Task 5 (`test_allowlisted_mcp_tool_call_is_executed_via_loopback`) is resolved inline with the real assertion to write, immediately following it.

**Type consistency:** `RawClientOp`/`ClientOp` (server Pydantic `op`/`args` ↔ shell `{op, args}`) match across Task 5 and Task 9. `CopilotTurnResponse{reply, clientOps}` (Task 5) matches `CopilotTurnResult{reply, clientOps}` (Task 11) and `CopilotPanel`'s usage (Task 12). `WidgetPropDescriptor{name, type, label, default}` (Task 7) is consumed identically in Task 8 (`clientTools.ts`) and Task 9 (`applyClientOp.ts`). `useMcpToken(): () => Promise<string>` (Task 10) matches its usage in `CopilotPanel` (Task 12: `const getMcpToken = useMcpToken(); ... await getMcpToken()`).
