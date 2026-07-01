import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MetadataForm } from "./MetadataForm";

test("submits trimmed title, abstract and split keywords", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "Old", abstract: "A", keywords: ["k1"] }}
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
  expect(onSubmit).toHaveBeenCalledWith({ title: "New", abstract: "A", keywords: ["a", "b", "c"] });
});

test("does not submit an empty title", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "", abstract: "", keywords: [] }}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});
