// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useInstanceInfo, useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { NewItemButton } from "./NewItemButton";
import { ImportFileButton } from "./ImportFileButton";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
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
