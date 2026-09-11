# GAP-19 — SDK d'embedding : intégrer une App/Dashboard dans un site tiers

**Date** : 2026-09-06
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (brainstorm dédié, ferme GAP-19 —
`docs/revue/2026-09-04-analyse-gaps.md`)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-19),
`docs/superpowers/specs/2026-09-05-sp54-itemclient-api-design.md` (liens de
partage à échéance, SP-54, mécanisme réutilisé ici), `CLAUDE.md` §« Pièges
récurrents » (n°1, n°3, n°4, n°5, n°11, n°12).

**Portée de ce document** : donner à un tiers le moyen d'intégrer une
App/Dashboard GeoStudio entière dans son propre site, en lecture seule, avec
une authentification déléguée par jeton invité — à la manière du « guest
token » de Metabase/Superset ou de l'embed Felt. Aucun code n'est modifié
ici — c'est le texte qui deviendra le plan.

---

## 1. Contexte

GeoStudio n'a aujourd'hui aucun moyen de faire vivre une App/Dashboard hors
de son propre shell authentifié : un tiers qui veut afficher une carte ou un
tableau de bord GeoStudio sur son propre site n'a que deux options,
toutes les deux mauvaises — donner un vrai compte OIDC au visiteur, ou
publier l'App/l'item comme public (`isPublished`/`isPublic`), ce qui
l'expose alors à *tout le monde*, pas seulement au site intégrateur. Le
lien de partage à échéance livré par SP-54 (GAP-12) résout un problème
voisin mais différent : `GET /share-links/{token}` (`core/app/items/
routes.py:340-379`) est une résolution **publique** qui ne renvoie que des
**métadonnées** (`ResolvedShareLink{itemId, title, resourceType,
expiresAt}`) — jamais la config, jamais les données. C'est exactement le
point où Metabase (SDK React + guest token JWT signé côté serveur),
Superset (`embedded-sdk` + guest token) et Felt (`<iframe>` + jeton
d'embed) vont plus loin : leur jeton invité porte, en plus de l'identité de
la ressource, une autorisation de lecture sur les données qu'elle
consomme.

Ce chantier ferme GAP-19 en dépassant `resolve_share_link_route` : le même
jeton HMAC de lien de partage (SP-54, `core/app/sharing/share_links.py`)
devient un jeton invité qui autorise, en plus de la lecture de l'item
lui-même, la lecture des collections que sa config référence comme sources
de données — même privées — pour la durée d'une requête qui le porte.
Unité d'intégration : une App/Dashboard **entière**, rendue en lecture
seule dans un `<iframe>`. Ni l'embedding par widget individuel, ni un SDK
JS chargé dynamiquement, ne sont dans ce périmètre (§6).

## 2. État vérifié du code (avant toute décision)

### 2.1 Le mécanisme de jeton existant (SP-54)

`core/app/sharing/share_links.py` : `mint_share_link_token(*, share_link_id,
tenant_id, item_id, ttl_seconds)` produit un JWT HS256 signé avec
`CORE_SHARE_LINK_TOKEN_SECRET`, claims `{typ: "share_link", share_link_id,
tenant_id, item_id, iat, exp}`, TTL bornée à 30 jours
(`_MAX_TTL_SECONDS`). `decode_share_link_token(token)` revalide `typ` et les
claims requis, lève `ShareLinkTokenError` (jamais un 500) sur tout jeton
invalide/expiré/mal typé.

`core/app/sharing/repository.py::get_active_share_link(session, *,
tenant_id, link_id)` — `None` si la ligne `ShareLink` est absente, révoquée
(`revoked_at`), ou expirée par la colonne (`expires_at`) — **double
vérification** avec le TTL porté par le jeton lui-même : une révocation
manuelle prime sur un jeton pas encore expiré.

`core/app/items/routes.py:340-379::resolve_share_link_route` — `GET
/share-links/{token}`, **aucune** `Depends(get_current_user)` : décode,
vérifie la révocation, résout l'item (`repo.get_item(..., current_user_id=
None)`), écrit un audit `share_link.access` (`actor_kind="anonymous"`), et
renvoie **uniquement** `ResolvedShareLink{itemId, title, resourceType,
expiresAt}` — jamais une config, jamais une donnée. C'est le point que ce
chantier dépasse, sans le modifier : cette route reste utile telle quelle
pour donner à la page d'embed l'`itemId`/le titre avant de charger quoi que
ce soit d'autre (§4.5).

### 2.2 La forme réelle d'une référence de collection dans une config — écart avec l'hypothèse du brainstorm

Le brief de ce chantier supposait des `DataSource` portant un champ
`source == "collection"`. **Ce champ n'existe pas sur `DataSource`** — il
existe sur `DatasetPayload`/`DatasetConfig` (la config d'un item de type
`dataset`), un objet différent. La forme réelle, vérifiée dans
`core/app/configs/schemas.py` et son miroir `shell/src/api/types.ts:737` :

```python
class DataSource(BaseModel):        # core/app/configs/schemas.py:14-19
    id: str
    type: str          # "features" | "static" | "statistics" (shell only ;
                        # non contraint côté cœur, cf. note ci-dessous)
    service: str        # toujours "core" en pratique (shell/src/builder/*)
    layer: str          # collectionId — SAUF si datasetId est posé (résolu
                        # automatiquement à la volée côté shell)
    query: dict
```

```ts
// shell/src/api/types.ts:737-744 — sur-ensemble réel de la forme cœur
export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string;      // résolu automatiquement si datasetId est présent
  datasetId?: string;  // référence un item "dataset" séparé (kind="dataset")
  query: Record<string, unknown>;
};
```

`BuilderConfig.dataSources: list[DataSource]` (`core/app/configs/
schemas.py:434`) est une liste **plate** au niveau racine de la config —
vérifié en lisant tous les widgets qui consomment une `DataSource`
(`chart.tsx`, `indicator.tsx`, `mapWidget.tsx`, `form.tsx`,
`sliderFilter.tsx`, `selectFilter.tsx`, `datasetCard.tsx`,
`ExplorerDrawer.tsx`) : **tous** résolvent leur collection via
`dataSources.find(d => d.id === props.dataSourceId).layer` (ou l'équivalent
via `DataContext`/`ctx.data?.layer`), jamais via une structure imbriquée
propre au widget. En particulier, le widget carte d'une App/Dashboard
(`mapWidget.tsx:325-346`) **construit ses couches à la volée depuis
`dataSources`** — il ne persiste aucun `MapConfig.layers[].collectionId`
propre. Conséquence directe et vérifiée (pas supposée, piège CLAUDE.md
n°12) : pour un item `kind in ("app", "dashboard")`, **la liste plate
`config.dataSources` est la source unique et suffisante** des références de
collection — pas besoin de descendre dans `layout.items[].props`,
`pages[].layout`, ni dans un widget conteneur (Onglets) : ces derniers ne
portent jamais leur propre `DataSource`, ils référencent toujours un id de
la liste plate. `MapConfig.layers[].collectionId` (`core/app/configs/
schemas.py:90-112`) existe bien dans le schéma, mais n'est réellement
peuplé et consommé que pour un item `kind == "map"` autonome — hors
périmètre de ce chantier (§1, §6).

**Deuxième niveau, non anticipé par le brief** : `DataSource.datasetId`
référence un item **séparé** de type `dataset` — pas une collection
directement. `shell/src/api/base.ts::resolveDataset(pk)` va chercher
`GET /configs/by-item/{pk}` (la config du *dataset*), lit
`config.dataset.collectionId` (si `source == "collection"`) et met le
résultat en cache 5 minutes (`DATASET_CACHE_TTL_MS`, GAP-65/SP-54). Un
widget lié par `datasetId` a donc besoin, pour se résoudre, de **deux**
autorisations en chaîne : lire la config de l'item `dataset` référencé
(une deuxième route `/configs/by-item/{id}`, sur un `item_id` différent de
l'item embarqué), *puis* lire la collection que cette config désigne. Un
dataset `source == "arcgis"` (`arcgisItemId` au lieu de `collectionId`)
référence une ressource externe moissonnée (SP-12k) — hors modèle
collection, donc hors scope d'autorisation invité de ce chantier (documenté
§6, pas silencieusement ignoré : un widget bâti sur un dataset ArcGIS dans
une App embarquée continuera de fonctionner exactement comme aujourd'hui
pour un visiteur anonyme, sans changement, puisque l'API ArcGIS FS
moissonnée est déjà servie par un chemin distinct — `GET /datasets/{id}/
arcgis/items` — non concerné par ce chantier).

### 2.3 Chokepoint déjà unique côté lecture de collection

`core/app/collections/routes.py:181-213::get_readable_collection(session,
user, collection_id, *, can_manage_collections=False)` est **le** point de
passage déjà partagé par toutes les routes de lecture scoped-collection
identifiées : `list_features`/`get_single_feature`/`aggregate_features`
(`app/features/routes.py`), `get_collection_tile` (`app/features/
tiles.py`), `get_collection`/`get_collection_schema`
(`app/collections/routes.py`), `list_attachments_route`/
`read_attachment_file` (`app/attachments/routes.py`). Ce n'est pas une
liste fermée supposée : c'est le résultat d'un `grep -rn
"get_readable_collection"` sur `core/app`. Étendre l'autorisation invité en
un seul point (cette fonction), plutôt qu'à chacun des huit call sites, est
donc le design qui referme le moins de surface à la fois — et évite de
recréer la classe de défaut « même règle dupliquée à N endroits » que SP-43
existe pour éliminer.

`export_collection_aggregate`/`export_collection_items` (`app/features/
routes.py`) et `POST /analytics/sql` passent par
`Depends(get_current_user)` **obligatoire**, jamais `_optional` : ils
restent **hors périmètre**, volontairement (§6) — un visiteur invité peut
voir les données rendues par les widgets, pas les télécharger en vrac ni
lancer du SQL libre. C'est un rétrécissement délibéré au-delà de la seule
mention « lecture seule » du brief : l'export/SQL Lab sont des surfaces
d'exfiltration bien plus larges qu'un rendu de widget, et aucun brainstorm
ne les a explicitement demandées.

### 2.4 Le contrat de couches (`core/pyproject.toml::[[tool.importlinter.
contracts]]`) contraint où vit la nouvelle logique — écart important avec
le libellé du brief

Ordre vérifié (extrait pertinent, du plus haut au plus bas — un module ne
peut importer que ce qui est *en dessous* de lui) :

```
... app.features > app.attachments > app.collections > app.configs
    > app.quotas > app.extensions > app.items > app.sharing > ...
```

Le brief suggérait une fonction `authorize_guest_collection_read(session,
*, share_link_claims, collection_id)` vivant implicitement du côté
`app.sharing` (« chemin parallèle à `can()` », qui vit dans
`app.sharing.authorization`). **Ce n'est pas possible tel quel** :
résoudre la portée d'un jeton invité exige de lire `BuilderConfig`/
`DataSource` (`app.configs.schemas`) et `get_config_by_item`
(`app.configs.repository`) — tous les deux dans `app.configs`, qui est
**au-dessus** d'`app.sharing` dans ce contrat. `app.sharing` ne peut pas
importer `app.configs` (sens interdit), donc la résolution de portée ne
peut **pas** vivre dans `app.sharing`.

Le seul emplacement qui peut légitimement importer à la fois
`app.configs.schemas/repository` (même paquet) et `app.sharing.
share_links/repository` (en dessous, donc importable) est **`app.configs`
lui-même** — précédent direct : `app.configs.bbox` (SP-55, GAP-06) existe
déjà exactement pour cette raison (« la même classe de cycle », son propre
commentaire dans `pyproject.toml:290-302`). Ce chantier suit donc le même
patron : nouveau sous-module `app/configs/guest_access.py`, consommé par
tout ce qui est au-dessus de `app.configs` dans le contrat
(`app.features`, `app.attachments`, `app.collections`, et `app.configs`
lui-même) — **aucune exemption `ignore_imports` nouvelle n'est nécessaire**,
contrairement à `app.configs.bbox` : `app.configs` important
`app.items`/`app.sharing` est déjà la direction normale du contrat
(`app.configs.routes` importe déjà `app.items.repository`/
`app.sharing.authorization.can`).

**Conséquence assumée, documentée, pas corrigée** : `app.extensions`
(`GET /extensions`, liste les extensions actives — SP-8/SP-42) est **en
dessous** d'`app.configs` dans ce contrat (`app.configs > app.quotas >
app.extensions`) et ne peut donc **pas** importer `app.configs.
guest_access`. `list_extensions` (`app/extensions/routes.py:98-109`)
résout aujourd'hui le tenant anonyme via `get_or_create_default_tenant`
(même patron que `get_readable_collection` avant ce chantier) — pour un
déploiement mono-tenant (le cas réel de toute instance GeoStudio à ce
jour), c'est déjà correct par construction. Pour un futur déploiement
multi-tenant, un widget d'extension personnalisée dans une App embarquée
verrait la liste d'extensions actives du tenant *par défaut*, pas
nécessairement celle du tenant réel de l'item partagé — un widget
d'extension non enregistré échoue silencieusement au rendu (comportement
existant de `WidgetHost`, non modifié ici). **Restructurer le contrat de
couches pour lever cette limitation est hors périmètre de ce chantier** —
GAP-19 ne le demande pas, et le corriger correctement impliquerait de
déplacer `app.extensions` au-dessus d'`app.configs` (ou de sortir la
résolution de tenant invité dans un module encore plus bas, réutilisable
partout, ce qui rouvrirait la question pour d'autres cas similaires
non recensés). Noté explicitement, pas swept sous le tapis (piège
CLAUDE.md n°3/12).

### 2.5 Transport du jeton côté shell — le mécanisme existe déjà pour un autre besoin

Le brief laissait ouvert « query param ou header ». Deux contraintes
tranchent :

1. **Le canal ne doit jamais toucher `Authorization`** : ce header est déjà
   surchargé par trois branches mutuellement exclusives dans
   `core/app/auth/dependency.py::get_current_user` (mock / jeton d'export /
   OIDC). En mode `CORE_AUTH_MODE=mock` (dev/test), **tout** Bearer non vide
   est accepté sans validation de contenu et renvoie un utilisateur mock
   **admin** (`get_current_user:172-183`) — poser le jeton invité sur
   `Authorization` le ferait donc passer pour un admin authentifié en mode
   mock, un contournement de sécurité pur. En mode OIDC réel, un jeton
   HS256 échouerait la vérification RS256 et lèverait une `HTTPException`
   non rattrapée par `get_current_user_optional` (qui ne fait *pas* de
   `try/except` autour de son appel à `get_current_user` — `app/auth/
   dependency.py:230-238`), cassant net toute route qui l'utilise déjà en
   mode anonyme. Le jeton invité doit donc voyager sur un **header dédié**,
   jamais sur `Authorization`.
2. **MapLibre GL (tuiles vectorielles) et les fetches manuels
   d'attachments** ont déjà exactement ce besoin résolu pour le jeton OIDC :
   `shell/src/map/MapView.tsx:1099-1103` utilise `transformRequest` pour
   injecter `Authorization: Bearer <token>` sur chaque requête de tuile
   MapLibre (pas de balise `<img>` brute nulle part dans ce chemin — vérifié
   par grep), et les lectures d'attachment (`MapView.tsx:1356-1390`) font un
   `fetch()` manuel avec le même en-tête. `getAuthToken?()`/`getCoreUrl?()`
   (`shell/src/api/types.ts:644-649`, déjà optionnels sur `ItemClient`,
   déjà threadés jusqu'à `MapView` via `mapWidget.tsx:358-359`) sont
   exactement le patron à dupliquer pour un second en-tête —
   `getShareLinkToken?()` — plutôt que d'inventer un mécanisme de query
   param à recâbler dans chaque constructeur d'URL (`buildFeaturesUrl`,
   `MapView`, `attachmentFileUrl`…).

Un en-tête HTTP dédié (`X-Share-Link-Token`) est donc la conception
retenue : câblable au même endroit que `Authorization` (`transformRequest`,
`fetch()` manuels, `request()`/`fetchGeoJsonFeatures()` de `base.ts`), sans
jamais interagir avec `get_current_user`/`get_current_user_optional`
(chemin réellement parallèle, conforme à la décision du brief), et sans
fuiter dans une URL (logs serveur, `Referer` d'un lien externe cliqué
depuis un popup).

### 2.6 `frame-ancestors`/`X-Frame-Options` — absent aujourd'hui, à surveiller

Vérifié par grep sur `docker-compose.yml`, `docker-compose.prod.yml`,
`shell/nginx.conf`, `core/app/security/*.py` : **aucun** en-tête
`X-Frame-Options` ni directive CSP `frame-ancestors` n'est actuellement
émis nulle part dans ce dépôt — la page `/embed/{token}` sera donc
intégrable en `<iframe>` sans changement. Ce n'est **pas** une garantie
pérenne : SP-48 (CSP enforcing) et SP-26 (durcissement pré-v0.1) ont
démontré un appétit répété pour ce genre de durcissement, et un futur
ajout de `frame-ancestors 'self'` (une pratique standard par ailleurs
recommandée) casserait silencieusement l'embedding sans que la personne
qui l'ajoute sache que cette page en dépend. Documenté ci-dessous comme
critère d'acceptation (§5.9) et comme risque à surveiller (§7) — jamais
« corrigé » ici puisqu'il n'y a rien à corriger aujourd'hui, seulement un
non-régression à graver.

## 3. Décisions (reformulées, avec justification issue du code réel)

1. **Unité d'intégration : une App/Dashboard entière** — `kind in ("app",
   "dashboard")` uniquement. Un jeton de lien de partage dont l'item
   racine n'est pas de l'un de ces deux kinds ne donne accès qu'aux
   métadonnées déjà servies aujourd'hui par `resolve_share_link_route`
   (comportement inchangé) — la page `/embed/{token}` affiche un message
   explicite (« ce type de contenu ne peut pas être intégré ») plutôt
   qu'un rendu vide ou une erreur générique. Pas de site (`kind ==
   "site"`) ni de map/dataset/bookmark/pipeline/alert/report autonomes
   dans ce chantier (§6) — leur `MapConfig.layers[].collectionId` propre
   (kind `map`) n'a jamais été vérifié comme faisant partie de ce modèle
   d'extraction (§2.2) et l'étendre y ajouterait un deuxième chemin
   d'extraction non prouvé.

2. **Réutilisation intégrale du mécanisme `share_link`** (aucun nouveau
   type de jeton, aucune nouvelle table) : `mint_share_link_token`/
   `decode_share_link_token`/`ShareLink`/`get_active_share_link`
   inchangés. Le jeton invité **est** le jeton de lien de partage — sa
   portée étendue (collections référencées) est calculée **à la
   résolution**, jamais stockée sur `ShareLink` ni encodée dans le JWT
   lui-même (qui reste `{share_link_id, tenant_id, item_id}` — cf. §4.1
   pour pourquoi recalculer à chaque requête plutôt que mettre en cache
   côté jeton).

3. **Portée = collections référencées par les `dataSources` de l'item
   racine**, résolue transitivement à travers tout `datasetId` (§2.2),
   jamais au-delà (pas de récursion à un 3ᵉ niveau — le schéma
   `DatasetPayload` ne porte pas lui-même de `datasetId`, vérifié). Cette
   portée est calculée pour la **durée d'une requête HTTP**, jamais
   persistée côté serveur au-delà (pas de session, pas de cache
   inter-requêtes côté cœur — un cache introduirait un problème de
   fraîcheur si la config de l'App change après l'émission du jeton ;
   voir §4.1 pour le coût mesuré de ce choix).

4. **Chemin d'autorisation parallèle, jamais une modification de `can()`/
   `decide()`/`get_current_user`** : nouveau module `app/configs/
   guest_access.py` (§2.4, §4.1), consommé additivement (paramètre
   optionnel de plus, jamais un remplacement) par chaque route de lecture
   concernée.

5. **Shell : nouvelle route publique `/embed/:token`**, hors
   `<RequireAuth>`/`<ProtectedLayout>` (siège au même niveau que
   `/sites/:slug`/`/public/items/:pk` dans `shell/src/shell/routes.tsx:
   428-431`), réutilisant `AppRenderer(config, mode="runtime")` sans le
   chrome du shell (pas de `TopBar`, pas de panneau d'actions
   export/enregistrer-la-vue — ces actions exigent un vrai utilisateur,
   cf. §6).

6. **`ShareForm.tsx` gagne une section « Intégrer »** à côté de la section
   liens de partage à échéance existante (`ShareLinksPanel`,
   `shell/src/shell/ShareForm.tsx:24-121`), réutilisant le **même** appel
   `useCreateShareLink`/`POST /items/{id}/share-links` — pas de nouvelle
   mutation. Seul changement de contrat : `ShareLinkCreated` gagne un
   champ `token: str` (en plus de `url`/`expiresAt` existants) — le jeton
   brut n'était jusqu'ici jamais renvoyé isolément (`url` l'encode déjà en
   toute fin de chemin, mais pointe vers le **cœur** —
   `CORE_BASE_URL`, `core/app/items/routes.py:291-297` — jamais vers le
   **shell**, qui est l'origine dont `/embed/{token}` a besoin). Extraire
   le token depuis `url` par découpage de chaîne côté shell serait fragile
   et couplerait le shell à un détail d'implémentation de la route cœur ;
   renvoyer le token explicitement est un changement de schéma mineur,
   additif, sans rien retirer.

## 4. Architecture

### 4.1 `app/configs/guest_access.py` (nouveau module)

```python
@dataclass(frozen=True)
class GuestActor:
    tenant_id: str
    item_id: str                       # item racine (celui du lien de partage)
    share_link_id: str
    allowed_item_ids: frozenset[str]    # item_id racine + tout datasetId référencé
    allowed_collection_ids: frozenset[str]

def resolve_guest_scope(session: Session, claims: ShareLinkTokenClaims) -> GuestActor | None:
    """None si l'item racine n'existe plus dans ce tenant, si sa config est
    absente, ou si son kind n'est pas dans ("app", "dashboard") (décision 1)."""
    facts = items_repo.get_access_facts(session, tenant_id=claims.tenant_id, item_id=claims.item_id)
    if facts is None:
        return None
    root = configs_repo.get_config_by_item(session, claims.item_id)
    if root is None or root.kind not in ("app", "dashboard"):
        return None

    allowed_item_ids = {claims.item_id}
    allowed_collection_ids: set[str] = set()
    for ds in root.config.dataSources:
        if ds.type == "static":
            continue
        if ds.datasetId:
            # Défense en profondeur : un datasetId doit appartenir au MÊME
            # tenant que l'item racine — get_config_by_item ne filtre pas
            # par tenant_id (cf. app/configs/repository.py:87-94), donc ce
            # contrôle n'est PAS redondant.
            ds_facts = items_repo.get_access_facts(
                session, tenant_id=claims.tenant_id, item_id=ds.datasetId
            )
            if ds_facts is None:
                continue
            allowed_item_ids.add(ds.datasetId)
            ds_config = configs_repo.get_config_by_item(session, ds.datasetId)
            if (
                ds_config is not None
                and ds_config.kind == "dataset"
                and ds_config.config.dataset is not None
                and ds_config.config.dataset.source == "collection"
                and ds_config.config.dataset.collectionId
            ):
                allowed_collection_ids.add(ds_config.config.dataset.collectionId)
            # source == "arcgis" : hors modèle collection, ignoré (§2.2/§6).
        elif ds.layer:
            allowed_collection_ids.add(ds.layer)

    return GuestActor(
        tenant_id=claims.tenant_id,
        item_id=claims.item_id,
        share_link_id=claims.share_link_id,
        allowed_item_ids=frozenset(allowed_item_ids),
        allowed_collection_ids=frozenset(allowed_collection_ids),
    )


def authorize_guest_item_read(guest: GuestActor | None, item_id: str) -> bool:
    return guest is not None and item_id in guest.allowed_item_ids


def authorize_guest_collection_read(guest: GuestActor | None, collection_id: str) -> bool:
    return guest is not None and collection_id in guest.allowed_collection_ids


def get_share_link_actor(
    x_share_link_token: str | None = Header(default=None, alias="X-Share-Link-Token"),
    session: Session = Depends(get_session),
) -> GuestActor | None:
    """Dépendance FastAPI additive — ne lève JAMAIS : un jeton absent, mal
    formé, révoqué ou expiré renvoie None, exactement comme
    get_current_user_optional renvoie None sans Authorization. La route
    appelante retombe alors sur son comportement anonyme existant (404 sur
    une collection privée non publique, ex.) plutôt que sur une erreur liée
    au jeton invité — un jeton cassé ne doit jamais empêcher un utilisateur
    réel authentifié par ailleurs d'utiliser la même route."""
    if not x_share_link_token:
        return None
    try:
        claims = decode_share_link_token(x_share_link_token)
    except ShareLinkTokenError:
        return None
    link = sharing_repo.get_active_share_link(
        session, tenant_id=claims.tenant_id, link_id=claims.share_link_id
    )
    if link is None:
        return None
    return resolve_guest_scope(session, claims)
```

**Coût par requête** : dans le pire cas (un widget référence un dataset via
`datasetId`), `get_share_link_actor` exécute jusqu'à 4 requêtes SQL
(`get_access_facts` racine, `get_config_by_item` racine,
`get_access_facts` dataset, `get_config_by_item` dataset) — comparable au
coût déjà payé par `_require_access` (deux requêtes) sur toute route
authentifiée existante, et strictement borné (pas de boucle, pas de
récursion, cf. décision 3). Accepté sans mémoïser au-delà de la requête
HTTP courante (décision 3) : une App affichant N widgets liés au même
dataset répète ce calcul N fois (une requête HTTP par widget/collection),
un `functools.lru_cache` au niveau du process serait dangereux ici (fuite
entre tenants/jetons révoqués) — un cache scoped à la requête FastAPI
(`Depends` est déjà mémoïsé UNE fois par requête HTTP, c'est le
comportement par défaut) suffit pour ne pas payer le coût deux fois pour
UNE requête portant plusieurs Depends sur le même jeton, ce qui couvre déjà
le cas réel (une requête = une ressource, jamais plusieurs collections dans
le même appel HTTP côté ce chantier).

### 4.2 `get_readable_collection` étendu (chokepoint unique, §2.3)

```python
def get_readable_collection(
    session, user, collection_id, *,
    can_manage_collections: bool = False,
    guest: "GuestActor | None" = None,           # nouveau paramètre optionnel
):
    col = None
    if user is not None:
        col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    elif guest is not None:
        col = repo.get_collection(session, tenant_id=guest.tenant_id, collection_id=collection_id)
    else:
        tenant = get_or_create_default_tenant(session)
        col = repo.get_collection(session, tenant_id=tenant.id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")

    if guest is not None and authorize_guest_collection_read(guest, collection_id):
        return col       # portée invité explicite : contourne can(), même
                          # sur une collection privée — c'est le but (décision 3)

    readable = can_manage_collections or can(
        session, user_id=user.id if user else "", action="read",
        item=repo.get_access_facts(col), kind="collection",
        actor_is_admin=bool(user and user.is_admin),
    )
    if not readable:
        raise HTTPException(status_code=404, detail="collection not found")
    return col
```

Important : quand `user is None` et `guest is not None`, la collection est
résolue avec `tenant_id=guest.tenant_id` — **pas** le tenant par défaut du
chemin anonyme existant (bug potentiel en déploiement multi-tenant,
corrigé au passage puisqu'il est sur le trajet de ce changement, jamais
laissé tel quel « parce que hors périmètre » — celui-là est bel et bien
dans le périmètre puisqu'il fait partie du chokepoint qu'on modifie déjà).

Chaque route listée en §4.3 gagne `guest: GuestActor | None =
Depends(get_share_link_actor)` et le passe à `get_readable_collection(...,
guest=guest)`.

### 4.3 Routes REST qui acceptent désormais un jeton invité (liste précise,
vérifiée par lecture — pas supposée)

| Route | Fichier | Changement |
|---|---|---|
| `GET /configs/by-item/{item_id}` | `app/configs/routes.py:352-365` | `user: User = Depends(get_current_user)` → `User \| None = Depends(get_current_user_optional)` ; branche invité via `authorize_guest_item_read` |
| `GET /collections/{id}/items` (`list_features`) | `app/features/routes.py:188-230` | + `guest` param, passé à `get_readable_collection` |
| `GET /collections/{id}/items/{fid}` (`get_single_feature`) | `app/features/routes.py:498-514` | idem |
| `POST /collections/{id}/aggregate` (`aggregate_features`) | `app/features/routes.py:251-280` | idem |
| `GET /collections/{id}/tiles/{z}/{x}/{y}.mvt` | `app/features/tiles.py:113-165` | idem |
| `GET /collections/{id}` (`get_collection`) | `app/collections/routes.py:415-460` | idem |
| `GET /collections/{id}/schema` | `app/collections/routes.py:463-482` | idem |
| `GET /collections/{id}/items/{fid}/attachments` | `app/attachments/routes.py:286-297` | idem |
| `GET /collections/{id}/items/{fid}/attachments/{aid}/file` | `app/attachments/routes.py:300-335` | idem |

**Explicitement non modifiées** (§2.3, §6) : `POST /collections/{id}/
export`, `GET /collections/{id}/export/items`, `POST /analytics/sql` (export
en vrac et SQL libre, hors lecture-seule visée) ; toutes les routes
d'écriture (`POST`/`PUT`/`DELETE` sur `/collections/{id}/items{,/{fid}}`,
`/attachments`) ; `GET /extensions` (§2.4, limitation documentée) ;
`GET /share-links/{token}` (déjà publique, inchangée, réutilisée telle
quelle par la page d'embed).

### 4.4 Shell — transport du jeton

- `shell/src/api/base.ts::createBase(opts)` gagne un champ optionnel
  `getShareLinkToken?: () => string | undefined`. `request()` et
  `fetchGeoJsonFeatures()` (les deux fonctions internes qui posent déjà
  `Authorization` conditionnellement) posent en plus
  `headers["X-Share-Link-Token"] = shareToken` quand
  `getShareLinkToken?.()` renvoie une valeur.
- `shell/src/api/itemClient.ts::createItemClient(opts)` accepte le même
  champ optionnel, le relaie à `createBase`, et l'expose sur l'objet
  `ItemClient` retourné (`getShareLinkToken: () => opts.getShareLinkToken?.()`),
  symétrique de `getAuthToken`/`getCoreUrl` déjà présents (lignes 54-55).
- `shell/src/api/types.ts::ItemClient` gagne `getShareLinkToken?(): string
  | undefined;`, juste sous `getCoreUrl?()` (même commentaire de contrat
  qu'eux : optionnel, absent sur un mock de test qui n'en a pas besoin).
- `shell/src/map/MapView.tsx` gagne un prop optionnel `getShareLinkToken?:
  () => string | undefined`, threadé par le même patron que
  `getAuthToken`/`getCoreUrl` (refs lignes 1003-1023) : ajouté dans
  `transformRequest` (ligne ~1099-1103, un header de plus à côté
  d'`Authorization`) et dans le fetch manuel d'attachment (lignes
  1356-1390, même ajout). **Pas** ajouté au loader Tile3D (lignes 804-825)
  — `tiles3d`/`terrain` ne font pas partie du modèle de couches d'un widget
  carte d'App/Dashboard (§2.2, §3 décision 1), aucun call site ne les
  utilise depuis `mapWidget.tsx`.
- `shell/src/builder/widgets/mapWidget.tsx:358-359` : ajoute
  `getShareLinkToken={client.getShareLinkToken}` à côté des deux props
  existants — seul call site de `<MapView>` atteignable depuis un
  App/Dashboard rendu par `AppRenderer` (le second call site,
  `MapEditorPage.tsx`, est l'éditeur de carte autonome, jamais atteint par
  un jeton invité — laissé inchangé).

### 4.5 Shell — page d'embed

Nouvelle route publique dans `shell/src/shell/routes.tsx`, au même niveau
que `/sites/:slug` (ligne 429, hors `<ProtectedLayout>`) :

```tsx
<Route path="/embed/:token" element={<EmbedRoute />} />
```

Nouveau `shell/src/pages/EmbedPage.tsx`, calqué sur `AppRuntimePage.tsx`
mais délibérément réduit :

1. `GET /share-links/{token}` (route publique existante, inchangée) pour
   obtenir `itemId`/`resourceType`/`title` — 401 affiché comme « lien
   expiré ou révoqué », lisible sans jargon.
2. Si `resourceType` n'est pas `app`/`dashboard` : message explicite « ce
   contenu ne peut pas être intégré » (décision 1) — **jamais** de tentative
   de rendu.
3. Construit son **propre** `ItemClient` local (`useMemo`, jamais celui du
   contexte ambiant `useItemClient()` — la page d'embed ne doit dépendre
   d'aucun état d'authentification de l'onglet hôte) :
   `createItemClient({ coreUrl: loadConfig(import.meta.env).coreUrl,
   getToken: () => undefined, getShareLinkToken: () => token })`, et
   l'enveloppe dans son propre `<ItemClientProvider>` (shadowing local,
   comportement standard du contexte React — aucun changement requis sur
   le provider lui-même).
4. `registerBuiltinWidgets()` (et les deux exemples) appelés au chargement
   du module, comme `AppRuntimePage.tsx:22-24` — chunk lazy séparé, jamais
   chargé tant que personne ne visite `/embed/*`.
5. `useAppConfig(itemId, { mode: "runtime" })` (déjà posé, réutilisé tel
   quel) → `<AppRenderer config={...} mode="runtime" />` — **sans** le
   bandeau d'action (export/enregistrer-la-vue), sans `TopBar`, sans
   `AppLayout` : une page nue, pensée pour un `<iframe>`.
6. Pas d'enregistrement d'extensions actives par défaut dans ce chantier
   au-delà de ce qu'`useActiveExtensions()` fait déjà (limitation §2.4/§4.3
   assumée, pas travaillée davantage ici) — le composant appelle la même
   fonction que `AppRuntimePage`, sans changement.

### 4.6 Shell — section « Intégrer » dans `ShareForm.tsx`

- Core : `ShareLinkCreated` (`core/app/sharing/schemas.py:22-24`) gagne
  `token: str`. `create_share_link_route` (`core/app/items/routes.py:
  263-297`) le renseigne avec la valeur déjà calculée localement (`token =
  mint_share_link_token(...)`, déjà en mémoire — zéro calcul
  supplémentaire).
- Shell : `ItemClient.createShareLink` (`shell/src/api/types.ts:472`,
  `shell/src/api/domains/items.ts:221-227`) renvoie désormais `{ url,
  expiresAt, token }`.
- `shell/src/shell/ShareForm.tsx::ShareLinksPanel` (lignes 24-121) : à côté
  du panneau existant, une section « Intégrer » n'apparaît **qu'après**
  création réussie d'un lien (même `lastCreatedUrl`/état local que
  l'existant, pas une nouvelle mutation — décision 6) et affiche un extrait
  `<iframe src="{window.location.origin}/embed/{token}" width="100%"
  height="600" style="border:0" loading="lazy"></iframe>` en texte
  sélectionnable (pas de bouton de téléchargement de fichier — sandbox de
  l'artefact/plateforme non pertinent ici, simple `<textarea readOnly>` ou
  équivalent existant du kit UI).

## 5. Critères d'acceptation

1. Un jeton de lien de partage émis pour une App référençant une collection
   **privée** X (via `dataSources[].layer`) : `GET /configs/by-item/{appId}`
   avec `X-Share-Link-Token: <token>` répond 200 ; `GET /collections/X/
   items`, `GET /collections/X/tiles/0/0/0.mvt`, `GET /collections/X/
   schema`, `POST /collections/X/aggregate` avec le même header répondent
   200 (pas 401, pas 403, pas 404) pour un appelant **sans** `Authorization`
   du tout.
2. **Test de non-régression de sécurité, explicite (demandé par le
   brief)** : le même jeton, appelé contre une collection privée Y qui
   existe, appartient au même tenant, mais n'est **pas** référencée par
   les `dataSources` de l'App — répond 404 sur chacune des routes du
   tableau §4.3, exactement comme un appel anonyme sans jeton du tout.
3. Un jeton dont l'item racine n'est **pas** `kind in ("app", "dashboard")`
   (ex. un `dataset` ou un `map` autonome) : `resolve_guest_scope` renvoie
   `None`, `GET /configs/by-item/{id}` avec ce header répond 404 (comme
   sans header). `GET /share-links/{token}` (inchangée) continue de
   répondre 200 avec les métadonnées, comme avant ce chantier.
4. Un jeton **révoqué** ou **expiré** : toutes les routes du tableau §4.3
   se comportent exactement comme sans header (retombent sur
   `user`/anonyme public existant) — jamais un 500, jamais un statut
   différent de celui d'un appel sans jeton.
5. `datasetId` cross-tenant (un `dataSources[].datasetId` pointant, par
   construction de test, vers un item d'un **autre** tenant) : ce
   `datasetId` n'apparaît ni dans `allowed_item_ids` ni ne contribue à
   `allowed_collection_ids` — la collection qu'il désignerait dans l'autre
   tenant reste inaccessible.
6. Un utilisateur réel authentifié (`Authorization: Bearer <jwt OIDC>`) sans
   aucun `X-Share-Link-Token` : comportement **strictement inchangé** sur
   les neuf routes du tableau §4.3 (suite de tests existante rejouée sans
   modification, doit rester verte).
7. `CORE_AUTH_MODE=mock` : un appel portant `X-Share-Link-Token` mais
   **aucun** `Authorization` n'est jamais traité comme un utilisateur mock
   admin (`get_current_user`/`get_current_user_optional` ne voient jamais
   ce header, par construction — test explicite qui pose le header seul et
   vérifie que le résultat est identique à un appel sans aucun header
   d'authentification, modulo la portée invité elle-même).
8. La page `/embed/{token}` (shell) : rendu Playwright d'une App à deux
   widgets (un lié à une collection directe, un lié via `datasetId`) avec
   un jeton mocké — les deux widgets affichent des données, aucun appel
   réseau ne porte de header `Authorization`, tous portent `X-Share-Link-Token`.
9. Aucune réponse de `/embed/*` ne porte de `X-Frame-Options` ni de CSP
   `frame-ancestors` restrictive (test explicite, cf. §2.6 — non-régression
   à graver plutôt que readonly aujourd'hui par absence).
10. `docker compose config` (ou équivalent statique) : aucun changement
    requis — ce chantier n'ajoute ni variable d'environnement, ni service,
    ni migration.
11. `cd core && PYTHONPATH=. uv run lint-imports` reste vert sans nouvelle
    entrée `ignore_imports` (§2.4).
12. Diff `openapi.json`/`core-schema.d.ts` régénéré et non vide, cohérent
    avec exactement les changements de schéma décrits (nouveau champ
    `token` sur `ShareLinkCreated`, nouveaux paramètres query/header sur
    les routes du tableau — les headers `Depends(Header(...))` n'apparaissent
    pas dans le schéma OpenAPI de la même façon qu'un `Query`, à vérifier
    empiriquement plutôt que supposé au moment d'exécuter, piège CLAUDE.md
    n°3).

## 6. Hors périmètre (explicite)

- **Embedding par widget individuel** — seule une App/Dashboard entière est
  intégrable (décision 1).
- **SDK JS chargé dynamiquement** — ce chantier livre un `<iframe>` brut ;
  un SDK npm/CDN qui orchestrerait la communication postMessage
  (redimensionnement auto, événements de navigation exposés à la page
  hôte, thème hérité du site intégrateur) est un suivi futur explicite, non
  entamé ici.
- **Écriture depuis un embed** : aucune route d'écriture n'accepte le
  jeton invité (§4.3) — un widget Formulaire affiché dans un embed échoue
  ses écritures avec l'erreur d'autorisation déjà produite aujourd'hui pour
  un appel anonyme (comportement de fallback existant, non retravaillé).
- **Export en vrac (CSV/XLSX/GeoJSON/GPKG) et SQL Lab** depuis un embed
  (§2.3, §4.3) — rétrécissement délibéré au-delà du texte du brief.
- **`GET /extensions` non corrigé pour la portée tenant invité** en
  déploiement multi-tenant (§2.4) — limitation documentée, pas un défaut
  silencieux.
- **Items `kind == "map"` ou tout autre kind autonome** intégrables via
  `/embed/{token}` — seuls `app`/`dashboard` (décision 1) ; `MapConfig.
  layers[].collectionId` n'est pas dans le modèle d'extraction de ce
  chantier.
- **Consommation anonyme complète d'un lien de partage simple** (sans
  App/Dashboard, juste la fiche métadonnées) — déjà hors périmètre de
  SP-54, toujours hors périmètre ici (`resolve_share_link_route` inchangée).
- **Restructurer le contrat de couches** pour permettre à `app.extensions`
  d'importer `app.configs.guest_access` (§2.4) — question architecturale
  plus large que ce GAP, non ouverte ici.

## 7. Risques assumés / limitations documentées

- **Multi-tenant + extension personnalisée dans une App embarquée** :
  résolution du tenant anonyme pour `GET /extensions` non corrigée (§2.4,
  §6). Sans impact aujourd'hui (déploiements mono-tenant).
- **`frame-ancestors`/`X-Frame-Options`** : absents aujourd'hui (§2.6),
  gravés en critère d'acceptation (§5.9) pour qu'un futur durcissement de
  sécurité ne les réintroduise pas sans le savoir sur `/embed/*` — mais
  rien n'empêche mécaniquement un futur ajout global de casser
  l'embedding ; seul un test explicite le détecterait.
- **Coût de résolution par requête** (§4.1) : jusqu'à 4 requêtes SQL
  supplémentaires par appel de route concernée quand un `datasetId` est en
  jeu — jugé acceptable (comparable à `_require_access`), non mesuré sous
  charge dans ce chantier (aucune route concernée n'est aujourd'hui un
  chemin chaud à fort trafic).
- **Pas de révocation immédiate à l'échelle de l'App** : si la config de
  l'App change après l'émission d'un jeton (nouvelle collection
  référencée, ou une collection retirée), la portée effective suit la
  config **courante** à chaque requête (décision 3, pas de cache
  inter-requêtes) — c'est un comportement voulu (la portée est toujours
  recalculée), pas une limitation, mais à ne pas confondre avec une
  révocation du jeton lui-même (toujours gérée par `ShareLink.revoked_at`,
  inchangé).
