// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CollectionAdmin } from "../api/types";
import { EditCollectionPanel } from "./EditCollectionPanel";

// jsdom n'implémente pas ces API navigateur consommées par Radix Select
// (piège n°10) — stub local à ce fichier.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// Ce fichier n'existait pas avant SP-40/Task 12 (vérifié — aucun autre
// panneau de shell/src/shell/*.tsx n'a de fichier de test dédié : ils sont
// tous testés en intégration via leur page admin parente, ex.
// CollectionsAdminPage.test.tsx). On isole ici EditCollectionPanel en
// mockant tout le module "../api/hooks" (patron déjà utilisé ailleurs dans
// ce dépôt pour isoler un composant de son SDK, ex. src/builder/EChart.test.tsx
// avec vi.hoisted), ce qui évite d'avoir besoin de QueryClientProvider/
// ItemClientProvider/MSW — le composant ne consomme que useUpdateCollection,
// useInstanceInfo et (depuis SP-41) useMetadataCatalog.
const { mockUseUpdateCollection, mockUseInstanceInfo, mockUseMetadataCatalog } = vi.hoisted(() => ({
  mockUseUpdateCollection: vi.fn(),
  mockUseInstanceInfo: vi.fn(),
  mockUseMetadataCatalog: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useUpdateCollection: mockUseUpdateCollection,
  useInstanceInfo: mockUseInstanceInfo,
  useMetadataCatalog: mockUseMetadataCatalog,
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
  license: "",
  licenseUri: "",
  producer: "",
  contact: "",
  updateFrequency: "",
  lineage: "",
  language: "fr",
  version: "",
  temporalStart: null,
  temporalEnd: null,
};

beforeEach(() => {
  mockUseUpdateCollection.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    isError: false,
  });
  mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });
  mockUseMetadataCatalog.mockReturnValue({
    data: {
      licenses: [
        {
          id: "etalab-2.0",
          label: "Licence Ouverte / Open Licence 2.0 (Etalab)",
          dcatUri: null,
          spdxId: "etalab-2.0",
        },
        { id: "other", label: "Autre (URI à saisir)", dcatUri: null, spdxId: "other" },
      ],
      frequencies: [{ id: "monthly", label: "Mensuelle" }],
      languages: [
        { id: "fr", label: "Français" },
        { id: "en", label: "Anglais" },
      ],
    },
  });
});

describe("EditCollectionPanel — champs attachment (SP-40)", () => {
  it("affiche les champs attachment déjà déclarés", async () => {
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, attachmentFields: [{ key: "photos", label: "Photos" }] }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Pièces jointes" }));
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
    await userEvent.click(screen.getByRole("tab", { name: "Pièces jointes" }));

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

describe("EditCollectionPanel — métadonnées ouvertes (SP-41)", () => {
  it("affiche les valeurs déjà déclarées", async () => {
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, producer: "Ma Régie", version: "1.0" }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    expect(screen.getByLabelText("Producteur")).toHaveValue("Ma Régie");
    expect(screen.getByLabelText("Version")).toHaveValue("1.0");
  });

  it("soumet une licence choisie", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
    await userEvent.click(
      await screen.findByRole("option", { name: "Licence Ouverte / Open Licence 2.0 (Etalab)" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ license: "etalab-2.0" }));
  });

  it("révèle le champ URI seulement pour la licence Autre", async () => {
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    expect(screen.queryByLabelText("URI de la licence")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
    await userEvent.click(await screen.findByRole("option", { name: "Autre (URI à saisir)" }));
    expect(screen.getByLabelText("URI de la licence")).toBeInTheDocument();
  });

  it("envoie une chaîne vide quand la licence redevient non déclarée", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, license: "etalab-2.0" }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    // Fait basculer explicitement le Select Licence vers le sentinel UNSET
    // ("Aucune licence déclarée") — sans ce clic, ce test ne fait que
    // revérifier un round-trip inchangé et laisse le ternaire
    // `license === UNSET ? "" : license` de submit() non exercé.
    await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
    await userEvent.click(await screen.findByRole("option", { name: "Aucune licence déclarée" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ license: "" }));
  });

  it("envoie une chaîne vide quand la fréquence de mise à jour redevient non renseignée", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, updateFrequency: "monthly" }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    // Même vérification que ci-dessus pour le ternaire jumeau
    // `updateFrequency === UNSET ? "" : updateFrequency`.
    await userEvent.click(screen.getByRole("combobox", { name: "Fréquence de mise à jour" }));
    await userEvent.click(await screen.findByRole("option", { name: "Non renseignée" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ updateFrequency: "" }));
  });

  it("envoie null pour une emprise temporelle non renseignée", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ temporalStart: null, temporalEnd: null }),
    );
  });
});
