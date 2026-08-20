// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import type { WidgetContext } from "../registry";
import type { WcWidgetManifest } from "./manifest";

export function makeWcHost(manifest: WcWidgetManifest) {
  return function WcHost({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
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
    }, []);

    useEffect(() => {
      const el = elRef.current as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      el.props = props;
      el.data = ctx.data;
      el.user = ctx.user;
      el.navigate = ctx.navigate;
    });

    useEffect(() => {
      const el = elRef.current;
      if (!el || !ctx.bus || !ctx.widgetId) return;
      const bus = ctx.bus;
      const widgetId = ctx.widgetId;
      const offs = (manifest.events ?? []).map((name) => {
        const listener = (e: Event) => bus.emit(widgetId, name, (e as CustomEvent).detail);
        el.addEventListener(name, listener);
        return () => el.removeEventListener(name, listener);
      });
      const unregs = (manifest.actions ?? []).map((name) =>
        bus.register(widgetId, name, (payload) => {
          (el as HTMLElement & Record<string, (payload?: unknown) => void>)[name]?.(payload);
        }),
      );
      return () => {
        offs.forEach((off) => off());
        unregs.forEach((unreg) => unreg());
      };
    }, [ctx.bus, ctx.widgetId]);

    return <div ref={containerRef} className="h-full w-full" />;
  };
}
