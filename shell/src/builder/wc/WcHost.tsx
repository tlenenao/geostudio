// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import type { WidgetContext } from "../registry";
import type { WcWidgetManifest } from "./manifest";

/** Version du contrat DOM servie à l'élément (L10, AUD-110) ; cf. `sdkVersion` du manifeste. */
export const SDK_VERSION = 1;

export function makeWcHost(manifest: WcWidgetManifest) {
  return function WcHost({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const elRef = useRef<HTMLElement | null>(null);
    // Les méthodes d'écriture du contrat lisent toujours le contexte courant : références stables.
    const ctxRef = useRef(ctx);
    ctxRef.current = ctx;
    const readyRef = useRef(false);

    useEffect(() => {
      const el = document.createElement(manifest.tag);
      elRef.current = el;
      containerRef.current?.appendChild(el);
      return () => {
        el.remove();
        elRef.current = null;
        readyRef.current = false;
      };
    }, []);

    useEffect(() => {
      const el = elRef.current as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      el.props = props;
      el.data = ctx.data;
      el.user = ctx.user;
      el.navigate = ctx.navigate;
      // Contrat DOM v1 (AUD-110).
      el.variables = ctx.variables ?? {};
      el.theme = ctx.theme;
      el.mode = ctx.mode;
      el.breakpoint = ctx.breakpoint;
      el.sdkVersion = SDK_VERSION;
      el.setVariable = (name: string, value: unknown) => {
        const c = ctxRef.current;
        // Inerte en édition (le builder n'est pas un runtime) et pour un nom inconnu de l'app.
        if (c.mode === "edit" || !c.setVariable) return;
        if (!c.variables || !(name in c.variables)) {
          console.warn(`setVariable: unknown app variable "${name}"`);
          return;
        }
        c.setVariable(name, value);
      };
      el.setFilter = (sourceId: string, query: Record<string, unknown>) => {
        const c = ctxRef.current;
        if (c.mode === "edit" || !c.setFilter) return;
        c.setFilter(sourceId, query);
      };
      if (!readyRef.current) {
        readyRef.current = true;
        el.dispatchEvent(new CustomEvent("gs:ready", { detail: { sdkVersion: SDK_VERSION } }));
      }
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
