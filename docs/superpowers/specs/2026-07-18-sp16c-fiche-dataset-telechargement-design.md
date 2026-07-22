# SP-16c — fiche dataset + téléchargement + template galerie : design

> Troisième et dernière sous-phase de **SP-16 « Portails & Sites »** (design
> macro :
> [`2026-07-14-sp16-portails-sites-design.md`](2026-07-14-sp16-portails-sites-design.md),
> arbitrages A31/A33/A34/A35/A38 tranchés le 2026-07-14). Découpage a/b/c fixé
> par le §9 du design macro : **a** = modèle `site`/slug + route publique +
> résolution shell (livré et clos, cf.
> [`2026-07-18-sp16a-modele-site-slug-design.md`](2026-07-18-sp16a-modele-site-slug-design.md)) ;
> **b** = widgets de contenu Hero/RichSection/Gallery (livré et clos, cf.
> [`2026-07-18-sp16b-widgets-contenu-design.md`](2026-07-18-sp16b-widgets-contenu-design.md)) ;
> **c** = fiche dataset + téléchargement + template galerie (ce document). SP-16
> s'exécute après SP-11 (clos), avant SP-12/SP-13 (A34). **Cette sous-phase clôt
> SP-16 et vise le jalon M13 « Portails ouverts ».**

## 1. Objectif

Livrer la **fiche de jeu de données** — un visiteur **anonyme** consulte une
collection publique (description, aperçu carte/table en lecture seule) et
**télécharge** les données (GeoJSON + CSV) — plus le **template galerie
« Portail de données »** qui pré-câble un portail complet (accueil éditorial +
galerie de découverte + fiche dataset téléchargeable).

Sur ce socle, l'admin dispose de la dernière pièce manquante du portail v1 : un
visiteur parcourt un portail public de marque et **repart avec un jeu de
données** sans jamais voir un item non publié — le critère d'acceptation du
jalon M13.

## 2. Décisions actées pour cette sous-phase

Rappel des arbitrages hérités du design macro SP-16 (§2, à ne pas rediscuter) :

| # | Décision |
|---|---|
| A31 | Config du portail = sous-gabarit d'`AppConfig`, un seul runtime `AppRenderer` — pas de deuxième moteur. |
| A33 | Domaine personnalisé **différé** : v1 accessible via `/sites/{slug}` et `/public/…`, pas de résolution par host. Les routes publiques ne servent que le tenant `default`. |
| A38 | Fonctions communautaires (commentaires/follow/discussions) **hors périmètre**. |

Décisions propres à SP-16c, tranchées au brainstorm du 2026-07-18 :

- **Forme = `DatasetCard` (widget placeable) + route publique dédiée
  `/public/datasets/:collectionId` rendant une `DatasetPage`.** La carte est un
  résumé compact posable sur n'importe quel item ; la page est la fiche
  complète (description + aperçu carte/table lecture seule + téléchargement).
- **Aucune nouvelle route cœur.** Tout ce dont la fiche a besoin est **déjà**
  exposé de façon anonyme pour les collections publiques (cf. §4). SP-16c est
  une sous-phase **shell + template**, sans changement de code cœur (hors
  éventuelle régénération de types si drift — non attendu).
- **L'aperçu carte/table de `DatasetPage` passe par le seul runtime
  `AppRenderer`** (A31) : une config minimale synthétisée en mémoire
  (`Carte` + `Table` liées à `collectionId`), rendue en mode `runtime`. Aucun
  composant de rendu neuf, aucune instanciation directe de widget hors du
  runtime.
- **Téléchargement v1 borné (macro §3) :** GeoJSON toujours disponible (lien
  direct vers l'URL OGC API Features de la collection, téléchargé par le
  navigateur) ; **CSV généré côté client, plafonné à 10 000 entités** — au-delà,
  bouton CSV désactivé avec message clair (« trop volumineux, export serveur à
  venir — SP-15 »), jamais de blocage silencieux ni de timeout navigateur.
- **Pas de fiche par item de type `map`/`app`** : la fiche décrit une
  **collection** (jeu de données), pas un item de config. La découverte des
  items publiés reste le rôle de `Gallery` (SP-16b) ; la fiche dataset est un
  objet distinct, adressé par `collectionId`.

## 3. Périmètre

**Dans le périmètre :**
- Widget built-in **`DatasetCard`** (`shell/src/builder/widgets/`), disponible
  pour **tout** type d'item : résumé compact d'une collection publique
  (titre, description, nombre d'entités), lien « Voir le jeu de données » vers
  `/public/datasets/{collectionId}`, boutons de téléchargement optionnels.
- Route shell publique **`/public/datasets/:collectionId`** → vue
  **`DatasetPage`** : fiche complète, hors `ProtectedLayout` (à côté de
  `/sites/:slug` et `/public/items/:pk` de SP-16a/b).
- Util de téléchargement partagé, isolé et testé (`datasetDownload.ts`) :
  URL GeoJSON + génération CSV client-side bornée à 10 000.
- `ItemClient` : lectures anonymes d'une collection et de son schéma
  (réutilisées ou ajoutées comme miroir des endpoints anonymes existants, à
  trancher en plan), aucune méthode d'écriture, aucun nouveau contrat serveur.
- Template galerie **« Portail de données »** (`templates.ts`) : site
  pré-câblé Hero + Gallery + `DatasetCard` (+ Carte/Table de démo lecture
  seule) sur une collection publique.

**Hors périmètre (différé, pas oublié) :**
- Toute nouvelle route ou nouveau modèle cœur (aucun besoin — cf. §4).
- Export **DCAT-AP / STAC** des fiches dataset (attend SP-12).
- Export **CSV/XLSX serveur** pour gros volumes (attend SP-15) — au-delà du
  seuil, le CSV client-side est désactivé, pas remplacé par un export serveur.
- Fiche pour un item de config (`map`/`app`/`dashboard`) — la fiche adresse une
  **collection**.
- Filtres/facettes interactifs sur la fiche ; métriques de téléchargement
  (extension naturelle d'`audit_log`, mais hors v1) ; fonctions communautaires
  (A38) ; domaine personnalisé / multi-tenant public (A33).

## 4. Architecture — cœur : rien à ajouter

La fiche s'alimente **exclusivement** d'endpoints déjà exposés de façon anonyme
pour les collections **publiques** (vérifié sur le code au brainstorm) :

| Besoin de la fiche | Endpoint existant | Anonyme |
|---|---|---|
| Métadonnées (titre, description, `featureCount`, `geometryType`, `srid`, `pkColumn`, `tableName`) | `GET /collections/{id}` | oui (`get_current_user_optional`) — **404 avant 403** si non lisible, aucune fuite d'existence |
| Champs pour les colonnes de l'aperçu Table | `GET /collections/{id}/schema` | oui |
| Features (aperçu carte/table, GeoJSON, CSV) | OGC API Features `GET /collections/{id}/items` | oui pour collection publique |

- `GET /collections/{id}` passe par `get_readable_collection` : pour un
  visiteur anonyme il résout le tenant `default` (A33), applique `can(read)`, et
  renvoie **404** pour toute collection non publique/inexistante — la fiche
  hérite donc gratuitement de la politique de non-fuite du projet.
- **Aucune migration, aucun nouveau handler, aucun nouveau champ sérialisé**
  côté cœur. Si une régénération `openapi.json`/`core-schema.d.ts` s'avère
  nécessaire (drift préexistant), elle est traitée comme d'habitude (§9) — mais
  cette sous-phase n'ajoute aucune surface d'API.

## 5. Architecture — shell

### 5.1 Widget `DatasetCard`
- Fichier `shell/src/builder/widgets/datasetCard.tsx` (mêmes conventions que les
  widgets existants : props typées, tests co-localisés, enregistrement dans
  `registry.ts`/`index.tsx`, thème `--gs-*`), disponible pour tout item.
- Props : `collectionId` (choisie via le **`DataSourceSelect` existant** dans le
  `PropsPanel` — pas de nouveau sélecteur), `showDownload?: boolean`
  (défaut `true`), `title?` (override optionnel du titre de collection).
- `Component` : `useQuery` → lecture des métadonnées de la collection ; rend
  titre + description + nombre d'entités ; lien **« Voir le jeu de données »** →
  `/public/datasets/{collectionId}` ; si `showDownload`, rend les boutons de
  téléchargement (mêmes affordances que `DatasetPage`, cf. 5.3).
- États explicites : chargement, collection introuvable/non publique (message
  discret, pas de fuite), erreur.

### 5.2 Route et vue `DatasetPage`
- `DatasetPage(collectionId)` — même patron que `SitePublicPage` (16a) /
  `PublicItemPage` (16b) : lit les métadonnées de la collection ; 404 ou erreur
  → page **« introuvable » générique** (aucune fuite d'existence d'une
  collection non publique).
- Route `/public/datasets/:collectionId`, déclarée **hors `ProtectedLayout`**
  dans `shell/src/shell/routes.tsx` (à côté de `/sites/:slug` et
  `/public/items/:pk`).
- Rendu : chrome de page (titre, description, nombre d'entités) + boutons de
  téléchargement (5.3) + **aperçu carte/table lecture seule** rendu par
  `AppRenderer(previewConfig, "runtime")` où `previewConfig` est une
  `AppConfig` **synthétisée en mémoire** contenant un widget `Carte` et un
  widget `Table` liés à `dataSource = collectionId` (A31, un seul runtime, aucun
  composant de rendu neuf). Les widgets Carte/Table lisent déjà les features
  d'une collection depuis le cœur (SP-3c/SP-4) et fonctionnent en lecture
  anonyme sur une collection publique.

### 5.3 Util de téléchargement partagé (`datasetDownload.ts`)
- Util isolé et testé, sans dépendance React :
  - `geojsonDownloadUrl(collectionId): string` — URL directe de l'endpoint OGC
    API Features items de la collection ; le bouton est un lien
    (`download`/nouvel onglet) téléchargé par le navigateur, **sans passer par
    le JS** (pas de mise en mémoire côté client). Toujours disponible.
  - `downloadCsv(collectionId): Promise<void>` — fetch **borné** des features
    (cap 10 000), conversion CSV côté client : une colonne par propriété du
    schéma + une colonne `geometry` sérialisée en GeoJSON (chaîne). Déclenche
    un téléchargement de blob.
  - `csvAvailable(featureCount: number): boolean` — `featureCount <= 10000`.
- **Seuil 10 000** lu depuis `featureCount` des métadonnées de collection
  (SP-6c) : au-delà, le bouton CSV est **désactivé** avec un message clair
  (« Jeu de données trop volumineux pour l'export CSV navigateur — export
  serveur à venir (SP-15) »). Le GeoJSON reste proposé.

### 5.4 `ItemClient`
- Lectures anonymes réutilisées ou ajoutées en miroir des endpoints existants
  (nom exact tranché en plan) : métadonnées de collection, schéma, features —
  aucune méthode d'écriture, aucun nouveau contrat serveur.
- **Round-trip des champs** : si `itemClient` reconstruit un objet collection
  champ par champ, `featureCount`/`description`/`geometryType` doivent être
  explicitement propagés en lecture (classe de bug
  `slug`/`visibleWhen`/`navigationMode`/`keywords` déjà rencontrée — testé, pas
  supposé).

### 5.5 Template galerie « Portail de données » (`templates.ts`)
- Nouvelle entrée : un `site` pré-câblé démontrant le portail complet — `Hero`
  (accueil éditorial) + `Gallery` (découverte des items publiés) + `DatasetCard`
  (fiche téléchargeable) + Carte/Table de démo en lecture seule, tous sur une
  collection publique seedée. Aucune UX neuve à apprendre : l'auteur part de ce
  template et adapte.

## 6. Sécurité et gouvernance

- **Aucun nouveau chemin d'autorisation.** La fiche ne lit que des endpoints
  anonymes existants qui appliquent déjà `can(read)` et la politique de
  publication SP-1c. `GET /collections/{id}` renvoie **404** pour une collection
  non publique/inexistante : `DatasetCard` et `DatasetPage` affichent
  « introuvable » **sans révéler** l'existence d'une collection privée.
- **Non-fuite testée** (risque ★★★, symétrique aux matrices déjà exigées par le
  projet) : collection non publique → fiche introuvable, aucune métadonnée ni
  feature exposée ; collection publique → fiche + aperçu + téléchargement.
- La revue finale de branche doit confirmer explicitement qu'aucun chemin
  shell ne contourne la frontière serveur (même exigence que chaque SP touchant
  au public depuis SP-1c) et qu'aucun endpoint privé n'est appelé sans auth.

## 7. Tests

**Cœur (pytest) :** aucun (pas de code cœur ajouté). On s'appuie sur la
couverture existante de `GET /collections/{id}` (404 avant 403, anonyme,
isolation tenant) déjà en place depuis SP-3a/SP-9.

**Shell (Vitest) :**
- `DatasetCard` : rendu titre/description/nombre d'entités ; lien vers
  `/public/datasets/{collectionId}` ; boutons de téléchargement présents/absents
  selon `showDownload` ; états chargement / introuvable / erreur ; héritage de
  thème (`--gs-*`).
- `DatasetPage` (MSW) : cas 200 → chrome + boutons + `AppRenderer` de l'aperçu
  rendu ; cas 404 (collection non publique/inexistante) → « introuvable » sans
  détail.
- `datasetDownload` : `geojsonDownloadUrl` correcte ; `csvAvailable` au seuil
  (`10000` vrai, `10001` faux) ; `downloadCsv` construit un CSV correct
  (colonnes de propriétés + colonne `geometry` GeoJSON) ; borne à 10 000
  respectée.
- `itemClient` : lectures de collection anonymes — URL/paramètres corrects ;
  round-trip `featureCount`/`description`/`geometryType`.

**E2E (nouvelle spec `sites-portal-dataset.spec.ts`) :**
1. Créer un `site`, y ajouter un `DatasetCard` lié à une collection publique
   seedée depuis la palette, Enregistrer.
2. Publier via la mécanique existante.
3. Session anonyme → visiter `/sites/{slug}` : la `DatasetCard` affiche le
   titre + le nombre d'entités et son lien.
4. Cliquer « Voir le jeu de données » → `/public/datasets/{collectionId}` :
   l'en-tête, l'aperçu carte/table (`AppRenderer` runtime) et le lien de
   téléchargement GeoJSON s'affichent ; le CSV se télécharge (collection sous le
   seuil).
5. Une collection non publique → `/public/datasets/{id}` rend « introuvable »,
   sans fuite d'information sur son existence.

## 8. Critères d'acceptation

- Un admin construit, depuis le builder existant sans nouvelle formation, un
  portail avec accueil éditorial (Hero + texte riche), galerie de découverte
  (Gallery, SP-16b) **et au moins une fiche dataset téléchargeable**
  (`DatasetCard` → `DatasetPage`), publié sur une URL stable.
- Un visiteur **anonyme** parcourt le portail, ouvre une fiche dataset, voit un
  aperçu carte/table en lecture seule, et **télécharge le jeu de données**
  (GeoJSON toujours ; CSV sous le seuil de 10 000) — sans jamais voir un item ou
  une collection non publiée.
- Une collection non publique n'apparaît jamais via `DatasetCard`/`DatasetPage`
  (matrice de non-fuite verte) ; la revue finale confirme qu'aucun chemin ne
  contourne `can()`/la politique de publication.
- Le template « Portail de données » produit un portail complet fonctionnel
  d'un clic.
- Toutes les specs E2E existantes (dont `sites-portal-shell.spec.ts` et
  `sites-portal-content.spec.ts`) restent vertes ; la nouvelle
  `sites-portal-dataset.spec.ts` s'ajoute. **SP-16 est clos, jalon M13 atteint.**

## 9. Points d'attention d'intégration

- **Pas de dérive OpenAPI attendue** : SP-16c n'ajoute aucune route ni champ
  cœur. Vérifier néanmoins en fin de branche que `openapi.json`/
  `core-schema.d.ts` sont en phase (le job `api-types-drift` reste le garde-fou,
  patron récurrent SP-9/SP-10/SP-16a/b).
- **Aperçu par config synthétisée** : la `previewConfig` de `DatasetPage` doit
  respecter le schéma `AppConfig` attendu par `AppRenderer` runtime (dataSource
  des widgets Carte/Table pointant sur `collectionId`). Vérifier qu'un item de
  collection sans géométrie exploitable dégrade proprement (carte vide + table),
  sans casser le rendu.
- **CSV client-side** : sérialisation de la géométrie en GeoJSON dans une
  colonne dédiée ; échappement CSV correct (guillemets, séparateurs, retours à
  la ligne dans les valeurs) — testé, classe de bug classique.
- **Réutilisation Carte/Table anonyme** : confirmer que les widgets Carte/Table
  lisent les features d'une collection publique **sans token** (chemin anonyme
  OGC) en runtime — déjà le cas pour un site public (SP-16a/b), à re-vérifier
  pour l'aperçu.

## 10. Risques

| Risque | Gravité | Garde-fou |
|---|---|---|
| Fuite d'une collection non publique via `DatasetCard`/`DatasetPage` | ★★★ (sécurité) | Lecture via `GET /collections/{id}` uniquement (404 avant 403, anonyme, tenant `default`) ; matrice de non-fuite testée ; revue finale vérifie l'absence de contournement |
| CSV client-side dégradé sur gros volumes | ★ (assumé) | Borne explicite 10 000 + bouton désactivé + message clair ; GeoJSON toujours proposé ; levé par SP-15 (export serveur) |
| Aperçu carte/table qui casse sur une collection atypique (sans géométrie, schéma exotique) | ★ | Config synthétisée testée sur cas dégradés ; carte vide + table plutôt que crash |
| Échappement CSV incorrect (valeurs contenant `,`/`"`/`\n`) | ★ | Util `datasetDownload` isolé + test adversarial dédié |
| Dérive OpenAPI / types générés | ★ | Aucune surface d'API ajoutée ; `api-types-drift` en garde-fou |

## 11. Découpage & estimation

Une seule branche livrable, exécutable en subagent-driven ou executing-plans
selon le découpage du plan, en tâches largement indépendantes :
1. util `datasetDownload` (URL GeoJSON + CSV client-side borné) + tests ;
2. `ItemClient` — lectures anonymes de collection/schéma (round-trip testé) ;
3. widget `DatasetCard` (+ `DataSourceSelect` dans le PropsPanel) ;
4. route `/public/datasets/:collectionId` + vue `DatasetPage` (aperçu par
   `AppRenderer` synthétisé) ;
5. template galerie « Portail de données » ;
6. E2E `sites-portal-dataset.spec.ts` + vérification des types générés.

Par analogie avec des lots widgets shell + template déjà livrés (SP-4a, SP-8a,
SP-16b) et sans aucun code cœur : **≈ 15-25 h**.
