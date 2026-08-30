// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { Skeleton } from "./Skeleton";
import { expectTokenizedClasses } from "./testUtils";

test("rend un bloc animé tokenisé", () => {
  const { container } = render(<Skeleton className="h-4 w-32" />);
  expect(container.firstChild).toHaveClass("animate-pulse", "bg-sunken", "h-4", "w-32");
  expectTokenizedClasses(container);
});
