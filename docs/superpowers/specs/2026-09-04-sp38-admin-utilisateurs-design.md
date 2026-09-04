# Page d'administration des utilisateurs (SP-38)

> Ferme le chantier 4.21 « Gestion des utilisateurs et des rôles »
> (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, vague 4).
> Spec brainstormée et validée avec Tanguy le 2026-09-04, à la suite de la
> clôture de SP-37 (lot « Carte ») et de SP-31 (rôles à base de privilèges).

## 1. Contexte & objectif

Le chantier 4.21 constatait : « `core/app/users/` n'a pas de `routes.py` ;
les rôles ne viennent que de `CORE_ADMIN_SUBS`/`CORE_ANALYST_SUBS`, lus à la
création de l'utilisateur seulement. Promouvoir quelqu'un exige aujourd'hui
d'éditer l'environnement et de recréer la ligne. »

**Vérifié par lecture directe du code (pas supposé) : ce constat est
aujourd'hui à moitié faux.** SP-31 (« rôles à base de privilèges ») a déjà
livré, sans le documenter comme tel dans son entrée CLAUDE.md, tout le
nécessaire côté cœur :

- `GET /users` (`core/app/auth/routes.py:114`) — liste paginée
  (`page`/`pageSize`), gardée par `Privilege.ADMIN_USERS_MANAGE`
  (`admin.users.manage`), retourne `{users: [{id, username, roleSlug}],
  total}`.
- `PATCH /users/{id}` (`core/app/auth/routes.py:130`) — change le rôle
  (`roleId`), même garde, audité (`user.role_change`), avec la garde
  anti-lockout déjà éprouvée sur `PATCH /roles/{id}` (409 si la cible est la
  dernière porteuse de `admin.users.manage` **et** `admin.roles.manage`
  combinés).
- `core/tests/test_users_admin_routes.py` — 7 tests couvrant liste, garde de
  privilège, promotion/rétrogradation, dernier admin protégé, 404
  cross-tenant, audit, rôle inconnu → 400.

Ce qui manque réellement : **aucune page du shell ne consomme ces routes**
(pas de `/admin/users`, pas de `UsersAdminPage`) — exactement la même classe
de défaut que SP-23 avait fermée pour l'historique de versions (K1) :
« livré + testé + mergé ≠ câblé » côté UI. C'est le seul morceau restant de
4.21.

## 2. Périmètre

**Dans le périmètre :**

1. **Cœur — un seul ajout** : paramètre de recherche `q` sur `GET /users`,
   pour que la recherche fonctionne à n'importe quelle échelle de tenant
   (exigé explicitement par Tanguy pendant le brainstorming — pas de
   filtrage côté client sur une seule page chargée). `list_users()`
   (`core/app/users/repository.py`) filtre sur `User.username.ilike(f"%{q}%")`
   quand `q` est fourni (même patron que `collections`/`items`/`harvest` —
   `core/app/collections/repository.py:145`, `core/app/items/repository.py:317`,
   `core/app/harvest/repository.py:166`), et le `total` retourné reflète déjà
   le sous-ensemble filtré (le calcul actuel compte sur la même requête que
   la pagination). Aucun changement de forme de réponse.
2. **Shell — API layer** (`shell/src/api/itemClient.ts`,
   `shell/src/api/types.ts`, `shell/src/api/hooks.ts`) :
   - `UserSummary = {id: string, username: string, roleSlug: string}`.
   - `itemClient.listUsers({page, pageSize, q}): Promise<{users:
     UserSummary[], total: number}>`.
   - `itemClient.updateUserRole(id: string, roleId: string):
     Promise<UserSummary>`.
   - `useUsers({page, pageSize, q})` (React Query, clé incluant les trois
     paramètres) et `useUpdateUserRole()` (mutation, invalide la clé
     `users` au succès — même patron que `useUpdateRole`).
3. **Page `UsersAdminPage`** (`shell/src/pages/UsersAdminPage.tsx`), même
   patron `TriptychLayout` que `RolesAdminPage` :
   - **browse** : lien retour Catalogue seul — même contenu que le
     `browse` de `RolesAdminPage`/`CollectionsAdminPage`/
     `HarvestSourcesAdminPage`, aucune de ces pages ne lie vers une page
     admin sœur ; seule `AdminExtensionsPage` joue ce rôle de hub (§2.6).
   - **work** : champ de recherche texte (contrôlé, retour à la page 1 à
     chaque changement) ; tableau `Nom d'utilisateur | Rôle` avec un
     `<select>` de rôle **inline par ligne** (options = `useRoles()`,
     `onChange` déclenche `updateUserRole` immédiatement, pas de bouton
     Enregistrer séparé) ; pagination Précédent/Suivant pilotée par
     `total`/`pageSize` (désactivés en butée).
   - **inspect** : panneau d'aide statique expliquant l'invariant
     anti-lockout (« le dernier titulaire de la gestion des rôles et des
     utilisateurs ne peut pas être rétrogradé »).
4. **Erreurs** : pas de distinction par code HTTP (aucune page admin du
   dépôt ne le fait aujourd'hui — `request()` ne remonte qu'un `Error`
   générique avec le statut dans le message, cf.
   `shell/src/api/itemClient.ts:340-355`) ; message générique par ligne en
   échec (« Échec de la mise à jour du rôle. »), état local
   `{userId, error} | null` pour ne pas polluer les autres lignes pendant
   qu'une mutation est en attente. Le `<select>` de la ligne en erreur
   revient à son rôle d'avant la tentative (pas d'état optimiste conservé).
5. **Route** : `/admin/users` dans `shell/src/shell/routes.tsx`,
   `RequirePrivilege privilege="admin.users.manage"`, même gabarit que les
   cinq autres routes `/admin/*`.
6. **Découverte** : `AdminExtensionsPage.tsx` gagne un lien croisé
   « Utilisateurs → » dans son panneau `browse` (même endroit que les liens
   existants vers `/admin/infrastructure` et `/admin/roles`,
   `AdminExtensionsPage.tsx:24-29`).
7. **CLAUDE.md** : ligne `### Livré` datée SP-38 ; retirer 4.21 de toute
   liste de suivi non bloquant si elle y apparaît (vérifier
   `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` — la case reste
   cochée dans ce document de référence, ne pas la modifier, seule
   CLAUDE.md liste les chantiers vague 4 restants de façon informelle).

**Hors périmètre, explicitement :**

- Exposer `email`/`firstName`/`lastName` côté API ou UI — `_user_json()``
  (`core/app/auth/routes.py:110`) ne retourne aujourd'hui que
  `id`/`username`/`roleSlug` ; les ajouter serait un changement de contrat
  de réponse non demandé, et le tableau n'a besoin que du nom d'utilisateur
  déjà affiché ailleurs (ex. `RolesAdminPage`).
- Créer ou supprimer un utilisateur depuis le shell — la création se fait
  exclusivement via OIDC (`get_or_create_user`, à la connexion), aucune
  route de suppression n'existe côté cœur ; ni l'un ni l'autre n'est demandé
  par 4.21.
- Distinguer les codes d'erreur HTTP (409 anti-lockout vs 400 rôle inconnu
  vs 404) par un message dédié — cf. §2.4, choix délibéré de cohérence avec
  le reste des pages admin.
- Recherche sur autre chose que `username` (email, nom, rôle) — seul le nom
  d'utilisateur est aujourd'hui exposé et affiché.
- Toute modification de `core/app/roles/` — le catalogue de rôles/privilèges
  est consommé tel quel (`useRoles()`), aucun changement.
- `core/app/users/routes.py` dédié — les deux routes restent dans
  `core/app/auth/routes.py`, où SP-31 les a placées (à côté de `GET /me` et
  des autres routes d'auth) ; les en extraire serait un refactor sans
  rapport avec ce chantier.

## 3. Mécanisme

**Recherche + pagination côté cœur** — extension de `list_users()` :

```diff
 def list_users(
-    session: Session, *, tenant_id: str, page: int, page_size: int
+    session: Session, *, tenant_id: str, page: int, page_size: int, q: str | None = None
 ) -> tuple[list[User], int]:
     base = select(User).where(User.tenant_id == tenant_id)
+    if q:
+        base = base.where(User.username.ilike(f"%{q}%"))
     total = session.scalar(select(func.count()).select_from(base.subquery()))
     ...
```

`GET /users` passe `q` en query param optionnel (`str | None = None`) et le
transmet tel quel — aucune validation supplémentaire (même absence de garde
que `page`/`pageSize` aujourd'hui, hors périmètre de ce chantier).

**Sélecteur de rôle inline** — chaque ligne du tableau porte son propre
`<select>` contrôlé par `role.slug`/`role.id` courant de l'utilisateur ; le
`onChange` appelle `updateUserRole.mutateAsync({id: user.id, roleId:
newRoleId})` immédiatement (pas de bouton Enregistrer séparé — cohérent
avec la demande explicite de Tanguy de garder l'interaction à un seul geste
par ligne). Pendant la mutation, le `<select>` de la ligne est désactivé
(`disabled={updateUserRole.isPending && pendingUserId === user.id}`) pour
éviter un double clic concurrent sur la même ligne ; les autres lignes
restent utilisables.

**Pagination** : `useUsers({page, pageSize: 50, q})`, boutons Précédent
(`disabled={page === 1}`) / Suivant (`disabled={page * pageSize >= total}`).
Changer `q` réinitialise `page` à 1 (géré par le composant, pas par le
hook).

## 4. Tests

1. **Cœur** (`core/tests/test_users_admin_routes.py`) : étendre avec un test
   `q` — créer trois utilisateurs (`alice`, `bob`, `charlie`), vérifier que
   `GET /users?q=al` ne retourne que `alice` avec `total == 1` ; vérifier
   qu'un `q` vide ou absent retourne tout (non-régression du comportement
   actuel).
2. **Shell — Vitest** (`UsersAdminPage.test.tsx`, patron
   `RolesAdminPage.test.tsx`) :
   - Chargement (`isLoading`), erreur de chargement.
   - Rendu du tableau avec `roleSlug` reflété dans le `<select>` de chaque
     ligne.
   - Changement de rôle : `onChange` appelle `updateUserRole` avec les bons
     `id`/`roleId`, désactivation pendant l'attente, ré-activation après.
   - Échec de mutation : message d'erreur affiché sur la bonne ligne
     uniquement, `<select>` revient à la valeur d'avant.
   - Recherche : taper dans le champ déclenche `useUsers` avec le bon `q`,
     réinitialise `page` à 1.
   - Pagination : boutons Précédent/Suivant désactivés en butée, activés
     sinon ; clic déclenche `useUsers` avec la bonne `page`.
3. **Route** (`routes.test.tsx`) : `/admin/users` gardée par
   `admin.users.manage`, même gabarit que les cinq routes `/admin/*`
   existantes.
4. **Pas de nouveau spec E2E dédié** — cohérent avec le périmètre des pages
   admin précédentes (`RolesAdminPage`/`HarvestSourcesAdminPage` n'en ont
   pas non plus) ; si la suite E2E complète (piège n°6, à lancer avant
   clôture) révèle une régression croisée, la corriger comme d'habitude.
5. `npm run test`, `uv run pytest` (module `app.users`/`app.auth`),
   `npm run e2e` verts, couverture shell non régressée (seuil 88, mesurée
   après nettoyage de `dist/`/`dist-export/`), couverture cœur non
   régressée (seuil 85).
6. **Régénération OpenAPI/types TS obligatoire** (piège n°1) : `GET /users`
   gagne un paramètre de requête — même incantation que d'habitude
   (`cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run python
   scripts/export_openapi.py openapi.json` puis `npm run gen:api-types`).

## 5. Critères de sortie

1. `GET /users?q=...` filtre par nom d'utilisateur, à n'importe quelle
   échelle de tenant (pas de filtrage côté client sur une page unique).
2. Un admin peut, depuis `/admin/users`, changer le rôle de n'importe quel
   utilisateur du tenant sans toucher à une variable d'environnement ; le
   changement est audité (déjà vrai côté cœur, vérifié ici bout en bout
   depuis l'UI).
3. La garde anti-lockout (dernier titulaire de
   `admin.users.manage`+`admin.roles.manage`) est visible depuis l'UI (409
   surfacé comme erreur sur la ligne, pas un crash silencieux).
4. `/admin/users` atteignable depuis `AdminExtensionsPage` et
   réciproquement vers `/admin/roles`.
5. Suites cœur et shell vertes, OpenAPI/types régénérés, CLAUDE.md à jour
   (entrée `### Livré` SP-38).

## 6. Risques et limites connues

- **Pas d'email/nom affiché** : si un tenant a des `username` peu lisibles
  (ex. un `sub` OIDC brut plutôt qu'un nom d'utilisateur humain), cette page
  hérite de cette limite — elle ne l'introduit pas (même limite que
  `RolesAdminPage`/tout le reste du shell, qui n'affiche jamais l'email
  utilisateur). Non traité ici, cf. §2 hors périmètre.
- **`q` non échappé pour les caractères spéciaux `ILIKE`** (`%`, `_`) — même
  absence de garde que les trois usages existants de ce patron dans le
  dépôt ; pas une régression introduite par ce chantier.
- **Pas de garde `pageSize` côté serveur** (déjà vrai avant ce chantier,
  aucun changement) — un client pourrait demander une page immense ; hors
  périmètre, le shell n'utilise que `pageSize=50`.
