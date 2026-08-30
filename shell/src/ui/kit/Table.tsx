// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

function TableRoot({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table
      className={cn("w-full border-collapse text-left text-sm text-ink", className)}
      {...props}
    />
  );
}

function TableHead({ columns }: { columns: string[] }) {
  return (
    <thead>
      <tr className="border-b border-rule">
        {columns.map((col) => (
          <th key={col} className="px-3 py-2 font-medium text-ink-2">
            {col}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-rule-2", className)} {...props} />;
}

function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2", className)} {...props} />;
}

export const Table = Object.assign(TableRoot, {
  Head: TableHead,
  Row: TableRow,
  Cell: TableCell,
});
