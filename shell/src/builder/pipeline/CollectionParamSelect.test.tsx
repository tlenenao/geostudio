// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { CollectionParamSelect } from "./CollectionParamSelect";

const COLLECTIONS: CollectionAdmin[] = [
  {
    id: "villes",
    title: "Villes",
    description: "",
    tableName: "villes",
    isPublic: true,
    editable: true,
    geometryType: null,
    srid: null,
    pkColumn: "id",
    canWrite: true,
    featureCount: 10,
    owner: "alice",
  },
  {
    id: "readonly_layer",
    title: "Lecture seule",
    description: "",
    tableName: "readonly_layer",
    isPublic: true,
    editable: false,
    geometryType: null,
    srid: null,
    pkColumn: "id",
    canWrite: false,
    featureCount: 3,
    owner: "bob",
  },
];

function renderSelect(props: Partial<Parameters<typeof CollectionParamSelect>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve(COLLECTIONS) };
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <CollectionParamSelect
          value=""
          onChange={onChange}
          variant="readable"
          ariaLabel="Collection"
          {...props}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange };
}

test("variant=readable lists every collection", async () => {
  renderSelect({ variant: "readable" });
  await waitFor(() =>
    expect(screen.getByRole("option", { name: /Lecture seule/ })).toBeInTheDocument(),
  );
  expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument();
});

test("variant=writable excludes collections the user cannot write", async () => {
  renderSelect({ variant: "writable" });
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  expect(screen.queryByRole("option", { name: /Lecture seule/ })).not.toBeInTheDocument();
});

test("selecting an option calls onChange with the collection id", async () => {
  const { onChange } = renderSelect({ variant: "readable" });
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Collection"), "villes");
  expect(onChange).toHaveBeenCalledWith("villes");
});
