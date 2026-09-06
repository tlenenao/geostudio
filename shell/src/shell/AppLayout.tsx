// SPDX-License-Identifier: Apache-2.0
import { useMe } from "../api/hooks";
import { TopBar } from "./chrome/TopBar";
import { DomainBar } from "./chrome/DomainBar";
import { BottomNav } from "./chrome/BottomNav";
import { StatusBar } from "./chrome/StatusBar";
import { useNarrowViewport } from "./chrome/useNarrowViewport";
import { useIsExportRender } from "./useIsExportRender";
import { t } from "../i18n";
import type { Profile } from "../auth/capabilities";

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
        <p className="bg-amber-100 px-6 py-2 text-center text-sm text-amber-900">
          {t("layout.readOnlyBanner")}
        </p>
      )}
      <TopBar tileset3dEnabled={tileset3dEnabled} />
      {!narrow && <DomainBar profile={profile} />}
      <div className="flex flex-1 flex-col overflow-y-auto p-6">{children}</div>
      {narrow && <BottomNav profile={profile} />}
      <StatusBar />
    </div>
  );
}
