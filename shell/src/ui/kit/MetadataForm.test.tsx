// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MetadataForm } from "./MetadataForm";

// jsdom n'implémente pas ces API navigateur consommées par Radix Select
// (piège n°10) — stub local à ce fichier.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const LICENSES = [{ id: "etalab-2.0", label: "Licence Ouverte / Open Licence 2.0 (Etalab)" }];
const LANGUAGES = [
  { id: "fr", label: "Français" },
  { id: "en", label: "Anglais" },
];

test("submits trimmed title, abstract and split keywords", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "Old", abstract: "A", keywords: ["k1"], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  const title = screen.getByLabelText("Titre");
  await userEvent.clear(title);
  await userEvent.type(title, "  New  ");
  const kw = screen.getByLabelText("Mots-clés");
  await userEvent.clear(kw);
  await userEvent.type(kw, "a, b ,c");
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).toHaveBeenCalledWith({
    title: "New",
    abstract: "A",
    keywords: ["a", "b", "c"],
    license: "",
    language: "fr",
  });
});

test("does not submit an empty title", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "", abstract: "", keywords: [], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});

test("pré-remplit les mots-clés existants (non-régression du bug d'ItemDetailPage)", () => {
  render(
    <MetadataForm
      initial={{
        title: "T",
        abstract: "A",
        keywords: ["existing-tag"],
        license: "",
        language: "fr",
      }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={vi.fn()}
      onCancel={() => {}}
    />,
  );
  expect(screen.getByLabelText("Mots-clés")).toHaveValue("existing-tag");
});

test("soumet la licence et la langue choisies", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "T", abstract: "", keywords: [], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
  await userEvent.click(
    await screen.findByRole("option", { name: "Licence Ouverte / Open Licence 2.0 (Etalab)" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Langue" }));
  await userEvent.click(await screen.findByRole("option", { name: "Anglais" }));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ license: "etalab-2.0", language: "en" }),
  );
});
