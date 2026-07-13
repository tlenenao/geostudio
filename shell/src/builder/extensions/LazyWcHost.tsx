import { useEffect, useState } from "react";
import type { ExtensionManifest } from "../../api/types";
import { makeWcHost } from "../wc/WcHost";
import type { WidgetContext } from "../registry";
import { ensureModuleLoaded } from "./moduleCache";

function Placeholder({ text, tone }: { text: string; tone: "loading" | "error" }) {
  return (
    <div
      className={
        tone === "error"
          ? "flex h-full items-center justify-center bg-slate-100 text-xs text-red-600"
          : "flex h-full items-center justify-center bg-slate-50 text-xs text-slate-400"
      }
    >
      {text}
    </div>
  );
}

export function makeLazyWcHost(manifest: ExtensionManifest) {
  const WcHost = makeWcHost(manifest);

  return function LazyWcHost(p: { props: Record<string, unknown>; ctx: WidgetContext }) {
    const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

    useEffect(() => {
      let cancelled = false;
      ensureModuleLoaded(manifest.moduleUrl)
        .then(() => { if (!cancelled) setStatus("ready"); })
        .catch(() => { if (!cancelled) setStatus("error"); });
      return () => { cancelled = true; };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    if (status === "loading") return <Placeholder text="Chargement…" tone="loading" />;
    if (status === "error") return <Placeholder text="Extension indisponible" tone="error" />;
    return <WcHost {...p} />;
  };
}
