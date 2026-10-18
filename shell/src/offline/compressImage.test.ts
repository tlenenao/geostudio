// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
import { COMPRESS_ABOVE_BYTES, compressImage, targetSize, type CompressEnv } from "./compressImage";

const big = (type = "image/jpeg", name = "IMG_1.JPG") =>
  new File([new Uint8Array(COMPRESS_ABOVE_BYTES + 10)], name, { type, lastModified: 123 });

function fakeEnv(opts: { w: number; h: number; blobSize?: number; noBitmap?: boolean }) {
  const drawImage = vi.fn();
  const createImageBitmap = vi
    .fn()
    .mockResolvedValue({ width: opts.w, height: opts.h, close: vi.fn() });
  const makeCanvas = vi.fn().mockReturnValue({
    getContext: () => ({ drawImage }),
    toBlob: vi.fn().mockResolvedValue(new Blob([new Uint8Array(opts.blobSize ?? 500)])),
  });
  const env: CompressEnv = {
    ...(opts.noBitmap ? {} : { createImageBitmap }),
    makeCanvas,
  };
  return { env, drawImage, createImageBitmap, makeCanvas };
}

test("targetSize : côté long ramené à 2048, proportions gardées, jamais d'agrandissement", () => {
  expect(targetSize(4096, 3072)).toEqual({ width: 2048, height: 1536 });
  expect(targetSize(3000, 6000)).toEqual({ width: 1024, height: 2048 });
  expect(targetSize(1000, 800)).toEqual({ width: 1000, height: 800 });
  expect(targetSize(2048, 2048)).toEqual({ width: 2048, height: 2048 });
});

test("une photo de 2 Mo ou moins est laissée telle quelle", async () => {
  const small = new File([new Uint8Array(COMPRESS_ABOVE_BYTES)], "a.jpg", { type: "image/jpeg" });
  const { env, createImageBitmap } = fakeEnv({ w: 4000, h: 3000 });
  expect(await compressImage(small, env)).toBe(small);
  expect(createImageBitmap).not.toHaveBeenCalled();
});

test("une grande photo est réduite en JPEG, orientation EXIF demandée, nom en .jpg", async () => {
  const { env, createImageBitmap, makeCanvas, drawImage } = fakeEnv({ w: 4032, h: 3024 });
  const out = await compressImage(big("image/heic", "IMG_1.HEIC"), env);
  expect(createImageBitmap).toHaveBeenCalledWith(expect.any(File), {
    imageOrientation: "from-image",
  });
  expect(makeCanvas).toHaveBeenCalledWith(2048, 1536);
  expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 2048, 1536);
  expect(out.type).toBe("image/jpeg");
  expect(out.name).toBe("IMG_1.jpg");
  expect(out.size).toBe(500);
  expect(out.lastModified).toBe(123);
});

test("une image plus petite que 2048 px n'est pas agrandie (ré-encodée seulement)", async () => {
  const { env, makeCanvas } = fakeEnv({ w: 1600, h: 1200 });
  await compressImage(big(), env);
  expect(makeCanvas).toHaveBeenCalledWith(1600, 1200);
});

test("repli sur l'original : createImageBitmap absent, erreur de décodage, résultat plus gros", async () => {
  const f = big();
  expect(await compressImage(f, fakeEnv({ w: 4000, h: 3000, noBitmap: true }).env)).toBe(f);
  const failing = fakeEnv({ w: 1, h: 1 });
  failing.createImageBitmap.mockRejectedValue(new Error("decode"));
  expect(await compressImage(f, failing.env)).toBe(f);
  const bloated = fakeEnv({ w: 4000, h: 3000, blobSize: COMPRESS_ABOVE_BYTES + 5000 });
  expect(await compressImage(f, bloated.env)).toBe(f);
});

test("un GIF, un SVG ou un fichier non image ne sont jamais touchés", async () => {
  const { env, createImageBitmap } = fakeEnv({ w: 4000, h: 3000 });
  for (const type of ["image/gif", "image/svg+xml", "application/pdf", "audio/mpeg"]) {
    const f = big(type, "x");
    expect(await compressImage(f, env)).toBe(f);
  }
  expect(createImageBitmap).not.toHaveBeenCalled();
});
