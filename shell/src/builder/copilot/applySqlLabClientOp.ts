// SPDX-License-Identifier: Apache-2.0
import type { RawClientOp } from "./applyClientOp";

export function applySqlLabClientOp(raw: RawClientOp, setSql: (sql: string) => void): void {
  if (raw.op !== "applySqlDraft") return;
  const sql = String(raw.args.sql ?? "").trim();
  if (!sql) return;
  setSql(sql);
}
