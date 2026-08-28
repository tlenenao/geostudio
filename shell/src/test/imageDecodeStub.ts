// SPDX-License-Identifier: Apache-2.0
import { vi } from "vitest";

// jsdom : Image existe mais ne charge RIEN (aucun onload/onerror), et
// URL.createObjectURL / URL.revokeObjectURL / HTMLImageElement.decode sont
// absents (mesuré). Ce double rend `decodeIconImage` testable : chaque
// affectation de `src` résout à la microtâche suivante, sauf pour les URLs de
// la liste `failing`.
export function installImageDecodeStub(options: { failing?: string[] } = {}) {
  const created: string[] = [];
  const revoked: string[] = [];
  let counter = 0;
  // On NE remplace PAS l'objet URL : on n'AJOUTE que les deux méthodes
  // manquantes sur le global réel, et on les retire en fin de test.
  //
  // Constat N5 (Important) du 2026-08-28 : la version précédente faisait
  // `vi.stubGlobal("URL", { ...URL, … })`. MESURÉ sous le jsdom installé :
  // `Object.keys({ ...URL })` vaut `["parse", "canParse"]` (les seules
  // propriétés propres énumérables de la classe) et
  // `new ({ ...URL })("http://x/")` lève `TypeError: spread is not a
  // constructor`. Tout `new URL(...)` du même test aurait donc échoué — y
  // compris `isHostedCoreUrl` (`shell/src/map/MapView.tsx:52-57`) et le
  // `new URL` interne de MSW, dont le `setup.ts` du dépôt est en
  // `onUnhandledRequest: "error"`.
  const target = globalThis.URL as unknown as Record<string, unknown>;
  const hadCreate = "createObjectURL" in target;
  const hadRevoke = "revokeObjectURL" in target;
  target.createObjectURL = vi.fn((_blob: Blob) => {
    const url = `blob:stub/${(counter += 1)}`;
    created.push(url);
    return url;
  });
  target.revokeObjectURL = vi.fn((url: string) => {
    revoked.push(url);
  });
  class StubImage {
    onload: (() => void) | null = null;
    onerror: ((e?: unknown) => void) | null = null;
    width = 24;
    height = 24;
    crossOrigin: string | null = null;
    #src = "";
    get src() {
      return this.#src;
    }
    set src(value: string) {
      this.#src = value;
      queueMicrotask(() => {
        if (options.failing?.some((f) => value.includes(f))) this.onerror?.(new Error("stub"));
        else this.onload?.();
      });
    }
  }
  // `Image` n'est pas un global natif indispensable ailleurs : stubGlobal
  // convient, et `vi.unstubAllGlobals()` le défait.
  vi.stubGlobal("Image", StubImage);
  // `vi.unstubAllGlobals()` ne défait PAS une mutation faite à la main : la
  // restauration est explicite, et c'est l'appelant qui la déclenche.
  return {
    created,
    revoked,
    restore() {
      if (!hadCreate) delete target.createObjectURL;
      if (!hadRevoke) delete target.revokeObjectURL;
    },
  };
}
