// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../ItemClientProvider";
import { ToastProvider } from "../../ui/kit/ToastProvider";
import { t } from "../../i18n";
import { useSaveDataset } from "./datasets.hooks";
import type { ItemClient } from "../types";

describe("useSaveDataset", () => {
  it("affiche un toast de succès après sauvegarde", async () => {
    const client = {
      saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    } as unknown as ItemClient;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    function wrapper({ children }: { children: ReactNode }) {
      return (
        <ToastPrimitive.Provider>
          <QueryClientProvider client={queryClient}>
            <ItemClientProvider client={client}>
              <ToastProvider>{children}</ToastProvider>
            </ItemClientProvider>
          </QueryClientProvider>
          <ToastPrimitive.Viewport />
        </ToastPrimitive.Provider>
      );
    }

    const { result } = renderHook(() => useSaveDataset("dataset-1"), { wrapper });
    const fakeDatasetConfig = {
      collectionId: "test-collection",
      visibleColumns: [],
    };

    await act(async () => {
      await result.current.mutateAsync(fakeDatasetConfig);
    });

    expect(await screen.findByText(t("toast.datasetSaved"))).toBeInTheDocument();
  });
});
