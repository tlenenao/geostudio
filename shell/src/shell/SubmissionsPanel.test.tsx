// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient, Submission } from "../api/types";
import { SubmissionsPanel } from "./SubmissionsPanel";

const pending: Submission = {
  id: "s1",
  status: "pending",
  properties: { nom: "Nid-de-poule" },
  geometry: null,
  attachment: { filename: "photo.png", contentType: "image/png", byteSize: 10 },
  createdAt: null,
};

function setup() {
  const client = {
    listSubmissions: vi.fn().mockResolvedValue([pending]),
    approveSubmission: vi.fn().mockResolvedValue(undefined),
    rejectSubmission: vi.fn().mockResolvedValue(undefined),
    listSubmissionTokens: vi.fn().mockResolvedValue([]),
    createSubmissionToken: vi.fn().mockResolvedValue({
      id: "k1",
      name: "mairie",
      prefix: "gss_abc",
      expiresAt: null,
      maxSubmissions: 50,
      submissionCount: 0,
      revokedAt: null,
      token: "gss_abc_SECRET",
    }),
    revokeSubmissionToken: vi.fn(),
  } as unknown as ItemClient;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <SubmissionsPanel collectionId="c" onClose={() => {}} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

describe("SubmissionsPanel", () => {
  it("liste la file, approuve et rejette", async () => {
    const client = setup();
    expect(await screen.findByText(/Nid-de-poule/)).toBeInTheDocument();
    expect(screen.getByText("Pièce jointe : photo.png")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approuver la soumission s1" }));
    await waitFor(() => expect(client.approveSubmission).toHaveBeenCalledWith("c", "s1"));
    await userEvent.click(screen.getByRole("button", { name: "Rejeter la soumission s1" }));
    await waitFor(() => expect(client.rejectSubmission).toHaveBeenCalledWith("c", "s1", ""));
  });

  it("crée un lien et n'affiche le jeton qu'à la création", async () => {
    const client = setup();
    await userEvent.type(screen.getByLabelText("Nom du lien"), "mairie");
    await userEvent.click(screen.getByRole("button", { name: "Créer un lien" }));
    expect(await screen.findByText("gss_abc_SECRET")).toBeInTheDocument();
    expect(client.createSubmissionToken).toHaveBeenCalledWith("c", {
      name: "mairie",
      expiresInDays: 30,
      maxSubmissions: 100,
    });
  });
});
