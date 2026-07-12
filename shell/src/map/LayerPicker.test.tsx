import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, LayerSource, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayerPicker } from "./LayerPicker";

const sources: LayerSource[] = [
  { id: "communes", title: "Communes", service: "martin", kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}", sourceLayer: "communes" },
  { id: "public.parcs", title: "Parcs", service: "core", kind: "feature",
    url: "https://core.test/collections/public.parcs/items", featureCount: 128 },
  { id: "public.legacy", title: "Legacy", service: "core", kind: "feature",
    url: "https://core.test/collections/public.legacy/items", featureCount: null },
];

function renderPicker(onAdd: (l: MapLayer) => void) {
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("lists sources and emits a vector MapLayer on click", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "vector",
    title: "Communes",
    visible: true,
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("emits a feature MapLayer for a core source", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.click(await screen.findByRole("button", { name: /Parcs/ }));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Parcs",
    visible: true,
    url: "https://core.test/collections/public.parcs/items",
  });
});

test("gives each added layer a distinct id", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  await userEvent.click(btn);
  const id1 = (onAdd.mock.calls[0][0] as MapLayer).id;
  const id2 = (onAdd.mock.calls[1][0] as MapLayer).id;
  expect(id1).not.toBe(id2);
});

test("shows a feature-count badge for a core source with a known count", async () => {
  renderPicker(vi.fn());
  const item = (await screen.findByRole("button", { name: /Parcs/ })).closest("li")!;
  expect(item).toHaveTextContent("128 entités");
});

test("shows no feature-count badge for a martin source or an unknown count", async () => {
  renderPicker(vi.fn());
  const martinItem = (await screen.findByRole("button", { name: /Communes/ })).closest("li")!;
  expect(martinItem).not.toHaveTextContent(/entités/);
  const legacyItem = (await screen.findByRole("button", { name: /Legacy/ })).closest("li")!;
  expect(legacyItem).not.toHaveTextContent(/entités/);
});
