// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";

export const MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024;

export function ThumbnailUpload({
  onUpload,
  pending,
}: {
  onUpload: (file: File) => void;
  pending?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);

  function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Le fichier doit être une image.");
      return;
    }
    if (file.size > MAX_THUMBNAIL_BYTES) {
      setError("L'image dépasse 2 Mo.");
      return;
    }
    setError(null);
    onUpload(file);
  }

  return (
    <div className="flex flex-col gap-1 text-sm text-ink">
      <label className="flex flex-col gap-1">
        Miniature
        <input
          aria-label="Miniature"
          type="file"
          accept="image/*"
          disabled={pending}
          onChange={onChange}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
