// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, type ReactNode } from "react";
import type { DataSource } from "../api/types";

type AddDataSource = (source: DataSource) => void;

const AddDataSourceContext = createContext<AddDataSource | null>(null);

export function DataSourcesEditProvider({
  onAdd,
  children,
}: {
  onAdd: AddDataSource;
  children: ReactNode;
}) {
  return <AddDataSourceContext.Provider value={onAdd}>{children}</AddDataSourceContext.Provider>;
}

export function useAddDataSource(): AddDataSource | null {
  return useContext(AddDataSourceContext);
}
