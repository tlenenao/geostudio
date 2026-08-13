// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { Tileset3DUploadButton } from "./Tileset3DUploadButton";

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function zipFile() {
  return new File(["PK\x03\x04fake-zip-content"], "city.zip", { type: "application/zip" });
}

test("uploads a small (single-part) tileset and closes on success", async () => {
  let completedParts: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads", () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" })),
    http.put("https://minio.test/part-1", () =>
      new HttpResponse(null, { status: 200, headers: { ETag: "\"etag-1\"" } })),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", async ({ request }) => {
      completedParts = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" })),
  );

  render(<Harness><Tileset3DUploadButton /></Harness>);
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  await waitFor(() => expect(screen.queryByText("Nouveau tileset 3D", { selector: "h2" })).not.toBeInTheDocument());
  expect(completedParts).toEqual({ parts: [{ partNumber: 1, etag: "\"etag-1\"" }] });
});

test("surfaces a job error instead of closing", async () => {
  server.use(
    http.post("https://core.test/tileset3d/uploads", () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" })),
    http.put("https://minio.test/part-1", () =>
      new HttpResponse(null, { status: 200, headers: { ETag: "\"etag-1\"" } })),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", () => new HttpResponse(null, { status: 204 })),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "error", errorMessage: "aucun tileset.json à la racine de l'archive", itemId: null })),
  );

  render(<Harness><Tileset3DUploadButton /></Harness>);
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  expect(await screen.findByRole("alert")).toHaveTextContent("aucun tileset.json à la racine de l'archive");
});
