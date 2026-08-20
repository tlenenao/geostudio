// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionSchema, DatasetConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CrossFilterLinkEditor } from "./CrossFilterLinkEditor";

const incidentsDataset: DatasetConfig = {
  source: "collection",
  collectionId: "incidents",
  columns: {},
};
const incidentsSchema: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "titre", type: "string", required: false },
    { name: "commune", type: "string", required: false },
  ],
};

function renderEditor(
  client: Partial<ItemClient>,
  props: Partial<Parameters<typeof CrossFilterLinkEditor>[0]> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChange = vi.fn();
  const onRemove = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <CrossFilterLinkEditor
          link={{ targetDatasetId: "", mode: "attribute", sourceField: "", targetField: "" }}
          sourceFields={["region", "commune"]}
          targetOptions={[{ pk: "ds-2", title: "Incidents" }]}
          onChange={onChange}
          onRemove={onRemove}
          {...props}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange, onRemove };
}

test("changing the target dataset calls onChange with the updated link", async () => {
  const { onChange } = renderEditor({});
  await userEvent.selectOptions(screen.getByLabelText("Dataset cible"), "ds-2");
  expect(onChange).toHaveBeenCalledWith({
    targetDatasetId: "ds-2",
    mode: "attribute",
    sourceField: "",
    targetField: "",
  });
});

test("switching to spatial mode resets the link to a bbox-precision spatial link", async () => {
  const { onChange } = renderEditor(
    {},
    { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } },
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode du lien"), "spatial");
  expect(onChange).toHaveBeenCalledWith({
    targetDatasetId: "ds-2",
    mode: "spatial",
    precision: "bbox",
  });
});

test("attribute mode offers source fields and the target dataset's own fields", async () => {
  renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema),
    },
    { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } },
  );
  expect(screen.getByLabelText("Champ source")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("Champ cible")).toBeInTheDocument());
  expect(screen.getByRole("option", { name: "commune" })).toBeInTheDocument();
});

test("spatial mode shows a precision select only when the target collection has geometry", async () => {
  renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema),
    },
    { link: { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" } },
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Précision spatiale du lien")).toBeInTheDocument(),
  );
});

test("spatial mode hides the precision select when the target collection has no geometry", async () => {
  renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue({ ...incidentsSchema, geometry: null }),
    },
    { link: { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" } },
  );
  await screen.findByLabelText("Dataset cible");
  expect(screen.queryByLabelText("Précision spatiale du lien")).not.toBeInTheDocument();
});

test("clicking remove calls onRemove", async () => {
  const { onRemove } = renderEditor({});
  await userEvent.click(screen.getByRole("button", { name: "Supprimer le lien" }));
  expect(onRemove).toHaveBeenCalled();
});
