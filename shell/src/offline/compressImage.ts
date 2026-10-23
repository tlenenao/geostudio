// SPDX-License-Identifier: Apache-2.0
// L8 : réduction des photos avant mise en file / envoi (zone à faible débit, quota IndexedDB).
// Jamais d'agrandissement, jamais de résultat plus gros que l'original, repli silencieux sur
// l'original dès qu'une étape n'est pas disponible (aucune saisie ne doit échouer à cause de ça).

/** Côté long maximal après réduction (px). */
export const MAX_SIDE = 2048;
/** Qualité JPEG de la ré-encodage. */
export const JPEG_QUALITY = 0.85;
/** En deçà, la photo est laissée telle quelle (octets). */
export const COMPRESS_ABOVE_BYTES = 2 * 1024 * 1024;

type Bitmap = { width: number; height: number; close?: () => void };
type Canvas = {
  getContext: (
    kind: "2d",
  ) => { drawImage: (b: Bitmap, x: number, y: number, w: number, h: number) => void } | null;
  toBlob: (type: string, quality: number) => Promise<Blob | null>;
};

export type CompressEnv = {
  createImageBitmap?: (file: Blob, options?: { imageOrientation?: string }) => Promise<Bitmap>;
  makeCanvas: (w: number, h: number) => Canvas;
};

/** Dimensions cibles : côté long ramené à `max`, proportions conservées, jamais agrandies. */
export function targetSize(width: number, height: number, max = MAX_SIDE) {
  const long = Math.max(width, height);
  if (long <= max) return { width, height };
  const k = max / long;
  return { width: Math.max(1, Math.round(width * k)), height: Math.max(1, Math.round(height * k)) };
}

function browserEnv(): CompressEnv {
  return {
    createImageBitmap:
      typeof createImageBitmap === "function"
        ? (f, o) => createImageBitmap(f, o as ImageBitmapOptions) as Promise<Bitmap>
        : undefined,
    makeCanvas: (w, h) => {
      const el = document.createElement("canvas");
      el.width = w;
      el.height = h;
      return {
        getContext: (k) => el.getContext(k) as ReturnType<Canvas["getContext"]>,
        toBlob: (type, quality) => new Promise((resolve) => el.toBlob(resolve, type, quality)),
      };
    },
  };
}

const SKIPPED = new Set(["image/gif", "image/svg+xml"]);

export async function compressImage(file: File, env: CompressEnv = browserEnv()): Promise<File> {
  if (!file.type.startsWith("image/") || SKIPPED.has(file.type)) return file;
  if (file.size <= COMPRESS_ABOVE_BYTES) return file;
  if (!env.createImageBitmap) return file;
  try {
    // `from-image` applique l'orientation EXIF : le pixel obtenu est déjà droit.
    const bitmap = await env.createImageBitmap(file, { imageOrientation: "from-image" });
    const { width, height } = targetSize(bitmap.width, bitmap.height);
    const canvas = env.makeCanvas(width, height);
    const g = canvas.getContext("2d");
    if (!g) return file;
    g.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();
    const blob = await canvas.toBlob("image/jpeg", JPEG_QUALITY);
    if (!blob || blob.size >= file.size) return file;
    const name = file.name.replace(/\.[^./]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg", lastModified: file.lastModified });
  } catch {
    return file;
  }
}
