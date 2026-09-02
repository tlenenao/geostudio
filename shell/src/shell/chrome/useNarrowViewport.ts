// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

// 640px = le seuil "sm" conventionnel de Tailwind, déjà idiomatique dans ce
// dépôt. Choisi (2026-09-02, revue transverse SP-30l) après mesure réelle :
// la grille triptyque trois colonnes de TriptychLayout.tsx clippait du
// contenu sur toute la bande ~391-540px avec l'ancien seuil de 390px
// (confirmé clippé à 540px), classant des téléphones réels courants
// (iPhone 14/15 Plus/Pro Max, Pixel 7/8 Pro, iPhone XR/11) en mode "large"
// alors qu'ils ne peuvent pas afficher la grille sans casse. Relever le
// seuil à 640px élimine cette famine-là (la pire, colonne centrale à
// clientWidth 0), mais NE garantit PAS l'absence de tout clipping au-dessus
// de 640px sur chaque écran : round 2 de correction (2026-09-02, même date,
// cf. CLAUDE.md entrée SP-30l) a mesuré, via un check corrigé pour observer
// l'état stabilisé plutôt que le premier échantillon, un clipping résiduel
// stable sur 6 des 8 écrans de référence à 641px (Catalogue, Cartes,
// Apps & sites, Analytique, Administration, Automatisation — cf. shell/e2e/
// triptych-narrow.spec.ts, WIDE_BOUNDARY_ROOT_CAUSE) — un défaut de
// TriptychLayout.tsx lui-même (ses colonnes latérales grandissent vers leur
// maximum combiné, 280+320=600px, avant que la colonne centrale ne reçoive
// quoi que ce soit), pas de ce seuil. Ce défaut est tracké séparément et
// n'est PAS corrigé par ce seuil ; SP-30 n'est donc pas déclaré clos tant
// qu'il ne l'est pas (CLAUDE.md, section "À venir", entrée SP-30).
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
