// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";

// Titre de page de premier niveau : un seul niveau (h1), une seule taille et
// une seule graisse pour toutes les pages (P34.08).
export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="text-lg font-semibold text-ink">{children}</h1>;
}
