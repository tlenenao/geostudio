# Spec — page Paramètres détaillée, fusionnée avec Administration

Date : 2026-09-20. Statut : validé (brainstorming), prêt pour plan.

## 1. Contexte

La route `/settings` existe depuis SP-30/SP-33 (`shell/src/shell/routes.tsx:345`) mais
n'affiche qu'un message « bientôt disponible » (`SettingsComingSoonPage.tsx`). Le
domaine `settings` (`shell/src/auth/capabilities.ts`) est le seul des neuf domaines
à n'exiger aucun privilège : c'est un espace personnel, ouvert à tout utilisateur
authentifié — distinct du domaine `admin`, qui exige au moins un des six privilèges
`admin.*`.

Audit fait pendant le brainstorming : un seul réglage personnel existe côté API sans
UI pour le consommer — `GET/PATCH /v1/notifications/preference`
(`core/app/notifications/routes.py:106-125`), déjà câblé jusqu'aux hooks React
(`shell/src/api/domains/notifications.hooks.ts:49-64`,
`useNotificationPreference`/`useUpdateNotificationPreference`). Aucune autre table
« par utilisateur » n'existe dans le cœur en dehors de `notification_preferences`
(vérifié par grep sur les `ForeignKey("users.id")`) — pas de jeton personnel, pas de
fuseau horaire, pas de thème (le shell est mono-thème, mono-langue française).

Décision utilisateur : fusionner la navigation « Paramètres » et « Administration »
en une seule entrée, avec visibilité section par section selon les privilèges —
plutôt que deux entrées de menu dont l'une (Paramètres) était vide.

## 2. Ce qui change

### 2.1 Contenu de `/settings` (nouveau, remplace le message « bientôt disponible »)

Trois sections empilées dans la colonne centrale (`work`) d'un `TriptychLayout` :

1. **Profil** (lecture seule) — depuis `useMe()` (déjà chargé partout dans le
   shell) : nom d'utilisateur, email, prénom/nom, rôle (même badge que
   `AccountMenu.tsx`, réutiliser `roleLabel()`/`BUILT_IN_ROLE_LABEL_KEYS`), tenant.
   Aucune mutation : l'identité est gérée par Keycloak (OIDC), jamais éditée dans
   le cœur.
2. **Notifications** — groupe de 3 boutons radio (`ui/kit/Radio`) : Toutes /
   Échecs seulement / Aucune, branché sur `useNotificationPreference()` +
   `useUpdateNotificationPreference()`. État de sauvegarde (en cours / erreur)
   affiché en ligne, patron déjà utilisé par `UsersAdminPage.tsx` pour le
   changement de rôle par ligne (pending + erreur scopée à l'élément modifié).
3. **Compte** — lien externe `${config.oidcAuthority}/account` (nouvel onglet,
   `rel="noopener"`) vers la console de compte Keycloak (mot de passe, 2FA).
   **Masqué si `config.authMode === "mock"`** (pas de Keycloak réel en dev/E2E,
   cf. `shell/src/config.ts:34`) — le rendu sans la section est le comportement
   attendu, pas une erreur.

Pas d'auto-suppression de compte (RGPD) dans ce périmètre — exclu explicitement
pendant le brainstorming (action destructive, sujet distinct).

### 2.2 Fusion navigation Paramètres / Administration

**Avant** : deux entrées dans `DOMAINS` (`capabilities.ts`) — `admin` (visible si
≥1 privilège `admin.*`, atterrit sur le premier `/admin/*` accessible via
`ADMIN_DESTINATIONS`/`getDomainPath()`, `shell/src/shell/chrome/domainRoutes.ts:27-56`)
et `settings` (toujours visible, atterrit sur `/settings`, vide).

**Après** : une seule entrée, `settings` (id conservé — diff minimal, label déjà
« Paramètres »), toujours visible, atterrit **toujours** sur `/settings`. L'entrée
`admin` disparaît de `DOMAINS`, de `DomainId`, de `DOMAIN_PATHS`, et
`ADMIN_DESTINATIONS`/le cas spécial de `getDomainPath()` sont supprimés — plus
nécessaires : la destination est toujours `/settings`, il n'y a plus de « premier
`/admin/*` accessible » à deviner.

La colonne de navigation latérale, aujourd'hui `AdminNav.tsx` (réutilisée en
`browse` sur les 7 pages `/admin/*`), est **renommée `SettingsNav.tsx`** (son
périmètre change réellement : ce n'est plus une nav admin-only) et gagne une
entrée en tête, **toujours visible, sans privilège** :

```
Général          → /settings           (nouveau, toujours visible)
Extensions       → /admin/extensions   (admin.extensions.manage)
Infrastructure   → /admin/infrastructure (settings.instance.manage)
Rôles            → /admin/roles        (admin.roles.manage)
Utilisateurs     → /admin/users        (admin.users.manage)
Collections      → /admin/collections  (admin.collections.manage)
Moissonnage      → /admin/harvest      (admin.harvest.manage)
Conformité       → /admin/compliance   (compliance.manage)
```

Les 7 entrées admin gardent exactement le filtrage par privilège actuel
(`ADMIN_LINKS.filter(...)` dans `AdminNav.tsx:39`) — doctrine inchangée : un
privilège manquant MASQUE l'entrée. `SettingsNav` devient la colonne `browse` des
8 pages (les 7 pages `/admin/*` existantes + `/settings`), remplaçant le simple
lien « ← Catalogue » qu'utilisait la maquette initiale de `/settings`.

**Ce qui NE change PAS** : aucune URL `/admin/*` ne bouge, aucune route ne change
de garde de privilège, aucun privilège n'est ajouté ou retiré. C'est une fusion de
navigation, pas une refonte d'autorisation.

## 3. Fichiers touchés (vue d'ensemble, détail dans le plan)

- `shell/src/pages/SettingsPage.tsx` (nouveau, remplace `SettingsComingSoonPage.tsx`
  qui est supprimé) — 3 sections + `TriptychLayout`.
- `shell/src/shell/chrome/AdminNav.tsx` → renommé `SettingsNav.tsx` (+ son test) —
  ajout de l'entrée « Général ».
- Les 7 pages `/admin/*` : import mis à jour (`AdminNav` → `SettingsNav`), sinon
  inchangées.
- `shell/src/auth/capabilities.ts` — suppression de l'entrée `admin` dans
  `DOMAINS` et du littéral `"admin"` dans `DomainId`.
- `shell/src/shell/chrome/domainRoutes.ts` — suppression de `admin` dans
  `DOMAIN_PATHS`, suppression de `ADMIN_DESTINATIONS` et du cas spécial dans
  `getDomainPath()` (la fonction peut redevenir un simple accès à
  `DOMAIN_PATHS`, ou être inlinée — détail de plan).
- `shell/src/shell/routes.tsx` — la route `/settings` pointe vers `SettingsPage`.
- `shell/src/i18n/catalog.fr.ts` — nouvelles clés `settings.*` ; suppression de
  `domain.admin` et `comingSoon.settings` (orphelines après la fusion) ; nouvelle
  clé pour le libellé « Général » et l'`aria-label` de `SettingsNav`
  (`adminNav.label` → `settingsNav.label`).

## 4. Tests

- **Unitaire (Vitest)** : `SettingsPage.test.tsx` — rendu des 3 sections,
  mutation de préférence (succès + erreur), masquage de la section Compte en
  mode mock. `SettingsNav.test.tsx` (reprend `AdminNav.test.tsx`) — l'entrée
  Général est toujours visible, les 7 entrées admin gardent leur filtrage.
  `capabilities.test.ts`/`BottomNav.test.tsx`/`DomainBar.test.tsx` : mise à jour
  des fixtures qui référencent encore le domaine `admin` (une seule entrée de
  domaine visible désormais, quel que soit le profil).
- **E2E (Playwright)** : naviguer vers `/settings`, changer la préférence de
  notification, vérifier la persistance après reload ; depuis `/settings`,
  suivre l'entrée « Extensions » de `SettingsNav` (profil admin du mock E2E) et
  vérifier l'atterrissage sur `/admin/extensions` ; vérifier qu'un profil sans
  privilège admin ne voit que « Général » dans `SettingsNav`.

## 5. Hors périmètre

- Auto-suppression de compte (RGPD) en libre-service.
- Toute édition de profil (nom, email) — géré par Keycloak, hors du cœur.
- Renommage des URLs `/admin/*`.
- Nouveau réglage personnel non listé ci-dessus (aucun autre trouvé côté API à
  l'audit du 2026-09-20).

## 6. Points d'attention pour le plan

- `getDomainPath()` perd son seul cas spécial (`admin`) : vérifier qu'aucun autre
  appelant ne dépend de sa signature `(domain, profile)` avant de la simplifier —
  sinon la garder telle quelle (wrapper trivial) plutôt que forcer un
  changement de signature non nécessaire.
- Le renommage `AdminNav` → `SettingsNav` touche l'import de 7 pages existantes
  (`AdminExtensionsPage`, `AdminInfrastructurePage`, `RolesAdminPage`,
  `UsersAdminPage`, `CollectionsAdminPage`, `HarvestSourcesAdminPage`,
  `ComplianceAdminPage`) — un `grep -rn "AdminNav"` avant de clore la tâche pour
  s'assurer qu'aucune référence n'est oubliée (piège n°1 du dépôt : surface
  renommée à moitié).
- i18n : la CI bloque toute clé orpheline/manquante (SP-29a/SP-57a) — supprimer
  `domain.admin`/`comingSoon.settings` du catalogue en même temps que leur
  dernier usage, pas après.
