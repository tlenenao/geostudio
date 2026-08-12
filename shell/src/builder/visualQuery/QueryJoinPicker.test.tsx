// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QueryJoinPicker } from "./QueryJoinPicker";

const BASE: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }],
};
const JOINED: CollectionSchema = {
  collection: "communes", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "population", type: "integer", required: false }],
};

describe("QueryJoinPicker", () => {
  test("propose seulement les colonnes communes aux deux collections comme colonne de jointure", async () => {
    const onChange = vi.fn();
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={JOINED}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "", how: "inner" }}
        onChange={onChange}
      />,
    );
    const options = screen.getAllByRole("option", { name: /commune$/ });
    expect(options).toHaveLength(1); // "commune" est la seule colonne présente des deux côtés
  });

  test("affiche un message si aucune colonne n'est commune", () => {
    const disjointJoined: CollectionSchema = { ...JOINED, fields: [{ name: "population", type: "integer", required: false }] };
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={disjointJoined}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "", how: "inner" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/Aucune colonne commune/)).toBeInTheDocument();
  });

  test("change how notifie le parent", async () => {
    const onChange = vi.fn();
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={JOINED}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "commune", how: "inner" }}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Type de jointure"), "left");
    expect(onChange).toHaveBeenCalledWith({ collectionId: "communes", on: "commune", how: "left" });
  });
});
