// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { Terrain3DUploadButton } from "./Terrain3DUploadButton";

const CORE_URL = "https://core.test";

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function renderButton(onUploaded: () => void) {
  return render(
    <Harness>
      <Terrain3DUploadButton onUploaded={onUploaded} pollIntervalMs={0} />
    </Harness>,
  );
}

test("uploads a DEM and calls onUploaded once the conversion job is done", async () => {
  server.use(
    http.post(`${CORE_URL}/terrain3d/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new HttpResponse(null, { status: 200 })),
    http.post(`${CORE_URL}/terrain3d/uploads`, () =>
      HttpResponse.json({ jobId: "job-1" }, { status: 201 }),
    ),
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "t-1" }),
    ),
  );
  const onUploaded = vi.fn();
  renderButton(onUploaded);

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief du massif");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith("t-1"));
});

test("shows the conversion error message and does not call onUploaded", async () => {
  server.use(
    http.post(`${CORE_URL}/terrain3d/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new HttpResponse(null, { status: 200 })),
    http.post(`${CORE_URL}/terrain3d/uploads`, () =>
      HttpResponse.json({ jobId: "job-1" }, { status: 201 }),
    ),
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "error", errorMessage: "GeoTIFF illisible", itemId: null }),
    ),
  );
  const onUploaded = vi.fn();
  renderButton(onUploaded);

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await screen.findByText("GeoTIFF illisible");
  expect(onUploaded).not.toHaveBeenCalled();
});

test("désactive Annuler pendant un envoi en cours (plus d'Escape/backdrop à gérer — panneau en ligne)", async () => {
  server.use(
    http.post(`${CORE_URL}/terrain3d/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new Promise(() => {})), // never resolves: stays "uploading"
  );
  renderButton(vi.fn());

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: /annuler/i })).toBeDisabled());
});

test("presigns on the terrain3d route with the file's real content type", async () => {
  // C2/C3 (revue finale) : la route générique /uploads/presign signe dans le
  // bucket d'ingestion, que le worker de conversion ne lit jamais ; et un
  // Content-Type signé en dur ne correspond pas à celui que fetch(PUT, body:
  // File) enverra (File.type), ce qui fait échouer S3 en 403
  // SignatureDoesNotMatch.
  let presignBody: unknown = null;
  server.use(
    http.post(`${CORE_URL}/terrain3d/uploads/presign`, async ({ request }) => {
      presignBody = await request.json();
      return HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" });
    }),
    http.put(`${CORE_URL}/fake-s3-put`, () => new HttpResponse(null, { status: 200 })),
    http.post(`${CORE_URL}/terrain3d/uploads`, () =>
      HttpResponse.json({ jobId: "job-1" }, { status: 201 }),
    ),
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "t-1" }),
    ),
  );
  const onUploaded = vi.fn();
  renderButton(onUploaded);

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "image/tiff" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith("t-1"));
  expect(presignBody).toEqual({ filename: "dem.tif", contentType: "image/tiff" });
});

test("le formulaire n'est jamais une fenêtre modale (pas de role=dialog)", async () => {
  renderButton(vi.fn());
  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  expect(await screen.findByLabelText(/fichier dem/i)).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
