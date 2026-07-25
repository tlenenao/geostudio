# SP-13a — modèle `site`/slug + route publique + résolution shell : design

> Première sous-phase de **SP-13 « Portails & Sites »** (design macro :
> [`2026-07-14-sp13-portails-sites-design.md`](2026-07-14-sp13-portails-sites-design.md),
> arbitrages A31/A33/A34/A35/A38 tranchés le 2026-07-14). Découpage a/b/c fixé
> par le §9 du design macro : **a** = modèle `site`/slug + route publique +
> résolution shell (ce document) ; **b** = widgets de contenu (Hero/
> RichSection/Gallery) ; **c** = fiche dataset + téléchargement + template
> galerie. SP-13 s'exécute après SP-11 (clos), avant SP-12/SP-17 (A34).

## 1. Objectif

Livrer la **tranche verticale minimale et testable de bout en bout** sur
laquelle b/c se poseront : un admin crée un item de type **`site`** (avec un
slug), le publie via la mécanique de partage existante (SP-1c, inchangée), et
un visiteur anonyme le consulte à l'URL stable `/sites/{slug}`, qui rend
`AppRenderer(config, "runtime")` — **même si le site est encore vide**. Aucun
widget de contenu n'est ajouté dans cette sous-phase (ils arrivent en b/c) :
le socle prouvé ici est le cycle *créer → publier → consulter publiquement par
slug*, plus l'isolation tenant sur la résolution de slug (le risque ★★★ du
design macro §8).

## 2. Décisions actées pour cette sous-phase

Rappel des arbitrages hérités du design macro SP-13 (§2, à ne pas rediscuter) :

| # | Décision |
|---|---|
| A31 | Config du portail = sous-gabarit d'`AppConfig`, un seul runtime `AppRenderer` — pas de deuxième moteur. |
| A33 | Domaine personnalisé **différé** : v1 accessible via `/sites/{slug}`, pas de résolution par host. |
| A38 | Fonctions communautaires (commentaires/follow/discussions) **hors périmètre**. |

Décisions propres à SP-13a, tranchées au brainstorm du 2026-07-18 :

- **Résolution du tenant sur la route publique = tenant par défaut (`"default"`)
  uniquement.** Conséquence directe de A33 (pas de résolution par host en v1) ;
  même convention que les routes anonymes existantes (`GET /extensions`,
  `GET /instance`). L'unicité `(tenant_id, slug)` reste stockée en base pour le
  multi-tenant futur, mais la route publique v1 ne sert que le tenant par
  défaut.
- **Slug éditable après création, avec garde d'unicité 409.** Le cycle de vie
  complet du slug (génération auto à la création + édition ultérieure validée)
  entre dès 16a — pas de « création seule ».
- **Aucun widget de contenu.** Le site publié est un `AppRenderer` en mode
  `runtime` possiblement vide ; Hero/RichSection/Gallery/DatasetCard sont
  explicitement repoussés en SP-13b/c.

## 3. Périmètre

**Dans le périmètre :**
- Nouveau `resource_type == "site"` (chaîne libre — aucun enum à élargir côté
  cœur, cf. §6.1).
- Colonne `items.slug` (nullable), unicité composite partielle par tenant.
- Génération de slug déterministe + résolution de collision.
- Route publique `GET /public/sites/{slug}` (tenant par défaut, 404 jamais 403).
- Édition du slug via le `PATCH /items/{id}` existant, 409 sur collision.
- Shell : type `site` dans les unions, `getItemBySlug`, route publique
  `/sites/:slug` → `SitePublicPage` → `AppRenderer` runtime, type « Site »
  dans `NewItemButton` avec champ slug.

**Hors périmètre (SP-13b/c ou différé) :**
- Widgets `Hero`/`RichSection`/`Gallery`/`DatasetCard` (SP-13b/c).
- Téléchargement de dataset, template galerie « Portail de données » (SP-13c).
- Domaine personnalisé (A33), résolution par host, `?tenant=` (multi-tenant
  public).
- Métriques d'usage, fonctions communautaires (A38).

## 4. Architecture — cœur (extension du module `items`, pas de nouveau module)

### 4.1 Migration Alembic
- Ajout `items.slug` (`String`, **nullable**).
- Index d'unicité **partiel** : `UNIQUE (tenant_id, slug) WHERE slug IS NOT
  NULL`. Deux tenants peuvent porter le même slug ; les items non-`site`
  restent `slug = NULL` sans contrainte d'unicité.
- Numéro de migration : suivant de la dernière tête Alembic au moment de
  l'exécution (0015 attendu, à confirmer par `alembic heads` en début de plan).

### 4.2 Génération et validation de slug
- Fonction pure `slugify(text: str) -> str` : minuscules, translittération
  ASCII, espaces/ponctuation → tirets simples, pas de tiret en tête/queue,
  chaîne vide → repli déterministe (p. ex. `site`).
- Résolution de collision `ensure_unique_slug(session, tenant_id, base) -> str`
  : si `base` est déjà pris pour le tenant, suffixe `-2`, `-3`… jusqu'au
  premier libre. Appelée à la création d'un `site` quand aucun slug n'est
  fourni **ou** quand le slug fourni entre en collision à la création (choix
  produit tranché en plan : à la création on résout silencieusement ; à
  l'édition explicite on renvoie 409 — voir 4.4).
- Validation de format `is_valid_slug(slug) -> bool` : `^[a-z0-9]+(?:-[a-z0-9]+)*$`,
  longueur bornée (p. ex. ≤ 100). Rejet 422 (format) distinct du 409 (collision).

### 4.3 Route publique `GET /public/sites/{slug}`
- Nouveau handler dans `core/app/public/routes.py`, miroir exact de
  `get_public_item` : délègue à un nouveau
  `items_repo.get_published_site_by_slug(session, *, slug, tenant_id="default")`
  qui `SELECT ... WHERE resource_type='site' AND slug=:slug AND
  tenant_id='default' AND is_published IS TRUE`, joint `User.username` comme
  `get_published_item`, retourne `ItemRead | None`.
- `None` → `HTTPException(404)`. **Jamais 403** : un site non publié, inexistant
  ou d'un autre tenant est indistinguable (pas de fuite d'existence — même
  politique que `GET /public/items/{id}`).
- Le rendu de la config est servi par la route publique **déjà existante**
  `GET /public/configs/by-item/{item_id}` (`core/app/public/routes.py`, accès
  anonyme) — aucune route de config nouvelle côté cœur. Cette route est le
  chemin anonyme correct : `GET /configs/by-item/{id}` exige `get_current_user`
  (401 sans jeton), inutilisable par un visiteur public.

### 4.4 Édition du slug
- `PATCH /items/{id}` accepte un champ `slug` optionnel dans son schéma de
  mise à jour. Chemin d'autorisation **inchangé** (`can()` + tenant du
  principal authentifié).
- Validation : format (422 si invalide) puis unicité **explicite** (409 si le
  slug demandé est déjà pris par un autre item du même tenant — pas de
  résolution silencieuse à l'édition, contrairement à la création).
- Un slug sur un item non-`site` : rejeté (422) ou ignoré — tranché en plan
  (recommandation : rejet 422, le slug n'a de sens que pour un `site`).

### 4.5 Autorisation et isolation
- **Aucun nouveau chemin d'autorisation** : un `site` est un item comme un
  autre (héritant de `can()`, de la politique de publication SP-1c et de
  `audit_log`). La revue finale de branche doit vérifier explicitement
  qu'aucune route — en particulier `GET /public/sites/{slug}` — ne contourne
  cette frontière.
- **Isolation tenant sur les slugs** : testée explicitement (même slug, deux
  tenants distincts ; la route publique ne sert que le tenant par défaut,
  l'homonyme de l'autre tenant reste 404).

## 5. Architecture — shell

- `api/types.ts` :
  - `Item.slug?: string`.
  - `ResourceType` : ajoute `"site"` (`"app" | "dashboard" | "map" | "site"`).
  - `CreateKind` : ajoute `"site"` (`"app" | "dashboard" | "site"`).
- `ItemClient` :
  - `getItemBySlug(slug: string): Promise<Item>` → `GET /public/sites/{slug}`
    (propage 404 en `null`/erreur typée pour que la page distingue introuvable).
    **Première méthode `/public/*` du shell** : `itemClient` n'appelle
    aujourd'hui aucune route publique (le runtime `/apps/:pk` existant passe
    par `getAppConfig` authentifié).
  - `getPublicAppConfig(pk: string): Promise<AppConfig>` → `GET /public/configs/
    by-item/{pk}` : **nouvelle méthode shell** appelant la route publique cœur
    **déjà existante**. Nécessaire car `getAppConfig` cible `/configs/by-item/{pk}`
    qui exige l'auth (401 anonyme) — un visiteur de site ne peut pas l'utiliser.
  - `createConfigItem` absorbe `kind: "site"` avec un `slug?: string`
    optionnel dans son input (pas de méthode de création dédiée si le contrat
    existant l'absorbe — confirmé faisable, `createConfigItem` renvoie déjà
    `Item`).
  - L'édition du slug réutilise le chemin `updateItem`/`PATCH` existant
    (`UpdatePatch` gagne `slug?`).
- **Route publique** `/sites/:slug`, déclarée hors `ProtectedLayout` dans
  `shell/src/shell/routes.tsx` (à côté de `/apps/:pk/:pageId?`) → nouveau
  `SitePublicPage(slug)` :
  1. `getItemBySlug(slug)` ; sur 404 → page « Introuvable » générique (aucun
     détail sur l'existence du slug).
  2. sinon `getPublicAppConfig(item.pk)` → `AppRenderer(config, "runtime")`.
- `NewItemButton` : ajoute l'option « Site » au sélecteur de type, avec un
  champ **slug** :
  - auto-généré depuis le titre à la frappe (slugify côté client, même
    algorithme conceptuel que le cœur — écho documenté, cf. CEL/A8, pas une
    frontière),
  - éditable,
  - validation de format côté client (bouton désactivé si invalide),
  - erreur inline serveur (409) si le slug entre en collision à la création
    explicite.
  Après création, ouvre dans le builder comme un item normal.

## 6. Points d'attention d'intégration

### 6.1 `resource_type` reste une chaîne libre
Vérifié : `core/app/items/models.py` déclare `resource_type: Mapped[str]` sans
`Literal`/enum, et aucun schéma Pydantic ne contraint la valeur — ajouter
`"site"` ne casse aucune validation existante. Côté shell, `ResourceType` est
une union TS à élargir (types générés + `itemClient` écrit à la main).

### 6.2 Dérive OpenAPI / types générés
Toute modification de schéma cœur (champ `slug` sur `ItemRead`/`UpdatePatch`,
nouvelle route publique) impose de régénérer `core/openapi.json` et
`shell/src/api/generated/core-schema.d.ts` — le job CI `api-types-drift`
échouera sinon (patron récurrent SP-9/SP-10/storytelling).

### 6.3 Round-trip du champ `slug` côté shell
Rappel de la classe de bug `visibleWhen`/`navigationMode` (SP-5b,
storytelling) : si `itemClient` reconstruit un `Item` champ par champ, `slug`
doit être explicitement propagé en lecture **et** en écriture — vérifié par un
test dédié, pas seulement supposé.

## 7. Tests

**Cœur (pytest) :**
- `slugify` déterministe (accents, ponctuation, casse, chaîne vide → repli).
- `ensure_unique_slug` : collision → suffixe numérique croissant.
- Unicité `(tenant_id, slug)` partielle : deux `site` même slug même tenant →
  rejet ; deux non-`site` `slug=NULL` → aucun rejet ; même slug, deux tenants →
  aucun rejet.
- `GET /public/sites/{slug}` : 200 si `site` publié sur `default` ; 404 si non
  publié, inexistant, non-`site`, ou d'un autre tenant (**jamais 403**).
- **Isolation tenant** : même slug pour tenant `default` et tenant `acme` ; la
  route ne sert que `default`, l'item d'`acme` reste 404 (matrice tenant×slug,
  symétrique aux matrices rôle×action du projet).
- `PATCH /items/{id}` avec `slug` : format invalide → 422 ; collision → 409 ;
  slug valide libre → 200 et persistance.

**Shell (Vitest) :**
- `SitePublicPage` (MSW) : cas 200 rend `AppRenderer` ; cas 404 rend la page
  « Introuvable » sans détail.
- Création type `site` : slug auto-généré depuis le titre, éditable, validation
  de format (bouton désactivé sur format invalide), erreur inline sur 409.
- Round-trip `slug` dans `itemClient` (lecture + écriture, cf. 6.3).

**E2E (nouvelle spec `sites-portal-shell.spec.ts`) :**
1. Catalogue → « Nouveau → Site » → titre (slug auto-généré) → créé, ouvert
   dans le builder.
2. Publier via la mécanique existante.
3. Session anonyme → visiter `/sites/{slug}` → `AppRenderer` runtime rendu
   (même vide, un conteneur runtime identifiable).
4. Un site **non publié** → `/sites/{slug}` rend la page « Introuvable », sans
   fuite sur son existence.

## 8. Critères d'acceptation

- Un admin crée un item type `site` avec un slug (auto-généré, éditable),
  le publie, et un visiteur anonyme le consulte à `/sites/{slug}` — le runtime
  `AppRenderer` s'affiche (même sans widget de contenu).
- Un slug peut être édité après création ; une collision renvoie 409 côté
  serveur, surfacée inline côté shell.
- Un site non publié / inexistant / d'un autre tenant renvoie une page
  « Introuvable » (404 serveur), jamais un 403 ni aucune fuite d'existence.
- La revue finale de branche confirme qu'aucun chemin (notamment
  `GET /public/sites/{slug}`) ne contourne `can()`/la politique de publication.
- Toutes les specs E2E existantes (38, incluant `storytelling.spec.ts`)
  restent vertes ; la nouvelle spec `sites-portal-shell.spec.ts` porte le total
  à 39.

## 9. Risques

| Risque | Gravité | Garde-fou |
|---|---|---|
| Confusion de tenant par résolution de slug | ★★★ (sécurité) | Test d'isolation tenant×slug dédié ; route figée sur tenant `default` en v1 ; revue finale vérifie l'absence de contournement d'autorisation |
| Fuite d'existence d'un site non publié (403 au lieu de 404) | ★★ | Politique 404-toujours testée explicitement (non publié / autre tenant / inexistant indistinguables) |
| Perte silencieuse du champ `slug` au round-trip shell | ★★ | Test de round-trip lecture+écriture dédié (classe de bug `visibleWhen`/`navigationMode`) |
| Dérive OpenAPI / types générés | ★ | Régénération `openapi.json`/`core-schema.d.ts` en fin de sous-phase, job CI `api-types-drift` |

## 10. Estimation

Socle cœur + shell d'ampleur comparable à SP-6a / SP-8a : **≈ 15-25 h**, une
seule sous-phase livrable, exécutable en TDD (subagent-driven ou executing-plans
selon le découpage du plan).
