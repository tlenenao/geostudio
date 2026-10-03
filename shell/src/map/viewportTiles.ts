// SPDX-License-Identifier: Apache-2.0
import { useSyncExternalStore } from "react";

// P29.06 : vue courante de la carte (publiée par MapView), lue par LayersPanel
// pour sonder les tuiles réellement affichées plutôt que la seule 0/0/0.
// ponytail: un seul « dernier viewport » global — deux cartes montées en même
// temps (widgets) se partagent la valeur ; un store par carte si le besoin vient.
export type Viewport = { zoom: number; bounds: [number, number, number, number] };

let current: Viewport | null = null;
const listeners = new Set<() => void>();

export function publishViewport(v: Viewport): void {
  // Clé stable (zoom entier + tuiles couvertes) : un simple pan dans les mêmes
  // tuiles ne doit pas re-notifier.
  if (current && tileKeys(current).join() === tileKeys(v).join()) return;
  current = v;
  listeners.forEach((l) => l());
}

export function useViewport(): Viewport | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => current,
  );
}

const MAX_TILES = 12;

function lonToX(lon: number, n: number): number {
  return Math.floor(((lon + 180) / 360) * n);
}
function latToY(lat: number, n: number): number {
  const r = (Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n);
}

// Tuiles « z/x/y » couvrant la vue, au zoom entier courant, rabaissé jusqu'à
// ≤ 12 tuiles (une vue large à z élevé ne doit pas déclencher 100 sondes).
export function tileKeys({ zoom, bounds }: Viewport): string[] {
  let z = Math.max(0, Math.min(24, Math.floor(zoom)));
  for (;;) {
    const n = 2 ** z;
    const x0 = Math.max(0, lonToX(bounds[0], n));
    const x1 = Math.min(n - 1, lonToX(bounds[2], n));
    const y0 = Math.max(0, latToY(bounds[3], n));
    const y1 = Math.min(n - 1, latToY(bounds[1], n));
    if ((x1 - x0 + 1) * (y1 - y0 + 1) <= MAX_TILES || z === 0) {
      const keys: string[] = [];
      for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) keys.push(`${z}/${x}/${y}`);
      return keys;
    }
    z -= 1;
  }
}
