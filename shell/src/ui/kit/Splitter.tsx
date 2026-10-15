// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";

export function Splitter({
  first,
  second,
  defaultFirstWidth = 280,
  min = 160,
  max = 640,
}: {
  first: React.ReactNode;
  second: React.ReactNode;
  defaultFirstWidth?: number;
  min?: number;
  max?: number;
}) {
  const [width, setWidth] = useState(defaultFirstWidth);
  const dragStart = useRef<{ pointerX: number; startWidth: number } | null>(null);

  const clamp = (w: number) => Math.min(max, Math.max(min, w));

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragStart.current = { pointerX: e.clientX, startWidth: width };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const delta = e.clientX - dragStart.current.pointerX;
    setWidth(clamp(dragStart.current.startWidth + delta));
  };
  const onPointerUp = () => {
    dragStart.current = null;
  };

  // REV-365 f : séparateur focalisable, pilotable aux flèches (pas de 16 px) et Début/Fin.
  const STEP = 16;
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const next =
      e.key === "ArrowLeft"
        ? width - STEP
        : e.key === "ArrowRight"
          ? width + STEP
          : e.key === "Home"
            ? min
            : e.key === "End"
              ? max
              : null;
    if (next === null) return;
    e.preventDefault();
    setWidth(clamp(next));
  };

  return (
    <div className="flex h-full w-full">
      <div style={{ width }} className="min-w-0 overflow-auto">
        {first}
      </div>
      {/* Séparateur redimensionnable focalisable (patron WAI-ARIA « window splitter ») :
          le linter ne le reconnaît pas comme widget interactif. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={width}
        aria-valuemin={min}
        aria-valuemax={max}
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="w-1 shrink-0 cursor-col-resize bg-rule hover:bg-accent"
      />
      <div className="min-w-0 flex-1 overflow-auto">{second}</div>
    </div>
  );
}
