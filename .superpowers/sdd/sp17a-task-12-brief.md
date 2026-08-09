### Task 12: Bootstrap d'auth — dérogation `exportToken`

**Files:**
- Modify: `shell/src/auth/useAuth.ts`
- Modify: `shell/src/auth/RequireAuth.tsx`
- Modify: `shell/src/App.tsx` (câblage de `getToken`)
- Test: `shell/src/auth/RequireAuth.test.tsx`

**Interfaces:**
- Produces: `RequireAuth` ne redirige plus vers Keycloak quand `?exportToken=...` est présent dans l'URL. `getToken` (passé à `createItemClient`) renvoie l'`exportToken` de l'URL en priorité s'il est présent, sinon le jeton OIDC/mock normal.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/auth/RequireAuth.test.tsx (ajouter aux tests existants du fichier)
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { RequireAuth } from "./RequireAuth";

it("renders children without triggering signIn when exportToken is present, even though not authenticated", () => {
  // Mock useAuth pour renvoyer isAuthenticated=false et une fonction signIn
  // qui, si elle est appelée, fait échouer le test — adapter au mock déjà
  // utilisé par les tests existants de ce fichier (vi.mock("./useAuth", ...)).
  render(
    <MemoryRouter initialEntries={["/maps/1?exportToken=abc123"]}>
      <RequireAuth>
        <div>contenu protégé</div>
      </RequireAuth>
    </MemoryRouter>,
  );
  expect(screen.getByText("contenu protégé")).toBeInTheDocument();
});
```

Inspecter le mock de `useAuth` déjà présent dans `RequireAuth.test.tsx` avant d'écrire ce test — l'assertion "signIn jamais appelé" doit réutiliser le même spy que les tests existants (ex. `expect(signIn).not.toHaveBeenCalled()`), pas un nouveau mock parallèle.

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/auth/RequireAuth.test.tsx`
Expected: FAIL — `RequireAuth` déclenche `signIn()` (redirection), le contenu protégé ne s'affiche jamais.

- [ ] **Step 3: Implémenter**

Dans `RequireAuth.tsx`, en tête du composant, avant l'effet qui appelle `signIn()` :

```tsx
import { useSearchParams } from "react-router-dom";
// ...
const [searchParams] = useSearchParams();
const hasExportToken = searchParams.get("exportToken") !== null;
```

Dans l'`useEffect` existant qui déclenche `signIn()` sur `!isLoading && !isAuthenticated && !error`, ajouter `hasExportToken` à la garde négative (`&& !hasExportToken`), et dans la condition de rendu qui bloque les enfants (`return null` tant que non authentifié), ajouter `|| hasExportToken` pour laisser passer :

```tsx
useEffect(() => {
  if (!isLoading && !isAuthenticated && !error && !hasExportToken) {
    signIn();
  }
}, [isLoading, isAuthenticated, error, hasExportToken, signIn]);

if (!hasExportToken && (isLoading || (!isAuthenticated && !error))) {
  return null;
}

return <>{children}</>;
```

Adapter précisément à la structure conditionnelle réelle déjà présente dans `RequireAuth.tsx` (inspecter le fichier avant d'éditer) — le principe est : la présence d'`exportToken` dans l'URL doit être une porte de sortie anticipée qui court-circuite à la fois le déclenchement de `signIn()` et le blocage du rendu des enfants.

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/auth/RequireAuth.test.tsx`
Expected: PASS

- [ ] **Step 5: Câbler `getToken` pour préférer `exportToken`**

Dans `shell/src/App.tsx` (ou le fichier exact qui construit `getToken` et l'injecte dans `createItemClient({ coreUrl, martinUrl, getToken })` — confirmer l'emplacement précis en inspectant `App.tsx` avant d'éditer), remplacer :

```tsx
getToken: getAccessToken,
```

par une fonction qui préfère l'`exportToken` d'URL :

```tsx
function useExportAwareToken(getAccessToken: () => string | undefined) {
  const [searchParams] = useSearchParams();
  const exportToken = searchParams.get("exportToken");
  return () => exportToken ?? getAccessToken();
}
// ...
getToken: useExportAwareToken(getAccessToken),
```

Ajuster la syntaxe exacte pour respecter les règles des hooks React (l'appel de `useSearchParams` doit se faire au niveau du composant qui construit `createItemClient`, pas conditionnellement) — inspecter la structure réelle de `App.tsx` pour placer cette logique au bon endroit (probablement dans le composant qui appelle déjà `useAuth()` pour obtenir `getAccessToken`).

- [ ] **Step 6: Test manuel de bout en bout du bootstrap**

Run: `cd shell && npm run dev` puis dans un navigateur, avec `VITE_AUTH_MODE=mock` (mode dev par défaut de ce dépôt), naviguer vers `/maps/<un-id-existant>?exportToken=fake&exportRender=1` sans être connecté au préalable.
Expected: la page se charge sans redirection vers Keycloak (mode mock ne redirige déjà pas normalement — vérifier plutôt en simulant `VITE_AUTH_MODE=oidc` localement si la config le permet ; sinon se contenter de la couverture par tests unitaires ci-dessus et noter dans le rapport de tâche que la vérification manuelle en mode OIDC réel n'a pas pu être faite dans cet environnement).

- [ ] **Step 7: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/auth/useAuth.ts shell/src/auth/RequireAuth.tsx shell/src/auth/RequireAuth.test.tsx shell/src/App.tsx
git commit -m "feat(shell): SP-17a — bootstrap d'auth : dérogation exportToken pour le rendu Playwright"
```

---

