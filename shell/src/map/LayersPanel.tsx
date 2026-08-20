// SPDX-License-Identifier: Apache-2.0
import type { MapLayer } from "../api/types";
import { LayerPicker } from "./LayerPicker";

export function LayersPanel({
  layers,
  onChange,
}: {
  layers: MapLayer[];
  onChange: (layers: MapLayer[]) => void;
}) {
  function toggle(id: string) {
    onChange(layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));
  }
  function remove(id: string) {
    onChange(layers.filter((l) => l.id !== id));
  }
  function move(index: number, delta: number) {
    const next = index + delta;
    if (next < 0 || next >= layers.length) return;
    const copy = [...layers];
    [copy[index], copy[next]] = [copy[next], copy[index]];
    onChange(copy);
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1">
        {layers.map((layer, i) => (
          <li key={layer.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">{layer.title}</span>
            <button
              type="button"
              aria-label={`Monter ${layer.title}`}
              disabled={i === 0}
              className="px-1 disabled:opacity-30"
              onClick={() => move(i, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={`Descendre ${layer.title}`}
              disabled={i === layers.length - 1}
              className="px-1 disabled:opacity-30"
              onClick={() => move(i, 1)}
            >
              ↓
            </button>
            <button
              type="button"
              aria-label={`${layer.visible ? "Masquer" : "Afficher"} ${layer.title}`}
              className="px-1"
              onClick={() => toggle(layer.id)}
            >
              {layer.visible ? "👁" : "🚫"}
            </button>
            <button
              type="button"
              aria-label={`Retirer ${layer.title}`}
              className="px-1 text-red-600"
              onClick={() => remove(layer.id)}
            >
              ✕
            </button>
          </li>
        ))}
        {layers.length === 0 && <li className="text-xs text-slate-400">Aucune couche.</li>}
      </ul>
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter une couche</p>
        <LayerPicker onAdd={(layer) => onChange([...layers, layer])} />
      </div>
    </div>
  );
}
