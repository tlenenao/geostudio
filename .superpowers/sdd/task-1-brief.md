### Task 1: `itemClient.runAnalyticsSql` + `SqlQueryError`

**Files:**
- Modify: `shell/src/api/types.ts:159-165` (add method to the `ItemClient` interface)
- Modify: `shell/src/api/itemClient.ts:85-118` (add `SqlQueryError` class + `requestAnalyticsSql` helper), `shell/src/api/itemClient.ts:711-719` (wire the method into `createItemClient`'s returned object)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: nothing new — `FieldError` type already imported in `itemClient.ts:2`; `coreUrl`/`getToken` already in scope inside `createItemClient`.
- Produces: `ItemClient.runAnalyticsSql(sql: string): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>`, exported class `SqlQueryError extends Error` (from `shell/src/api/itemClient.ts`). Task 3 imports both.

- [ ] **Step 1: Write the failing tests**

Open `shell/src/api/itemClient.test.ts`. Change the import on line 4 from:

```ts
import { createItemClient, FeatureValidationError } from "./itemClient";
```

to:

```ts
import { createItemClient, FeatureValidationError, SqlQueryError } from "./itemClient";
```

Then append these three tests at the end of the file:

```ts
test("runAnalyticsSql posts { sql } and returns columns/rows/truncated", async () => {
  let auth: string | null = null;
  let body: unknown;
  server.use(
    http.post("https://core.test/analytics/sql", async ({ request }) => {
      auth = request.headers.get("authorization");
      body = await request.json();
      return HttpResponse.json({ columns: ["nom"], rows: [["Alice"]], truncated: false });
    }),
  );
  const result = await makeClient("abc").runAnalyticsSql("select nom from personnes");
  expect(auth).toBe("Bearer abc");
  expect(body).toEqual({ sql: "select nom from personnes" });
  expect(result).toEqual({ columns: ["nom"], rows: [["Alice"]], truncated: false });
});

test("runAnalyticsSql throws SqlQueryError with the server message on 400", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json(
        { detail: { errors: [{ field: "sql", code: "sql_error", message: "Binder Error: table 'x' does not exist" }] } },
        { status: 400 },
      ),
    ),
  );
  const err = await makeClient().runAnalyticsSql("select * from x").catch((e) => e);
  expect(err).toBeInstanceOf(SqlQueryError);
  expect((err as SqlQueryError).message).toBe("Binder Error: table 'x' does not exist");
});

test("runAnalyticsSql throws a plain Error on 403 (non-analyst)", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ detail: "analyst role required" }, { status: 403 }),
    ),
  );
  await expect(makeClient().runAnalyticsSql("select 1")).rejects.toThrow(/403/);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `runAnalyticsSql is not a function` (and `SqlQueryError` import fails to resolve, since neither exists yet).

- [ ] **Step 3: Implement `SqlQueryError` and the request helper**

In `shell/src/api/itemClient.ts`, immediately after the `FeatureValidationError` class (currently lines 85-92, right before `requestFeatureWrite`), insert:

```ts
export class SqlQueryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SqlQueryError";
  }
}
```

Immediately after the `requestFeatureWrite` function (currently ending at line 118, right before `function buildFeaturesUrl`), insert:

```ts
async function requestAnalyticsSql(
  coreUrl: string,
  token: string | undefined,
  sql: string,
): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${coreUrl}/analytics/sql`, {
    method: "POST",
    headers,
    body: JSON.stringify({ sql }),
  });
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { detail?: { errors?: FieldError[] } } | null;
    throw new SqlQueryError(data?.detail?.errors?.[0]?.message ?? "Requête SQL invalide.");
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} POST /analytics/sql`);
  }
  return (await res.json()) as { columns: string[]; rows: unknown[][]; truncated: boolean };
}
```

In `shell/src/api/types.ts`, in the `ItemClient` interface, change:

```ts
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
}
```

to:

```ts
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
  runAnalyticsSql(sql: string): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>;
}
```

In `shell/src/api/itemClient.ts`, inside the object returned by `createItemClient` (currently ending with `getIngestionJob` at lines 711-718, then the closing `};` at line 719), change:

```ts
    async getIngestionJob(jobId: string) {
      return request<{
        status: "pending" | "running" | "done" | "error";
        errorMessage: string | null;
        collectionId: string | null;
        itemId: string | null;
      }>("GET", `/uploads/${jobId}`);
    },
  };
```

to:

```ts
    async getIngestionJob(jobId: string) {
      return request<{
        status: "pending" | "running" | "done" | "error";
        errorMessage: string | null;
        collectionId: string | null;
        itemId: string | null;
      }>("GET", `/uploads/${jobId}`);
    },

    async runAnalyticsSql(sql: string) {
      return requestAnalyticsSql(coreUrl, getToken(), sql);
    },
  };
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS, all tests in the file green.

- [ ] **Step 5: Type-check**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors (the `ItemClient` interface addition must be satisfied by the only implementation, `createItemClient`, which Step 3 already updated).

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient.runAnalyticsSql wraps POST /analytics/sql (SP-14i)"
```

---

