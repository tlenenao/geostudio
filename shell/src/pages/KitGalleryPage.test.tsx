// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { KitGalleryPage } from "./KitGalleryPage";

vi.mock("../api/hooks", () => ({
  useMe: () => ({ isLoading: false, data: { isAdmin: true } }),
}));

// Checkbox/Radio/Switch/Slider (rendus sans interaction dans la galerie)
// appellent ResizeObserver sans garde côté Radix — stub local à ce fichier,
// même patron que Slider.test.tsx/Tooltip.test.tsx. jsdom n'a pas
// ResizeObserver ; un noop suffit ici. Ne pas ajouter à src/test/setup.ts
// (piège documenté).
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <KitGalleryPage />
    </QueryClientProvider>,
  );
}

test("rend sans lever pour les primitives du kit", () => {
  expect(() => renderPage()).not.toThrow();
  expect(screen.getByRole("heading", { name: "Galerie de primitives" })).toBeInTheDocument();
});

test("le bouton d'ambiance bascule document.documentElement.dataset.theme", async () => {
  renderPage();
  const toggle = screen.getByRole("button", { name: "Ambiance sombre" });
  expect(document.documentElement.dataset.theme).toBeUndefined();
  await userEvent.click(toggle);
  expect(document.documentElement.dataset.theme).toBe("dark");
  await userEvent.click(screen.getByRole("button", { name: "Ambiance claire" }));
  expect(document.documentElement.dataset.theme).toBe("light");
});
