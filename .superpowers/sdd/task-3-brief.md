### Task 3: `SqlLabPage` — editor, execution, results, history

**Files:**
- Create: `shell/src/pages/SqlLabPage.tsx`
- Test: `shell/src/pages/SqlLabPage.test.tsx`

**Interfaces:**
- Consumes: `itemClient.runAnalyticsSql(sql: string): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>` and `SqlQueryError` (Task 1, `shell/src/api/itemClient.ts`) ; `readSqlHistory()`/`appendSqlHistory()`/`SqlHistoryEntry` (Task 2, `shell/src/lib/sqlLabHistory.ts`) ; `useMe()` (`shell/src/api/hooks.ts`, already exists, returns `UseQueryResult<Me>`) ; `useItemClient()` (`shell/src/api/ItemClientProvider.tsx`, already exists) ; `Button` (`shell/src/ui/button.tsx`, already exists).
- Produces: exported component `SqlLabPage` (from `shell/src/pages/SqlLabPage.tsx`, no props). Task 4 imports it for routing.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/pages/SqlLabPage.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { SqlLabPage } from "./SqlLabPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <SqlLabPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockMe(isAnalyst: boolean) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1", username: "alice", firstName: "Alice", lastName: "Martin",
        isAdmin: false, isAnalyst,
      }),
    ),
  );
}

beforeEach(() => localStorage.clear());

test("shows an access-denied message for a non-analyst user", async () => {
  mockMe(false);
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
});

test("executes a query and renders the result table", async () => {
  mockMe(true);
  let posted: unknown;
  server.use(
    http.post("https://core.test/analytics/sql", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({ columns: ["nom", "surface"], rows: [["Parc A", 12], ["Parc B", 30]], truncated: false });
    }),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select nom, surface from parcs");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Parc A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "30" })).toBeInTheDocument();
  await waitFor(() => expect(posted).toEqual({ sql: "select nom, surface from parcs" }));
});

test("shows the truncation notice when the result was capped", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: true }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByText("Résultat tronqué aux 1 premières lignes.")).toBeInTheDocument();
});

test("shows the server error message and keeps the SQL text on failure", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json(
        { detail: { errors: [{ field: "sql", code: "sql_error", message: "Parser Error: syntax error" }] } },
        { status: 400 },
      ),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Parser Error: syntax error");
  expect(textarea).toHaveValue("select * fro x");
});

test("records history on success and reloads a past query when clicked", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: false }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByRole("columnheader", { name: "id" });
  await userEvent.clear(textarea);
  const historyButton = await screen.findByRole("button", { name: "Recharger la requête : select id from x" });
  await userEvent.click(historyButton);
  expect(textarea).toHaveValue("select id from x");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
Expected: FAIL — cannot find module `./SqlLabPage`.

- [ ] **Step 3: Write the implementation**

Create `shell/src/pages/SqlLabPage.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useMe } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import { appendSqlHistory, readSqlHistory, type SqlHistoryEntry } from "../lib/sqlLabHistory";
import { Button } from "../ui/button";

type SqlResult = { columns: string[]; rows: unknown[][]; truncated: boolean };

export function SqlLabPage() {
  const meQuery = useMe();
  const client = useItemClient();
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [history, setHistory] = useState<SqlHistoryEntry[]>(() => readSqlHistory());

  const run = useMutation({
    mutationFn: (query: string) => client.runAnalyticsSql(query),
    onSuccess: (data, query) => {
      setResult(data);
      setHistory(appendSqlHistory({ sql: query, executedAt: new Date().toISOString(), status: "ok", rowCount: data.rows.length }));
    },
    onError: (_error, query) => {
      setResult(null);
      setHistory(appendSqlHistory({ sql: query, executedAt: new Date().toISOString(), status: "error" }));
    },
  });

  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  if (meQuery.data?.isAnalyst !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux analystes.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-bold">SQL Lab</h1>
      <label className="flex flex-col gap-1 text-sm">
        Requête SQL
        <textarea
          aria-label="Requête SQL"
          className="h-32 rounded-md border border-slate-300 p-2 font-mono text-xs"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
        />
      </label>
      <Button
        size="sm"
        className="w-fit"
        disabled={!sql.trim() || run.isPending}
        onClick={() => run.mutate(sql)}
      >
        Exécuter
      </Button>
      {run.isError && (
        <p role="alert" className="text-sm text-red-600">
          {(run.error as Error).message}
        </p>
      )}
      {result && (
        <div>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                {result.columns.map((col) => (
                  <th key={col} className="border-b border-slate-200 p-1">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="border-b border-slate-100 p-1">
                      {cell === null || cell === undefined ? "" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.truncated && (
            <p className="mt-1 text-xs text-slate-500">
              Résultat tronqué aux {result.rows.length} premières lignes.
            </p>
          )}
        </div>
      )}
      {history.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Historique</p>
          <ul className="flex flex-col gap-1">
            {history.map((entry, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span aria-hidden="true">{entry.status === "error" ? "✕" : "✓"}</span>
                <button
                  type="button"
                  aria-label={`Recharger la requête : ${entry.sql}`}
                  className="text-left font-mono text-slate-600 hover:underline"
                  onClick={() => setSql(entry.sql)}
                >
                  {entry.sql}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
Expected: PASS, 5/5 tests green.

- [ ] **Step 5: Type-check**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/pages/SqlLabPage.tsx src/pages/SqlLabPage.test.tsx
git commit -m "feat(shell): page SQL Lab — éditeur, exécution, résultats, historique (SP-14i)"
```

---

