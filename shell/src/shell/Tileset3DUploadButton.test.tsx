// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("blocks closing (Annuler, Escape, backdrop) while an upload is in progress", async () => {
  let releaseCreate: () => void = () => {};
  const createGate = new Promise<void>((resolve) => {
    releaseCreate = resolve;
  });
  server.use(
    http.post("https://core.test/tileset3d/uploads", async () => {
      // Held open deliberately: keeps phase at "uploading" so the test can
      // assert the close guard while the request chain is still in flight.
      await createGate;
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" })),
    http.put("https://minio.test/part-1", () =>
      new HttpResponse(null, { status: 200, headers: { ETag: "\"etag-1\"" } })),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", () => new HttpResponse(null, { status: 204 })),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" })),
  );

  const { container } = render(<Harness><Tileset3DUploadButton /></Harness>);
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  const cancelButton = await screen.findByText("Annuler");
  await waitFor(() => expect(cancelButton).toBeDisabled());

  // Clicking a disabled button fires no onClick handler — this proves the
  // button itself can no longer trigger a close, not just that it looks
  // disabled.
  await userEvent.click(cancelButton);
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Escape is wired through Dialog's onClose, the same guarded handler.
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Backdrop click goes through the same onClose prop.
  const backdrop = container.querySelector('[aria-hidden="true"]');
  expect(backdrop).not.toBeNull();
  fireEvent.click(backdrop as Element);
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Let the held request settle so the upload completes normally and
  // doesn't leak a pending promise into the next test.
  releaseCreate();
  await waitFor(() => expect(screen.queryByText("Nouveau tileset 3D", { selector: "h2" })).not.toBeInTheDocument());
});
