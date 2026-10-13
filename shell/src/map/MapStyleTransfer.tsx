// SPDX-License-Identifier: Apache-2.0
// ARC-28 : export / import d'un style MapLibre depuis le panneau des couches.
import { useRef, useState } from "react";
import type { MapLayer } from "../api/types";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";
import "../i18n/domains/map";
import { exportMapLibreStyle, importMapLibreStyle } from "./mapLibreStyle";

const MAX_STYLE_BYTES = 5 * 1024 * 1024;

const readText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(file);
  });

export function MapStyleTransfer({
  layers,
  onChange,
}: {
  layers: MapLayer[];
  onChange: (layers: MapLayer[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);

  const doExport = () => {
    const blob = new Blob([JSON.stringify(exportMapLibreStyle(layers, "GeoStudio"), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "style-maplibre.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const doImport = async (file: File) => {
    try {
      if (file.size > MAX_STYLE_BYTES) throw new Error("size");
      const { layers: imported, skipped } = importMapLibreStyle(JSON.parse(await readText(file)));
      // Ids régénérés : un style importé ne doit jamais entrer en collision avec une couche existante.
      const fresh = imported.map((l) => ({ ...l, id: crypto.randomUUID() }));
      onChange([...layers, ...fresh]);
      setMessage(
        t("styleTransfer.importResult", { imported: fresh.length, skipped: skipped.length }),
      );
    } catch {
      setMessage(t("styleTransfer.invalid"));
    }
  };

  return (
    <div className="border-t border-rule pt-2">
      <p className="mb-1 text-xs font-medium text-ink-2">{t("styleTransfer.heading")}</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="outline" onClick={doExport}>
          {t("styleTransfer.export")}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => input.current?.click()}>
          {t("styleTransfer.import")}
        </Button>
        <input
          ref={input}
          type="file"
          accept="application/json,.json"
          className="hidden"
          data-testid="style-import-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void doImport(f);
          }}
        />
      </div>
      {message && (
        <p role="status" className="mt-1 text-xs text-ink-3">
          {message}
        </p>
      )}
    </div>
  );
}
