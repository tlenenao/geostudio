// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { BASEMAPS } from "./basemaps";
import { BasemapSelect } from "./BasemapSelect";

test("shows the current basemap and reports changes as a style url", async () => {
  const onChange = vi.fn();
  render(<BasemapSelect value={BASEMAPS[0].style} onChange={onChange} />);
  const select = screen.getByLabelText("Fond de carte") as HTMLSelectElement;
  expect(select.value).toBe(BASEMAPS[0].style);
  await userEvent.selectOptions(select, BASEMAPS[1].style);
  expect(onChange).toHaveBeenCalledWith(BASEMAPS[1].style);
});
