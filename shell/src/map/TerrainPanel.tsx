// SPDX-License-Identifier: Apache-2.0
import type { MapTerrainConfig } from "../api/types";

export function TerrainPanel({
  value, onChange,
}: {
  value: MapTerrainConfig | null;
  onChange: (next: MapTerrainConfig | null) => void;
}) {
  const enabled = value != null;

  function toggle(checked: boolean) {
    onChange(checked ? { tilesUrl: "", encoding: "terrarium", exaggeration: 1 } : null);
  }

  function patch(partial: Partial<MapTerrainConfig>) {
    if (!value) return;
    onChange({ ...value, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Terrain 3D</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Activer le terrain 3D"
          type="checkbox"
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        Activer le terrain 3D
      </label>
      {enabled && value && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            URL de tuiles (terrain-RGB, encodage terrarium)
            <input
              aria-label="URL de tuiles terrain"
              type="text"
              placeholder="https://…/{z}/{x}/{y}.png"
              value={value.tilesUrl}
              onChange={(e) => patch({ tilesUrl: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Exaggeration
            <input
              aria-label="Exaggeration du terrain"
              type="number"
              step={0.1}
              min={0}
              value={value.exaggeration ?? 1}
              onChange={(e) => patch({ exaggeration: Number(e.target.value) })}
            />
          </label>
        </>
      )}
    </div>
  );
}
