// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import type { HarvestSource } from "../api/types";
import { EditHarvestSourcePanel } from "./EditHarvestSourcePanel";

const { mockUseUpdateHarvestSource, mockUseInstanceInfo } = vi.hoisted(() => ({
  mockUseUpdateHarvestSource: vi.fn(),
  mockUseInstanceInfo: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useUpdateHarvestSource: mockUseUpdateHarvestSource,
  useInstanceInfo: mockUseInstanceInfo,
}));

const SOURCE: HarvestSource = {
  id: "s1",
  type: "stac",
  url: "https://x",
  mode: "reference",
  enabled: true,
  intervalMinutes: 45,
  lastRunAt: null,
  lastStatus: null,
  lastError: null,
} as HarvestSource;

describe("EditHarvestSourcePanel — intervalMinutes", () => {
  test("l'intervalle existant est pré-rempli et modifiable", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateHarvestSource.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });

    render(<EditHarvestSourcePanel source={SOURCE} onClose={() => {}} />);
    expect(screen.getByLabelText(/Intervalle/)).toHaveValue(45);
    fireEvent.change(screen.getByLabelText(/Intervalle/), { target: { value: "10" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ intervalMinutes: 10 })),
    );
  });
});
