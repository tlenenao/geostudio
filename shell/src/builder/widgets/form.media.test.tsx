// SPDX-License-Identifier: Apache-2.0
// L8 : champs média typés (accept/capture selon la nature) et non-régression I1/I2.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AttachmentKind, ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import type { FormField } from "./form";
import { mediaAttrs } from "./form";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});
afterEach(() => vi.unstubAllGlobals());

const base = { order: 0, hidden: false, required: false };

function renderMedia(
  kind: AttachmentKind | undefined,
  { mobile = true, client = {} as Partial<ItemClient> } = {},
) {
  const fields: FormField[] = [
    { ...base, name: "nom", type: "string", label: "Nom" },
    {
      ...base,
      name: "media",
      type: "attachment",
      label: "Média",
      order: 1,
      ...(kind ? { kind } : {}),
    },
  ];
  const c = {
    createFeature: vi.fn().mockResolvedValue({ id: 42 }),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
    ...client,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={c}>
        <Form
          props={{ dataSourceId: "ds", fields, submitLabel: "Envoyer", geometryType: null, mobile }}
          ctx={
            {
              mode: "runtime",
              data: { loading: false, error: false, records: [], layer: "c" },
            } as WidgetContext
          }
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return c;
}

const fileInput = () => document.querySelector('input[type="file"]') as HTMLInputElement;

test("mediaAttrs : accept/capture par nature de média", () => {
  expect(mediaAttrs("image")).toEqual({ accept: "image/*", capture: "environment" });
  expect(mediaAttrs("video")).toEqual({ accept: "video/*", capture: "environment" });
  expect(mediaAttrs("audio")).toEqual({ accept: "audio/*", capture: "user" });
  expect(mediaAttrs("file")).toEqual({});
  expect(mediaAttrs(undefined)).toEqual({});
});

test.each([
  ["image", "image/*", "environment"],
  ["video", "video/*", "environment"],
  ["audio", "audio/*", "user"],
] as const)("un champ %s mobile règle accept=%s et capture=%s", (kind, accept, capture) => {
  renderMedia(kind);
  expect(fileInput()).toHaveAttribute("accept", accept);
  expect(fileInput()).toHaveAttribute("capture", capture);
});

test("un champ fichier mobile n'impose ni accept ni capture", () => {
  renderMedia("file");
  expect(fileInput()).not.toHaveAttribute("accept");
  expect(fileInput()).not.toHaveAttribute("capture");
});

test("sans nature déclarée, le comportement historique (image + caméra) est conservé", () => {
  renderMedia(undefined);
  expect(fileInput()).toHaveAttribute("capture", "environment");
});

test("un fichier audio est mis en file puis envoyé avec son type MIME", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  renderMedia("audio", { client: { presignAttachmentUpload, confirmAttachmentUpload } });
  await userEvent.upload(fileInput(), new File(["x"], "note.mp3", { type: "audio/mpeg" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalled());
  expect(presignAttachmentUpload).toHaveBeenCalledWith(
    "c",
    "42",
    expect.objectContaining({ contentType: "audio/mpeg", filename: "note.mp3" }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "https://s3/u",
    expect.objectContaining({ headers: { "Content-Type": "audio/mpeg" } }),
  );
});

// --- Non-régression I1/I2 (revue SP ARC-27) : un échec d'envoi ne vide jamais le formulaire.
test("I2 : un PUT refusé (res.ok faux) n'appelle pas confirm", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  renderMedia("image", { client: { presignAttachmentUpload, confirmAttachmentUpload } });
  await userEvent.type(screen.getByLabelText("Nom"), "garde-moi");
  await userEvent.upload(fileInput(), new File(["x"], "p.jpg", { type: "image/jpeg" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("l'envoi de la photo a échoué");
  expect(confirmAttachmentUpload).not.toHaveBeenCalled();
});

test("I1 : après l'échec de la photo, la saisie et le fichier restent dans le formulaire", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3/u", key: "k" });
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  renderMedia("image", {
    client: { presignAttachmentUpload, confirmAttachmentUpload: vi.fn(), updateFeature },
  });
  await userEvent.type(screen.getByLabelText("Nom"), "garde-moi");
  await userEvent.upload(fileInput(), new File(["x"], "p.jpg", { type: "image/jpeg" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Nom")).toHaveValue("garde-moi");
  expect(screen.getByText("Photo prête : p.jpg")).toBeInTheDocument();
  expect(screen.getByText(/Modification de l'enregistrement #42/)).toBeInTheDocument();
});

test("I2 : le Content-Type du PUT est celui du presign (même valeur, y compris par défaut)", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3/u", key: "k" });
  renderMedia("file", {
    client: {
      presignAttachmentUpload,
      confirmAttachmentUpload: vi.fn().mockResolvedValue(undefined),
    },
  });
  await userEvent.upload(fileInput(), new File(["x"], "doc.bin", { type: "" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const signed = presignAttachmentUpload.mock.calls[0][2].contentType;
  expect(fetchMock.mock.calls[0][1].headers["Content-Type"]).toBe(signed);
  expect(signed).toBe("application/octet-stream");
});
