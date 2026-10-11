// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ConfigWarningsBanner } from "./ConfigWarningsBanner";

test("lists every warning in a role=status region (REV-305)", () => {
  render(<ConfigWarningsBanner warnings={["message 'a' to: unknown target 'x'", "autre"]} />);
  const status = screen.getByRole("status");
  expect(status).toHaveTextContent("message 'a' to: unknown target 'x'");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("renders nothing without warnings", () => {
  const { container } = render(<ConfigWarningsBanner warnings={[]} />);
  expect(container).toBeEmptyDOMElement();
});
