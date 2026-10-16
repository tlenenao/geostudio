// SPDX-License-Identifier: Apache-2.0
// ARC-27 : saisie mobile issue d'un XLSForm (pertinence, aide, GPS, photo, « mes saisies »).
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import { isFieldVisible, type FormField } from "./form";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const base = { order: 0, hidden: false, required: false };
const fields: FormField[] = [
  { ...base, name: "nom", type: "string", label: "Nom", hint: "Nom complet", order: 0 },
  { ...base, name: "age", type: "integer", label: "Âge", order: 1 },
  { ...base, name: "tuteur", type: "string", label: "Tuteur", visibleWhen: "age < 18", order: 2 },
  { ...base, name: "photo", type: "attachment", label: "Photo", order: 3 },
];

function renderCollect(client: Partial<ItemClient> = {}, extra: Record<string, unknown> = {}) {
  const c = {
    createFeature: vi.fn().mockResolvedValue({ id: 42 }),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
    listMyEntries: vi.fn().mockResolvedValue([]),
    ...client,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={c}>
        <Form
          props={{
            dataSourceId: "ds1",
            fields,
            submitLabel: "Envoyer",
            geometryType: "Point",
            mobile: true,
            showMyEntries: true,
            ...extra,
          }}
          ctx={
            {
              mode: "runtime",
              data: { loading: false, error: false, records: [], layer: "collecte" },
            } as WidgetContext
          }
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return c;
}

test("isFieldVisible : sans condition visible ; condition non vraie ou sur valeur nulle masque", () => {
  const f = fields[2];
  const names = ["nom", "age", "tuteur"];
  expect(isFieldVisible(fields[0], {}, names)).toBe(true);
  expect(isFieldVisible(f, { age: 10 }, names)).toBe(true);
  expect(isFieldVisible(f, { age: 30 }, names)).toBe(false);
  expect(isFieldVisible(f, {}, names)).toBe(false);
  expect(isFieldVisible({ ...f, visibleWhen: "((" }, { age: 1 }, names)).toBe(false);
});

test("un champ non pertinent est masqué puis affiché, et n'est pas envoyé quand masqué", async () => {
  const c = renderCollect();
  expect(screen.getByText("Nom complet")).toBeInTheDocument();
  expect(screen.queryByLabelText("Tuteur")).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Âge"), "10");
  await userEvent.type(await screen.findByLabelText("Tuteur"), "Marie");
  await userEvent.clear(screen.getByLabelText("Âge"));
  await userEvent.type(screen.getByLabelText("Âge"), "40");
  await waitFor(() => expect(screen.queryByLabelText("Tuteur")).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
  const sent = (c.createFeature as ReturnType<typeof vi.fn>).mock.calls[0][1];
  expect(sent.properties).not.toHaveProperty("tuteur");
  expect(sent.properties.age).toBe(40);
});

test("le bouton GPS renseigne longitude et latitude", async () => {
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: {
      getCurrentPosition: (ok: (p: unknown) => void) =>
        ok({ coords: { longitude: 2.35, latitude: 48.85 } }),
    },
  });
  renderCollect();
  await userEvent.click(screen.getByRole("button", { name: "Utiliser ma position" }));
  expect(screen.getByLabelText("Longitude")).toHaveValue(2.35);
  expect(screen.getByLabelText("Latitude")).toHaveValue(48.85);
});

test("un refus de géolocalisation affiche une alerte", async () => {
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: { getCurrentPosition: (_ok: unknown, ko: () => void) => ko() },
  });
  renderCollect();
  await userEvent.click(screen.getByRole("button", { name: "Utiliser ma position" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Position indisponible");
});

test("la photo choisie est envoyée après la création de la saisie", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3.test/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  const c = renderCollect({ presignAttachmentUpload, confirmAttachmentUpload });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).toHaveAttribute("capture", "environment");
  await userEvent.upload(input, new File(["x"], "p.jpg", { type: "image/jpeg" }));
  expect(await screen.findByText("Photo prête : p.jpg")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalled());
  expect(c.createFeature).toHaveBeenCalled();
  expect(presignAttachmentUpload).toHaveBeenCalledWith("collecte", "42", {
    fieldKey: "photo",
    filename: "p.jpg",
    contentType: "image/jpeg",
  });
});

test("« mes saisies » liste les saisies de l'appelant", async () => {
  renderCollect({
    listMyEntries: vi
      .fn()
      .mockResolvedValue([{ fid: "7", at: "2026-10-12T08:00:00Z", properties: { nom: "Dupont" } }]),
  });
  expect(await screen.findByText("Dupont")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Mes saisies" })).toBeInTheDocument();
});

test("« mes saisies » vide affiche un état vide", async () => {
  renderCollect();
  expect(await screen.findByText("Aucune saisie pour le moment.")).toBeInTheDocument();
});

test("la photo sans type MIME est envoyée avec le Content-Type signé", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3.test/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  renderCollect({ presignAttachmentUpload, confirmAttachmentUpload });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  // accept="image/*" écarterait un File.type vide : on le désactive pour simuler .heic Linux.
  await userEvent
    .setup({ applyAccept: false })
    .upload(input, new File(["x"], "p.heic", { type: "" }));
  expect(await screen.findByText("Photo prête : p.heic")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalled());
  expect(fetchMock).toHaveBeenCalledWith(
    "https://s3.test/u",
    expect.objectContaining({ headers: { "Content-Type": "application/octet-stream" } }),
  );
});

test("un PUT S3 refusé garde la saisie en édition, la photo en file et affiche l'erreur", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 403 })
    .mockResolvedValueOnce({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3.test/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const c = renderCollect({ presignAttachmentUpload, confirmAttachmentUpload, updateFeature });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(["x"], "p.jpg", { type: "image/jpeg" }));
  expect(await screen.findByText("Photo prête : p.jpg")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("l'envoi de la photo a échoué");
  expect(confirmAttachmentUpload).not.toHaveBeenCalled();
  expect(screen.getByText("Photo prête : p.jpg")).toBeInTheDocument();
  // Réessayer : la saisie existe déjà (mise à jour, pas de doublon), la photo repart.
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalledTimes(1));
  expect(c.createFeature).toHaveBeenCalledTimes(1);
  expect(updateFeature).toHaveBeenCalled();
  // La file est vidée et l'erreur levée : un nouvel envoi ne renvoie pas la photo.
  await waitFor(() => expect(screen.queryByText("Photo prête : p.jpg")).not.toBeInTheDocument());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(updateFeature).toHaveBeenCalledTimes(2));
  expect(confirmAttachmentUpload).toHaveBeenCalledTimes(1);
  expect(presignAttachmentUpload).toHaveBeenCalledTimes(2);
});
