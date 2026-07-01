import { createContext, useContext } from "react";
import type { ItemClient } from "./types";

const ItemClientContext = createContext<ItemClient | null>(null);

export function ItemClientProvider({
  client,
  children,
}: {
  client: ItemClient;
  children: React.ReactNode;
}) {
  return (
    <ItemClientContext.Provider value={client}>{children}</ItemClientContext.Provider>
  );
}

export function useItemClient(): ItemClient {
  const client = useContext(ItemClientContext);
  if (!client) {
    throw new Error("useItemClient must be used within an ItemClientProvider");
  }
  return client;
}
