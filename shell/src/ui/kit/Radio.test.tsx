// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Radio } from "./Radio";
import { expectTokenizedClasses } from "./testUtils";

test("sélectionne une option au clic et notifie onValueChange", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange}>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Éditeur" }));
  expect(onValueChange).toHaveBeenCalledWith("editeur");
  expectTokenizedClasses(container);
});

test("la navigation clavier flèche bas déplace la sélection", async () => {
  const onValueChange = vi.fn();
  render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange}>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  screen.getByRole("radio", { name: "Lecteur" }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onValueChange).toHaveBeenCalledWith("editeur");
});

test("disabled empêche la sélection", async () => {
  const onValueChange = vi.fn();
  render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange} disabled>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Éditeur" }));
  expect(onValueChange).not.toHaveBeenCalled();
});

test("disabled empêche la sélection au clavier", async () => {
  const onValueChange = vi.fn();
  render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange} disabled>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  screen.getByRole("radio", { name: "Lecteur" }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onValueChange).not.toHaveBeenCalled();
});
