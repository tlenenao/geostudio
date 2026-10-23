// SPDX-License-Identifier: Apache-2.0
// AUD-131 (D7) : rafraîchissement planifié par source de données.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DataProvider, useDataStates } from "./DataContext";
import { DataSourcePanel } from "./DataSourcePanel";

function Quiet() {
  useDataStates();
  return null;
}

test("une source avec refreshSeconds est relue à l'échéance, une autre jamais", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const queryDataSource = vi.fn().mockResolvedValue([{ id: 1, properties: {} }]);
    const client = {
      queryDataSource,
      featuresUrl: vi.fn().mockReturnValue("https://fs/x/items.json"),
    } as unknown as ItemClient;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const sources: DataSource[] = [
      {
        id: "live",
        type: "features",
        service: "featureserv",
        layer: "a",
        query: {},
        refreshSeconds: 10,
      },
      { id: "still", type: "features", service: "featureserv", layer: "b", query: {} },
    ];
    render(
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client}>
          <DataProvider sources={sources}>
            <Quiet />
          </DataProvider>
        </ItemClientProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(queryDataSource).toHaveBeenCalledTimes(2));
    await vi.advanceTimersByTimeAsync(10_500);
    await waitFor(() => expect(queryDataSource).toHaveBeenCalledTimes(3));
    const ids = queryDataSource.mock.calls.map(([s]) => (s as DataSource).id);
    expect(ids.filter((id) => id === "live")).toHaveLength(2);
    expect(ids.filter((id) => id === "still")).toHaveLength(1);
  } finally {
    vi.useRealTimers();
  }
});

test("le panneau choisit un rafraîchissement planifié, et le retire", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "parcs", query: {} },
  ];
  const onChange = vi.fn();
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Rafraîchissement de la source d1"), "60");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].refreshSeconds).toBe(60);
  rerender(
    <DataSourcePanel sources={[{ ...sources[0], refreshSeconds: 60 }]} onChange={onChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Rafraîchissement de la source d1"), "");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].refreshSeconds).toBeUndefined();
});
