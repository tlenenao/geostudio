import { useEffect } from "react";
import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, signIn } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      signIn();
    }
  }, [isLoading, isAuthenticated, signIn]);

  if (isLoading) {
    return (
      <div role="status" className="p-8 text-sm text-muted-foreground">
        Connexion…
      </div>
    );
  }
  if (!isAuthenticated) {
    return null;
  }
  return <>{children}</>;
}
