import { useEffect } from "react";
import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, error, signIn } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !error) {
      signIn();
    }
  }, [isLoading, isAuthenticated, error, signIn]);

  if (isLoading) {
    return (
      <div role="status" className="p-8 text-sm text-muted-foreground">
        Connexion…
      </div>
    );
  }
  if (error) {
    return (
      <div role="alert" className="p-8 text-sm text-red-600">
        Échec de la connexion : {error}{" "}
        <button className="underline" onClick={signIn}>Réessayer</button>
      </div>
    );
  }
  if (!isAuthenticated) {
    return null;
  }
  return <>{children}</>;
}
