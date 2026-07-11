import type { AppConfig } from "../api/types";
import { getPages } from "./pages";
import { validateExpression } from "./expr";

type CalculatedColumn = { label: string; expr: string };

export function getConfigExpressionErrors(config: AppConfig): string[] {
  const errors: string[] = [];
  for (const page of getPages(config)) {
    for (const item of page.layout.items) {
      if (item.visibleWhen) {
        const err = validateExpression(item.visibleWhen);
        if (err) errors.push(`Widget ${item.id} (condition d'affichage) : ${err}`);
      }
      const columns = item.props.columns;
      if (Array.isArray(columns)) {
        for (const col of columns as unknown[]) {
          if (typeof col === "object" && col !== null && "expr" in col) {
            const { label, expr } = col as CalculatedColumn;
            const err = validateExpression(expr);
            if (err) errors.push(`Widget ${item.id}, colonne "${label}" : ${err}`);
          }
        }
      }
    }
  }
  return errors;
}
