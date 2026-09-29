// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useState } from "react";
import { useMe } from "../api/hooks";
import { TopBar } from "./chrome/TopBar";
import { DomainBar } from "./chrome/DomainBar";
import { BottomNav } from "./chrome/BottomNav";
import { StatusBar } from "./chrome/StatusBar";
import { useNarrowViewport } from "./chrome/useNarrowViewport";
import { useIsExportRender } from "./useIsExportRender";
import { t } from "../i18n";
import type { Profile } from "../auth/capabilities";

// D07 : chargé paresseusement — le chunk n'est demandé qu'au premier
// Ctrl/Cmd+K (ou clic sur le déclencheur visible de TopBar), jamais au
// chargement initial (patron déjà posé par SP-60 pour les routes, ici
// appliqué à un composant hors route).
const CommandPalette = lazy(() =>
  import("../ui/kit/CommandPalette").then((m) => ({ default: m.CommandPalette })),
);

export function AppLayout({ children }: { children: React.ReactNode }) {
  const meQuery = useMe();
  // GAP-31 : GET /me sert déjà `capabilities` sous la même forme exacte que
  // GET /instance (garanti par un test dédié côté cœur, cf. commentaire de
  // Me.capabilities dans api/types.ts) — un second appel réseau ici était
  // redondant. useInstanceInfo() reste utilisé ailleurs (TerrainPanel,
  // form.tsx, pages d'admin, NewItemButton, ItemActions, MapEditorPage...),
  // ce correctif ne touche que ce composant.
  const capabilities = meQuery.data?.capabilities;
  const readOnly = capabilities?.readOnly === true;
  const tileset3dEnabled = capabilities?.tileset3dEnabled === true;
  const isExportRender = useIsExportRender();
  const narrow = useNarrowViewport();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Cf. commentaire d'origine (conservé à l'identique) : le worker d'export
  // Playwright navigue directement sur une route protégée avec
  // ?exportRender=1 — le chrome (TopBar/DomainBar/StatusBar) ne doit pas
  // apparaître dans la capture.
  if (isExportRender) {
    return <div className="h-screen w-screen">{children}</div>;
  }

  const profile: Profile = {
    privileges: new Set(meQuery.data?.privileges ?? []),
    capabilities: {
      readOnly,
      etlEnabled: capabilities?.etlEnabled === true,
      exportEnabled: capabilities?.exportEnabled === true,
      appExportEnabled: capabilities?.appExportEnabled === true,
      tileset3dEnabled,
      terrain3dEnabled: capabilities?.terrain3dEnabled === true,
      copilotEnabled: capabilities?.copilotEnabled === true,
      quotasEnabled: capabilities?.quotasEnabled === true,
    },
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {readOnly && (
        <p className="bg-warn-soft px-6 py-2 text-center text-sm text-warn">
          {t("layout.readOnlyBanner")}
        </p>
      )}
      <TopBar tileset3dEnabled={tileset3dEnabled} onOpenPalette={() => setPaletteOpen(true)} />
      {!narrow && <DomainBar profile={profile} />}
      <div className="flex flex-1 flex-col overflow-y-auto p-6">{children}</div>
      {narrow && <BottomNav profile={profile} />}
      <StatusBar />
      {paletteOpen && (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} profile={profile} />
        </Suspense>
      )}
    </div>
  );
}
