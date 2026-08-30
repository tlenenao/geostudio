// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Kbd } from "./Kbd";
import { expectTokenizedClasses } from "./testUtils";

test("rend un élément kbd tokenisé", () => {
  const { container } = render(<Kbd>⌘K</Kbd>);
  expect(screen.getByText("⌘K").tagName).toBe("KBD");
  expectTokenizedClasses(container);
});
