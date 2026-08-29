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
  // Texte réel de chaque Blob passé à `createObjectURL`, dans l'ordre de
  // création (`contents[i]` correspond à `created[i]`). Ajouté en revue
  // (2026-08-28, trou 1) : sans ça, un test ne peut vérifier QUE la donnée
  // statique `LUCIDE_ICON_SVGS[...]` — jamais ce qui a réellement traversé
  // `rasterizeLucideIcon` (substitution `currentColor` incluse), et un
  // `split`/`join` devenu no-op silencieux ne serait détecté par rien.
  const contents: Promise<string>[] = [];
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

  // MESURÉ sous le jsdom installé : `Blob.prototype` n'a que `constructor`,
  // `slice`, `size`, `type` — ni `.text()`, ni `.arrayBuffer()`, ni
  // `.stream()`. On ajoute `.text()` nous-mêmes via `FileReader`, seule voie
  // de lecture d'un Blob réellement présente dans cet environnement
  // (`readAsText` fonctionne, vérifié), et on la retire au `restore()`
  // comme pour les deux méthodes de `URL` ci-dessus.
  const blobProto = Blob.prototype as unknown as Record<string, unknown>;
  const hadBlobText = "text" in blobProto;
  if (!hadBlobText) {
    blobProto.text = function (this: Blob) {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error ?? new Error("FileReader error"));
        reader.readAsText(this);
      });
    };
  }

  // URL de blob -> texte (résolu de façon asynchrone, via le `.text()`
  // ci-dessus) : permet à `StubImage` de savoir échouer un décodage sur la
  // base du contenu réel du SVG (donc du nom d'icône, présent dans son
  // attribut `class="lucide lucide-<name>"`), pas seulement sur l'URL
  // opaque `blob:stub/N`.
  const contentByUrl = new Map<string, Promise<string>>();
  target.createObjectURL = vi.fn((blob: Blob) => {
    const url = `blob:stub/${(counter += 1)}`;
    created.push(url);
    const text = (blob as unknown as { text(): Promise<string> }).text();
    contents.push(text);
    contentByUrl.set(url, text);
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
      // On attend le contenu (résolu de façon asynchrone) avant de décider :
      // `options.failing` peut désigner soit un fragment d'URL (rétrocompat,
      // p. ex. "blob:stub/" pour tout faire échouer), soit un nom d'icône
      // présent dans le SVG lui-même (p. ex. "map-pin").
      const content = contentByUrl.get(value) ?? Promise.resolve("");
      void content.then((text) => {
        queueMicrotask(() => {
          const fails = options.failing?.some((f) => value.includes(f) || text.includes(f));
          if (fails) this.onerror?.(new Error("stub"));
          else this.onload?.();
        });
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
    contents,
    restore() {
      if (!hadCreate) delete target.createObjectURL;
      if (!hadRevoke) delete target.revokeObjectURL;
      if (!hadBlobText) delete blobProto.text;
    },
  };
}
