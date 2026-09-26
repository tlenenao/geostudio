// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../ItemClientProvider";
import { ToastProvider } from "../../ui/kit/ToastProvider";
import { t } from "../../i18n";
import {
  useCreatePipeline,
  useSavePipeline,
  useCreatePipelineWebhookToken,
  useRevokePipelineWebhookToken,
} from "./pipelines.hooks";
import type { ItemClient, PipelinePayload } from "../types";

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const mockClient = {
    createPipelineItem: vi.fn().mockResolvedValue(undefined),
    savePipelineConfig: vi.fn().mockResolvedValue(undefined),
    createPipelineWebhookToken: vi.fn().mockResolvedValue(undefined),
    revokePipelineWebhookToken: vi.fn().mockResolvedValue(undefined),
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

describe("useCreatePipeline", () => {
  it("affiche un toast de succès après création", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreatePipeline(), { wrapper });
    const fakeInput = {
      title: "Test Pipeline",
      owner: "test-owner",
      pipeline: { nodes: [], edges: [] } as PipelinePayload,
    };

    await act(async () => {
      await result.current.mutateAsync(fakeInput);
    });

    expect(await screen.findByText(t("toast.pipelineCreated"))).toBeInTheDocument();
  });
});

describe("useSavePipeline", () => {
  it("affiche un toast de succès après sauvegarde", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSavePipeline("pipeline-1"), { wrapper });
    const fakePayload = { nodes: [], edges: [] } as PipelinePayload;

    await act(async () => {
      await result.current.mutateAsync(fakePayload);
    });

    expect(await screen.findByText(t("toast.pipelineSaved"))).toBeInTheDocument();
  });
});

describe("useCreatePipelineWebhookToken", () => {
  it("affiche un toast de succès après création", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreatePipelineWebhookToken("pipeline-1"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(await screen.findByText(t("toast.webhookTokenCreated"))).toBeInTheDocument();
  });
});

describe("useRevokePipelineWebhookToken", () => {
  it("affiche un toast de succès après révocation", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useRevokePipelineWebhookToken("pipeline-1"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("token-1");
    });

    expect(await screen.findByText(t("toast.webhookTokenRevoked"))).toBeInTheDocument();
  });
});
