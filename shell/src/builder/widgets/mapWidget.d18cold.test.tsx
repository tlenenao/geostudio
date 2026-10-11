// SPDX-License-Identifier: Apache-2.0
// REV-250 : jumelle de MapEditorPage.d18cold.test.tsx pour le widget carte.
// Le test D18 de mapWidget.test.tsx ne reproduit le défaut (indicateur « déjà
// ajusté » posé alors que le ref de MapView, chargé en lazy(), est encore
// null) que s'il tourne en premier dans son fichier. Ici la factory du mock
// de MapView est bloquée sur une barrière : le chunk est froid tant que le
// test ne la lève pas.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useEffect, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";

const { gate, fitBoundsSpy } = vi.hoisted(() => {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { gate: { promise, release }, fitBoundsSpy: vi.fn() };
});

vi.mock("../../map/MapView", async () => {
  await gate.promise;
  return {
    MapView: forwardRef(({ onReady }: { onReady?: () => void }, ref: React.Ref<unknown>) => {
      useImperativeHandle(ref, () => ({
        flyTo: vi.fn(),
        highlight: vi.fn(),
        fitBounds: fitBoundsSpy,
      }));
      useEffect(() => {
        onReady?.();
      }, [onReady]);
      return <div data-testid="mapview" />;
    }),
  };
});

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
  fitBoundsSpy.mockClear();
});

test("auto-cadrage D18 : fonctionne quand le chunk lazy de MapView charge APRÈS les données (REV-250)", async () => {
  const Map = getWidget("map")!.Component;
  const data: DataSourceState = {
    loading: false,
    error: false,
    url: "https://fs/parcs/items.json",
    records: [
      { id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 10] } },
      { id: 2, properties: {}, geometry: { type: "Point", coordinates: [3, 20] } },
    ],
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{ queryDataSource: vi.fn() } as unknown as ItemClient}>
        <Map props={{ dataSourceId: "d" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // Les enregistrements sont déjà là au premier rendu ; le chunk MapView est
  // bloqué : l'effet d'auto-cadrage s'exécute avec un ref null.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(screen.queryByTestId("mapview")).toBeNull();
  expect(fitBoundsSpy).not.toHaveBeenCalled();

  await act(async () => gate.release());
  await screen.findByTestId("mapview");
  await waitFor(() => expect(fitBoundsSpy).toHaveBeenCalledTimes(1));
  expect(fitBoundsSpy).toHaveBeenCalledWith([1, 10, 3, 20]);
});
