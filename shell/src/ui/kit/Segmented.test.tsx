// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Segmented } from "./Segmented";
import { expectTokenizedClasses } from "./testUtils";

const OPTIONS = [
  { value: "quantile", label: "Quantile" },
  { value: "jenks", label: "Jenks" },
];

test("clic sélectionne une option exclusive", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Segmented
      aria-label="Méthode"
      value="quantile"
      onValueChange={onValueChange}
      options={OPTIONS}
    />,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Jenks" }));
  expect(onValueChange).toHaveBeenCalledWith("jenks");
  expectTokenizedClasses(container);
});

test("l'option active porte aria-checked=true", () => {
  render(
    <Segmented aria-label="Méthode" value="quantile" onValueChange={() => {}} options={OPTIONS} />,
  );
  expect(screen.getByRole("radio", { name: "Quantile" })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByRole("radio", { name: "Jenks" })).toHaveAttribute("aria-checked", "false");
});
