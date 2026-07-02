import type { MapConfig } from "../api/types";

export function MapLegend({ layers }: { layers: MapConfig["layers"] }) {
  const visible = layers.filter((l) => l.visible);
  if (visible.length === 0) return null;
  return (
    <ul className="absolute bottom-2 left-2 z-10 rounded-md bg-white/90 p-2 text-xs shadow">
      {visible.map((l) => (
        <li key={l.id}>{l.title}</li>
      ))}
    </ul>
  );
}
