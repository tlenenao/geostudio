// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { NativeSelect } from "./NativeSelect";

test("rend un select natif à la hauteur h-9 du kit", () => {
  render(
    <NativeSelect aria-label="Format">
      <option value="a4">A4</option>
    </NativeSelect>,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toHaveClass("h-9", "border-control");
});
