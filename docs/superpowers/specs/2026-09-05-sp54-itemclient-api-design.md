# SP-54 — API shell (ItemClient) : combler les surfaces + partage avancé

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (issu de la revue SP-42, `docs/revue/2026-09-04-analyse-gaps.md`)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-42, GAP-65,
GAP-40, GAP-47, GAP-38, GAP-12), `docs/revue/2026-09-04-backlog.md`,
`docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (chantier 4.23),
`CLAUDE.md` §« Pièges récurrents » (n°1, n°3, n°11, n°12).

**Portée de ce document** : un inventaire vérifié et un ordre d'exécution pour
combler 6 trous de surface côté `ItemClient`/MCP identifiés par la revue
SP-42 : partage par groupe incomplet (créer un groupe, y ajouter des
membres), profil `getMe()` tronqué et cache dataset sans TTL, recherche
hybride des collections jamais exposée (shell et MCP), jumelles MCP
manquantes (`query_features`), schéma `AppConfig` dupliqué, et liens de
partage à échéance absents. Aucun code n'est modifié ici — c'est le texte
qui deviendra le plan SP-54.

**Coordination avec SP-51 — à lire avant d'exécuter l'un ou l'autre plan** :
voir §7. Vérification de la structure du dépôt faite au moment d'écrire
cette spec (piège CLAUDE.md n°12, ne pas recopier un état supposé) :
`shell/src/api/itemClient.ts` (58 lignes) compose déjà 15 modules
`shell/src/api/domains/*.ts` + `shell/src/api/base.ts` ; `shell/src/api/
hooks.ts` (17 lignes) compose déjà 11 modules `*.hooks.ts` ; `core/app/mcp/
tools.py` a déjà été remplacé par un paquet `core/app/mcp/tools/` (12
modules) ; `core/app/roles/kind_registry.py` existe déjà. Le découpage
SP-43 est **terminé**, pas seulement en cours — tous les pointeurs
ci-dessous visent l'état actuel de ces fichiers.

---

## 1. GAP-42 + volet « groupes » de GAP-65 : créer un groupe, y ajouter un membre

### 1.1 État vérifié

`shell/src/shell/ShareForm.tsx` affiche les groupes existants
(`useGroups()` → `client.listGroups()`) et permet d'attribuer un rôle
(`viewer`/`editor`) à chacun pour l'objet en cours de partage — mais
**aucun bouton, aucun champ, n'y permet de créer un nouveau groupe ni d'y
inscrire un membre**. Le partage par groupe n'est donc utilisable en
pratique que pour un tenant dont les groupes ont déjà été créés hors
produit (script, appel API direct).

Côté cœur, les deux routes existent et sont testées
(`core/app/sharing/routes.py:38-84`, `core/tests/test_sharing_routes.py` —
`test_create_and_list_groups`, `test_add_member`,
`test_add_member_by_non_creator_returns_404`,
`test_add_member_cross_tenant_user_returns_404`,
`test_add_member_to_unknown_group_returns_404`,
`test_create_group_writes_audit_log`) :

- `POST /groups` (`CreateGroupRequest{name}` → `GroupRead{id, name}`,
  201) — écrit un audit `group.create`.
- `POST /groups/{group_id}/members` (`AddMemberRequest{userId}` → 204) —
  écrit un audit `group.add_member`. Repository
  (`core/app/sharing/repository.py:114-129`) : **un ajout de membre
  n'est autorisé que par le créateur du groupe** (`group.created_by ==
  caller_id`, sinon 404 — pas 403, comportement délibéré vérifié par un
  test dédié, ne pas le "corriger" en 403).

Côté ItemClient, `Group = { id: string; title: string }`
(`shell/src/api/types.ts:165`) et `listGroups(): Promise<Group[]>`
(`shell/src/api/domains/items.ts:160-163`) sont les **seules** méthodes
exposées — aucune `createGroup`/`addMember`. Côté MCP,
`core/app/mcp/tools/sharing.py` n'expose que `get_sharing`/`set_sharing` —
aucun outil pour les groupes du tout (pas même la lecture).

**Piège identifié à documenter, pas à corriger silencieusement** : `Group`
(front) ne porte pas `createdBy` — `GroupRead` (cœur) non plus. Une UI qui
afficherait « ajouter un membre » seulement pour les groupes créés par
l'utilisateur courant ne peut donc pas le faire de façon fiable sans un
changement de schéma cœur (hors périmètre choisi, cf. §1.2). La conception
retenue affiche le contrôle pour tout groupe et laisse le 404 remonter
comme message d'erreur explicite plutôt que de le masquer par une UI qui
prétendrait connaître le propriétaire.

### 1.2 Portée retenue

- `ItemClient.createGroup(name: string): Promise<Group>` (POST /groups).
- `ItemClient.addGroupMember(groupId: string, userId: string):
  Promise<void>` (POST /groups/{id}/members), qui doit surfacer un message
  clair sur un 404 (« ce groupe n'existe pas, ou vous n'en êtes pas le
  créateur ») plutôt que le message générique `Request failed: 404 ...`
  actuel de `request()`.
- UI : `ShareForm.tsx` gagne un formulaire d'ajout de groupe (nom +
  bouton) et, par groupe listé, un contrôle « Ajouter un membre ».
  **Correction après vérification** (le brouillon initial de cette section
  proposait de réutiliser `listUsers` comme recherche légère — vérifié
  faux) : `GET /users` (`core/app/auth/routes.py:114,122`) est gardé par
  `require_privilege(..., Privilege.ADMIN_USERS_MANAGE.value)` — un
  utilisateur ordinaire qui partage un de ses items n'a presque jamais ce
  privilège (réservé au rôle Administrateur). Aucune autre route de
  recherche d'utilisateur n'existe dans `core/app/users/`/`core/app/
  auth/`. **Portée retenue en conséquence** : le formulaire demande
  l'identifiant utilisateur exact (`userId`, un UUID) plutôt qu'une
  recherche par nom — ergonomie minimale mais honnête sur ce que
  l'autorisation actuelle permet réellement ; l'API `AddMemberRequest`
  attend de toute façon un `userId`, pas un nom. Une recherche
  d'utilisateur non-admin (ex. par nom, restreinte aux membres du même
  tenant) resterait un chantier ergonomique séparé, non retenu ici — noter
  cette limite dans l'aide contextuelle du formulaire plutôt que la
  masquer.
- MCP : `list_groups`/`create_group`/`add_group_member`, ajoutés à
  `core/app/mcp/tools/sharing.py`, calquant directement
  `app.sharing.repository` (pas de service partagé existant pour les
  groupes — la route REST elle-même appelle le repository directement,
  cf. §1.1 ; créer un service partagé serait un refactor plus large,
  hors périmètre de ce chantier de comblement de surface).

---

## 2. GAP-65 (reste) : `getMe()` tronqué, cache dataset sans TTL

### 2.1 `getMe()` ignore 4 champs pourtant servis

`core/app/auth/routes.py:58-69` (`MeResponse`) sert `id`, `tenantId`,
`email`, et `capabilities` (objet `MeCapabilities`, 8 booléens de
capacité d'instance) en plus des champs déjà lus côté shell. Vérifié :
`shell/src/api/types.ts:68-76` (`Me`) ne déclare **aucun** de ces quatre
champs, et `shell/src/api/domains/identity.ts:29-48`
(`getMe()`) ne les lit pas dans la réponse — ils sont silencieusement
perdus, même si le cœur les sert déjà.

**Note de conception** : le cœur documente explicitement
(`auth/routes.py:32-40`) que `capabilities` sur `/me` est un **doublon
délibéré** de `GET /instance` (« Le shell dérive l'état de ses domaines
d'un profil unique... au lieu de croiser deux requêtes dans chaque
écran » — un test cœur, `test_auth_me_capabilities.py`, interdit aux deux
de diverger). Le shell utilise aujourd'hui exclusivement
`getInstanceInfo()`/`useInstanceInfo()` (`shell/src/api/domains/
items.ts:79-81`, consommé par au moins `MapEditorPage.tsx`,
`RolesAdminPage.tsx` — recherche non exhaustive) pour ses capacités
d'instance. **Décision retenue : ajouter les 4 champs à `Me`/`getMe()`
pour que l'interface reflète fidèlement le contrat réel du cœur (parité de
lecture, cf. règle CLAUDE.md n°1 — le sas ne doit pas cacher une partie de
ce que le cœur sert), sans retirer `getInstanceInfo()`/`useInstanceInfo()`
ni migrer ses consommateurs actuels — c'est un chantier de refactor plus
large (remplacerait un appel déjà répandu par un autre), hors périmètre
d'un chantier de comblement de surface.**

### 2.2 Cache dataset sans TTL ni invalidation

`shell/src/api/base.ts:189` (`datasetCache = new Map<string,
ResolvedDataset>()`) et `resolveDataset()` (lignes 191-222) : une entrée,
une fois posée, n'expire **jamais** et n'est invalidée que par un appel
`saveDatasetConfig()`/`createDatasetItem()` passant par **ce même**
`ItemClient` (ils écrivent directement dans `datasetCache`, cf.
`domains/datasets.ts:142-151,199-208`). Un dataset modifié par une autre
session (autre onglet, autre utilisateur, un pipeline qui réécrit le
document dataset en tâche de fond) reste indéfiniment stale pour toute la
durée de vie de l'`ItemClient` courant — pas de rafraîchissement possible
sans recharger la page.

**Portée retenue** : ajouter un TTL (constante, valeur par défaut
proposée : 5 minutes — un dataset change rarement en pratique dans la
même session, mais 5 minutes borne le pire cas sans réintroduire une
requête réseau à chaque accès) aux entrées de `datasetCache`
(`{ value: ResolvedDataset; expiresAt: number }`), et exposer une méthode
d'invalidation explicite `ItemClient.invalidateDatasetCache(pk?:
string): void` (sans argument : vide tout le cache — avec : une seule
entrée) pour un futur appelant qui saurait qu'un dataset a changé
ailleurs (ex. une notification in-app de fin de pipeline, domaine
`app/notifications/` déjà livré par SP-39 — le branchement réel de cette
invalidation sur un événement de notification est noté comme suivi
possible, **hors périmètre de ce plan**, qui ne fait qu'exposer la
primitive). Le nom « invalidation liée à React Query » du GAP est
partiellement trompeur : `datasetCache` est un cache **interne à
`ItemClient`**, pas une query React Query — il n'y a pas de clé
`queryKey` à invalidate côté React Query pour ce cache précis (les hooks
qui en dépendent, ex. `useDatasetConfig`, ont leur propre `queryKey`
React Query orthogonal). La portée retenue ici est donc : TTL + primitive
d'invalidation manuelle sur le cache interne, pas un branchement sur le
cache de React Query lui-même (qui n'a pas cette donnée).

---

## 3. GAP-40 + volet « collections » de GAP-47 : recherche hybride des collections

### 3.1 État vérifié

`core/app/collections/repository.py::list_visible_collections` (lignes
101-147) **implémente déjà** la recherche hybride RRF (trigram + vecteur,
`hybrid_search_ids`, même mécanisme que pour les items) derrière un
paramètre `q: str | None`, avec repli `ILIKE` hors PostgreSQL. La route
`GET /collections` (`core/app/collections/routes.py:310-312`) accepte déjà
`q` et le relaie. **Le trou est entièrement côté consommateur** :

- `shell/src/api/types.ts:402` (`listCollections(): Promise<
  CollectionAdmin[]>`) et son implémentation
  (`shell/src/api/domains/collectionsAdmin.ts:28-31`) ne prennent aucun
  paramètre.
- `core/app/mcp/tools/catalog.py:68-94` (`search_catalog`) exclut
  explicitement les collections par docstring (« items only, not
  collections ») — c'est la moitié « collections » du GAP-47.
- Seul consommateur shell actuel de `listCollections()` :
  `CollectionsAdminPage.tsx` (via `useCollectionsAdmin()`,
  `shell/src/api/domains/collectionsAdmin.hooks.ts:6-13`) — pas de
  sélecteur de collection ailleurs qui bénéficierait d'une recherche
  (le choix d'une source de couche carte passe par
  `listLayerSources`/`fetchCoreCollections`, un chemin distinct, hors
  périmètre de ce GAP).

### 3.2 Portée retenue

- `ItemClient.listCollections(params?: { q?: string }):
  Promise<CollectionAdmin[]>` (signature élargie, rétrocompatible —
  tout appelant existant continue de fonctionner sans argument).
- `CollectionsAdminPage.tsx` gagne un champ de recherche, même patron que
  `LayerPicker.tsx` (`role="searchbox"`, `aria-label="Rechercher..."`).
- MCP : soit élargir `search_catalog` avec un paramètre `type` qui
  accepterait `"collection"` en plus des types d'item existants (rupture
  de la docstring actuelle qui dit explicitement "items only"), soit un
  outil dédié `search_collections`. **Décision retenue : outil dédié**
  `search_collections(q, page, pageSize)` — ne pas réécrire la sémantique
  d'un outil existant déjà documenté et potentiellement déjà utilisé par
  un agent qui s'appuie sur « items only » ; un outil séparé est un ajout
  pur, jamais un changement cassant.

---

## 4. GAP-47 (reste) : `query_features` (MCP) ne relaie jamais `geom_intersects`

Confirmé. `core/app/mcp/tools/catalog.py:97-137` (`query_features`)
n'accepte que `collectionId`/`bbox`/`filters`/`limit`/`offset` — jamais
`geom_intersects`, alors que `select_features()`
(`core/app/features/repository.py:140-151`) le supporte déjà nativement
et que la route REST équivalente (`core/app/features/routes.py:189,200`)
le relaie déjà. Le cross-filter carte (widget carte → dataset lié par
géométrie) dépend précisément de ce mécanisme côté produit — un agent
MCP ne peut aujourd'hui reproduire un filtre spatial de cross-filter que
par un `bbox` grossier, jamais une intersection de géométrie exacte.

**Portée retenue** : ajouter le paramètre `geomIntersects: dict | None`
à `query_features`, sérialisé/parsé exactement comme la route REST
(`_parse_geom_intersects`, `core/app/features/routes.py:136-158` — MCP
reçoit déjà un objet JSON typé via le protocole, donc pas besoin de
reparser une chaîne : passer le dict directement à `select_features`,
en réutilisant la même validation d'erreur `FilterError`).

---

## 5. GAP-38 : schéma `AppConfig`, deux implémentations parallèles

### 5.1 État vérifié

`GET /schemas/app-config` (`core/app/schemas_routes.py:9-11`) et la
ressource MCP `schema://app-config`
(`core/app/mcp/tools/__init__.py:54-58`) appellent **toutes les deux**
`BuilderConfig.model_json_schema()` indépendamment — même source
(`app.configs.schemas.BuilderConfig`), donc pas de divergence de contenu
possible aujourd'hui, mais deux points d'implémentation qui pourraient
diverger si l'un des deux gagnait un jour un post-traitement (filtrage de
champs internes, par exemple) sans que l'autre suive. La route REST est
testée (`core/tests/test_mcp_schema.py:9-29`, malgré son nom qui prête à
confusion — c'est un test de la route HTTP, pas du MCP) mais **jamais
consommée par le shell** (grep vide sur `/schemas/app-config` dans
`shell/src`, hors le fichier généré `core-schema.d.ts`).

### 5.2 Portée retenue

- **Unifier l'implémentation, pas les deux surfaces** (les deux routes
  d'accès — REST pour un futur outillage externe, MCP pour l'agent —
  restent légitimes et servent des publics différents) : factoriser
  `BuilderConfig.model_json_schema()` derrière une fonction unique
  (`core/app/configs/schemas.py::app_config_json_schema()` ou
  équivalent), appelée par les deux points d'entrée. Diff attendu minime
  (une ligne d'appel de fonction à chaque site), mais ferme la
  possibilité de divergence future.
- **Trouver un consommateur shell réel**, pour que la route ne reste pas
  un point mort testé mais jamais exercé en pratique : le point d'usage
  le plus direct est une validation locale d'un brouillon d'`AppConfig`
  avant `saveAppConfig()` (`shell/src/api/domains/apps.ts`), avec un
  message d'erreur utile avant l'aller-retour réseau. **Portée
  minimale retenue** : ajouter `ItemClient.getAppConfigSchema():
  Promise<Record<string, unknown>>` et l'utiliser au moins une fois (un
  test qui vérifie que le schéma récupéré valide bien un `AppConfig`
  minimal réel, via une bibliothèque de validation JSON Schema déjà
  présente dans les dépendances si il y en a une — **à vérifier avant
  d'écrire la tâche**, ne pas supposer qu'`ajv` ou équivalent est déjà
  une dépendance ; si aucune bibliothèque de validation JSON Schema n'est
  présente, le test vérifie seulement la forme du schéma retourné
  (`type: "object"`, `properties` présent), sans validation complète).

---

## 6. GAP-12 : liens de partage à échéance (chantier 4.23)

### 6.1 État vérifié

`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:433` (chantier
4.23) demande des liens de partage à échéance (jeton, expiration, audit).
Aucune trace dans `core/app/sharing/` — seul le partage groupe/rôle plat
(`ItemShare`, `GroupMember`) existe. Le patron directement réutilisable,
vérifié : `core/app/auth/export_tokens.py` (SP-17a) — un jeton JWT HS256
signé avec `CORE_EXPORT_TOKEN_SECRET`, TTL court (~2 min, configurable),
claims `{typ, tenant_id, user_id, job_id, iat, exp}`, décodage qui
distingue explicitement l'absence de secret (`KeyError`, instance sans
worker d'export déployé) d'un jeton invalide — **les deux se traduisent
en 401, jamais en 500** (commentaire `export_tokens.py:61-64`, à
reproduire à l'identique pour la même raison : un jeton de partage forgé
par un attaquant sur une instance qui n'a jamais configuré le secret ne
doit jamais faire planter la route en 500).

Différence de nature à ne pas gommer : le jeton d'export authentifie un
**worker interne** (Playwright) agissant pour le compte de l'utilisateur
qui a demandé l'export, TTL de l'ordre de la minute, jamais présenté à un
tiers externe. Un lien de partage à échéance est **présenté à un tiers
externe** (un lien copié-collé, potentiellement partagé par email/chat),
donc : TTL beaucoup plus long (jours/semaines, configurable par l'auteur
du partage, pas une constante fixe), et — contrairement au jeton d'export
— doit être **révocable avant expiration** (l'auteur doit pouvoir couper
l'accès immédiatement, ex. si le lien a fuité). Le jeton d'export
documente explicitement l'absence de tout précédent de révocation dans ce
dépôt (`export_tokens.py:4-8`) — **ce chantier introduit donc le premier**
mécanisme de révocation avant expiration du dépôt, pas une simple
recopie du patron TTL seul.

### 6.2 Portée retenue

- Nouveau module `core/app/sharing/share_links.py` (jeton) + table
  `share_link` (id, item_id, tenant_id, created_by, expires_at,
  revoked_at nullable, created_at) — migration Alembic. **Révocation par
  ligne de base** (pas seulement par TTL du jeton, contrairement à
  l'export) : chaque vérification d'un jeton de lien re-consulte la ligne
  correspondante (par son `id` embarqué dans les claims) pour confirmer
  `revoked_at IS NULL` en plus de l'expiration du JWT lui-même — sinon un
  lien révoqué resterait utilisable jusqu'à l'expiration naturelle du
  jeton, contradiction directe avec l'exigence de révocation immédiate.
- Routes : `POST /items/{id}/share-links` (créer, TTL choisi par
  l'auteur, borné par une constante max côté serveur — ex. 30 jours),
  `DELETE /items/{id}/share-links/{linkId}` (révoquer), `GET /share-links/
  {token}` (résoudre : renvoie l'item en lecture seule si le jeton est
  valide et non révoqué, 401 sinon) — toutes avec audit
  (`share_link.create`/`share_link.revoke`/`share_link.access`).
- Shell : `ItemClient.createShareLink(itemId, ttlDays): Promise<{url:
  string, expiresAt: string}>`, `listShareLinks(itemId)`,
  `revokeShareLink(itemId, linkId)` ; UI dans `ShareForm.tsx` (section
  distincte du partage par groupe) ou un panneau dédié si `ShareForm`
  devient trop chargé (à trancher en tâche, après avoir vu le rendu réel
  une fois le groupe/membre de §1 ajouté au même formulaire).
- **Hors périmètre explicite** : consommation anonyme d'un lien de
  partage par un visiteur sans compte (le chantier 4.23 tel que cité ne
  précise pas ce cas, et l'ouvrir supposerait de revoir la façade
  d'authentification du cœur — OIDC délégué à Keycloak, aucune session
  anonyme aujourd'hui ; à trancher explicitement avec Tanguy avant
  d'étendre la portée si le besoin apparaît).

Cette portée est la plus large des 6 GAPs de ce plan (3-5j annoncés,
confirmés réalistes vu la nouvelle table + migration + 3 routes + jeton +
UI).

---

## 7. Coordination avec SP-51 (chantier parallèle, même famille SP-43)

**SP-51** (« Parité carte : widget App Builder vs éditeur autonome ») a
été spécifié le même jour, à partir de la même revue SP-42. Vérification
faite au moment d'écrire cette spec :

- **Chevauchement confirmé** : `shell/src/api/base.ts` — ce plan y ajoute
  le TTL/invalidation de `datasetCache` (§2.2) ; SP-51 n'y touche pas dans
  son périmètre retenu (son seul point de contact possible,
  `toFrontLayer()`/GAP-46, s'est révélé déjà résolu). Même fichier,
  régions différentes (§2.2 modifie `resolveDataset`/`datasetCache` vers
  le haut du fichier ; `toFrontLayer` est ailleurs) — risque de conflit de
  merge faible mais non nul en édition strictement simultanée.
- **Chevauchement probable** : `shell/src/api/types.ts` (interface
  `ItemClient`) — ce plan y ajoute `createGroup`/`addGroupMember`/
  `invalidateDatasetCache`/`listCollections(params?)`/
  `getAppConfigSchema`/`createShareLink`/`listShareLinks`/
  `revokeShareLink` (7 méthodes) ; SP-51 y ajoute une seule méthode
  (`sampleDataSourceField`, sans rapport fonctionnel). Un même fichier,
  deux blocs d'ajout à des endroits différents de l'interface — conflit
  de merge mécanique résoluble par relecture, mais réel si les deux
  branches divergent longtemps sans rebase.
- `shell/src/api/domains/items.ts` (où vit `listGroups`) : ce plan y
  ajoute `createGroup`/`addGroupMember`, aucun chevauchement avec SP-51.

**Recommandation, identique à celle du plan SP-51** : séquencer ce plan et
le plan SP-51 (l'un puis l'autre, ordre indifférent) **ou** confier les
deux à la même session/agent si une exécution simultanée est souhaitée.
Ne pas lancer deux implémenteurs différents en parallèle sans l'un des
deux garde-fous — précédent CLAUDE.md « Sessions concurrentes sur le même
arbre ».

---

## 8. Ordre d'exécution proposé (du moins au plus risqué)

1. **GAP-38** — factorisation pure + un consommateur shell minimal,
   risque bas (aucune route nouvelle, comportement identique).
2. **GAP-65 / getMe** — extension additive d'un type de réponse déjà
   servi par le cœur, risque bas.
3. **GAP-65 / cache dataset** — ajout de TTL + primitive d'invalidation,
   risque bas à moyen (ne doit rien changer pour les appelants existants
   qui ne connaissent pas la nouvelle méthode).
4. **GAP-40 + volet collections de GAP-47** — le paramètre `q` existe
   déjà de bout en bout côté cœur, risque bas.
5. **GAP-47 (reste) / `geom_intersects`** — relais d'un paramètre déjà
   supporté par la couche repository, risque bas.
6. **GAP-42 + volet groupes de GAP-65** — nouvelle UI + nouvelles
   méthodes `ItemClient` + nouveaux outils MCP, risque moyen (surface
   nouvelle, mais routes cœur déjà testées).
7. **GAP-12** — le plus gros morceau : nouvelle table, migration, jeton
   avec révocation (mécanisme inédit dans ce dépôt), 3 routes, UI. Risque
   le plus élevé de ce plan.

---

## 9. Hors périmètre (explicite)

- **Consommation anonyme d'un lien de partage** (GAP-12, cf. §6.2) — à
  trancher séparément si le besoin apparaît.
- **Retrait de `getInstanceInfo()`/`useInstanceInfo()`** au profit de
  `Me.capabilities` (GAP-65) — la duplication reste assumée côté cœur
  (commentaire `auth/routes.py:32-40`), ce plan ajoute la lecture côté
  shell sans migrer les consommateurs existants.
- **Recherche d'utilisateur dédiée pour « ajouter un membre »** —
  vérifié : `listUsers`/`GET /users` exige `Privilege.
  ADMIN_USERS_MANAGE`, indisponible à un partageur ordinaire (cf. §1.2,
  correction après vérification). Le formulaire retenu demande un
  `userId` exact ; une recherche non-admin resterait un chantier séparé.
- **Un service partagé `sharing/service.py` pour les groupes** — la route
  REST elle-même appelle le repository directement aujourd'hui ; ce plan
  reproduit ce même patron côté MCP plutôt que de refactorer les deux
  vers un service commun (hors périmètre d'un chantier de comblement de
  surface, cf. inventaire SP-43 qui ne cite pas ce fichier).
- **Élargissement de `search_catalog` existant** pour couvrir les
  collections (GAP-40) — décision retenue : outil MCP dédié
  (`search_collections`), pas une modification de la sémantique déjà
  documentée d'un outil existant (cf. §3.2).
