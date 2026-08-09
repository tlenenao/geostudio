### Task 11: `ExportPanel` (bouton + dialogue + poll) + intégration

**Files:**
- Create: `shell/src/builder/print/ExportPanel.tsx`
- Create: `shell/src/builder/print/ExportPanel.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`

**Interfaces:**
- Consumes: `itemClient.createExport`/`getExportJob` (Tâche 8), `useInstanceInfo` (Tâche 2).
- Produces: `ExportPanel({ itemId }: { itemId: string })` — bouton « Exporter », dialogue de choix de format, poll (patron `PipelineRunPanel`), lien de téléchargement une fois `done`, message d'erreur `role="alert"` si `error` ou si l'appel initial échoue.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/builder/print/ExportPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ItemClientProvider } from "../../api/ItemClientProvider"; // adapter au nom réel du provider utilisé par PipelineRunPanel.test.tsx
import { ExportPanel } from "./ExportPanel";
import type { ItemClient } from "../../api/itemClient";

function renderPanel(client: Partial<ItemClient>) {
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <ExportPanel itemId="item-1" />
    </ItemClientProvider>,
  );
}

describe("ExportPanel", () => {
  it("creates an export job on click and polls until done, then shows a download link", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    let call = 0;
    const getExportJob = vi.fn().mockImplementation(() => {
      call += 1;
      const status = call < 2 ? "running" : "done";
      return Promise.resolve({ id: "job-1", status, resultUrl: status === "done" ? "https://minio.test/x.pdf" : null, error: null });
    });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    expect(createExport).toHaveBeenCalledWith("item-1", "pdf");
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toHaveAttribute("href", "https://minio.test/x.pdf"), { timeout: 5000 });
    expect(call).toBeGreaterThanOrEqual(2);
  });

  it("surfaces a job error via role=alert instead of silently stopping", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi.fn().mockResolvedValue({ id: "job-1", status: "error", resultUrl: null, error: "render timeout" });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PNG" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("render timeout"));
  });

  it("surfaces a failure to even create the job", async () => {
    const createExport = vi.fn().mockRejectedValue(new Error("Request failed: 403 POST /export"));
    renderPanel({ createExport, getExportJob: vi.fn() });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
  });
});
```

Vérifier le nom exact du provider React exposant `ItemClient` au reste de l'arbre (utilisé par `PipelineRunPanel.test.tsx`) avant d'écrire ce test, et l'aligner précisément.

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implémenter**

```tsx
// shell/src/builder/print/ExportPanel.tsx
import { useState } from "react";
import { useItemClientInternal } from "../../api/hooks";
import type { ExportFormat, ExportJob } from "../../api/types";

const POLL_INTERVAL_MS = 1500;

export function ExportPanel({ itemId }: { itemId: string }) {
  const client = useItemClientInternal();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function poll(jobId: string) {
    for (;;) {
      const latest = await client.getExportJob(jobId);
      setJob(latest);
      if (latest.status !== "pending" && latest.status !== "running") return;
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
  }

  async function onExport(format: ExportFormat) {
    setDialogOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createExport(itemId, format);
      await poll(jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de l'export.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button type="button" onClick={() => setDialogOpen(true)} disabled={running}>
        Exporter
      </button>
      {dialogOpen && (
        <div role="dialog" aria-label="Choisir le format d'export" className="flex gap-2">
          <button type="button" onClick={() => onExport("png")}>PNG</button>
          <button type="button" onClick={() => onExport("pdf")}>PDF</button>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a role="link" href={job.resultUrl} download>
          Télécharger l'export
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert">{error ?? job?.error ?? "Échec de l'export."}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Intégrer dans `MapEditorPage.tsx`**

Ajouter, gardé par la capacité `exportEnabled` (`useInstanceInfo()`, même patron que `etlEnabled` dans `NewItemButton.tsx`), dans l'aside du mode édition normal (pas dans la branche `isExportRender` de la Tâche 10) :

```tsx
import { ExportPanel } from "../builder/print/ExportPanel";
import { useInstanceInfo } from "../api/hooks";
// ...
const instanceQuery = useInstanceInfo();
const exportEnabled = instanceQuery.data?.exportEnabled === true;
// ... dans l'aside, à la suite de PrintLayoutPanel :
{pk !== null && exportEnabled && <ExportPanel itemId={pk} />}
```

- [ ] **Step 6: Intégrer dans `AppRuntimePage.tsx`**

Dans la barre du haut déjà gardée par `{!isExportRender && ( ... )}` (Tâche 10), à côté du bouton « Enregistrer la vue » :

```tsx
import { ExportPanel } from "../builder/print/ExportPanel";
import { useInstanceInfo } from "../api/hooks";
// ...
const instanceQuery = useInstanceInfo();
const exportEnabled = instanceQuery.data?.exportEnabled === true;
// ...
{exportEnabled && <ExportPanel itemId={pk} />}
```

- [ ] **Step 7: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/print/ExportPanel.tsx shell/src/builder/print/ExportPanel.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): SP-17a — ExportPanel (bouton, dialogue, poll) intégré carte/app"
```

---

