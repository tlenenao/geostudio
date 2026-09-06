# SP-55 — Catalogue : tri, facettes, recherche spatiale, SEO (chantiers 4.7, 4.8, 4.10)

Date : 2026-09-05. Ferme trois chantiers indépendants de la vague 4
(`docs/vision/2026-08-20-revue-projet-et-plan-daction.md` §7, lignes
397-400) recensés par la revue SP-42 sous **GAP-05**, **GAP-06**, **GAP-07**
(`docs/revue/2026-09-04-analyse-gaps.md:49-51`).

**Aucune dépendance sur SP-43** (refactorisation structurelle) : ce document
part de l'état réel du dépôt au 2026-09-05, qu'une partie de SP-43 ait déjà
été exécutée ou non sur `dev` au moment où ce plan tourne. Les chemins de
fichiers cités ci-dessous (`shell/src/api/domains/items.ts`,
`shell/src/api/domains/items.hooks.ts`, `shell/src/api/base.ts`) sont déjà la
forme post-découpage — vérifiés directement dans le dépôt, pas supposés.

## Contexte et périmètre

Les trois chantiers touchent la même page (`CatalogPage.tsx`) et la même
route (`GET /items`), mais sont fonctionnellement indépendants ; ils sont
traités dans trois sections séparées, avec un ordre d'exécution recommandé
(§5) qui reflète leur risque relatif, pas une dépendance technique entre eux.

**Vérifié avant d'écrire ce document** :
- `grep -in "sort\|facet" shell/src/pages/CatalogPage.tsx` : vide. La page
  (`shell/src/pages/CatalogPage.tsx:1-220`) n'a qu'un champ de recherche
  plein texte, un sélecteur de type, un sélecteur de portée (`ItemScope`) et
  une pagination. Aucun tri, aucune facette, aucune recherche spatiale.
- `core/app/items/repository.py::list_items` (lignes 241-331) trie
  **toujours** par `Item.created_at.desc()` (ligne 324 pour le chemin
  ILIKE ; le chemin RRF hybride, lignes 291-316, trie par le score de
  pertinence sans option de repli) — aucun paramètre de tri, aucun filtre
  par propriétaire arbitraire (seul `scope=mine` filtre sur
  l'utilisateur **courant**), aucun filtre par mot-clé sur ce endpoint
  (`list_published_items`, lignes 334-366, a un filtre `tag` mais c'est un
  endpoint distinct, réservé à `/public/items`, jamais consommé par
  `CatalogPage`).
- L'emprise spatiale d'une collection est déjà calculée à deux endroits
  distincts, tous deux par un scan `ST_Extent` en direct, jamais persisté :
  `core/app/collections/extent.py::table_extent` (pas de reprojection,
  consommé par `GET /collections/{id}` et par l'import — voir
  `core/app/ingestion/importer.py:187`) et
  `core/app/stac/extent.py::estimated_bbox_4326` (reprojection 4326,
  consommé par les exports STAC/DCAT). Aucun des deux n'est relié à un
  `Item` — `Item` n'a pas de colonne de géométrie ni de FK vers
  `Collection` (`core/app/collections/models.py::Collection` n'a pas de
  colonne `item_id` non plus ; le seul lien est indirect, à travers
  `MapConfig.layers[].collectionId`, une clé posée dans le JSON de config,
  jamais indexée).
- `shell/index.html` ne contient qu'un `<title>GeoStudio</title>` statique
  et deux balises `<meta charset>`/`<meta viewport>` — aucun `og:`,
  `canonical`, ni description. `shell/nginx.conf` est un serveur de fichiers
  statique pur (`try_files $uri $uri/ /index.html`), sans aucune capacité de
  proxy vers `core`. `grep -rn "sitemap\|robots.txt" shell/` : vide (hors ce
  document).

## 1. GAP-05 — Tri et facettes (3-5j)

**Critère de sortie (texte du chantier 4.7)** : trier le catalogue par date
de modification et filtrer par mot-clé sans passer par la recherche plein
texte.

### 1.1 Backend — `core/app/items/repository.py::list_items`

Trois paramètres nouveaux, tous optionnels (rétrocompatibles) :

- `sort: str | None` — une valeur parmi `"date_desc"` (défaut actuel,
  inchangé), `"date_asc"`, `"updated_desc"`, `"title_asc"`, `"title_desc"`.
  Pas de valeur `"relevance"` distincte : quand `q` est posé et qu'aucun
  `sort` explicite n'est demandé, l'ordre RRF existant (déjà un tri par
  pertinence) reste le défaut inchangé — c'est ce que le texte du chantier
  appelle « pertinence ». Un `sort` explicite (date/titre) **avec** `q`
  posé écrase l'ordre RRF : le chemin hybride doit alors trier les
  `page_items` récupérés par PK avant de les sérialiser, au lieu de
  s'appuyer sur l'ordre de `candidate_ids` (RRF).
- `owner: str | None` — nom d'utilisateur exact (`User.username`), filtré
  via le même `join(User, User.id == Item.owner_id)` déjà présent dans la
  requête. Distinct de `scope=mine` (qui filtre sur l'utilisateur
  **courant**) : `owner` accepte n'importe quel nom d'utilisateur visible
  dans la portée déjà appliquée — le filtre `owner` s'ajoute **après** le
  filtre `scope`/`can()`, jamais à la place (même discipline que le
  commentaire existant ligne 286-289 : la visibilité passe toujours
  avant le reste).
- `keyword: list[str] | None` (paramètre de requête répété, `?keyword=a&keyword=b`,
  sémantique **ET** : un item doit contenir tous les mots-clés demandés).
  `Item.keywords` est une colonne `JSON` générique (pas `JSONB`), portable
  SQLite/Postgres mais sans opérateur de containment natif exploitable des
  deux côtés — **même choix que `list_published_items` (lignes 356-361)** :
  filtre en Python après avoir chargé les lignes de la page candidate,
  jamais un `WHERE` SQL sur le JSON. Contrainte : dès que `keyword` est
  posé, la pagination `LIMIT/OFFSET` SQL (lignes 322-325) doit être
  contournée au profit d'un chargement de **toutes** les lignes visibles
  (scope+type+q déjà appliqués) suivi d'un filtre + slice Python, exactement
  le patron de `list_published_items`. Documenter la même hypothèse
  d'échelle qu'à cet endroit (« petite échelle, catalogue d'un tenant,
  recompute du total après filtre acceptable ») — ne pas la re-justifier
  différemment, ne pas introduire une deuxième heuristique.

Nouvel endpoint `GET /items/facets` (`core/app/items/routes.py`, à côté de
`list_items`), même filtres d'entrée que `GET /items` (`q`, `type`, `scope`,
`owner`) **sauf** pagination — il porte sur l'intégralité de l'ensemble
visible filtré, pas une page. Réponse :

```python
class ItemFacets(BaseModel):
    owners: list[OwnerFacet]      # OwnerFacet = {username: str, count: int}
    keywords: list[KeywordFacet]  # KeywordFacet = {keyword: str, count: int}
```

Agrégation en Python (même raison d'échelle que ci-dessus — pas de `GROUP BY`
SQL sur une colonne JSON portable). Plafonner `keywords` aux 50 valeurs les
plus fréquentes (constante nommée, ex. `_MAX_FACET_KEYWORDS = 50`) — un
tenant avec un vocabulaire de mots-clés très large ne doit pas produire une
réponse non bornée. `owners` n'a pas besoin d'un tel plafond au même niveau
de risque (un tenant a rarement plus de quelques dizaines d'utilisateurs
actifs), mais appliquer la même prudence (même constante ou une variante,
au choix de l'exécutant, à documenter).

### 1.2 Frontend

- `shell/src/api/types.ts::ListItemsParams` gagne `sort?`, `owner?`,
  `keywords?: string[]`. Nouveau type `ItemFacets` (miroir camelCase du
  schéma Pydantic ci-dessus). `ItemClient` (interface) gagne
  `getItemFacets(params): Promise<ItemFacets>`.
- `shell/src/api/domains/items.ts::createItemsMethods` : étendre
  `listItems()` pour sérialiser `sort`/`owner`/`keywords` (un
  `q.append("keyword", k)` par valeur, cohérent avec le paramètre de requête
  répété côté FastAPI) ; ajouter `getItemFacets()` suivant le même patron
  (`URLSearchParams` + `request<ItemFacets>("GET", ...)`) — pas de fonction
  de transformation `toFront*` nécessaire, `ItemFacets`/les champs
  `ListItemsParams` passent tels quels comme le reste des champs `Item`
  (contrairement à `MapLayer`, qui seul passe par
  `shell/src/api/base.ts::toFrontLayer` — piège CLAUDE.md n°5 : **non
  concerné ici**, aucun champ de config n'est touché par cette section).
- `shell/src/api/domains/items.hooks.ts` : nouveau `useItemFacets(params,
  opts)` (même patron que `useItems`).
- `shell/src/pages/CatalogPage.tsx` : dans le panneau `browse` (`filter`),
  ajouter sous le sélecteur « Portée » existant :
  - un `<select>` "Trier par" (les 5 valeurs de `sort`, français : « Date de
    modification (récent d'abord) », etc.) ;
  - un `<select>` "Propriétaire" peuplé par `useItemFacets(...).owners` (une
    option `Tous` + une par propriétaire, libellé `username (count)`) ;
  - une liste de mots-clés à bascule (chips, `aria-pressed`) peuplée par
    `useItemFacets(...).keywords`, état `selectedKeywords: string[]` passé à
    `useItems({ ..., keywords: selectedKeywords })`.
  - Le volet « Résumé » (`inspect`) affiche les filtres actifs
    supplémentaires, même patron que les lignes 206-213 existantes.

### 1.3 Chemins de lecture (piège CLAUDE.md n°5)

Aucun nouveau champ persistant sur `Item` dans cette section (uniquement des
paramètres de requête) — pas de risque de perte au rechargement à auditer
ici. Le risque « chemin de lecture » de ce SP est entièrement dans la
section GAP-06 (§2.4).

## 2. GAP-06 — Recherche spatiale au catalogue (3-5j)

**Critère de sortie (texte du chantier 4.8)** : dessiner un rectangle sur la
Corrèze ne ramène que les jeux qui l'intersectent.

### 2.1 Décision de conception : ne pas dupliquer une troisième fonction d'emprise

Les deux fonctions existantes (`table_extent`, `estimated_bbox_4326`)
scannent la table en direct (`ST_Extent`, sous RLS) à chaque appel — c'est
acceptable pour un `GET /collections/{id}` unitaire ou un export STAC/DCAT
d'une seule collection, mais **inacceptable pour une recherche catalogue** :
une page de résultats afficherait potentiellement des dizaines d'items, et
`Item` n'a de toute façon aucun FK vers `Collection` pour même savoir quelle
table scanner à la volée. Solution retenue : **persister une emprise sur
`Item`**, calculée au moment où sa config est écrite, en réutilisant
`table_extent` (pas une troisième implémentation) sur les collections que la
config référence.

### 2.2 Modèle

Migration Alembic (prochain numéro à vérifier au moment de l'exécution —
`0035` au 2026-09-05, une autre session a pu avancer ce compteur entre
temps) : 4 colonnes nullables sur `items` — `bbox_min_x`, `bbox_min_y`,
`bbox_max_x`, `bbox_max_y` (`Float`/`double precision`, `nullable=True`, pas
de défaut). `NULL` sur les 4 = « pas d'emprise connue » (item non
géographique, ou config jamais réévaluée depuis ce SP). Pas de colonne
géométrie PostGIS : un simple rectangle en 4 flottants suffit au filtre
d'intersection (§2.4) et reste portable SQLite pour les tests unitaires
existants (`core/tests/test_items_repository.py` construit son moteur en
SQLite mémoire — une colonne `geometry` PostGIS y serait inutilisable).

`core/app/items/schemas.py::ItemRead` gagne `bbox: list[float] | None = None`
(forme `[minX, minY, maxX, maxY]`, pas la forme `{"spatial": {"bbox": [...]}}`
de `GET /collections/{id}` — nouveau champ, pas de contrainte de
rétrocompatibilité avec ce format-là).

### 2.3 Point de calcul unique — piège vécu par SP-42/SP-43, ne pas le reproduire

**Vérifié avant d'écrire cette section** : la config d'un item est écrite
par **au moins quatre chemins** qui appellent chacun `app/configs/repository.py`
directement : `create_config` (route POST `/configs`), `update_config`
(route PUT `/configs/{id}`), `rollback_config` (route POST
`/configs/{id}/rollback`) — et **le MCP** :
`core/app/mcp/tools/configs.py::save_app_config` appelle
`configs_repo.update_config(...)` **directement**, pas à travers la route
HTTP. C'est exactement la classe de bug que CLAUDE.md documente comme
« déjà rouvert trois fois » (REST → MCP → terrain3d/tileset3d, fermé
seulement quand SP-42 a trouvé le point de passage unique réel). Pour ne
pas reproduire ce défaut : le recalcul de bbox se fait **dans**
`core/app/configs/repository.py::create_config`, `update_config` et
`rollback_config` (les trois fonctions de bas niveau), pas dans les
handlers de route ni dupliqué côté MCP — les quatre appelants (3 routes +
1 outil MCP) en héritent automatiquement sans rien changer chacun de leur
côté.

Algorithme (nouvelle fonction `core/app/items/bbox.py::recompute_item_bbox`,
appelée par les trois fonctions ci-dessus juste avant de committer, avec le
`session` déjà ouvert) :
1. Si `config.kind != "map"` → poser les 4 colonnes à `None`, sortir (scope
   v1 délibérément restreint aux items `map` — voir §2.6 hors périmètre).
2. Parcourir `config.map.layers`, collecter les `collectionId` distincts
   des couches `kind in ("vector", "feature")` qui en portent un
   (`MapLayer.collectionId`, optionnel sur ces deux variantes —
   `shell/src/api/types.ts:189-221`).
3. Pour chaque `collectionId`, charger la `Collection` (même tenant),
   introspecter sa table (`app.collections.introspection_pg::introspect_table`,
   déjà utilisé par `run_import`) et appeler
   `app.collections.extent.table_extent` (réutilisé tel quel).
4. Unir les bbox obtenues (min des min, max des max). Aucune bbox obtenue
   (aucune couche géographique, ou collections toutes vides) → `None` sur
   les 4 colonnes.
5. Poser `item.bbox_min_x`, etc. sur l'`Item` (déjà chargé par les fonctions
   appelantes) — pas de commit ici, laissé à l'appelant (cohérent avec le
   reste de `configs/repository.py`, qui ne committe jamais lui-même).

### 2.4 Filtre spatial sur `GET /items`

Nouveau paramètre `bbox: str | None` (`"minX,minY,maxX,maxY"`, 4 flottants
séparés par des virgules — même convention textuelle que le paramètre
`bbox` d'OGC API Features déjà utilisé par `core/app/features/routes.py`,
à vérifier et réutiliser plutôt qu'inventer un format différent).
Traduit en un test d'intersection de rectangles sur les 4 colonnes stockées
(pas de scan de géométrie) :

```python
if bbox:
    minx, miny, maxx, maxy = bbox
    query = query.where(
        Item.bbox_min_x.isnot(None),
        Item.bbox_max_x >= minx,
        Item.bbox_min_x <= maxx,
        Item.bbox_max_y >= miny,
        Item.bbox_min_y <= maxy,
    )
```

Posé **après** le filtre scope/can() existant, avant le tri (compatible
avec GAP-05 : les deux filtres sont indépendants et cumulables). Le chemin
de recherche hybride (RRF, `q` posé) doit aussi respecter ce filtre — il
s'applique le plus simplement à `base_stmt` (la requête passée à
`hybrid_search_ids`), pas après coup sur les résultats RRF.

### 2.5 Rattrapage des items existants (backfill)

Les items `map` créés **avant** ce SP n'auront jamais eu leur config
réécrite depuis — leurs 4 colonnes resteront `NULL` indéfiniment tant que
personne ne les rouvre et sauvegarde. C'est un vrai manque fonctionnel (le
critère de sortie ne serait vérifiable que sur les items créés après ce SP,
alors que le catalogue existant en a déjà — l'import GeoJSON/CSV/GPKG/
Shapefile de SP-6 crée systématiquement un item `map`, voir
`core/app/ingestion/importer.py:194-228`). Prévoir une tâche de rattrapage
qui appelle `recompute_item_bbox` sur tous les items `map` existants
(itération simple, idempotente, rejouable sans effet de bord) — soit un
script one-off (`core/scripts/backfill_item_bbox.py`, patron à confirmer
au moment du plan avec les scripts existants sous `core/scripts/`), soit une
route d'administration protégée par un privilège existant, au choix de
l'exécutant. Ne pas la sauter : sans elle, le critère de sortie ne serait
démontrable que sur des données créées pour l'occasion.

### 2.6 Frontend — dessin d'un rectangle sur une carte

**C'est la pièce la plus neuve de cette section : `CatalogPage` n'a
aujourd'hui aucune carte.** `shell/src/map/MapMeasureSketchToolbar.tsx` +
`measureSketch.ts` (SP-27) dessinent des croquis point/ligne/polygone
**éphémères sur une carte déjà montée** dans l'éditeur ou le widget carte —
ils supposent un `MapView`/une instance MapLibre déjà en place, ce que
`CatalogPage` n'a jamais eu. Ce SP doit donc monter un **nouveau composant
minimal**, `shell/src/pages/CatalogSpatialFilter.tsx` : une instance
MapLibre autonome (même fond de carte par défaut que
`shell/src/map/basemaps.ts::DEFAULT_BASEMAP`), une interaction
clic-glisser-relâcher qui dessine un rectangle (pas besoin de la logique
polygone/`shapeToGeoJSONFeature` de `measureSketch.ts` — un simple calcul de
bbox à partir des deux coins), un bouton « Effacer », et un état
`bbox: [number, number, number, number] | null` remonté au parent
(`CatalogPage`) pour peupler `ListItemsParams.bbox`. Placé dans le panneau
`browse` de `CatalogPage`, sous les facettes de la §1.2.

### 2.7 Hors périmètre explicite

- Items `dashboard`/`site`/`app` (widgets qui référencent des datasets à
  travers une configuration plus indirecte que `MapConfig.layers[]`) : bbox
  reste `None` pour ces types en v1. Un suivi peut étendre l'algorithme du
  §2.3 à ces kinds, hors budget de ce SP (l'estimé GAP-06, 3-5j, ne couvre
  que le cas direct).
- Rafraîchissement automatique de la bbox quand la **collection** change de
  contenu (nouvelles features insérées après coup) sans que la config de
  l'item ne soit resauvegardée : la bbox reflète l'état de la collection au
  moment de la dernière écriture de config, pas en continu. Documenté comme
  limite connue, pas un bug.

### 2.8 Chemins de lecture (piège CLAUDE.md n°5)

`bbox` est un champ **calculé côté serveur, jamais soumis par le client** —
contrairement à `popup`/`symbology` (le piège historique), il n'existe
aucun `toFrontLayer()`/transform client à mettre à jour pour le faire
survivre à un rechargement : `ItemRead.bbox` passe tel quel dans la réponse
JSON de `GET /items`/`GET /items/{id}`, lu directement par
`shell/src/api/domains/items.ts`. Le risque réel de ce SP n'est pas un oubli
de lecture mais un oubli **d'écriture** au bon endroit (§2.3) — c'est
pourquoi cette section lui consacre plus de place qu'au chemin de lecture
habituel.

## 3. GAP-07 — SEO des portails publics (2-3j)

**Critère de sortie (texte du chantier 4.10)** : une page `/sites/{slug}`
produit un aperçu correct partagée dans un message, et apparaît dans un
`sitemap.xml`.

### 3.1 Pourquoi une balise `<meta>` posée en JS ne suffit pas

Le shell est une SPA pure (`shell/index.html` ne charge que
`/src/main.tsx`). Un aperçu de partage (Slack, Twitter/X, Facebook,
Discord, WhatsApp…) est produit par un robot qui récupère le HTML **sans
exécuter de JavaScript** — poser `og:title`/`og:image` via un
`useEffect()` dans `SitePublicPage.tsx` serait invisible pour ces robots
(ça reste utile pour Googlebot, qui **exécute** le JS avant d'indexer, et
pour l'onglet du navigateur d'un humain — donc à faire quand même, voir
§3.4, mais insuffisant seul pour le critère de sortie tel qu'écrit). Il faut
un chemin HTML **déjà rendu côté serveur** pour ces robots-là — ce SP ne
migre pas le shell vers du SSR (disproportionné pour ce chantier) mais
route sélectivement les requêtes de robots connus vers une réponse HTML
minimale rendue par `core`.

### 3.2 Nouvelles routes core (`core/app/public/routes.py`)

Ce module est déjà le bon endroit : il importe déjà `items_repo` et expose
déjà `get_published_site_by_slug` (ligne 46, consommé par
`GET /public/sites/{slug}`, JSON). Deux ajouts :

```python
@router.get("/sitemap.xml", response_class=Response)
def public_sitemap(session: Session = Depends(get_session)) -> Response:
    sites = items_repo.list_published_items(  # ou une variante dédiée, à trancher au plan
        session, resource_type="site", page=1, page_size=<sans borne haute documentée>
    )
    base = os.environ["PUBLIC_BASE_URL"]
    body = _render_sitemap_xml(base, sites.items)  # <url><loc>{base}/sites/{slug}</loc><lastmod>...</lastmod></url>
    return Response(content=body, media_type="application/xml")


@router.get("/robots.txt", response_class=Response)
def public_robots(session: Session = Depends(get_session)) -> Response:
    base = os.environ["PUBLIC_BASE_URL"]
    return Response(
        content=f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n",
        media_type="text/plain",
    )


@router.get("/sites/{slug}/social-preview", response_class=Response)
def public_site_social_preview(slug: str, session: Session = Depends(get_session)) -> Response:
    item = items_repo.get_published_site_by_slug(session, slug=slug)
    if item is None:
        raise HTTPException(status_code=404)
    base = os.environ["PUBLIC_BASE_URL"]
    html = _render_social_preview_html(base, item)  # <title>, meta description, og:*, canonical
    return Response(content=html, media_type="text/html")
```

`list_published_items` prend déjà `resource_type`/`tag`/pagination — à
vérifier au moment du plan si sa signature couvre proprement « tous les
sites publiés, sans pagination visible dans le XML » ou s'il faut une
petite variante dédiée (probable : le sitemap veut TOUT, pas une page).

Nouvel env var **`PUBLIC_BASE_URL`** (ex. `https://gis.example.fr`, sans
slash final) — distinct de `SHELL_BASE_URL` (`http://shell:8300`, usage
interne réseau Docker réservé à `export-worker` qui navigue en Playwright,
**jamais une URL publique valide** — vérifié dans
`docker-compose.yml:510`/`.env.example:193`, ne pas le réutiliser ici par
erreur) et de `CORE_BASE_URL` (identité du cœur lui-même, pas du domaine
public front). À ajouter à l'environnement du service `core` dans
`docker-compose.yml` + documenté dans `.env.example`, avec un défaut
raisonnable pour le développement (`http://localhost:5173` ou équivalent,
à confirmer contre `VITE_CORE_URL`/le port réel du shell en dev). Cf. piège
CLAUDE.md n°2 (« câblé » ≠ juste documenté) : vérifier après coup avec
`docker compose config` que la variable atteint bien le bloc
`environment:` du service `core`, et que
`core/tests/test_deployability.py::test_every_core_env_var_is_wired_to_a_service`
(et le test voisin sur les substitutions documentées) restent verts avec la
nouvelle variable.

### 3.3 Routage Traefik (`docker-compose.yml`)

Le shell (routeur `shell`, priorité 1, `Host(`${DOMAIN}`)`, catch-all) sert
aujourd'hui tout ce qui n'est pas `/api` (routeur `core`, priorité 10). Deux
nouveaux routeurs sur le service `core`, priorité **strictement supérieure**
à 1 (pour gagner sur le catch-all shell) — valeurs proposées 20/25, à
confirmer contre les priorités déjà utilisées par les routeurs admin
(15, `docker-compose.yml:147`) pour ne rien chevaucher par accident :

1. **`seo-static`** : `Path(`/sitemap.xml`) || Path(`/robots.txt`)`, vers
   `core:8200`, avec une règle de réécriture de chemin (`/sitemap.xml` →
   `/public/sitemap.xml`, `/robots.txt` → `/public/robots.txt`) — Traefik
   v3.0.4 (`docker-compose.yml:697`, version vérifiée) exprime ça avec un
   middleware `replacepathregex` (à vérifier contre la doc Traefik v3 réelle
   au moment de l'implémentation — piège CLAUDE.md n°3, ne jamais supposer
   la syntaxe d'un knob tiers).
2. **`seo-bots`** : `PathPrefix(`/sites/`) && HeaderRegexp(`User-Agent`,
   `(?i)(facebookexternalhit|Twitterbot|Slackbot|LinkedInBot|Discordbot|
   WhatsApp|TelegramBot|Googlebot|bingbot)`)`, vers `core:8200`, avec un
   middleware `replacepathregex` (`^/sites/([^/]+)$` →
   `/public/sites/$1/social-preview`). Un navigateur humain (User-Agent
   normal) ne matche aucun des deux routeurs ci-dessus et retombe sur le
   routeur `shell` (priorité 1) — comportement inchangé pour les vrais
   visiteurs.

Ce sont des ajouts d'étiquettes Docker Compose pratiquement identiques dans
leur forme aux routeurs admin déjà existants (`martin`/`titiler`/`grafana`,
lignes 143-206) — même patron à suivre : `traefik.enable`, `.rule`,
`.entrypoints`, `.tls.certresolver`, `.priority`, `.middlewares`.

### 3.4 Frontend — méta pour le rendu JS (navigateur humain + Googlebot)

`shell/src/pages/SitePublicPage.tsx` : nouveau hook
`shell/src/shell/useDocumentMeta.ts` (`useEffect` posant/retirant
`document.title`, un `<meta name="description">` et un
`<link rel="canonical">` upsertés dans `<head>`), appelé avec
`item.title`/`item.abstract`. Complète (ne remplace pas) le chemin robot du
§3.2 — utile pour l'onglet navigateur d'un humain et pour Googlebot (qui
exécute le JS avant indexation, contrairement aux robots de prévisualisation
de messagerie visés par `seo-bots`).

### 3.5 Hors périmètre explicite

- `sitemap.xml` ne référence que les items `site` publiés — pas les
  `dataset`/`map`/`app`/etc. publiés par ailleurs (`GET /public/items`
  existe déjà pour ceux-là mais n'a pas de page dédiée indexable au même
  sens — un site est la seule surface "page publique" au sens SEO du terme
  ici).
- Image Open Graph (`og:image`) : réutiliser `thumbnailUrl` de l'`Item`
  quand il existe (`{CORE_BASE_URL}{item.thumbnailUrl}` — déjà relatif au
  cœur, cf. `core/app/items/repository.py:135`), sans validation de
  dimensions/format (les recommandations 1200×630 des réseaux sociaux ne
  sont pas vérifiées ni imposées).
- Pas de sitemap d'images ni de `sitemap-index.xml` multi-fichiers (un seul
  fichier plat, taille du catalogue de sites publics d'un tenant largement
  sous les limites de 50k URL/50 Mo du protocole).

## 4. Ordre d'exécution recommandé

1. GAP-05 (risque bas, aucune migration, purement additif) ;
2. GAP-06 (risque moyen — migration + point d'écriture partagé à ne pas
   dupliquer, cf. §2.3 — mais isolable de GAP-05) ;
3. GAP-07 (risque le plus élevé de la série — c'est le seul qui touche
   l'infrastructure Traefik/Docker Compose, jamais couvert par la suite
   Vitest/pytest ; à vérifier manuellement contre une stack réelle avant de
   clore, pas seulement contre `docker compose config`).

## 5. Risques et questions ouvertes

- **GAP-06** : le budget 3-5j est tendu si le composant carte minimal du
  §2.6 s'avère plus coûteux que prévu (aucune brique de dessin de rectangle
  n'existe déjà dans `shell/src/map/` — tout le reste de ce SP est
  additif/mécanique). Si le budget déborde, dégrader en un formulaire à 4
  champs numériques (`minLon`/`minLat`/`maxLon`/`maxLat`) sans carte,
  fonctionnellement équivalent pour l'API mais qui ne remplit pas
  littéralement « dessiner un rectangle » du critère de sortie — à trancher
  avec Tanguy si ça devient nécessaire, pas unilatéralement.
- **GAP-07** : la syntaxe exacte des middlewares Traefik v3
  (`replacepathregex`, `headerregexp` ou noms équivalents) n'a pas été
  vérifiée contre la documentation Traefik réelle au moment d'écrire ce
  document (piège CLAUDE.md n°3 — à faire explicitement en premier geste de
  la tâche correspondante, pas en fin de tâche). Le défaut de
  `PUBLIC_BASE_URL` en développement doit être choisi et testé contre la
  stack `docker compose up` par défaut, pas seulement supposé.
- **GAP-05/06** : le filtre `keyword` (§1.1) et le filtre `bbox` (§2.4)
  contournent tous deux, chacun à sa façon, le chemin RRF hybride
  (`hybrid_search_ids`) quand `q` est posé en même temps — vérifier à
  l'implémentation qu'ils composent correctement **ensemble** (recherche +
  mot-clé + bbox + tri, tous posés à la fois) plutôt que testés seulement
  un par un (piège CLAUDE.md n°4 : les défauts de croisement ne se voient
  qu'à la revue finale, pas tâche par tâche).

## 6. Décomposition en tâches (indicatif, affiné en plan)

1. Backend GAP-05 : tri + filtre owner/keyword sur `list_items`.
2. Backend GAP-05 : endpoint `GET /items/facets`.
3. Frontend GAP-05 : types/client/hooks/UI `CatalogPage` (tri, facettes,
   filtre propriétaire) + tests unitaires + E2E.
4. Backend GAP-06 : migration + modèle bbox + `recompute_item_bbox` câblé
   sur les 3 fonctions de `configs/repository.py` + backfill.
5. Backend GAP-06 : filtre `bbox` sur `GET /items` (+ interaction avec RRF).
6. Frontend GAP-06 : `CatalogSpatialFilter` (dessin de rectangle) + intégration
   `CatalogPage` + tests unitaires + E2E.
7. Backend GAP-07 : `sitemap.xml`/`robots.txt`/`social-preview` + `PUBLIC_BASE_URL`.
8. Infra GAP-07 : routeurs Traefik + `docker-compose.yml`/`.env.example` +
   vérification `test_deployability.py`.
9. Frontend GAP-07 : `useDocumentMeta` sur `SitePublicPage`.
10. Clôture : suite complète (core+shell+e2e), régénération OpenAPI/types TS,
    vérification manuelle de la stack Docker pour GAP-07 (pas seulement
    `docker compose config`), mise à jour `CLAUDE.md`.
