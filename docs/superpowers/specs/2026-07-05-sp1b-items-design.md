# GeoStudio SP-1b — Module items

> Design / spec. Deuxième sous-phase de SP-1. Le cœur devient propriétaire des
> **items** (titre, résumé, propriétaire, vignette, publication) — jusqu'ici
> cette donnée vit dans GeoNode, appelé en HTTP distant depuis `configs/routes.py`
> et directement depuis le shell (`itemClient.ts`).
>
> Date : 2026-07-05.
> Statut : design proposé.
> Prérequis : SP-1a (tenants/users/auth/audit/frontières) livré.

---

## 1. Contexte et périmètre

Aujourd'hui, un item est en réalité **deux ressources séparées reliées par une
convention** : une ressource GeoNode (titre, propriétaire, vignette, date,
`is_published`) et une `Config` dans le cœur (`item_id` = pk GeoNode, en
`String` nullable, sans contrainte FK réelle puisque GeoNode n'est pas la même
base). La création (`POST /configs`) appelle GeoNode en HTTP puis écrit la
config locale ; la suppression fait l'inverse. Le commentaire dans
`routes.py` documente déjà le risque assumé : *« si `delete_item` lève, la
config est préservée … le sens inverse est une fenêtre distribuée acceptée »*.

SP-1b élimine cette fenêtre : **item et config vivent dans la même base, la
même transaction.** Le cœur expose désormais une table `items` de premier
rang, et `configs.item_id` devient une vraie FK non nulle.

**Contenu.**
- Table `items` (titre, résumé, mots-clés, propriétaire, type, vignette,
  `is_published`).
- `configs.item_id` : FK réelle, non nulle, `ON DELETE CASCADE` côté DB en
  filet de sécurité (la suppression applicative reste explicite et transactionnelle,
  la contrainte est une seconde ligne de défense).
- Endpoints `GET/PATCH/DELETE /items/{id}`, `GET /items` (listing paginé,
  recherche, filtre par type) — alignés sur `ListItemsParams`/`ItemPage` du
  shell (`shell/src/api/types.ts`), pour que `CoreItemClient` (SP-1d) n'ait
  qu'à brancher, pas à réinventer un contrat.
- Vignettes (arbitrage A6) : upload et lecture **proxées par le cœur** (choix
  explicitement laissé libre par A6 pour les vignettes, à la différence des
  uploads de données qui iront en présigné S3 plus tard).
- Suppression transactionnelle config+item.

**Hors périmètre (SP-1c).** L'enforcement réel des scopes `shared`/`public` par
rapport aux groupes/partages : ces tables n'existent pas encore. Le scope
`shared` reste donc, pour cette sous-phase, un ensemble vide assumé (documenté
en §4) — corrigé dès que `item_shares` existe. Aucune UI ni endpoint
d'administration des groupes (SP-1c). Pas de branchement du shell sur ces
endpoints (SP-1d) : ils sont testés en isolation (pytest + `curl`), le shell
continue de parler à GeoNode jusqu'à la bascule.

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Relation item/config | **1:1, un item n'existe qu'au travers d'une config.** Pas de `POST /items` autonome — la création reste `POST /configs` (comme aujourd'hui), qui écrit désormais `items` + `configs` dans une seule transaction locale au lieu d'un appel GeoNode + une écriture locale. Un seul chemin de création, pas deux API qui peuvent diverger. |
| Vignettes (A6) | **Proxy cœur**, upload (`POST /items/{id}/thumbnail`, multipart) et lecture (`GET /items/{id}/thumbnail`) — bucket MinIO privé, le cœur applique les mêmes règles d'accès que pour la lecture de l'item (pas d'URL publique à durée de vie à gérer côté shell pour un objet aussi mineur qu'une vignette). |
| Propriétaire | `items.owner_id` → FK `users.id` (la table existe depuis SP-1a). Le contrat API expose toujours `owner: string` (username, comme aujourd'hui) — **aucun changement du type `Item` côté shell.** |
| Recherche (`q`) | `ILIKE` sur `title`/`abstract` — suffisant pour le volume v0 ; full-text search explicitement hors périmètre. |
| Pagination | offset/limit + `COUNT(*)` — même contrat (`page`, `pageSize`, `total`) que `ItemPage`. |
| Scope `shared` (temporaire) | Renvoie une page vide jusqu'à SP-1c (documenté, pas un bug — le shell ne branche cet endpoint qu'en SP-1d, aucune régression visible). |
| Audit | `item.create`, `item.update`, `item.delete`, `item.publish`/`item.unpublish` — actions distinctes pour rester lisibles dans `audit_log`, plutôt qu'un unique `item.update` générique. |

## 3. Modèle de données

```python
class Item(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)  # "app" | "dashboard" | "map"
    title: Mapped[str] = mapped_column(String, nullable=False)
    abstract: Mapped[str] = mapped_column(String, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)  # clé objet MinIO
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

Migration Alembic : crée `items` ; ajoute `configs.item_id` comme FK
(`ForeignKey("items.id", ondelete="CASCADE")`), NOT NULL. Les configs
existantes (dev) sont ré-associées à une ligne `items` reconstituée à partir des
données GeoNode disponibles à date de migration — sujet à un script de
migration ponctuel, cohérent avec A15 (pas de prod identifiée à migrer, c'est
du réamorçage de données de dev).

## 4. Endpoints

```
GET    /items?q=&type=&scope=&page=&pageSize=   → ItemPage (voir §2 pour scope)
GET    /items/{id}                              → Item | 404
PATCH  /items/{id}                               (title, abstract, keywords, isPublished)
DELETE /items/{id}                               → 204 (supprime item + config, une transaction)
POST   /items/{id}/thumbnail                     (multipart) → 204
GET    /items/{id}/thumbnail                     → bytes (proxy MinIO)
```

`POST /configs` (existant, inchangé côté contrat) : dans la même transaction,
insère `items` (title/owner/resourceType tirés de la requête) **puis**
`configs` avec `item_id` pointant sur la ligne fraîchement créée. Le
`GeoNodeItemClient` n'est plus appelé pour la création — `app/geonode.py` reste
présent mais orphelin jusqu'à sa suppression en SP-1d (pas de suppression
anticipée : SP-1b ne touche pas au périmètre GeoNode/démolition).

`DELETE /configs/{id}` et `DELETE /configs/by-item/{id}` : suppriment
`config_revisions` → `configs` → `items` dans une seule transaction locale ;
le commentaire de risque distribué dans `routes.py` disparaît (il n'y a plus
d'appel réseau dans ce chemin).

Scope query (`GET /items`), pour cette sous-phase :
- `all` : tous les items du tenant (pas encore filtré par visibilité réelle —
  SP-1c ajoute le filtre `can()`).
- `mine` : `owner_id = current_user.id`.
- `public` : `is_published = true`.
- `shared` : page vide (voir §2).

## 5. Gestion d'erreurs

- `GET/PATCH/DELETE /items/{id}` sur un id inconnu → `404` (jamais de détail
  qui permettrait de distinguer "n'existe pas" de "pas autorisé" — cohérent
  avec la discipline anti-énumération déjà en place pour l'accès anonyme aux
  items non publiés).
- `POST /items/{id}/thumbnail` : type MIME non image → `400` ; taille > seuil
  (2 Mo) → `413`.
- Suppression : si `items` a une FK entrante non prévue (aucune à ce stade),
  la transaction remonte une erreur explicite plutôt qu'un état partiel.

## 6. Stratégie de tests

- Pytest/SQLite : CRUD items, pagination, recherche `q`, filtre `type`,
  transaction de suppression (config + item disparaissent ensemble, y compris
  en cas d'erreur simulée sur l'un des deux DELETE → rollback complet, testé
  avec une exception injectée).
- Upload/lecture vignette : MinIO mocké (comme `httpx.MockTransport` pour
  GeoNode aujourd'hui) — pas de dépendance à un vrai MinIO en test unitaire.
- Audit : chaque action items produit la ligne attendue.
- Un test vérifie explicitement que `scope=shared` renvoie une page vide (pour
  que SP-1c parte d'un comportement documenté, pas d'un oubli).

## 7. Critères d'acceptation

- Créer un item via `POST /configs` puis le lire via `GET /items/{id}` renvoie
  les mêmes `title`/`owner`/`resourceType`.
- Supprimer un item supprime sa config et réciproquement (un seul point
  d'entrée de suppression, cohérent des deux côtés).
- `GET /items?scope=mine` ne renvoie que les items du user courant ;
  `scope=public` ne renvoie que les publiés.
- Une vignette uploadée est relisible via `GET /items/{id}/thumbnail`.
- Zéro appel réseau vers GeoNode dans le chemin de création/suppression d'item.

## 8. Risques

Le point délicat est la migration des configs existantes en dev (reconstituer
`items` pour des configs déjà créées avant cette migration) — acceptable car
volume de dev faible et A15 couvre déjà le cas général (repartir propre si
besoin). Le proxy de vignettes fait transiter les octets par Python : accepté
pour le volume (images de quelques centaines de Ko), à réévaluer si des
vignettes lourdes apparaissent.
