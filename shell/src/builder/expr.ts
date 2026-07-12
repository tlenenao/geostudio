import { evaluate, parse } from "cel-js";

export type ExprContext = {
  vars: Record<string, unknown>;
  record?: Record<string, unknown>;
  user: { name: string };
};

export function evaluateExpression(expr: string, ctx: ExprContext): unknown {
  try {
    return evaluate(expr, ctx);
  } catch (err) {
    console.warn(`evaluateExpression: "${expr}" a échoué`, err);
    return undefined;
  }
}

export function validateExpression(expr: string): string | null {
  const result = parse(expr);
  if (result.isSuccess) return null;
  return result.errors.join("; ");
}
