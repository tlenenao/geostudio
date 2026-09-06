// SPDX-License-Identifier: Apache-2.0
import { Checkbox } from "./Checkbox";
import { Table } from "./Table";
import { t } from "../../i18n";

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  getRowLabel,
  selectedIds,
  onSelectedIdsChange,
  sortKey,
  sortDirection,
  onSortChange,
}: {
  columns: { key: string; label: string; render: (row: T) => React.ReactNode }[];
  rows: T[];
  getRowId: (row: T) => string;
  getRowLabel?: (row: T) => string;
  selectedIds?: Set<string>;
  onSelectedIdsChange?: (ids: Set<string>) => void;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  onSortChange?: (key: string) => void;
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
            <Table.Row key={id}>
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
