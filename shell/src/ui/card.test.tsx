// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { test } from "vitest";
import { Card } from "./card";
import { expectTokenizedClasses } from "./kit/testUtils";

// `Card` a zéro consommateur ailleurs dans `src` (vérifié par grep,
// SP-B12c) — un fichier de test dédié est nécessaire, aucun rendu existant
// ne l'exerce.
test("SP-B12c : Card n'a pas de couleur Tailwind codée en dur", () => {
  const { container } = render(
    <Card>
      <p>contenu</p>
    </Card>,
  );
  expectTokenizedClasses(container);
});
