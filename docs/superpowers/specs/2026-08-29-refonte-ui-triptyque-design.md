# Refonte de l'interface du shell : socle triptyque (SP-29 → SP-33)

> Brainstormée et validée avec Tanguy le 2026-08-29. Diagnostic de l'existant,
> quinze directions d'UI globale étudiées, socle « triptyque universel »
> retenu. Maquettes de référence, versionnées avec cette spec :
> `docs/design/maquettes-geostudio.html` (les trois socles candidats, la palette
> et la typographie proposées) et `docs/design/triptyque-geostudio.html` (le
> socle retenu, affiné : les neuf domaines, huit écrans maquettés, les droits
> utilisateurs, la déclinaison à 390 px). Ce sont des pages autonomes, à ouvrir
> dans un navigateur — elles sont la référence visuelle de SP-30.
>
> Ce document est le **design du chantier entier**. Seul SP-29 y est spécifié
> au niveau d'exécution (§10) ; SP-30 à SP-33 y ont leur périmètre et leurs
> critères de sortie (§9) et recevront chacun leur propre spec.

## 1. Contexte & objectif

Vingt-huit SP ont livré un cœur qui moissonne, tuile, chiffre des secrets,
planifie des rapports et se fait piloter par un agent. Rien de tout cela n'a
d'interface à la hauteur.

Mesures faites le 2026-08-29 sur `shell/src` (18 486 lignes de TSX, fichiers de
test exclus), croisées avec les 108 routes du cœur :

- **Aucun système de design, au sens littéral.** `shell/src/index.css` contient
  une ligne : `@import "tailwindcss";`. Pas de `tailwind.config`, pas de token,
  pas d'échelle typographique. 38 classes de couleur distinctes, dont 348
  occurrences de `slate` et 116 de `red` : la palette de fait est le gris
  d'usine plus le rouge des erreurs.
- **Le produit ne s'applique pas le thème qu'il vend.** `shell/src/builder/theme.ts`
  définit `DEFAULT_THEME_COLORS` (primary, background, surface, text, muted,
  border), `DEFAULT_FONT`, `DEFAULT_RADIUS`, `DEFAULT_SPACE`, éditables par
  l'utilisateur dans `ThemePanel.tsx` et appliqués aux apps générées. Le shell
  ne les consomme jamais. Le système à installer n'est pas à inventer : il est
  déjà spécifié, testé et exposé — jamais retourné vers l'intérieur.
- **« Adaptable » n'existe pas.** 5 usages de breakpoint sur tout le shell
  (`sm:` ×4, `lg:` ×1), 0 occurrence de `dark:`. Largeurs d'éditeur en dur :
  `w-48`, `w-64`, `w-72`.
- **Quatre primitives pour douze types d'objets.** `ui/{button,card,input,dialog}.tsx`,
  et `Card` n'est importée que par `ui/ItemCard.tsx`. Face à 36 fichiers
  important `Button` : **139 `<button>` bruts**, **159 `<input>` bruts**, et
  **83 `<select>` bruts pour zéro primitive Select**.
- **Les éditeurs sont des empilements verticaux.** `pages/AppBuilderPage.tsx`
  (454 lignes) empile treize panneaux dans un `aside` de 192 px, sans onglet ni
  accordéon : Widgets, Pages, Sources, Actions, Navigation, Interactions,
  Variables, Thème, Impression, Historique, Export, Copilote.
  `pages/MapEditorPage.tsx` applique le même patron dans 288 px.
- **La navigation ignore les deux tiers du produit.** `shell/AppLayout.tsx` :
  un `<nav class="w-48">` de cinq `<Link>` en texte brut, sans icône, sans état
  actif, pour dix-sept routes protégées et douze types d'objets. `/bookmarks`,
  `/reports`, `/pipelines/new` et `/datasets/visual-query/new` n'ont **aucune
  entrée de navigation**.
- **L'interface ment sur les droits.** `shell/ItemActions.tsx` affiche Modifier,
  Partager, Publier et Supprimer sur **chaque** item du catalogue. Le type
  `Item` (`shell/src/api/types.ts:18-30`) et le schéma `ItemRead`
  (`core/app/items/schemas.py:5-16`) ne portent aucune permission : le shell
  n'a rien pour décider, et c'est l'API qui renvoie 403 après le clic.
- **Neuf capacités livrées du cœur n'ont aucun écran** : coffre de secrets
  (3 routes, `core/app/secrets/routes.py`), journal d'audit, file de tâches
  `procrastinate`, fédération STAC/DCAT, utilisateurs et groupes, recherche
  sémantique (SP-7), bibliothèque d'icônes, vue d'ensemble des alertes,
  gestion 3D.

**Objectif du chantier** : installer pour la première fois un système de
design, un socle de navigation qui couvre la totalité du produit, et une
interface qui dit la vérité sur ce que la personne a le droit de faire.

## 2. Arbitrages tranchés en session (2026-08-29)

| # | Sujet | Décision |
|---|---|---|
| A1 | Premiers utilisateurs | Équipe SIG / analystes (experts, clavier, double écran) |
| A2 | Suite E2E | **Réécriture au fil du chantier** — le vocabulaire de l'interface est libre |
| A3 | Accessibilité | **WCAG AA visé, sans audit formel ni déclaration RGAA** |
| A4 | Kit de composants | **Primitives headless + nos tokens** (pas shadcn copié, pas de kit maison intégral) |
| A5 | Identité | **Identité GeoStudio propre + marque blanche par tenant** |
| A6 | Périmètre fonctionnel | **Les neuf capacités sans écran entrent au périmètre** |
| A7 | Stratégie de bascule | **Fondation complète, puis bascule d'un bloc** — jamais deux styles à l'écran |
| A8 | Découpage | Le bloc = **le shell existant** ; les surfaces neuves arrivent après, additives |
| A9 | Runtime des apps | **Studio seulement** — `AppRenderer` et les 41 widgets ne sont pas refondus |
| A10 | Adaptabilité | **Bureau prioritaire, aucun écran ne casse jusqu'à 390 px** ; outils carte tactiles hors périmètre |
| A11 | Mode sombre | **Oui, dès la fondation** — chaque token défini dans les deux ambiances |
| A12 | Internationalisation | **Extraire tous les libellés**, ne livrer que le français |
| A13 | Socle | **Triptyque universel** (option B des trois candidats) |
| A14 | Propriété d'une tâche | **Le créateur de la tâche**, y compris pour une exécution planifiée |
| A15 | Noms de secrets | **Visibles des administrateurs seulement** — ni valeur ni référence pour les autres |

**Conséquence assumée de A9** : le panneau d'aperçu du builder affichera des
widgets à l'ancienne esthétique à l'intérieur d'un studio refait. C'est un
aperçu — il est censé ressembler à l'app publiée, pas au studio.

## 3. Le socle : la loi du triptyque

Trois volets, appliqués **sans exception** à tous les écrans du produit.

### 3.1 — Volet 1, Parcourir

Le navigateur. Deux onglets courts : la **source locale** (couches, étapes de
pipeline, schémas SQL, sections d'administration) et le **Catalogue**, toujours
présent, jamais à plus d'un clic. Recherche en tête, facettes en dessous.
Repliable par raccourci.

### 3.2 — Volet 2, Travailler

La surface propre à l'objet : carte, canevas d'app, graphe DAG, éditeur SQL,
tableau, formulaire. C'est le **seul** volet dont la nature change d'un écran à
l'autre. Toute barre d'outils flottante vit ici et nulle part ailleurs.

### 3.3 — Volet 3, Inspecter — et il n'est jamais vide

C'est la règle qui rend le triptyque applicable partout, y compris à SQL Lab et
au journal d'audit — les deux écrans qui semblaient l'invalider :

> L'inspecteur montre **la sélection courante**. En l'absence de sélection, il
> montre **l'objet courant lui-même** : métadonnées, partages, versions,
> lignage.

Exemples : dans SQL Lab, une colonne de résultat sélectionnée donne son type,
ses valeurs distinctes, ses nulls et sa distribution ; sans sélection, c'est la
requête (limite, délai, moteur, historique). Dans le builder, un widget
sélectionné donne ses propriétés ; sans sélection, c'est l'app (thème,
variables, navigation, interactions, impression, export, historique, copilote)
— les treize panneaux d'aujourd'hui sont tous là, mais plus **tous là en même
temps**.

### 3.4 — Zéro boîte de dialogue

Toute création et toute configuration est un parcours dans les volets ou une
route plein écran avec rail d'étapes. Les **seize fichiers qui rendent
aujourd'hui un `<Dialog>`** — dont sept composants dédiés `*Dialog.tsx` —
disparaissent.

**Unique exception, explicite** : la confirmation d'une action destructive
(supprimer un item, révoquer un partage, purger un secret). Un parcours plein
écran pour confirmer une suppression serait absurde. `ConfirmDialog` survit,
correctement outillé cette fois (`aria-modal`, piège de focus, restitution du
focus, verrou de défilement — aucun de ces quatre points n'est traité par
`ui/dialog.tsx` aujourd'hui).

### 3.5 — Barre de domaines

Neuf entrées (§4), calculées depuis les droits (§6.6). Deuxième ligne du chrome,
sous la barre supérieure.

### 3.6 — Barre supérieure et ⌘K

Marque, omnibox `⌘K`, avatar. L'omnibox est **le seul champ de recherche
globale** : elle interroge la recherche sémantique du catalogue (SP-7, pgvector
+ RRF, aujourd'hui sans aucune interface) et la liste des commandes disponibles
pour le compte courant.

### 3.7 — Barre d'état

Tâches en cours, échecs, tenant, version. Présente sur tous les écrans : c'est
par elle que la file `procrastinate` cesse d'être invisible.

### 3.8 — Le catalogue en colonne vertébrale

Le catalogue n'est plus une page d'accueil qu'on quitte. Il est le **second
onglet du volet gauche de chaque écran** : ajouter une couche à une carte, une
source à un pipeline, un dataset à un widget se fait sans changer d'écran.

Sa forme pleine (domaine « Catalogue ») gagne quatre vues sur le même jeu de
résultats : **grille**, **tableau**, **carte** (situer les items ayant une
emprise) et **lignage** (le graphe donnée → pipeline → dataset → carte → app).
La vue lignage est la seule concession faite à la direction « toile infinie »
étudiée puis écartée : elle devient une vue du catalogue, pas un socle.

## 4. Les neuf domaines

| Domaine | Parcourir | Travailler | Inspecter |
|---|---|---|---|
| **Catalogue** | Recherche texte + sémantique¹, facettes sur les 12 types, portée, collection, propriétaire, date | Grille · Tableau · Carte¹ · Lignage¹ — tri, sélection multiple, actions groupées | Fiche complète : miniature, métadonnées, partages, versions, objets liés, actions |
| **Cartes** | Couches · Catalogue | Carte plein volet, mesure, croquis, fond, terrain, tuiles 3D | Symbologie, étiquettes, popup, opacité, contour, icônes |
| **Données** | Collections · Catalogue | Table des entités, aperçu carte, requête visuelle, imports | Champ sélectionné : type, distinctes, nulls, RLS, `canWrite` |
| **Apps & sites** | Structure des pages · Palette de widgets · Catalogue | Canevas d'app, aperçu, mode narratif, pages du site | Propriétés du widget, liaisons CEL, variables, thème, impression, export |
| **Automatisation** | Étapes · Catalogue · Connecteurs · Secrets¹ (admin) | Graphe DAG, planification cron, règles d'alerte, rapports planifiés | Nœud : paramètres, aperçu de sortie, secret utilisé (admin) |
| **Analytique** | Schémas et tables · Vues enregistrées · Catalogue | SQL Lab, requête visuelle, agrégats, cross-filter | Colonne de résultat, ou la requête elle-même |
| **Tâches**¹ | Filtres : état, type, objet, période | File d'exécution : imports, moissonnages, pipelines, exports, rapports | Tâche : objet lié, durée, tentatives, journal, relance |
| **Administration**¹ | Utilisateurs¹, groupes¹, collections, extensions, moissonnage, audit¹, secrets¹ | Tableau de la section, journal d'audit filtrable | Entrée : rôles, appartenances, ou le diff d'une écriture auditée |
| **Paramètres**¹ | Instance, marque & thème, apparence, langue, capacités, observabilité, sauvegarde | Formulaire de la section — un écran par sujet, aucun dialogue | Aperçu en direct, et ce que le réglage affecte |

¹ Surface sans aucun écran aujourd'hui.

## 5. Système de design

### 5.1 — Contrat de tokens

Une seule couche de tokens CSS, définie dans `shell/src/styles/tokens.css`,
exposée à Tailwind v4 via `@theme` et consommée par tout le shell.

Familles : `--color-*` (fond, surface, surélevé, encre à trois niveaux, filets,
accent + variantes, quatre sémantiques, quatre tokens de carte),
`--font-*`, `--text-*` (échelle typographique), `--radius-*`, `--space-*`,
`--shadow-*`.

**Relation au `Theme` des apps** — c'est le point de conception le plus
délicat du chantier, et il se tranche ainsi :

- Le contrat de nommage est **partagé** : les six couleurs du `Theme` des apps
  (`primary`, `background`, `surface`, `text`, `muted`, `border`) plus police,
  rayon et espacement sont **exactement** les tokens que le studio consomme.
  C'est ce qui rend la marque blanche possible sans deuxième système.
- Mais les deux ne sont **pas la même instance** : le thème d'une app est choisi
  par son auteur et s'applique au rendu de cette app ; les tokens du studio sont
  choisis par le tenant. Un thème d'app violet ne repeint pas le studio de son
  auteur. Le `Theme` d'app reste porté par sa config (aucun changement de
  schéma) ; le thème du tenant est un objet de paramétrage nouveau.
- La palette du studio est **plus large** que celle des apps (encre à trois
  niveaux, filets, sémantiques, tokens de carte). Les six couleurs du contrat
  partagé sont les **entrées** ; les autres en sont dérivées ou fixes.

### 5.2 — Les deux ambiances (A11)

Chaque token est défini dans les deux ambiances dès le premier commit. Le
sombre n'est pas une inversion : contrastes recalculés, accent ajusté, et
tokens de carte propres (un fond de carte clair sur un studio sombre est
illisible).

### 5.3 — Typographie

Trois rôles : interface (grotesque technique, lisible à 10 px dans un
inspecteur dense), données et identifiants (monospace, `tabular-nums` partout
où des chiffres s'alignent), textes longs (documentation, descriptions).
Familles servies localement — aucun chargement depuis un CDN tiers : le shell
s'exporte en conteneur autoporté (SP-18) et se rend hors ligne dans le worker
d'export Playwright (SP-17).

### 5.4 — Identité et marque blanche (A5)

Identité GeoStudio par défaut ; un tenant peut redéfinir nom affiché, logo,
couleur d'accent et rayon. **Garde de contraste obligatoire** : l'écran de
paramétrage vérifie les ratios WCAG AA de la combinaison choisie sur les deux
ambiances et refuse d'appliquer une combinaison illisible. C'est le prix d'une
marque blanche honnête.

### 5.5 — Primitives headless (A4)

Un jeu de primitives accessibles habillées par nos tokens. **Le choix de la
bibliothèque n'est pas tranché dans cette spec** : il fait l'objet d'un spike
en tête de SP-29 (§10.2), parce que le texte d'un plan est régulièrement faux
sur les interfaces tierces (piège n°3 documenté). Le spike vérifie contre la
source réelle : compatibilité React 19, coût en poids ajouté au bundle,
licence compatible Apache-2.0, et comportement en rendu Playwright headless.
Candidat de départ : Radix UI Primitives ; alternatives à mesurer : Base UI,
Ark UI.

## 6. Droits utilisateurs

L'interface doit s'adapter aux droits **avant** de s'adapter à la largeur.

### 6.1 — Les cinq axes réels

1. **Rôles de compte** : `isAdmin`, `isAnalyst` (`core/app/users/models.py:25-26`,
   exposés par `GET /me`, `core/app/auth/routes.py:29-40`).
2. **Droits par objet** : `can(session, user_id, action, item, kind, actor_is_admin)`
   — `core/app/sharing/authorization.py:30`. Quatre actions
   (`read`/`write`/`delete`/`share`), deux types (`item`/`collection`), rôles de
   groupe `viewer`/`editor`, plus propriétaire, plus `is_public`/`is_published`.
   Le rôle admin ne court-circuite que les collections.
3. **Droits par collection** : RLS PostGIS + `canWrite`, déjà consommé par
   `builder/widgets/form.tsx:355` et `builder/pipeline/CollectionParamSelect.tsx:22`.
4. **Capacités d'instance** : sept drapeaux servis par `GET /instance`
   (`core/app/instance/routes.py:17-27`) — `readOnly`, `etlEnabled`,
   `exportEnabled`, `appExportEnabled`, `tileset3dEnabled`, `terrain3dEnabled`,
   `copilotEnabled`.
5. **Mode démo lecture seule** : `readOnly`, transversal aux quatre autres.

### 6.2 — Doctrine : trois traitements

| Traitement | Quand | Effet |
|---|---|---|
| **Absent** | L'accès supposerait un changement de rôle | Ni dans la barre de domaines, ni dans ⌘K, ni dans les volets. L'utilisateur n'apprend pas que ça existe. |
| **Verrouillé et expliqué** | L'utilisateur peut légitimement se demander pourquoi, ou pourrait obtenir le droit | Contrôle visible, désactivé, **avec la raison et le recours** (« Publier est réservé au propriétaire », « demandez le rôle éditeur à tanguy »). Jamais un cadenas muet. |
| **Lecture seule** | `read` accordé, `write` refusé | Même surface, sans les contrôles d'écriture. L'inspecteur cesse d'être un formulaire et devient une fiche. |

Règle de répartition entre les deux premiers : **un rôle manquant masque, une
capacité coupée verrouille**. Un rôle est une information sur la personne ; une
capacité est une information sur le déploiement, qu'un administrateur doit
pouvoir comprendre.

**Anti-règle** : aucun contrôle de l'interface ne doit produire un 403. Si le
cœur va refuser, l'UI le savait avant le clic.

**Contre-anti-règle** : le rendu conditionnel n'est *jamais* une frontière de
sécurité. Le cœur reste seul juge — c'est déjà écrit noir sur blanc dans
`CollectionParamSelect.tsx:5`, et cela ne change pas.

### 6.3 — Contrat d'API : les permissions dans le payload

`ItemRead` (`core/app/items/schemas.py:5`) gagne un champ :

```python
class ItemPermissions(BaseModel):
    read: bool
    write: bool
    delete: bool
    share: bool

class ItemRead(BaseModel):
    ...
    permissions: ItemPermissions
```

Calculé côté serveur depuis `can()`, **jamais** recalculé côté client. Même
traitement pour les collections (`canWrite` existe déjà, il devient un objet de
permissions complet) et pour `GET /me`, qui gagne les capacités d'instance afin
que le shell n'ait plus deux sources à croiser.

La couche `app.items` est autorisée à importer `app.sharing` : le contrat de
couches (`pyproject.toml`, liste des 30 entrées) place `app.sharing` sous
`app.items`. Aucune entrée de contrat n'est à ajouter.

### 6.4 — Le point dur : ne pas créer un N+1

`can()` appelle `has_group_role()` (`core/app/sharing/repository.py:11`), soit
une requête par item et par jeu de rôles. Appelé naïvement depuis `_to_read()`
(`core/app/items/repository.py:64`) sur une page de 12 items, cela ferait
jusqu'à 24 requêtes supplémentaires par affichage de catalogue.

**Mécanisme retenu** : une fonction de lot dans `app.sharing`,
`roles_for_items(session, *, tenant_id, user_id, item_ids) -> dict[str, set[str]]`,
qui fait **une** requête pour tous les items de la page, puis une évaluation en
mémoire des mêmes règles que `can()`. Pour garantir qu'elles ne divergent
jamais, `can()` est refactorée pour déléguer sa décision à une fonction pure
`decide(action, facts, roles, is_owner, actor_is_admin, kind) -> bool`, appelée
par les deux chemins. Un test de parité exhaustif compare les deux chemins sur
le produit cartésien des situations.

### 6.5 — Côté shell : une seule porte

Un composant unique, `shell/src/auth/Gate.tsx` :

```tsx
<Gate on={item} can="write" fallback="lock" reason="…">
  <Button>Modifier</Button>
</Gate>
```

Trois modes de repli : `hide`, `lock` (avec sa raison et son recours),
`readonly`. **Interdiction d'écrire une comparaison de droits ailleurs** —
`item.owner === me`, `meQuery.data?.isAdmin === true` et consorts disparaissent
des pages : **neuf occurrences dans cinq fichiers** aujourd'hui —
`SqlLabPage.tsx:40`, `AdminExtensionsPage.tsx:6,14`,
`HarvestSourcesAdminPage.tsx:20,30`, `CollectionsAdminPage.tsx:13,23`,
`AppLayout.tsx:65,84`. La règle vit à un seul endroit, testable — le pendant
côté UI de la porte unique du cœur.

### 6.6 — Dérivation des surfaces

La barre de domaines, les commandes de ⌘K, les onglets du volet gauche et les
sections de l'inspecteur se calculent depuis la même source
(`shell/src/auth/capabilities.ts`). Retirer un rôle fait disparaître le domaine
**et** ses commandes de la palette, sans code supplémentaire.

### 6.7 — Matrice domaine × profil

● complet · ◐ partiel ou verrouillé · ○ absent

| Domaine | Administrateur | Créateur | Analyste | Lecteur |
|---|---|---|---|---|
| Catalogue | ● | ● | ◐ lecture | ◐ lecture |
| Cartes | ● | ● | ◐ lecture | ◐ lecture |
| Données | ● | ◐ collections partagées | ◐ lecture | ○ |
| Apps & sites | ● | ● | ○ | ○ |
| Automatisation | ● | ◐ ses pipelines, aucun secret | ○ | ○ |
| Analytique | ● | ◐ sans SQL Lab | ● SQL Lab compris | ○ |
| Tâches | ● toutes | ◐ celles qu'il a créées | ◐ celles qu'il a créées | ○ |
| Administration | ● | ○ | ○ | ○ |
| Paramètres | ● instance & tenant | ◐ préférences | ◐ préférences | ◐ préférences |

Le mode démo se superpose à n'importe quelle colonne : il retire toute écriture
sans rien masquer, et l'annonce par un bandeau.

### 6.8 — Les deux arbitrages du 2026-08-29

**A14 — une tâche appartient à qui l'a créée.** Y compris une exécution
planifiée : c'est le créateur du cron qui la voit dans son domaine Tâches, pas
l'administrateur. Celui-ci voit toutes les tâches du tenant, en plus des
siennes. Conséquence à traiter : la file `procrastinate` doit porter
l'identité du déclencheur. À vérifier au moment du plan de SP-31 — si la
colonne n'existe pas, elle fait l'objet d'une migration Alembic, testée sur
base non vide dans les deux sens (piège n°8).

**A15 — les noms de secrets ne sont visibles que des administrateurs.** Ni la
valeur (jamais, pour personne : c'est déjà le contrat de SP-15e), ni la
référence. Un créateur ne voit donc pas la liste du coffre, et la section
« Secrets » du volet gauche du domaine Automatisation lui est **absente**.

Conséquence assumée, à spécifier dans SP-31 : un nœud de pipeline consommant un
secret affiche à un créateur *« Secret configuré par un administrateur »*, en
lecture seule. Il peut exécuter le pipeline ; il ne peut ni voir quel secret est
utilisé, ni le changer. Recâbler un secret est une action d'administrateur.
C'est plus restrictif que ce que le cœur impose aujourd'hui — c'est un choix
produit, pas une contrainte technique, et il est réversible.

## 7. Adaptabilité (A10)

Bureau prioritaire (cible 1280 px et au-delà), mais **aucun écran ne casse
jusqu'à 390 px**. La règle de dégradation est unique et découle du socle :
**un volet devient un onglet**. La barre de domaines devient la barre de
navigation du bas, le surplus passant dans « Plus ».

C'est la meilleure propriété du triptyque : aucune composition à réinventer par
écran, la même règle produit le mobile de tous.

**Hors périmètre** : l'optimisation tactile des outils cartographiques de mesure
et de croquis (SP-27) reste pensée à la souris. C'était l'option d'adaptabilité
supérieure, non retenue.

## 8. Internationalisation (A12)

Tous les libellés passent par une couche d'extraction pendant la réécriture des
écrans — le moment où on les touche déjà. **Seul le français est livré.** Le
surcoût est faible maintenant et l'économie majeure ensuite ; aucune
infrastructure n'existe aujourd'hui et tous les libellés sont en dur.

Mécanisme : à choisir au plan de SP-29 entre une couche minimale maison
(catalogue de clés typées, zéro dépendance) et une bibliothèque établie. Le
critère est le poids ajouté au bundle et à l'export autoporté, pas le confort.

## 9. Découpage

Le bloc de bascule est **le shell existant** (A7 + A8). Les surfaces neuves
arrivent après, additives, sans jamais recréer de cohabitation de styles.

| SP | Périmètre | Critère de sortie |
|---|---|---|
| **SP-29** | Fondation : tokens deux ambiances, kit de primitives, couche i18n, contrat de permissions (API + `Gate`) | Tout est en place, **rien n'a changé à l'écran** ; les 112 E2E restent verts sans modification (sauf l'exception §10.1.7) |
| **SP-30** | Bascule d'un bloc du shell existant sur le socle triptyque : 16 pages, 20 routes, 16 fichiers à dialogue | Aucun écran de l'ancien chrome ne subsiste ; suite E2E réécrite et verte ; 390 px vérifié sur les huit écrans de référence |
| **SP-31** | Domaines Automatisation et Tâches : centre de tâches, coffre de secrets (admin), vue d'ensemble des alertes | Toute la file `procrastinate` est observable et relançable depuis l'UI |
| **SP-32** | Domaine Administration : utilisateurs, groupes, journal d'audit, fédération STAC/DCAT | Aucune administration ne requiert plus d'appel API à la main |
| **SP-33** | Domaine Paramètres : instance, marque blanche, apparence, langue, capacités, sauvegarde ; catalogue enrichi (sémantique, vues carte et lignage), bibliothèque d'icônes, gestion 3D | Les neuf capacités listées au §1 ont un écran |

## 10. SP-29 en détail

### 10.1 — Périmètre

**Dans le périmètre :**

1. `shell/src/styles/tokens.css` — le contrat de tokens complet, deux ambiances,
   exposé à Tailwind v4 par `@theme`.
2. Les polices servies localement + le contrat typographique.
3. Le kit de composants (§10.3), habillé par les tokens, avec ses tests.
4. `shell/src/i18n/` — la couche d'extraction et le catalogue français.
5. `core` — `ItemPermissions` sur `ItemRead`, permissions sur les collections,
   capacités sur `GET /me`, `roles_for_items()` et la refactorisation de `can()`
   vers une fonction de décision pure partagée (§6.4).
6. `shell/src/auth/{Gate.tsx,capabilities.ts}` + les types générés régénérés.
7. **Une seule exception visible, assumée** : `shell/ItemActions.tsx` est câblé
   sur `Gate` dès SP-29. Ce n'est pas un restylage mais la correction d'un
   défaut réel — des actions qui produisent un 403 — et l'attendre jusqu'à SP-30
   n'a pas de justification. Cette exception coûte la mise à jour des tests E2E
   qui cliquent ces actions ; elle est signalée ici pour pouvoir être annulée
   sans rien casser d'autre.

**Hors périmètre de SP-29 :**

- Tout écran. Aucune page de `shell/src/pages/` n'est restructurée (hormis §10.1.7).
- Le socle triptyque lui-même : `AppLayout`, la barre de domaines, ⌘K, la barre
  d'état — ils arrivent en SP-30.
- `AppRenderer` et les 41 widgets (A9).
- Les pages publiques (`SitePublicPage`, `PublicItemPage`, `DatasetPage`).
- Le thème d'app (`builder/theme.ts`, `ThemePanel`) : inchangé. Seul le contrat
  de nommage est partagé (§5.1), pas le code.

### 10.2 — Spike préalable, obligatoire

Avant la première tâche d'implémentation, et **vérifié contre la source réelle**
(le paquet installé, pas la documentation ni la mémoire — piège n°3) :

1. Compatibilité React 19 de la bibliothèque de primitives candidate.
2. Poids ajouté au bundle, mesuré, et impact sur l'export autoporté (SP-18c).
3. Licence effective, compatible Apache-2.0.
4. Rendu correct dans le worker d'export Playwright headless (SP-17a).
5. Tailwind v4 `@theme` : forme exacte acceptée pour nos familles de tokens.

Le résultat du spike est consigné dans le plan avant la première tâche. S'il
invalide le candidat, on essaie le suivant sans re-demander.

### 10.3 — Le kit

Formulaire : `Field`, `Input`, `Textarea`, `Select`, `Combobox`, `Checkbox`,
`Radio`, `Switch`, `Slider`, `Segmented`, `ColorField`, `NumberField`.
Structure : `Tabs`, `Tree`, `Table`/`DataTable`, `Panel`, `Section`,
`Toolbar`, `Breadcrumb`, `Splitter`.
Surfaces : `Popover`, `Menu`, `Tooltip`, `Drawer`, `ConfirmDialog`.
États : `Badge`, `Chip`, `Toast`, `Skeleton`, `EmptyState`, `Banner`,
`Progress`, `Spinner`.
Divers : `Button`, `IconButton`, `Avatar`, `Kbd`, `Gate`.

Trois cibles chiffrées, dérivées du diagnostic : les **83 `<select>` bruts**,
les **159 `<input>` bruts** et les **139 `<button>` bruts** ont désormais une
primitive à laquelle se rattacher. Leur remplacement effectif est le travail de
SP-30, pas de SP-29.

Icônes : basculer sur `lucide-react` pour unifier avec le catalogue Lucide
curaté de SP-27 (aujourd'hui `lucide-static` en dépendance de développement,
consommé par `builder/widgets/lucideIconSvgs.generated.ts`). À arbitrer au plan
selon le poids mesuré : l'alternative est de continuer à générer des SVG.

### 10.4 — Tests

- **Unitaires shell** : un fichier de test par primitive (clavier, focus, ARIA,
  états désactivés, les deux ambiances) ; `Gate` testé sur le produit cartésien
  des quatre actions × quatre profils × trois modes de repli.
- **Unitaires cœur** : parité `decide()` / `can()` exhaustive (§6.4) ;
  sérialisation des permissions pour propriétaire, éditeur, lecteur, public,
  admin.
- **Anti-régression N+1** : un test qui compte les requêtes SQL émises par
  `GET /items?pageSize=12` et échoue si le nombre croît avec la taille de page.
  Une assertion de durée ne prouverait rien (piège n°7).
- **E2E** : inchangés, sauf ceux que touche l'exception §10.1.7.
- **Portes de qualité** : `ruff`, `mypy --strict` sur les modules concernés,
  `lint-imports` (aucune entrée nouvelle attendue), seuils de couverture
  non régressifs — 85 côté cœur, 88 côté shell, ce dernier **mesuré après
  nettoyage de `dist/` et `dist-export/`** (piège documenté quatre fois).
- **OpenAPI + types TS régénérés** : obligatoire, `ItemRead` change (piège n°1).
  Diff non vide attendu ici.

### 10.5 — Critères de sortie

1. `npm run test`, `npm run e2e`, `uv run pytest` verts.
2. Toutes les portes de qualité passent, seuils non régressés.
3. `openapi.json` et `core-schema.d.ts` régénérés et commités.
4. Aucune capture d'écran des seize pages existantes ne diffère — hormis
   `ItemActions` (§10.1.7).
5. Une page de galerie interne rend les quarante primitives dans les deux
   ambiances et à trois largeurs, servant de référence visuelle à SP-30.

## 11. Risques et limites connues

- **SP-30 est un gros bloc.** Seize pages et vingt routes basculées d'un coup,
  avec réécriture de la suite E2E : c'est la plus grosse revue finale jamais
  pratiquée sur ce dépôt. Le découpage en tâches devra isoler les écrans par famille, et la
  revue finale de branche est non négociable (piège n°4).
- **La galerie de primitives n'est pas une non-régression visuelle.** Aucun
  outillage de comparaison de captures n'est prévu — c'était une question posée
  et non tranchée. Sans lui, la cohérence se maintient à la discipline.
- **A15 est plus restrictif que le cœur.** Un créateur perd la capacité de
  câbler un secret dans son propre pipeline. Si l'usage montre que c'est
  bloquant, le desserrage est un changement d'UI seul.
- **A14 suppose une identité de déclencheur** dans la file `procrastinate`, non
  vérifiée à ce stade. Si elle manque, SP-31 porte une migration.
- **Le mode sombre touche les fonds de carte.** MapLibre, deck.gl et les
  tuiles servies par Martin/TiTiler ont leurs propres styles. SP-30 devra
  décider si un fond de carte sombre est fourni ou si la carte reste claire
  dans un studio sombre. Non tranché ici.
- **L'aperçu du builder restera hétérogène** tant que A9 tient.

## 12. Hors périmètre du chantier entier

- Refonte de `AppRenderer` et des 41 widgets (A9).
- Traitement éditorial des pages publiques.
- Optimisation tactile des outils de mesure et de croquis.
- Livraison d'une seconde langue (A12 : extraction seule).
- Déclaration de conformité RGAA et audit d'accessibilité formel (A3).
- Outillage de non-régression visuelle.
