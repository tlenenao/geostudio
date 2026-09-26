// SPDX-License-Identifier: Apache-2.0
import { Checkbox } from "./Checkbox";
import { Table } from "./Table";
import { t } from "../../i18n";

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  getRowLabel,
  getRowClassName,
  selectedIds,
  onSelectedIdsChange,
  sortKey,
  sortDirection,
  onSortChange,
  onRowClick,
}: {
  columns: { key: string; label: string; render: (row: T) => React.ReactNode }[];
  rows: T[];
  getRowId: (row: T) => string;
  getRowLabel?: (row: T) => string;
  /** Optional per-row class name (e.g. to highlight a selected row). */
  getRowClassName?: (row: T) => string | undefined;
  selectedIds?: Set<string>;
  onSelectedIdsChange?: (ids: Set<string>) => void;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  onSortChange?: (key: string) => void;
  onRowClick?: (row: T) => void;
}) {
  const selectable = selectedIds !== undefined && onSelectedIdsChange !== undefined;

  const resolveRowLabel = (row: T): string => {
    const rendered = columns[0]?.render(row);
    return (
      getRowLabel?.(row) ??
      (typeof rendered === "string"
        ? t("dataTable.selectRow", { item: rendered })
        : t("dataTable.selectRowGeneric"))
    );
  };

  return (
    <Table>
      <thead>
        <tr className="border-b border-rule">
          {selectable && <th className="w-8 px-3 py-2" />}
          {columns.map((col) => (
            <th
              key={col.key}
              className="cursor-pointer px-3 py-2 font-medium text-ink-2"
              onClick={() => onSortChange?.(col.key)}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSortChange?.(col.key);
                }
              }}
              aria-sort={
                sortKey === col.key
                  ? sortDirection === "desc"
                    ? "descending"
                    : "ascending"
                  : "none"
              }
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const id = getRowId(row);
          return (
            <Table.Row
              key={id}
              className={getRowClassName?.(row)}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      // Guard against nested interactive elements (a button
                      // or checkbox in a rendered cell) re-triggering the
                      // row-level activation when their own keydown bubbles
                      // up — mirrors the sortable-header guard above.
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        if (e.key === " ") e.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
              style={onRowClick ? { cursor: "pointer" } : undefined}
            >
              {selectable && (
                <Table.Cell>
                  <Checkbox
                    aria-label={resolveRowLabel(row)}
                    checked={selectedIds!.has(id)}
                    onCheckedChange={(checked) => {
                      const next = new Set(selectedIds);
                      if (checked) next.add(id);
                      else next.delete(id);
                      onSelectedIdsChange!(next);
                    }}
                  />
                </Table.Cell>
              )}
              {columns.map((col) => (
                <Table.Cell key={col.key}>{col.render(row)}</Table.Cell>
              ))}
            </Table.Row>
          );
        })}
      </tbody>
    </Table>
  );
}
