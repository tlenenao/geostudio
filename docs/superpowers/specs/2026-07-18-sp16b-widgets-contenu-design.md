# SP-16b — widgets de contenu (Hero / RichSection / Gallery) : design

> Deuxième sous-phase de **SP-16 « Portails & Sites »** (design macro :
> [`2026-07-14-sp16-portails-sites-design.md`](2026-07-14-sp16-portails-sites-design.md),
> arbitrages A31/A33/A34/A35/A38 tranchés le 2026-07-14). Découpage a/b/c fixé
> par le §9 du design macro : **a** = modèle `site`/slug + route publique +
> résolution shell (livré et clos, cf.
> [`2026-07-18-sp16a-modele-site-slug-design.md`](2026-07-18-sp16a-modele-site-slug-design.md)) ;
> **b** = widgets de contenu Hero/RichSection/Gallery (ce document) ; **c** =
> fiche dataset + téléchargement + template galerie. SP-16 s'exécute après
> SP-11 (clos), avant SP-12/SP-13 (A34).

## 1. Objectif

Livrer trois **widgets de contenu** — `Hero`, `RichSection`, `Gallery` —
enregistrés dans le registre de widgets existant (`registerWidget`) et
disponibles pour **tout** type d'item (pas seulement `site` : un dashboard peut
aussi vouloir un bloc de texte), plus le petit socle cœur + shell qui rend la
`Gallery` réellement fonctionnelle pour un visiteur **anonyme** d'un site
publié.

Sur ce socle, un admin construit — depuis le builder existant, sans nouvelle
formation — une page d'accueil éditoriale (Hero + texte riche) et une galerie
de découverte des items publiés, le tout rendu par le seul runtime
`AppRenderer` (A31, aucun deuxième moteur).

## 2. Décisions actées pour cette sous-phase

Rappel des arbitrages hérités du design macro SP-16 (§2, à ne pas rediscuter) :

| # | Décision |
|---|---|
| A31 | Config du portail = sous-gabarit d'`AppConfig`, un seul runtime `AppRenderer` — pas de deuxième moteur. |
| A33 | Domaine personnalisé **différé** : v1 accessible via `/sites/{slug}`, pas de résolution par host. Les routes publiques ne servent que le tenant `default`. |
| A38 | Fonctions communautaires (commentaires/follow/discussions) **hors périmètre**. |

Décisions propres à SP-16b, tranchées au brainstorm du 2026-07-18 :

- **Périmètre = Hero + RichSection + Gallery uniquement.** `DatasetCard`/
  `DatasetPage`, le téléchargement multi-format et le template galerie
  « Portail de données » restent explicitement en SP-16c.
- **RichSection rend du Markdown via `marked` + `DOMPurify`.** CommonMark
  complet, systématiquement assaini avant insertion DOM (le risque XSS est
  assumé et gardé, cf. §6). Deux nouvelles dépendances shell (`marked`,
  `dompurify`).
- **Les vignettes de `Gallery` ouvrent une vue publique par item**, réutilisant
  la route anonyme **déjà existante** `GET /public/configs/by-item/{pk}` — même
  patron `AppRenderer` runtime que `SitePublicPage` de 16a. Aucune nouvelle
  route de config côté cœur.
- **Le filtre de `Gallery` est fixé par l'auteur** (props `type`/`tag`/`limit`),
  pas de contrôles de filtrage interactifs offerts au visiteur. Section de
  découverte curatée, pas un explorateur de catalogue live.

## 3. Périmètre

**Dans le périmètre :**
- Trois widgets built-in : `Hero`, `RichSection`, `Gallery`, enregistrés dans
  `shell/src/builder/widgets/` (mêmes conventions que les widgets existants),
  disponibles pour tout item.
- Nouvelle route cœur anonyme **`GET /public/items`** (liste des items publiés
  du tenant `default`, filtrable par `type`/`tag`, paginée) — le socle sans
  lequel `Gallery` ne peut pas s'alimenter pour un visiteur anonyme.
- Exposition de **`ItemRead.keywords: list[str]`** (affichage des tags sur les
  vignettes).
- Nouvelle vue shell publique **per-item** (`/public/items/:pk`) réutilisant
  `GET /public/configs/by-item/{pk}` existant : cible des clics de vignette.
- `ItemClient.listPublicItems(params)`.

**Hors périmètre (SP-16c ou différé) :**
- `DatasetCard`/`DatasetPage`, aperçu carte/table en lecture seule d'une
  collection (SP-16c).
- Téléchargement GeoJSON/CSV (SP-16c).
- Template galerie « Portail de données » (SP-16c).
- Filtrage interactif de la galerie côté visiteur (décision §2 : filtre fixé
  par l'auteur).
- Éditeur Markdown WYSIWYG riche : `RichSection` reste une zone de texte
  Markdown brute (périmètre macro §7).
- Domaine personnalisé, résolution par host, multi-tenant public (A33).
- Métriques d'usage, fonctions communautaires (A38).

## 4. Architecture — cœur (extension du module `items`, pas de nouveau module)

### 4.1 Route anonyme `GET /public/items`
- Nouveau handler dans `core/app/public/routes.py`, anonyme (aucun
  `get_current_user`), délègue à une fonction repo **dédiée** :
  `list_published_items(session, *, tenant_id="default", resource_type=None,
  tag=None, page=1, page_size=…) -> ItemPage`.
- La fonction dédiée `SELECT ... WHERE is_published IS TRUE AND
  tenant_id='default'` (+ `resource_type` si fourni), joint `User.username`
  comme `get_published_item`. **Pas de réutilisation du chemin authentifié
  `list_items`** : une fonction dédiée published-only, symétrique à
  `get_published_site_by_slug` de 16a, ferme tout risque de fuite d'un item non
  publié ou d'un autre tenant.
- **Filtre `tag`** : porte sur la colonne JSON `items.keywords`
  (`Mapped[list] = mapped_column(JSON, …)`). L'implémentation portable
  Postgres/SQLite (opérateur JSON-contains vs post-filtrage Python avec `total`
  recalculé) est tranchée en plan — le contrat testé reste : « seuls les items
  publiés dont `keywords` contient `tag` sont retournés ».
- Paramètres de requête : `type` (→ `resource_type`), `tag`, `page`,
  `pageSize` — mêmes conventions que `GET /items`.

### 4.2 Exposition de `keywords`
- `ItemRead` gagne `keywords: list[str]` (défaut `[]`). Renseigné à la
  sérialisation depuis `Item.keywords`. Aucune migration (colonne déjà
  présente).

### 4.3 Aucune route de config nouvelle
- La vue publique per-item est servie par `GET /public/configs/by-item/{pk}`
  **déjà existante** (anonyme, vérifie la publication et renvoie 404 sinon).
  Rien à ajouter côté cœur pour le rendu.

### 4.4 Autorisation et isolation
- **Aucun nouveau chemin d'autorisation** : `GET /public/items` n'expose que du
  publié sur le tenant `default`. La revue finale de branche doit vérifier
  explicitement qu'aucun item non publié / d'un autre tenant / partagé mais non
  publié ne peut sortir par cette route (matrice de non-fuite, cf. §6).

## 5. Architecture — shell

### 5.1 Route et vue publique per-item
- Nouveau `PublicItemPage(pk)` — généralisation de `SitePublicPage` : appelle
  `getPublicAppConfig(pk)` (existant) → `AppRenderer(config, "runtime")` ; 404
  ou erreur → page « introuvable » générique (aucune fuite d'existence).
- Route `/public/items/:pk`, déclarée **hors `ProtectedLayout`** dans
  `shell/src/shell/routes.tsx` (à côté de `/sites/:slug`).
- **Note (limitation assumée, non élargie ici)** : `AppRenderer` runtime rend
  les configs de type app/dashboard/site. Un item `map` dont la config n'est
  pas une config d'app-style est une limitation **préexistante** du runtime,
  ni introduite ni corrigée par 16b ; le filtre auteur de `Gallery` permet de
  curer les types affichés. Documenté, pas de traitement spécial.

### 5.2 `ItemClient`
- `listPublicItems(params: { type?: string; tag?: string; page?: number;
  pageSize?: number }): Promise<ItemPage>` → `GET /public/items?...`.
- La vue per-item réutilise `getPublicAppConfig` existant ; pas de nouvelle
  méthode de config.
- **Round-trip `keywords`** : si `itemClient` reconstruit un `Item` champ par
  champ, `keywords` doit être explicitement propagé en lecture (classe de bug
  `slug`/`visibleWhen`/`navigationMode` déjà rencontrée — testé, pas supposé).

### 5.3 Les trois widgets (`shell/src/builder/widgets/`, thème `--gs-*`)

**`Hero`** — bandeau éditorial.
- Props : `title`, `subtitle`, `backgroundImageUrl`, `ctaLabel`, `ctaHref`,
  `align` (`"left" | "center"`).
- `events: ["cta"]` : au clic sur le CTA, ouvre `ctaHref` (nouvel onglet,
  `noopener`) **et** émet un event bus (même patron que le widget `button`),
  branchable aux actions composées.
- États : sans `backgroundImageUrl` → aplat de couleur de thème ; sans
  `ctaLabel` → pas de bouton.

**`RichSection`** — bloc de texte riche.
- Prop : `markdown` (chaîne).
- Rendu : util isolé et testé `sanitizeMarkdown(md: string): string` =
  `DOMPurify.sanitize(marked.parse(md))`, inséré via `dangerouslySetInnerHTML`.
- Styling « prose » sur les variables de thème (titres, listes, liens).
- État vide → placeholder discret en mode édition.

**`Gallery`** — grille de découverte des items publiés.
- Props (filtre **fixé par l'auteur**) : `type?`, `tag?`, `limit?`,
  `columns?`.
- `Component` : `useQuery` → `listPublicItems({ type, tag, page: 1, pageSize:
  limit })` → grille de vignettes. Chaque vignette : `thumbnailUrl` (repli
  aplat), `title`, `abstract`, `keywords` (tags) ; **lien vers
  `/public/items/{pk}`**.
- États explicites : chargement, vide (« Aucun élément publié »), erreur.
- `PropsPanel` : sélecteur de type (liste des `ResourceType`), champ tag, champ
  limite, champ colonnes.

## 6. Sécurité et gouvernance

- **Non-fuite de `GET /public/items`** (risque ★★★) : la route ne retourne
  jamais un item non publié, d'un autre tenant, ou partagé mais non publié —
  testé en matrice explicite (symétrique aux matrices rôle×action /
  tenant×slug déjà exigées par le projet). Fonction repo dédiée published-only,
  jamais le chemin authentifié.
- **XSS via Markdown** (risque ★★) : `RichSection` insère du HTML dérivé d'une
  entrée d'auteur via `dangerouslySetInnerHTML`. `DOMPurify.sanitize` est
  **obligatoire** et non contournable (encapsulé dans `sanitizeMarkdown`) ;
  test adversarial dédié (`<script>`, `<img onerror=…>`, `javascript:` href).
- Aucune décision d'autorisation shell nouvelle : la frontière réelle reste
  `can()` / la politique de publication SP-1c, inchangée.

## 7. Tests

**Cœur (pytest) :**
- `list_published_items` : ne retourne que du publié sur `default` ; filtre
  `type` ; filtre `tag` (JSON `keywords`) ; pagination (`total`/`page`/
  `pageSize`).
- **Matrice de non-fuite** : item non publié → absent ; item publié d'un autre
  tenant → absent ; item partagé mais non publié → absent ; item publié
  `default` → présent.
- `GET /public/items` : anonyme 200 ; respecte `type`/`tag`/pagination ;
  n'expose jamais de champ sensible.
- `ItemRead.keywords` sérialisé correctement (liste vide par défaut, liste
  peuplée quand renseignée).

**Shell (Vitest) :**
- `Hero` : rendu titre/sous-titre/fond/CTA ; clic CTA émet l'event bus **et**
  ouvre `ctaHref` ; héritage de thème (`--gs-*`) ; états sans image / sans CTA.
- `RichSection` : rendu Markdown (titres, gras/italique, liens, listes) ;
  **sanitisation** — `<script>` et attributs `onerror`/`javascript:` retirés
  (test adversarial) ; état vide.
- `Gallery` : `useQuery` appelle `listPublicItems` avec les props de l'auteur ;
  grille rendue ; vignette liée à `/public/items/{pk}` ; états loading / vide /
  erreur.
- `PublicItemPage` (MSW) : cas 200 rend `AppRenderer` ; cas 404 rend
  « introuvable » sans détail.
- `itemClient.listPublicItems` : URL/paramètres corrects ; round-trip
  `keywords` (lecture).

**E2E (nouvelle spec `sites-portal-content.spec.ts`) :**
1. Créer un `site`, y ajouter Hero + RichSection + Gallery depuis la palette,
   Enregistrer.
2. Publier via la mécanique existante.
3. Session anonyme → visiter `/sites/{slug}` : le Hero (titre), le Markdown
   rendu et la galerie des items publiés s'affichent — et **aucun** item non
   publié.
4. Cliquer une vignette → la vue per-item (`/public/items/{pk}`) rend
   `AppRenderer` runtime.

## 8. Critères d'acceptation

- Un admin ajoute Hero + RichSection + Gallery à un `site` depuis le builder
  existant, publie, et un visiteur anonyme voit une page d'accueil éditoriale
  (bandeau + texte riche) et une galerie des seuls items publiés à
  `/sites/{slug}`.
- Une vignette de galerie ouvre une vue publique de l'item ciblé, rendue par
  `AppRenderer` runtime, sans authentification.
- `GET /public/items` n'expose jamais un item non publié ni d'un autre tenant
  (matrice de non-fuite verte).
- `RichSection` neutralise toute charge XSS (test adversarial vert).
- La revue finale de branche confirme qu'aucun chemin (notamment
  `GET /public/items`) ne contourne `can()` / la politique de publication.
- Toutes les specs E2E existantes (40, dont `sites-portal-shell.spec.ts`)
  restent vertes ; la nouvelle `sites-portal-content.spec.ts` porte le total
  à **41**.

## 9. Points d'attention d'intégration

- **Dérive OpenAPI / types générés** : nouvelle route `GET /public/items` +
  `ItemRead.keywords` imposent de régénérer `core/openapi.json` et
  `shell/src/api/generated/core-schema.d.ts` — le job CI `api-types-drift`
  échoue sinon (patron récurrent SP-9/SP-10/SP-16a).
- **Nouvelles dépendances shell** (`marked`, `dompurify`, typings associés) :
  vérifier le gate `npm audit` (`shell-deps-audit`, SP-9 sécurité minimale) en
  fin de branche ; les deux paquets sont réputés maintenus, mais l'audit peut
  faire remonter une transitive à allowlister explicitement.
- **Filtre `tag` sur JSON** : la portabilité Postgres/SQLite du prédicat
  `keywords contains tag` est tranchée en plan (JSON-contains natif vs
  post-filtrage Python avec `total` recalculé). Aucune des deux options ne
  change le contrat testé.

## 10. Risques

| Risque | Gravité | Garde-fou |
|---|---|---|
| Fuite d'items non publiés / d'un autre tenant par `GET /public/items` | ★★★ (sécurité) | Fonction repo dédiée published+default only ; matrice de non-fuite testée ; revue finale vérifie l'absence de contournement |
| XSS via `marked` + `dangerouslySetInnerHTML` dans `RichSection` | ★★ | `DOMPurify.sanitize` obligatoire, encapsulé et non contournable ; test adversarial dédié |
| Nouveaux deps (`marked`/`dompurify`) heurtent le gate `npm audit` | ★ | Paquets maintenus ; vérification `shell-deps-audit` en fin de branche ; allowlist explicite si transitive |
| Vignette liée à un item `map` non rendu par `AppRenderer` runtime | ★ (assumé) | Limitation préexistante non élargie ; filtre auteur curate les types ; documenté |
| Dérive OpenAPI / types générés | ★ | Régénération `openapi.json`/`core-schema.d.ts`, job `api-types-drift` |

## 11. Découpage & estimation

Une seule branche livrable, exécutable en subagent-driven ou executing-plans
selon le découpage du plan, en tâches largement indépendantes :
1. socle cœur — `GET /public/items` + `list_published_items` +
   `ItemRead.keywords` ;
2. shell — `PublicItemPage` + route `/public/items/:pk` + `listPublicItems` ;
3. widget `Hero` ;
4. widget `RichSection` (+ `sanitizeMarkdown`) ;
5. widget `Gallery` (dépend de 1 et 2) ;
6. E2E `sites-portal-content.spec.ts` + régénération des types.

Par analogie avec des lots widgets shell + petit endpoint cœur déjà livrés
(SP-4a, SP-8a) : **≈ 20-35 h**.
