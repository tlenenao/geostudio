# SP-13 — Portails & Sites : design

> Chantier dédié (arbitrage **A35**, tranché le 2026-07-14 —
> [gap analysis dataviz/analytics](../../vision/geostudio-dataviz-analytics-gap-analysis.md)
> §3.9/§7.3/§9.2, validé par Tanguy). S'exécute **après SP-11, avant SP-12/SP-17**
> (A34) ; son ordre relatif à SP-14 est libre (chantiers mutuellement
> indépendants). Dépend uniquement de SP-11 au sens large (aucune dépendance
> technique dure — un portail v1 fonctionne déjà avec les seuls items publiés
> existants ; SP-11 conditionne surtout la maturité produit générale avant
> d'ouvrir un nouveau front public).

## 1. Contexte et objectif

**Constat.** Un item GeoStudio publié est une URL isolée. Il n'existe aucune
façade publique regroupant plusieurs items sous une identité de marque,
éditorialisée, découvrable — le manque structurel face à ArcGIS Hub, CKAN ou
un portail data.gouv.fr thématique (voir gap analysis §3.9). C'est un manque
commercial direct pour la cible collectivités (persona n° 8 de la vision),
qui a une obligation de communication et d'open-data.

**Objectif.** Un admin construit, **sans code et sans nouvel outil** (le
builder existant, augmenté de quelques widgets de contenu), un portail public
de marque : page d'accueil éditoriale, galerie de découverte filtrable des
items publiés, fiches de jeux de données téléchargeables — publié sur une URL
stable.

## 2. Décisions actées pour ce chantier

Rappel des arbitrages tranchés le 2026-07-14 (à ne pas rediscuter dans
l'exécution de ce SP ; toute révision passe par une mise à jour explicite de
la feuille de route) :

| # | Sujet | Décision |
|---|---|---|
| A31 | Modèle de config du portail | **Sous-gabarit d'`AppConfig`** — un seul runtime `AppRenderer`, pas de deuxième moteur |
| A33 | Domaine personnalisé | **Différé** — v1 accessible via `/sites/{slug}`, pas de domaine tiers |
| A34/A35 | Structure et séquencement | **SP dédié (SP-13)**, exécuté après SP-11, avant SP-12/SP-17 |
| A38 | Fonctions communautaires | **Différées** (commentaires, follow, discussions) — hors périmètre v1 |

## 3. Périmètre

**Dans le périmètre v1 :**
- Nouveau type d'item **`site`** (à côté de `app`/`dashboard`/`map`), même
  table `items`, même `can()`, même `audit_log`, mêmes révisions de config
  (`configs`/`config_revisions` inchangés).
- `items.slug` (nouvelle colonne) : requis et unique **par tenant** pour le
  type `site`, généré par défaut depuis le titre (slugification déterministe,
  collision → suffixe numérique), éditable par l'auteur.
- Route publique **`GET /public/sites/{slug}`** : miroir exact de
  `GET /public/items/{id}` (SP-1c), indexé par slug — un site non publié ou
  inexistant renvoie 404 (jamais 403, pour ne pas fuiter son existence — même
  politique que les items aujourd'hui).
- Route shell publique `/sites/:slug` : résout l'item par slug, délègue à
  `AppRenderer` en mode `runtime` — **aucun nouveau composant de rendu**.
- Nouveaux **widgets de contenu**, enregistrés dans le registre existant
  (`registerWidget`) et disponibles pour **tout** type d'item (pas restreints
  aux sites — un dashboard peut aussi vouloir un bloc de texte) :
  - `Hero` : titre, sous-titre, image de fond, bouton d'appel à l'action.
  - `RichSection` : bloc de texte (markdown simple, pas d'éditeur WYSIWYG
    riche — périmètre fermé, cf. risques §7).
  - `Gallery` : grille de vignettes cliquables des items publiés,
    filtrable par tag/type (consomme `listItems(scope: "public")` existant).
  - `DatasetCard`/`DatasetPage` : fiche d'une collection publique
    (description, aperçu carte/table en lecture seule, lien de
    téléchargement).
- Téléchargement multi-format **v1, volontairement limité** :
  - GeoJSON via l'URL OGC API Features déjà exposée par la collection (SP-3,
    aucune nouvelle brique).
  - CSV généré **côté client** à partir des features déjà chargées pour
    l'aperçu — borne explicite de volumétrie (message clair au-delà d'un
    seuil, pas de blocage silencieux ni de timeout navigateur).
  - **Assumé et documenté** : pas d'export DCAT-AP/STAC (attend SP-12), pas
    d'export serveur pour gros volumes (attend SP-16) — le portail v1 sert la
    découverte et le petit volume, pas le catalogue interopérable complet.
- Gestion : le catalogue existant (création/édition/partage/publication)
  gère un item `site` comme n'importe quel autre item ; seule la création
  demande un champ slug en plus.

**Hors périmètre v1 (différé, pas oublié) :**
- Domaine personnalisé (A33).
- Fonctions communautaires : commentaires, abonnement/follow, discussions
  (A38).
- Métriques d'usage (vues, téléchargements) — extension naturelle
  d'`audit_log` déjà append-only, mais pas dans ce SP.
- Export DCAT-AP/STAC des fiches dataset (SP-12).
- Export CSV/XLSX serveur pour gros volumes (SP-16).
- Éditeur de contenu riche façon CMS (blocs avancés, mise en page libre) —
  `RichSection` reste un bloc markdown simple en v1.

## 4. Architecture

### 4.1 Cœur (extension du module `items` existant — pas de nouveau module)

- Migration Alembic : `items.slug` (nullable pour les types autres que
  `site` ; contrainte d'unicité composite `(tenant_id, slug)` où `slug` non
  nul).
- `items.type` gagne la valeur `"site"` (enum déjà extensible, comme les
  types existants).
- Génération de slug : fonction pure (slugify + résolution de collision par
  suffixe numérique), appelée à la création si aucun slug n'est fourni,
  validée à la mise à jour (format, unicité) avec 409 explicite en cas de
  collision.
- Nouvelle route `GET /public/sites/{slug}` (`core/app/public/routes.py`) :
  résout par `(tenant par défaut ou déduit du host, slug)`, réutilise
  **exactement** la fonction de vérification de publication déjà utilisée par
  `GET /public/items/{id}`.
- Aucune nouvelle logique d'autorisation : un site suit `can()` et la
  politique de publication en place depuis SP-1c, sans exception.

### 4.2 Shell

- `api/types.ts` : `Item.slug?: string` ; nouveau type d'item `"site"` dans
  les unions existantes.
- `ItemClient` : `getItemBySlug(slug)` pour la résolution publique ; création
  d'un item `site` réutilise `createConfigItem` existant avec le champ slug
  en plus (pas de nouvelle méthode de création dédiée si le contrat existant
  l'absorbe — **à confirmer en plan**).
- Nouvelle route shell publique `/sites/:slug` (hors `RequireAuth`, comme les
  items publiés existants aujourd'hui), qui appelle `getItemBySlug`, gère le
  404 (page « introuvable » générique, pas de détail sur l'existence du slug),
  puis rend `AppRenderer(config, "runtime")`.
- `CreateItemDialog` : nouveau type « Site » à côté de Carte/App/Dashboard,
  avec champ slug (auto-généré depuis le titre, éditable, validation de
  format côté client + erreur inline serveur sur collision).
- Widgets `Hero`/`RichSection`/`Gallery`/`DatasetCard` : nouveaux fichiers
  sous `shell/src/builder/widgets/`, mêmes conventions que les widgets
  existants (props typées, tests co-localisés, enregistrement dans
  `registry.ts`/`index.tsx`).
- `templates.ts` : nouvelle entrée galerie « Portail de données » (site
  pré-câblé : Hero + Gallery + une `DatasetCard` d'exemple).

### 4.3 Sécurité et gouvernance

- **Aucun nouveau chemin d'autorisation** : un site est un item comme un
  autre, il hérite de `can()`, de la politique de publication et de l'audit
  déjà en place — la revue finale de branche doit vérifier explicitement
  qu'aucune route (notamment `GET /public/sites/{slug}`) ne contourne cette
  frontière (même exigence que chaque SP touchant à la sécurité depuis SP-1c).
- **Isolation tenant sur les slugs** : un même slug peut exister pour deux
  tenants distincts sans collision ni fuite d'information croisée — testé
  explicitement (matrice tenant×slug, symétrique aux matrices rôle×action
  déjà exigées par le projet).

## 5. Flux

1. **Création** : catalogue → « Nouveau → Site » → titre (+ slug
   auto-généré, éditable) → ouvre dans le builder comme un item normal.
2. **Édition** : l'auteur ajoute Hero/RichSection/Gallery/DatasetCard depuis
   la palette existante (drag-and-drop, aucune nouvelle UX à apprendre) →
   Enregistrer (révision, comme tout `AppConfig`).
3. **Publication** : mécanique de partage/publication existante (SP-1c),
   inchangée.
4. **Consultation publique** : `/sites/{slug}` → `GET /public/sites/{slug}`
   → 404 si non publié/inexistant → `AppRenderer(config, "runtime")`.
5. **Téléchargement** : bouton sur `DatasetCard` → GeoJSON via l'URL OGC API
   Features existante (publique si la collection est publique) ; CSV généré
   côté client pour les volumes sous le seuil documenté.

## 6. Tests

**Cœur (pytest) :**
- Migration `items.slug` : unicité par tenant, nullable pour les non-sites.
- Génération de slug déterministe + résolution de collision.
- `GET /public/sites/{slug}` : 200 si publié, 404 si non publié/inexistant
  (jamais 403), isolation tenant (même slug, deux tenants, aucune collision
  ni fuite).
- Garde d'unicité à la mise à jour du slug (409 si collision).

**Shell (Vitest) :**
- Nouveaux widgets (`Hero`, `RichSection`, `Gallery`, `DatasetCard`) :
  rendu, états loading/vide/erreur.
- Résolution de route `/sites/:slug` (mock MSW) : cas 200, cas 404.
- Création d'item type `site` avec validation de slug (format, collision).
- `Gallery` : filtrage par tag/type, rendu de la grille.

**E2E (nouvelle spec `sites-portal.spec.ts`) :**
1. Créer un site depuis le catalogue → ajouter Hero + Gallery +
   DatasetCard → publier.
2. Visiter `/sites/{slug}` en session anonyme → la galerie affiche les items
   publics attendus (et aucun item non publié).
3. Ouvrir la fiche dataset → télécharger le GeoJSON.
4. Un site non publié renvoie une page « introuvable », sans fuite
   d'information sur son existence.

## 7. Critères d'acceptation

- Un admin construit, depuis le builder existant sans nouvelle formation, un
  portail avec page d'accueil éditoriale + galerie de découverte + au moins
  une fiche dataset téléchargeable, publié sur une URL stable `/sites/{slug}`.
- Un visiteur anonyme parcourt le portail et télécharge un jeu de données
  sans jamais voir un item non publié.
- Toutes les specs E2E existantes (incluant `storytelling.spec.ts` si livrée
  avant ce SP) restent vertes.
- La revue finale de branche confirme qu'aucun chemin ne contourne
  `can()`/la politique de publication existante.

## 8. Risques

| Risque | Gravité | Garde-fou |
|---|---|---|
| Confusion de tenant par résolution de slug | ★★★ (sécurité) | Test d'isolation tenant×slug dédié avant toute activation |
| Dérive vers un CMS complet (`RichSection` qui enfle) | ★★ | Périmètre fermé explicitement dès la spec : un bloc markdown simple, pas d'éditeur riche façon Wordpress |
| Téléchargement CSV client-side dégradé sur gros volumes | ★ (assumé) | Borne explicite + message clair ; levé naturellement par SP-16 (export serveur) |
| Le chantier dilue encore la route d'un solo à 10–25 h/sem | ★★ | Périmètre v1 volontairement étroit (A33/A38) ; sous-phases livrables à la rédaction du plan, sur le modèle SP-4/SP-8 |

## 9. Estimation

Par analogie avec des chantiers shell+cœur de complexité comparable déjà
livrés (SP-4 formulaires ≈ 60–110 h, SP-8 SDK Web Components ≈ 60–110 h) :
**≈ 60–100 h**, découpable en sous-phases livrables (a. modèle `site`/slug +
route publique + résolution shell ; b. widgets de contenu (Hero/RichSection/
Gallery) ; c. fiche dataset + téléchargement + template galerie), sur le
modèle des sous-phases déjà pratiqué pour SP-1/SP-6/SP-8.
