// SPDX-License-Identifier: Apache-2.0
import { evaluateExpression, type ExprContext } from "./expr";

function isExprBinding(value: unknown): value is { $expr: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.keys(value).length === 1 &&
    typeof (value as Record<string, unknown>).$expr === "string"
  );
}

export function resolveExprBindings(value: unknown, ctx: ExprContext): unknown {
  if (isExprBinding(value)) {
    return evaluateExpression(value.$expr, ctx);
  }
  if (Array.isArray(value)) {
    return value.map((v) => resolveExprBindings(v, ctx));
  }
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = resolveExprBindings(v, ctx);
    }
    return out;
  }
  return value;
}
