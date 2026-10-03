// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ApiError, isConflictError } from "../api/ApiError";
import { t } from "../i18n";
import { SaveConflictNotice } from "./SaveConflictNotice";

test("isConflictError ne reconnaît que le 412", () => {
  expect(isConflictError(new ApiError(412, { detail: "stale" }))).toBe(true);
  expect(isConflictError(new ApiError(422))).toBe(false);
  expect(isConflictError(new Error("x"))).toBe(false);
  expect(isConflictError(undefined)).toBe(false);
});

test("SaveConflictNotice annonce le conflit (role=alert) et déclenche le rechargement", async () => {
  const onReload = vi.fn();
  render(<SaveConflictNotice onReload={onReload} />);
  expect(screen.getByRole("alert")).toHaveTextContent(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  expect(onReload).toHaveBeenCalledTimes(1);
});

test("SaveConflictNotice accepte un message et un libellé propres à l'éditeur", () => {
  render(<SaveConflictNotice onReload={() => {}} message="Autre texte" reloadLabel="Relire" />);
  expect(screen.getByText("Autre texte")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Relire" })).toBeInTheDocument();
});
