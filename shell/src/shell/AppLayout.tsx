// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useInstanceInfo, useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { NewItemButton } from "./NewItemButton";
import { ImportFileButton } from "./ImportFileButton";
import { Tileset3DUploadButton } from "./Tileset3DUploadButton";
import { useIsExportRender } from "./useIsExportRender";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const tileset3dEnabled = instanceQuery.data?.tileset3dEnabled === true;
  const isExportRender = useIsExportRender();

  // Playwright's export capture (Task 6, core/app/export/jobs.py) navigates
  // straight to a route nested under ProtectedLayout (e.g. /maps/:pk) with
  // ?exportRender=1. ProtectedLayout keeps RequireAuth in the tree (needed
  // for the future exportToken bypass, Task 12) but the header/nav/read-only
  // banner chrome this layout renders must not show up in the capture — a
  // page-level "nude chrome" guard (e.g. MapEditorPage's) can only omit what
  // that page itself renders, not what AppLayout wraps it in. Skip straight
  // to the children so the capture is exactly what the target page renders.
  //
  // The normal branch below establishes its own viewport height via
  // `min-h-screen` (a viewport unit, not a percentage-height chain through
  // body/#root, which have no explicit height set in index.css). The export
  // branch must do the same: without an explicit height here, MapEditorPage's
  // `h-full w-full` map container and AppRuntimePage's `h-full w-full` app
  // container resolve their percentage heights against an auto-height
  // containing block and collapse to zero, so every capture would be blank.
  // `h-screen w-screen` mirrors the same viewport-unit approach the normal
  // branch already uses.
  if (isExportRender) {
    return <div className="h-screen w-screen">{children}</div>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      {readOnly && (
        <p className="bg-amber-100 px-6 py-2 text-center text-sm text-amber-900">
          Mode démo — lecture seule, les modifications ne sont pas enregistrées.
        </p>
      )}
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <span className="text-lg font-bold">GeoStudio</span>
        <div className="flex items-center gap-3 text-sm">
          <NewItemButton />
          <ImportFileButton />
          {tileset3dEnabled && <Tileset3DUploadButton />}
          <span>{username}</span>
          <Button size="sm" variant="outline" onClick={signOut}>
            Déconnexion
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
          {meQuery.data?.isAdmin === true && (
            <>
              <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
                Extensions
              </Link>
              <Link to="/admin/collections" className="mt-1 block text-sm font-medium hover:underline">
                Collections
              </Link>
              <Link to="/admin/harvest" className="mt-1 block text-sm font-medium hover:underline">
                Moissonnage
              </Link>
            </>
          )}
          {meQuery.data?.isAnalyst === true && (
            <Link to="/analytics/sql" className="mt-2 block text-sm font-medium hover:underline">
              SQL Lab
            </Link>
          )}
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
