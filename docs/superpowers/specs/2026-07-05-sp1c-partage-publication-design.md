# GeoStudio SP-1c — Partage & publication

> Design / spec. Troisième sous-phase de SP-1. Apporte le modèle
> privé/groupe/public (arbitrages A1/A2) et la publication anonyme au cœur.
> C'est le morceau à tester le plus durement de toute la feuille de route : il
> s'agit de sécurité, sur un produit public.
>
> Date : 2026-07-05.
> Statut : design proposé.
> Prérequis : SP-1a (auth/audit), SP-1b (table `items`) livrés.

---

## 1. Contexte et périmètre

Le shell a déjà toute l'UX de partage (`ShareDialog.tsx`) et son contrat côté
type (`Sharing = { public: boolean, groups: { groupId, role }[] }`,
`ShareRole = "viewer" | "editor"`) — actuellement servie par GeoNode. SP-1c
reproduit ce modèle dans le cœur : c'est le modèle GeoNode actuel (recommandation
A2), donc le moindre mouvement pour cette UX qui reste inchangée.

**Contenu.**
- Tables `groups`, `group_members`, `item_shares`.
- `can(user, action, object)` — fonction unique d'autorisation (A1), utilisée
  par toutes les routes touchant à un item.
- Enforcement des scopes en **lecture et en écriture** (`GET /items` filtré
  réellement par visibilité ; `PATCH`/`DELETE` refusés si non autorisé).
- `is_published` + accès anonyme en runtime : route publique, item publié
  uniquement, 404 sinon.
- Chaque partage/publication écrit dans `audit_log`.

**Hors périmètre.** UI d'administration des groupes (v0 : création de groupes
via un endpoint simple, pas d'écran dédié — les groupes de démo sont créés par
fixtures/seed, une UI minimale peut suivre en dehors de SP-1 si un besoin réel
apparaît). RLS PostGIS (A3, différée à SP-3 — ceci est de l'autorisation
applicative sur les objets `item`, pas sur des lignes de données métier).
Héritage hiérarchique de dossiers/espaces (hors modèle v0). Branchement du
shell sur ces endpoints (SP-1d).

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Moteur d'autorisation (A1) | Tables maison + `can()` in-process, point d'entrée unique. Remplaçable par OpenFGA plus tard sans toucher les routes, tant que `can()` reste la seule porte. |
| Source des groupes (A2) | Gérés par le cœur (pas de claims Keycloak) — indépendant de l'IdP, modèle GeoNode actuel. |
| Modélisation du partage | `items.is_public: bool` (colonne plate — le toggle "public" du `ShareDialog` n'a pas de rôle associé, toujours lecture) + table `item_shares` (`item_id`, `group_id`, `role`) pour les partages de groupe. Pas de ligne "groupe magique" pour le public : deux mécanismes distincts, qui correspondent exactement aux deux champs du type `Sharing`. |
| Rôle du partage public | Toujours lecture seule (le toggle n'a pas de sélecteur de rôle dans l'UX existante) — un item public n'est jamais éditable par un tiers via ce seul mécanisme. |
| 404 vs 403 | Item invisible en lecture (ni owner, ni groupe, ni public, ni publié) → **404** (anti-énumération). Item visible en lecture mais action refusée (ex. viewer qui tente un `PATCH`) → **403** (l'existence est déjà connue, pas de fuite supplémentaire). |
| Publication vs partage public | Deux notions distinctes et non substituables : `is_public` = visible dans le catalogue par tous les utilisateurs **authentifiés** du tenant ; `is_published` (déjà en base depuis SP-1b) = accessible **anonymement** en exécution (runtime), sans session. Publier n'implique pas de rendre public dans le catalogue, et réciproquement. |
| `scope=public` (catalogue) | Filtre sur `is_published`, **pas** sur `is_public` — comportement déjà celui du shell aujourd'hui contre GeoNode (`filter{is_published}`), repris à l'identique. |
| `scope=shared` | Items où l'utilisateur a un accès via un groupe (`item_shares` + `group_members`), à l'exclusion des items dont il est propriétaire. Remplace l'actuel filtrage client approximatif (`items.filter(i => i.owner !== me)` dans `itemClient.ts`) par une vraie requête serveur. |
| `scope=all` | Tout ce que `can(user, "read", item)` autorise : propriétaire, partagé (groupe ou public), ou publié. |

## 3. Modèle de données

```python
class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime]

class GroupMember(Base):
    __tablename__ = "group_members"
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)

class ItemShare(Base):
    __tablename__ = "item_shares"
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "viewer" | "editor"
```

Migration : crée les trois tables ; ajoute `items.is_public: bool default false`.

## 4. `can(user, action, object)`

```python
def can(user: User, action: Literal["read", "write", "delete", "share"], item: Item) -> bool:
    if item.owner_id == user.id:
        return True
    if action == "read":
        if item.is_public or item.is_published:
            return True
        return _has_group_role(user, item, roles={"viewer", "editor"})
    if action in ("write", "delete", "share"):
        return _has_group_role(user, item, roles={"editor"})
    return False
```

`_has_group_role` : jointure `item_shares` ⋈ `group_members` sur
`(item_id=item.id, user_id=user.id)`, vrai si une ligne a un rôle dans
l'ensemble demandé. `share` (modifier le partage lui-même) exige `editor` au
même titre que `write` — v0 ne distingue pas un rôle "admin" séparé, cohérent
avec le modèle GeoNode repris.

Toutes les routes `items`/`configs` qui touchent à un item existant appellent
`can()` avant d'agir ; `GET /items` (listing) traduit le `scope` demandé en
prédicat SQL équivalent (pas un filtre en mémoire après coup — pour rester
correct sur la pagination, contrairement au comportement actuel côté shell).

## 5. Endpoints

```
GET  /items/{id}/sharing         → Sharing  (403 si can(read) faux → en pratique 404, voir §2)
PUT  /items/{id}/sharing         (Sharing)  → 204, exige can(user, "share", item)
GET  /groups                     → Group[]  (tous les groupes du tenant — pas de notion privée de groupe en v0)
POST /groups                     (name)     → Group  (réservé à un rôle admin — v0 : tout utilisateur authentifié, resserré si besoin réel émerge)
POST /groups/{id}/members        (userId)   → 204

GET  /public/items/{id}          → Item        (sans auth, 404 si !is_published)
GET  /public/configs/by-item/{id} → ConfigRead (sans auth, 404 si !is_published — sert le runtime anonyme)
```

Le routeur `/public/*` ne dépend pas de `get_current_user` — c'est la seule
porte d'entrée anonyme du cœur, elle vérifie `is_published` explicitement
plutôt que de réutiliser `can()` (qui suppose toujours un `User`).

## 6. Gestion d'erreurs

- `GET /items/{id}` sans droit de lecture → `404` (voir règle §2).
- `PATCH`/`DELETE /items/{id}` avec droit de lecture mais pas d'écriture →
  `403`.
- `PUT /items/{id}/sharing` par un non-propriétaire/non-éditeur → `403`.
- `GET /public/items/{id}` sur un item non publié → `404`, identique que
  l'item existe et ne soit pas publié, ou qu'il n'existe pas du tout (même
  logique anti-énumération, appliquée ici à l'anonyme).
- `POST /groups/{id}/members` avec un `userId` d'un autre tenant → `404`
  (jamais de fuite d'existence cross-tenant).

## 7. Stratégie de tests

- Matrice `can()` en pytest pur (sans HTTP) : propriétaire/groupe
  viewer/groupe editor/public/publié/aucun, croisée avec les quatre actions —
  c'est la partie à couvrir le plus densément (commentaire du risque §9 de la
  feuille de route).
- `GET /items?scope=...` : un jeu de fixtures (3 users, 2 groupes, items
  owned/shared/public/published/invisible) vérifie que chaque scope renvoie
  exactement l'ensemble attendu, y compris la pagination.
- `GET /public/items/{id}` : testé à la fois publié (200, aucune auth requise)
  et non publié (404) et inexistant (404, réponse indiscernable).
- Test de régression explicite : un item partagé à un groupe est visible par
  ses membres et invisible aux autres (repris tel quel du critère
  d'acceptation SP-1 de la feuille de route).

## 8. Critères d'acceptation

- Un item partagé à un groupe est visible par ses membres et invisible aux
  autres.
- Un item publié est accessible anonymement en runtime ; un non publié renvoie
  404.
- Toute création/modification de partage apparaît dans `audit_log`
  (`item.share`).
- `scope=shared` renvoie un ensemble correct et paginé (pas une approximation
  côté client comme aujourd'hui).

## 9. Risques

Le plus gros risque de sécurité de toute la feuille de route : un bug dans
`can()` expose des items privés. Mitigé par la matrice de tests exhaustive
(§7) et par le fait que `can()` est la **seule** porte — aucune route ne doit
implémenter sa propre logique de visibilité en parallèle. Revue de code dédiée
recommandée avant merge sur `main`.
