// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { CreateHarvestSourcePanel } from "./CreateHarvestSourcePanel";

// Patron d'isolation déjà utilisé par EditCollectionPanel.test.tsx : mock de
// tout le module "../api/hooks" via vi.hoisted (référencer une simple const
// dans la factory de vi.mock échoue en TDZ — piège CLAUDE.md n°3, le patron
// littéral de la spec ne compile pas tel quel).
const { mockUseCreateHarvestSource, mockUseInstanceInfo } = vi.hoisted(() => ({
  mockUseCreateHarvestSource: vi.fn(),
  mockUseInstanceInfo: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useCreateHarvestSource: mockUseCreateHarvestSource,
  useInstanceInfo: mockUseInstanceInfo,
}));

describe("CreateHarvestSourcePanel — intervalMinutes", () => {
  test("un intervalle renseigné est transmis à la création", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseCreateHarvestSource.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });

    render(<CreateHarvestSourcePanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://x" } });
    fireEvent.change(screen.getByLabelText(/Intervalle/), { target: { value: "30" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ intervalMinutes: 30 })),
    );
  });

  test("un intervalle vide n'est pas transmis (undefined, pas 0/NaN)", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseCreateHarvestSource.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });

    render(<CreateHarvestSourcePanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://x" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).not.toHaveProperty("intervalMinutes");
  });
});
