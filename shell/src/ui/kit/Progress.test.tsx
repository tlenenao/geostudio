// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Progress } from "./Progress";
import { expectTokenizedClasses } from "./testUtils";

test("expose la valeur courante via aria-valuenow", () => {
  const { container } = render(<Progress aria-label="Import" value={40} max={100} />);
  const bar = screen.getByRole("progressbar", { name: "Import" });
  expect(bar).toHaveAttribute("aria-valuenow", "40");
  expect(bar).toHaveAttribute("aria-valuemax", "100");
  expectTokenizedClasses(container);
});
