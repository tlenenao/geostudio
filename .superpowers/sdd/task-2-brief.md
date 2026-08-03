### Task 2: `lib/sqlLabHistory.ts` — local query history

**Files:**
- Create: `shell/src/lib/sqlLabHistory.ts`
- Test: `shell/src/lib/sqlLabHistory.test.ts`

**Interfaces:**
- Consumes: nothing (pure module, `localStorage` only, no imports from elsewhere in the app).
- Produces: `SqlHistoryEntry` type (`{ sql: string; executedAt: string; status: "ok" | "error"; rowCount?: number }`), `readSqlHistory(): SqlHistoryEntry[]`, `appendSqlHistory(entry: SqlHistoryEntry): SqlHistoryEntry[]` (from `shell/src/lib/sqlLabHistory.ts`). Task 3 imports all three.

- [ ] **Step 1: Write the failing test**

Create `shell/src/lib/sqlLabHistory.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { appendSqlHistory, readSqlHistory } from "./sqlLabHistory";

beforeEach(() => localStorage.clear());

describe("sqlLabHistory", () => {
  test("readSqlHistory returns an empty list when nothing is stored", () => {
    expect(readSqlHistory()).toEqual([]);
  });

  test("readSqlHistory returns an empty list when the stored value is corrupted JSON", () => {
    localStorage.setItem("geostudio.sqlLab.history", "{not json");
    expect(readSqlHistory()).toEqual([]);
  });

  test("appendSqlHistory prepends the newest entry and persists it", () => {
    appendSqlHistory({ sql: "select 1", executedAt: "2026-08-03T10:00:00Z", status: "ok", rowCount: 1 });
    const after = appendSqlHistory({ sql: "select 2", executedAt: "2026-08-03T10:01:00Z", status: "error" });
    expect(after).toEqual([
      { sql: "select 2", executedAt: "2026-08-03T10:01:00Z", status: "error" },
      { sql: "select 1", executedAt: "2026-08-03T10:00:00Z", status: "ok", rowCount: 1 },
    ]);
    expect(readSqlHistory()).toEqual(after);
  });

  test("appendSqlHistory caps the list at 20 entries, dropping the oldest", () => {
    for (let i = 0; i < 20; i++) {
      appendSqlHistory({ sql: `select ${i}`, executedAt: `t${i}`, status: "ok" });
    }
    const result = appendSqlHistory({ sql: "select 20", executedAt: "t20", status: "ok" });
    expect(result).toHaveLength(20);
    expect(result[0].sql).toBe("select 20");
    expect(result.find((e) => e.sql === "select 0")).toBeUndefined();
  });
});
```

(`beforeEach`/`describe`/`test`/`expect` are Vitest globals in this project — `globals: true` in `shell/vite.config.ts`, no import needed, matching the style already used in `shell/src/lib/datasetSchema.test.ts`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/lib/sqlLabHistory.test.ts`
Expected: FAIL — cannot find module `./sqlLabHistory`.

- [ ] **Step 3: Write the implementation**

Create `shell/src/lib/sqlLabHistory.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
export type SqlHistoryEntry = {
  sql: string;
  executedAt: string;
  status: "ok" | "error";
  rowCount?: number;
};

const STORAGE_KEY = "geostudio.sqlLab.history";
const MAX_ENTRIES = 20;

export function readSqlHistory(): SqlHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SqlHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function appendSqlHistory(entry: SqlHistoryEntry): SqlHistoryEntry[] {
  const next = [entry, ...readSqlHistory()].slice(0, MAX_ENTRIES);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // localStorage indisponible (navigation privée, quota dépassé) —
    // l'historique dégrade silencieusement, l'exécution de la requête
    // elle-même n'est pas affectée.
  }
  return next;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/lib/sqlLabHistory.test.ts`
Expected: PASS, 4/4 tests green.

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/lib/sqlLabHistory.ts src/lib/sqlLabHistory.test.ts
git commit -m "feat(shell): sqlLabHistory — historique local des requêtes SQL Lab (SP-14i)"
```

---

