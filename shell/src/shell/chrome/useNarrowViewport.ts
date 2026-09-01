// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

// 640px = le seuil "sm" conventionnel de Tailwind, déjà idiomatique dans ce
// dépôt. Choisi (2026-09-02, revue transverse SP-30l) après mesure réelle :
// la grille triptyque trois colonnes de TriptychLayout.tsx clippe du contenu
// sur toute la bande ~391-540px (confirmé clippé à 540px), et ne tient sans
// aucun clipping qu'à partir de 640px. 390px seul (le seuil précédent)
// classait des téléphones réels courants (iPhone 14/15 Plus/Pro Max,
// Pixel 7/8 Pro, iPhone XR/11) en mode "large" alors qu'ils ne peuvent pas
// afficher la grille sans casse.
export const NARROW_QUERY = "(max-width: 640px)";

export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return narrow;
}
