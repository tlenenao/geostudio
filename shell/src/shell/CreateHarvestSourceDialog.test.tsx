// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CreateHarvestSourceDialog } from "./CreateHarvestSourceDialog";

function Harness({ onClose }: { onClose: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <CreateHarvestSourceDialog open={true} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("sends the selected type (arcgis) on creation", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "arcgis",
          url: "https://x/FeatureServer",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );

  render(<Harness onClose={() => {}} />);
  await userEvent.type(screen.getByLabelText("URL"), "https://x/FeatureServer");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "arcgis");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(body).toEqual({
      type: "arcgis",
      url: "https://x/FeatureServer",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("envoie le type WMS et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "wms",
          url: "https://ows/x",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );

  render(<Harness onClose={() => {}} />);
  await userEvent.type(screen.getByLabelText("URL"), "https://ows/x");
  // Passer d'abord en copie (autorisé pour STAC), puis basculer en WMS :
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wms");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(body).toEqual({
      type: "wms",
      url: "https://ows/x",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("garde le mode copie disponible pour WFS", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })));
  render(<Harness onClose={() => {}} />);
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wfs");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});
