// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { BASEMAPS } from "./basemaps";
import { BasemapSelect } from "./BasemapSelect";

test("REV-367 i : liste aussi les fonds partagés du tenant", async () => {
  const client = {
    listTenantBasemaps: vi.fn().mockResolvedValue([{ id: "b1", label: "Ortho", style: "xyz:u" }]),
  } as unknown as ItemClient;
  render(
    <ItemClientProvider client={client}>
      <BasemapSelect value={BASEMAPS[0].style} onChange={() => {}} />
    </ItemClientProvider>,
  );
  expect(await screen.findByRole("option", { name: "Ortho" })).toHaveValue("xyz:u");
});

test("shows the current basemap and reports changes as a style url", async () => {
  const onChange = vi.fn();
  render(<BasemapSelect value={BASEMAPS[0].style} onChange={onChange} />);
  const select = screen.getByLabelText("Fond de carte") as HTMLSelectElement;
  expect(select.value).toBe(BASEMAPS[0].style);
  await userEvent.selectOptions(select, BASEMAPS[1].style);
  expect(onChange).toHaveBeenCalledWith(BASEMAPS[1].style);
});
