// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CollectionAdmin } from "../api/types";
import { EditCollectionPanel } from "./EditCollectionPanel";

// Ce fichier n'existait pas avant SP-40/Task 12 (vérifié — aucun autre
// panneau de shell/src/shell/*.tsx n'a de fichier de test dédié : ils sont
// tous testés en intégration via leur page admin parente, ex.
// CollectionsAdminPage.test.tsx). On isole ici EditCollectionPanel en
// mockant tout le module "../api/hooks" (patron déjà utilisé ailleurs dans
// ce dépôt pour isoler un composant de son SDK, ex. src/builder/EChart.test.tsx
// avec vi.hoisted), ce qui évite d'avoir besoin de QueryClientProvider/
// ItemClientProvider/MSW — le composant ne consomme que useUpdateCollection
// et useInstanceInfo.
const { mockUseUpdateCollection, mockUseInstanceInfo } = vi.hoisted(() => ({
  mockUseUpdateCollection: vi.fn(),
  mockUseInstanceInfo: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useUpdateCollection: mockUseUpdateCollection,
  useInstanceInfo: mockUseInstanceInfo,
}));

const baseCollection: CollectionAdmin = {
  id: "incidents",
  title: "Incidents",
  description: "",
  tableName: "incidents",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 3,
  owner: "admin",
  attachmentFields: [],
};

beforeEach(() => {
  mockUseUpdateCollection.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    isError: false,
  });
  mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });
});

describe("EditCollectionPanel — champs attachment (SP-40)", () => {
  it("affiche les champs attachment déjà déclarés", () => {
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, attachmentFields: [{ key: "photos", label: "Photos" }] }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue("photos")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Photos")).toBeInTheDocument();
  });

  it("ajoute puis soumet un nouveau champ attachment", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, attachmentFields: [] }}
        onClose={vi.fn()}
      />,
    );

    // Ordre corrigé par rapport au texte littéral du brief (piège n°3) :
    // cliquer "Ajouter un champ" avant d'avoir tapé une clé/un libellé
    // serait un no-op (addAttachmentField renvoie tôt sur draft vide),
    // laissant attachmentFields à [] au moment du submit — l'assertion
    // finale serait irréalisable. Ordre réel exercé : taper, puis ajouter,
    // puis soumettre.
    await userEvent.type(screen.getByLabelText("Clé du champ"), "documents");
    await userEvent.type(screen.getByLabelText("Libellé du champ"), "Documents");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un champ" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ attachmentFields: [{ key: "documents", label: "Documents" }] }),
    );
  });
});
