import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <span className="text-lg font-bold">GeoStudio</span>
        <div className="flex items-center gap-3 text-sm">
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
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
