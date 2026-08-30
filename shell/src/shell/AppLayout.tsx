// SPDX-License-Identifier: Apache-2.0
import { useMe, useInstanceInfo } from "../api/hooks";
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
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const tileset3dEnabled = instanceQuery.data?.tileset3dEnabled === true;
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
    isAdmin: meQuery.data?.isAdmin === true,
    isAnalyst: meQuery.data?.isAnalyst === true,
    capabilities: {
      readOnly,
      etlEnabled: instanceQuery.data?.etlEnabled === true,
      exportEnabled: instanceQuery.data?.exportEnabled === true,
      appExportEnabled: instanceQuery.data?.appExportEnabled === true,
      tileset3dEnabled,
      terrain3dEnabled: instanceQuery.data?.terrain3dEnabled === true,
      copilotEnabled: instanceQuery.data?.copilotEnabled === true,
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
