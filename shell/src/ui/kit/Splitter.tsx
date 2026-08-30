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

  return (
    <div className="flex h-full w-full">
      <div style={{ width }} className="min-w-0 overflow-auto">
        {first}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={width}
        aria-valuemin={min}
        aria-valuemax={max}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="w-1 shrink-0 cursor-col-resize bg-rule hover:bg-accent"
      />
      <div className="min-w-0 flex-1 overflow-auto">{second}</div>
    </div>
  );
}
