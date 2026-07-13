import { useEffect, useRef } from "react";
import type { WidgetContext } from "../registry";
import type { WcWidgetManifest } from "./manifest";

export function makeWcHost(manifest: WcWidgetManifest) {
  return function WcHost({
    props,
    ctx,
  }: {
    props: Record<string, unknown>;
    ctx: WidgetContext;
  }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const elRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
      const el = document.createElement(manifest.tag);
      elRef.current = el;
      containerRef.current?.appendChild(el);
      return () => {
        el.remove();
        elRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      const el = elRef.current as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      el.props = props;
      el.data = ctx.data;
      el.user = ctx.user;
      el.navigate = ctx.navigate;
    });

    return <div ref={containerRef} className="h-full w-full" />;
  };
}
