// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

// Seuil de la grille triptyque à trois colonnes vs. le mode mobile (onglets
// + BottomNav) — partagé avec AppLayout.tsx (bascule DomainBar/BottomNav).
// Historique : 390px (SP-30) → 640px ("sm" Tailwind, revue transverse
// SP-30l — corrigeait la pire famine mais laissait la colonne centrale de
// TriptychLayout.tsx sans plancher réel entre ~641px et ce seuil, mesuré
// clippé sur 6 des 8 écrans de référence) → 899px (SP-33, spec
// docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md).
// SP-33 a donné à la colonne centrale un plancher CSS explicite
// (minmax(360px,1fr), TriptychLayout.tsx) ; ce seuil est calé juste
// au-dessus de la somme des trois planchers (browse 220 + centre 360 +
// inspect 260 = 840px, +~60px de marge) pour que la grille à trois
// colonnes ne soit jamais rendue en dessous du point où les trois peuvent
// coexister sans dépassement — sous ce seuil, le mode mobile prend le
// relais. Deux défauts pré-existants et distincts sur l'écran Cartes
// (colonne browse trop étroite pour LayersPanel ; <span> de titre
// LayersPanel à largeur nulle) restent hors périmètre de ce chantier — cf.
// shell/e2e/triptych-narrow.spec.ts et CLAUDE.md, lot "Carte".
export const NARROW_QUERY = "(max-width: 899px)";

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

// REV-286(a) : entre 640 et 899 px le chrome reste en mode mobile (BottomNav)
// mais TriptychLayout affiche deux volets (travail + volet latéral à onglets)
// au lieu d'un seul. `phone` n'est évalué que si `narrow` l'est : un stub
// matchMedia à valeur unique (tests) reste cohérent.
export const PHONE_QUERY = "(max-width: 639px)";
export type ViewportMode = "wide" | "medium" | "narrow";

function readViewportMode(): ViewportMode {
  if (!window.matchMedia(NARROW_QUERY).matches) return "wide";
  return window.matchMedia(PHONE_QUERY).matches ? "narrow" : "medium";
}

export function useViewportMode(): ViewportMode {
  const [mode, setMode] = useState<ViewportMode>(readViewportMode);

  useEffect(() => {
    const queries = [window.matchMedia(NARROW_QUERY), window.matchMedia(PHONE_QUERY)];
    const onChange = () => setMode(readViewportMode());
    queries.forEach((q) => q.addEventListener("change", onChange));
    return () => queries.forEach((q) => q.removeEventListener("change", onChange));
  }, []);

  return mode;
}
