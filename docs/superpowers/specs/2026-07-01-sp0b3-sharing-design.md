# GeoStudio SP-0b.3 — Partage, permissions & portée

> Design / spec. Dernière tranche de SP-0b (suite de SP-0b.1/0b.2). Ajoute le partage des
> items (visibilité privé/public + partage à des groupes GeoNode existants avec un rôle) et
> un filtre de portée au catalogue. Entièrement front (via `item-client` → GeoNode) ;
> aucun changement du Builder Service.
>
> Date : 2026-07-01
> Statut : design validé — prêt pour `writing-plans`.
> Prérequis : SP-0b.1 (shell) et SP-0b.2 (item-client + ItemActions + CatalogPage) livrés.

---

## 1. Contexte et périmètre

SP-0b.2 a livré la gestion des items (créer/éditer/supprimer). SP-0b.3 ajoute la
**collaboration** :

- **Visibilité** d'un item : privé / public (anonyme peut voir).
- **Partage à des groupes GeoNode existants** avec un **rôle** : Lecteur (view/download) ou
  Éditeur (+ édition).
- **Filtre de portée** au catalogue : Tous / Mes éléments / Partagés avec moi / Publics.

**Hors périmètre :** administration des groupes (création, membres) — reste dans l'admin
GeoNode ; partage par utilisateur individuel ; matrice de permissions complète (4 niveaux
fins) ; permissions au niveau couche/champ.

Partage et groupes sont des concepts **GeoNode** : tout passe par `item-client` → GeoNode.
**Le Builder Service n'est pas modifié.**

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Modèle de partage | Visibilité (privé/public) + partage à des **groupes** avec rôle **Lecteur/Éditeur** |
| Groupes | **Consommés** (existants) ; pas d'admin de groupes |
| Catalogue | Filtre de **portée** : Tous / Mes éléments / Partagés avec moi / Publics |
| Backend | **Aucun changement** (GeoNode gère permissions et groupes) |

## 3. `item-client` — extensions (façade)

Types (dans `types.ts`) :
```ts
export type Group = { id: string; title: string };
export type ShareRole = "viewer" | "editor";
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole }[];
};
export type ItemScope = "all" | "mine" | "shared" | "public";
```

Méthodes ajoutées à `ItemClient` :
- `listGroups(): Promise<Group[]>` → `GET {geonodeUrl}/api/v2/groups` ; mappe vers `Group`.
- `getSharing(pk: string): Promise<Sharing>` → `GET {geonodeUrl}/api/v2/resources/{pk}/permissions` ; mappe le payload GeoNode vers `Sharing`.
- `setSharing(pk: string, sharing: Sharing): Promise<void>` → `PUT {geonodeUrl}/api/v2/resources/{pk}/permissions` ; mappe `Sharing` vers le payload GeoNode.
- `listItems` gagne `scope?: ItemScope` et `me?: string` dans `ListItemsParams`.

**Mapping visibilité / rôle ↔ GeoNode** (isolé dans la façade, mocké en test) :
- `public: true` ⇒ le groupe anonyme obtient `view_resourcebase` (+ download) ; `false` ⇒ retiré.
- rôle `viewer` ⇒ `view_resourcebase` + `download_resourcebase` ; `editor` ⇒ + `change_resourcebase`.
- Les clés exactes du payload permissions GeoNode dépendent de la version ; elles sont
  confinées à `item-client` et définies par les handlers MSW pour les tests.

**Mapping `scope` ↔ filtres GeoNode** (best-effort, isolé) :
- `mine` ⇒ `filter{owner.username.in}={me}`.
- `public` ⇒ filtre de visibilité publique (paramètre GeoNode de publication).
- `shared` ⇒ ressources visibles non possédées par `{me}` (l'API GeoNode ne renvoie déjà que
  les ressources accessibles ; la façade exclut celles dont `owner == me`).
- `all` (défaut) ⇒ aucun filtre de portée.

## 4. Hooks (TanStack Query)

- `useGroups()` → `useQuery(["groups"], listGroups)`.
- `useSharing(pk)` → `useQuery(["sharing", pk], () => getSharing(pk))`.
- `useSetSharing(pk)` → `useMutation(setSharing)` ; `onSuccess` invalide `["sharing", pk]` et
  `["items"]` (la visibilité peut changer l'appartenance à une portée).
- `useItems` étendu : la `queryKey` inclut déjà `params` (donc `scope`) — pas de changement de
  signature du hook, seulement du type `ListItemsParams`.

## 5. UI

- **`ShareDialog({ item, open, onClose })`** (réutilise `Dialog`) :
  - Toggle **Public** (case à cocher / switch).
  - Liste des groupes (via `useGroups`) : chaque groupe sélectionnable avec un rôle
    (Lecteur/Éditeur) ; l'état initial vient de `useSharing(item.pk)`.
  - **Enregistrer** → `useSetSharing` ; ferme au succès ; `role="alert"` en cas d'échec ;
    bouton désactivé pendant l'envoi.
  - États loading (chargement du partage/groupes) et erreur localisés.
- Entrée **« Partager »** ajoutée au menu `ItemActions` (à côté de Modifier/Miniature/Supprimer),
  ouvrant `ShareDialog`.
- **Filtre de portée** dans `CatalogPage` : un `<select>` (`aria-label="Portée"`) Tous / Mes
  éléments / Partagés avec moi / Publics ; passe `scope` (+ `me` depuis `useMe`) à `useItems`.
  Changer la portée remet la page à 1.

## 6. Flux de données

- **Partager** : ouvrir ShareDialog → `useSharing(pk)` + `useGroups()` chargent l'état →
  édition (public / groupes / rôles) → `useSetSharing` PUT → invalide `["sharing", pk]` +
  `["items"]`.
- **Filtrer** : changer la portée → `useItems({ scope, me, ... })` refait la requête (nouvelle
  `queryKey`) → grille mise à jour.

## 7. Gestion d'erreurs

- Échec de `setSharing` → `role="alert"` dans le dialog + le dialog reste ouvert ; pas de
  fermeture ; rollback non nécessaire (pas d'optimistic sur le partage).
- `getSharing`/`listGroups` en erreur → état d'erreur localisé dans le dialog + retry.
- Filtre portée : loading/empty/erreur gérés comme le catalogue existant.
- 401/403 → géré par le shell (SP-0b.1).

## 8. Stratégie de tests

- **Façade (MSW)** : `listGroups` (mapping) ; `getSharing`/`setSharing` (mapping Sharing↔
  payload GeoNode, aller-retour) ; `listItems` avec chaque `scope` (bons paramètres/filtre).
- **Hooks** : `useGroups`, `useSharing`, `useSetSharing` (invalidations `["sharing",pk]` +
  `["items"]`).
- **Composants (RTL)** : `ShareDialog` (toggle public, sélection groupe + rôle, submit,
  états loading/erreur) ; filtre portée du `CatalogPage` (change scope → requête).
- **E2E (Playwright, mock auth)** : partager un item à un groupe (ouvrir menu → Partager →
  cocher un groupe/rôle → Enregistrer) ; filtrer le catalogue par portée.

## 9. Phasage du plan d'implémentation

- **0b.3-a** : `item-client` (`listGroups`/`getSharing`/`setSharing`) + hooks
  (`useGroups`/`useSharing`/`useSetSharing`) + `ShareDialog` + entrée « Partager » dans
  `ItemActions`.
- **0b.3-b** : `ItemScope` + `listItems` scope + filtre portée dans `CatalogPage` + E2E.

Chaque phase est testable seule ; `writing-plans` produira d'abord le plan de **0b.3-a**.

## 10. Contraintes globales

- Front-only : aucune modification du Builder Service ; tout partage/groupe via `item-client` →
  GeoNode.
- Tout accès réseau via `item-client` ; aucun import GeoNode hors de la façade.
- `Item`/`ItemClient` étendus, pas de rupture des contrats existants.
- Pas de token en localStorage (inchangé).
- Les clés du payload permissions GeoNode et les paramètres de filtre de portée sont
  best-effort (confinés à la façade, définis par les mocks) ; à ajuster contre la version
  GeoNode réelle sans impacter les consommateurs.
