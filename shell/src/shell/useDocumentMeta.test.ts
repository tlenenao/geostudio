// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { useDocumentMeta } from "./useDocumentMeta";

afterEach(() => {
  document.title = "";
  document
    .querySelectorAll('meta[name="description"], link[rel="canonical"]')
    .forEach((el) => el.remove());
});

test("pose document.title, une meta description et un lien canonical", () => {
  renderHook(() =>
    useDocumentMeta({
      title: "Portail public",
      description: "Un portail de démo",
      canonicalUrl: "https://gis.example.fr/sites/portail-public",
    }),
  );

  expect(document.title).toBe("Portail public");
  const meta = document.querySelector('meta[name="description"]');
  expect(meta).not.toBeNull();
  expect(meta!.getAttribute("content")).toBe("Un portail de démo");
  const link = document.querySelector('link[rel="canonical"]');
  expect(link).not.toBeNull();
  expect(link!.getAttribute("href")).toBe("https://gis.example.fr/sites/portail-public");
});

test("met à jour les balises existantes plutôt que d'en dupliquer (deux montages)", () => {
  const { rerender } = renderHook(
    (props: { title: string }) =>
      useDocumentMeta({
        title: props.title,
        description: "Desc",
        canonicalUrl: "https://gis.example.fr/sites/a",
      }),
    { initialProps: { title: "Premier titre" } },
  );
  expect(document.title).toBe("Premier titre");
  expect(document.querySelectorAll('meta[name="description"]')).toHaveLength(1);

  rerender({ title: "Second titre" });
  expect(document.title).toBe("Second titre");
  expect(document.querySelectorAll('meta[name="description"]')).toHaveLength(1);
  expect(document.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
});

test("nettoie les balises posées au démontage", () => {
  const { unmount } = renderHook(() =>
    useDocumentMeta({
      title: "Portail public",
      description: "Un portail de démo",
      canonicalUrl: "https://gis.example.fr/sites/portail-public",
    }),
  );
  expect(document.querySelector('meta[name="description"]')).not.toBeNull();

  unmount();

  expect(document.querySelector('meta[name="description"]')).toBeNull();
  expect(document.querySelector('link[rel="canonical"]')).toBeNull();
});
