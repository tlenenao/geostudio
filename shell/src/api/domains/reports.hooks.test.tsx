// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../ItemClientProvider";
import { ToastProvider } from "../../ui/kit/ToastProvider";
import { t } from "../../i18n";
import { useCreateReportSchedule, useSaveReportSchedule } from "./reports.hooks";
import type { ItemClient, ReportSchedulePayload } from "../types";

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const mockClient = {
    createReportScheduleItem: vi.fn().mockResolvedValue(undefined),
    saveReportScheduleConfig: vi.fn().mockResolvedValue(undefined),
  } as unknown as ItemClient;

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ToastPrimitive.Provider>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={mockClient}>
            <ToastProvider>{children}</ToastProvider>
          </ItemClientProvider>
        </QueryClientProvider>
        <ToastPrimitive.Viewport />
      </ToastPrimitive.Provider>
    );
  };
}

describe("useCreateReportSchedule", () => {
  it("affiche un toast de succès après création", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateReportSchedule(), { wrapper });
    const fakeInput = {
      title: "Test Report",
      owner: "test-owner",
      report: {
        bookmarkItemId: "bookmark-1",
        refreshPolicy: { enabled: false, cron: "" },
        channels: [],
      } as ReportSchedulePayload,
    };

    await act(async () => {
      await result.current.mutateAsync(fakeInput);
    });

    expect(await screen.findByText(t("toast.reportScheduleCreated"))).toBeInTheDocument();
  });
});

describe("useSaveReportSchedule", () => {
  it("affiche un toast de succès après sauvegarde", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSaveReportSchedule("report-1"), { wrapper });
    const fakePayload = {
      bookmarkItemId: "bookmark-1",
      refreshPolicy: { enabled: false, cron: "" },
      channels: [],
    } as ReportSchedulePayload;

    await act(async () => {
      await result.current.mutateAsync(fakePayload);
    });

    expect(await screen.findByText(t("toast.reportScheduleSaved"))).toBeInTheDocument();
  });
});
