// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { Avatar } from "./Avatar";
import { expectTokenizedClasses } from "./testUtils";

test("affiche le repli tant que l'image n'a pas chargé (jsdom ne charge aucune image)", async () => {
  const { container } = render(<Avatar src="/photo.jpg" alt="Tanguy" fallback="TL" />);
  await waitFor(() => expect(screen.getByText("TL")).toBeInTheDocument());
  expectTokenizedClasses(container);
});

test("sans src, affiche directement le repli", async () => {
  const { container } = render(<Avatar alt="Tanguy" fallback="TL" />);
  await waitFor(() => expect(screen.getByText("TL")).toBeInTheDocument());
  expectTokenizedClasses(container);
});
