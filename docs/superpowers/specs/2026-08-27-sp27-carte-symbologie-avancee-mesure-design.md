# Carte : symbologie avancée, étiquettes, icônes et mesure/croquis (SP-27)

> Chantiers 4.4 « Étiquettes, contour, opacité, icônes » et 4.5 « Mesure et
> croquis pour le lecteur » du plan d'action
> `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (§6/§7, vague 4,
> lot Carte), suite directe de SP-24 (4.1, popup + clic tuiles) et SP-25 (4.2
> + 4.3, symbologie couleur/taille + classes/palettes). Spec brainstormée et
> validée avec Tanguy le 2026-08-27.

## 1. Contexte & objectif

Le plan (lignes 389-390) demande deux choses indépendantes, bundlées dans un
seul SP par décision de session (même précédent que SP-25 bundlant 4.2+4.3) :

- **4.4** — compléter la symbologie déclarative posée par SP-25
  (`LayerSymbology`) avec étiquettes, contour (couleur/épaisseur/style),
  opacité, icônes de points. Preuve de sortie littérale : *une couche de
  communes étiquetées par leur nom, identique à l'export*.
- **4.5** — un outil de mesure (distance/surface) et de croquis (annotation
  éphémère) pour un lecteur sans droit d'écriture. Preuve de sortie
  littérale : *mesurer une distance sur une carte publiée sans droit
  d'écriture*.

Vérifié contre le code avant d'écrire cette spec :

- `shell/src/builder/widgets/mapSymbology.ts` (SP-25) expose déjà
  `LayerSymbology` (`color`, `size`), `computeColorDomain`/
  `computeSizeDomain`/`normalizeDomain`, `buildMapPaint`/`buildLegend`, et
  `jenksBreaks`/`quantileMeasures`. `MapSymbologyEditor.tsx` est partagé par
  `LayersPanel.tsx` (éditeur standalone) et `mapWidget.tsx`'s `PropsPanel`
  (widget carte des apps/dashboards/sites).
- Aucune occurrence de `text-field`, `icon-image` ni `stroke` dans
  `shell/src/map`/`shell/src/builder/widgets` — E4 est toujours vrai.
- `MapLayer` (kind `vector`/`feature`, `shell/src/api/types.ts:107-138`) a
  déjà `symbology?: LayerSymbology` et `popup?: PopupConfig`, en plus du
  `paint?: Record<string, unknown>` brut. Côté cœur,
  `core/app/configs/schemas.py:104` porte `symbology: dict | None` —
  **non typé**, donc les nouveaux champs `stroke`/`label`/`icon` ajoutés
  côté shell **round-trippent automatiquement**, comme `popup` l'a fait dès
  SP-24, sans migration ni changement de schéma cœur pour eux-mêmes.
- `popupTemplate.ts` (SP-24) expose déjà `interpolatePopupTemplate`/
  `closingBrace`/`ExprContext`, un évaluateur **CEL complet** (`cel-js`,
  `builder/expr.ts`) sur un gabarit `${...}` avec un scanner d'accolade
  conscient des guillemets CEL. C'est la même syntaxe qu'on réutilise pour
  les étiquettes (§3.3), mais **jamais** `renderPopupTemplate` (qui
  sanitize en markdown — une étiquette de carte est du texte brut rendu par
  le moteur GL, pas du HTML).
- `MapView.tsx` n'a **aucune** notion de `promoteId`/`feature-state`
  aujourd'hui. Le commentaire au-dessus du composant (I4 de la revue finale
  SP-24) explique pourquoi une prop `exprContext` a été retirée : aucun
  hôte réel ne pouvait la remplir. Conséquence directe pour cette spec : le
  contexte CEL d'une étiquette est construit **en interne**, `record.*`
  seulement (`{vars: {}, user: {name: ""}, record: feature.properties}`),
  exactement comme `popupContent.ts:37` le fait déjà pour le popup — pas de
  nouvelle prop.
- Aucune bibliothèque d'icônes (`lucide-static` ou autre) et aucune
  bibliothèque de calcul géométrique (`turf` ou équivalent) ne sont des
  dépendances du shell aujourd'hui (`package.json` vérifié).
- `WidgetContext` (`builder/registry.ts:8-18`) porte déjà `mode: RenderMode`
  ("edit" | "preview" | "runtime" — vérifié dans `api/types.ts`). Aucun
  champ `exportRender` n'y est threadé.
- `app/ingestion/storage.py`'s `generate_presigned_put_url` est déjà
  réutilisé tel quel par `app/tileset3d` et `app/terrain3d` pour un upload
  direct navigateur→S3 — précédent direct pour la bibliothèque d'icônes
  personnalisées (§3.4).
- Dernière migration Alembic : `0028_collection_spatial_index.py`.

## 2. Périmètre

**Dans le périmètre — 4.4 :**

- `LayerSymbology` gagne trois nouveaux encodages optionnels (`stroke`,
  `label`, `icon`) et un champ fixe (`opacity`), tous compilés dans
  `buildMapPaint`/`buildLegend` à la sauvegarde (même mécanisme que
  couleur/taille — figés, jamais recalculés au rendu, précédent SP-25 §3.2).
- `stroke` — encodage **indépendant** de `color` (son propre champ, sa
  propre classification/palette pour la couleur ; un encodage numérique
  séparé pour l'épaisseur, même modèle que `size`) plus un style fixe
  (plein/pointillé/pointillé fin), jamais data-driven.
- `opacity` — une valeur fixe par couche (0-100 %), jamais data-driven.
- `label` — gabarit `${...}` **CEL complet**, compilé pour un rendu
  natif MapLibre via `feature-state` (§3.3) — fonctionne sur `kind:
  "vector"` (tuilé) **et** `kind: "feature"` (GeoJSON), au prix d'un
  recalcul continu documenté comme le point de vigilance perf principal de
  cette spec (§7).
- `icon` — encodage catégoriel (un champ → une icône par valeur, même
  modèle que la couleur catégorielle), depuis un set curaté **Lucide** de
  150+ pictogrammes classés par catégorie (`lucide-static`, nouvelle
  dépendance) **plus** une bibliothèque d'icônes personnalisées
  tenant-scoped, uploadées une fois et réutilisables sur n'importe quelle
  couche/carte (§3.4).

**Dans le périmètre — 4.5 :**

- Outil de mesure (distance/surface), calcul géodésique **écrit à la main**
  (haversine, aire sphérique — aucune bibliothèque, précédent
  `jenksBreaks`/`popupTemplate`).
- Outil de croquis éphémère (tracé libre, rectangle/cercle/polygone,
  marqueur de texte, couleur, effacer tout) — jamais persisté, jamais
  envoyé au serveur.
- Les deux, montés **uniquement** dans `mapWidget.tsx`'s `Component`, actifs
  quand `ctx.mode !== "edit"` (donc en runtime app/dashboard **et** sur
  `/sites/{slug}`, qui réutilise le même widget par construction — règle
  d'architecture n°3 de CLAUDE.md).

**Hors périmètre, explicitement :**

- **Clustering de points** (mentionné par E4, absent du titre du chantier
  4.4). Suivi non bloquant (§7).
- **Mesure/croquis dans l'éditeur de cartes standalone**
  (`MapEditorPage`) — décision de session : réservé aux surfaces
  « lecteur » citées par la preuve de sortie du plan.
- **Opacité et dash pattern data-driven** — restent des réglages fixes par
  couche (décision de session, §4).
- **Masquage de la barre mesure/croquis pendant `?exportRender=1`** — aucun
  flag `exportRender` n'est aujourd'hui threadé jusqu'à `ctx` ; l'ajouter
  pour un défaut cosmétique (barre visible et inerte dans une capture)
  ferait déborder le SP sur une plomberie hors sujet. Suivi non bloquant.
- **Étiquettes/icônes/contour sur les couches `kind: "feature"` sans
  `collectionId` résolu côté `LayersPanel`** — même limite déjà acceptée
  par SP-25 (M7, éditeur de symbologie couleur déjà `null` faute de
  collection interrogeable). `label`/`icon` fonctionnent malgré tout sur
  `kind: "feature"` **côté rendu** (le calcul de domaine catégoriel s'y
  fait différemment, cf. §3.4) — seule l'édition dans `LayersPanel` reste
  limitée aux couches `vector`.
- **Toute correction trouvée hors des fichiers déjà touchés** — suivi non
  bloquant, précédent constant de ce dépôt.

## 3. Mécanisme

### 3.1 — Modèle de données

`shell/src/builder/widgets/mapSymbology.ts`, étendu :

```ts
export type StrokeStyle = "solid" | "dashed" | "dotted";

export type LayerSymbology = {
  color?: { ... };  // existant SP-25, inchangé
  size?: { ... };    // existant SP-25, inchangé
  stroke?: {
    color?: {
      field: string;
      mode: "categorical" | "numeric";
      classification?: ColorClassification;
      palette: PaletteId;
      domain: ColorDomain;
      computedAt: string;
    };
    width?: { field: string; domain: { min: number; max: number }; computedAt: string };
    style: StrokeStyle; // fixe, défaut "solid"
  };
  opacity?: number; // 0-100, fixe, hors encodage
  label?: {
    template: string;    // gabarit ${...} CEL, syntaxe partagée avec PopupConfig.template
    size: number;         // px, défaut 12
    color: string;        // défaut "#1e293b"
    haloColor: string;    // défaut "#ffffff"
    haloWidth: number;    // px, défaut 1
  };
  icon?: {
    field: string;
    domain: { kind: "categorical"; values: string[] };
    mapping: Record<string, IconRef>;
    fallback?: IconRef;
    size: number;   // multiplicateur d'échelle icon-size, défaut 1
    computedAt: string;
  };
};

export type IconRef =
  | { source: "lucide"; name: string }
  | { source: "custom"; id: string };
```

`stroke.color`/`stroke.width` réutilisent **tels quels**
`computeColorDomain`/`computeSizeDomain`/`normalizeDomain` — aucune nouvelle
logique de classification à écrire, seulement de nouveaux sites d'appel dans
`MapSymbologyEditor` (§3.5) et deux nouvelles branches dans `buildMapPaint`/
`buildLegend`.

Côté cœur : **aucun changement de schéma**. `symbology: dict | None`
(`configs/schemas.py:104`) round-trippe déjà n'importe quelle forme — vérifié
contre le comportement de `popup`/`symbology` depuis SP-24/SP-25, qui
utilisent le même mécanisme.

### 3.2 — `buildMapPaint`/`buildLegend` étendus

- `stroke-color`/`fill-outline-color`/`line-color` (selon `renderAs`, même
  sélection de propriété que `color`) : `match`/`step`/`interpolate` sur
  `stroke.color`, identique en forme à ce que `color` produit déjà.
- `stroke-width` (`fill` n'a pas de largeur de contour propre en MapLibre —
  une couche `polygon` avec `stroke` gagne une **seconde couche** `line`
  calquée sur les mêmes coordonnées, patron déjà en germe dans le découpage
  en sous-couches par géométrie de SP-24/I1) : `interpolate` sur
  `stroke.width`, identique en forme à `size`.
- `line-dasharray` fixe selon `stroke.style` (`[2, 2]` pour `dashed`, `[1,
  2]` pour `dotted`, absent pour `solid`).
- `fill-opacity`/`circle-opacity`/`line-opacity` = `opacity / 100` fixe.
- `icon-image` : expression `match` sur `icon.field` → id d'image
  MapLibre (§3.4), forme identique au `match` de couleur catégorielle.
- `buildLegend` gagne une entrée contour (swatch + libellé) et une entrée
  icône (pictogramme + libellé par valeur).
- Le point de câblage ne change pas : `MapView` continue de ne lire que
  `layer.paint`, recompilé depuis `symbology` à la sauvegarde (précédent
  SP-25 §3.5) — aucun changement dans `MapView` pour ces quatre nouveaux
  encodages, seulement pour l'étiquette (§3.3) et l'icône (§3.4, chargement
  des images).

### 3.3 — Étiquettes : `feature-state` (le point technique le plus lourd)

Nouveau module pur `shell/src/map/labelFeatureState.ts` :

```ts
export function computeLabelStateUpdates(
  features: { id: string | number; properties: Record<string, unknown> }[],
  template: string,
): { id: string | number; label: string }[];
// Pour chaque feature : interpolatePopupTemplate(template, {vars: {},
// user: {name: ""}, record: properties}) — jamais renderPopupTemplate
// (pas de sanitisation markdown, MapLibre affiche du texte brut).
```

Câblage dans `MapView.tsx` (nouvel effet, parallèle à celui d'`applyLayers`) :

1. Pour toute couche `vector`/`feature` dont `symbology.label` est défini,
   la source correspondante gagne `promoteId: layer.pkColumn ?? "id"`
   **à la création de la source** (§3.5 précédent SP-24 : un id stable est
   requis pour `setFeatureState`).
2. Une couche `symbol` dédiée est ajoutée au-dessus du rendu principal
   (`text-field: ["feature-state", "label"]`, `text-size`/`text-color`/
   `text-halo-*` posés depuis `label.size`/`color`/`haloColor`/`haloWidth`
   — valeurs fixes MapLibre, pas d'expression).
3. Sur `sourcedata` (source chargée) et `moveend` (débouncé, ~150ms — même
   ordre de grandeur que les debounces déjà en place dans le shell), le
   module interroge les features **actuellement chargées** —
   `map.querySourceFeatures(sourceId)` pour `vector` (tuiles déjà en
   mémoire), la liste GeoJSON déjà résidente pour `feature` — calcule le
   gabarit par feature via `computeLabelStateUpdates`, et appelle
   `map.setFeatureState({source, sourceLayer, id}, {label})` pour chacune.
4. Coût borné à ce qui est **visible/chargé**, jamais à la collection
   entière — mais c'est un vrai recalcul JS continu à chaque déplacement
   de carte, sur une couche stylée en étiquette. Documenté en §7 comme le
   risque de performance principal de cette spec, pas mesuré empiriquement
   avant l'implémentation (aucune preuve de charge dans cette spec — à
   faire en tâche).

### 3.4 — Icônes

Nouveau module `shell/src/builder/widgets/iconLibrary.ts` :

```ts
export type IconCategory =
  | "generic" | "buildings" | "nature" | "transport"
  | "services" | "safety-health" | "leisure";

export const LUCIDE_ICONS: { name: string; category: IconCategory }[];
// ≥150 noms d'icônes lucide-static pertinents pour de la cartographie
// (map-pin, building-2, tree-pine, bus, shopping-cart, hospital,
// tent, school, parking-circle, etc.), curatés à la main, groupés par
// catégorie ci-dessus.

export async function rasterizeLucideIcon(name: string): Promise<ImageBitmap>;
// Charge le SVG lucide-static correspondant, le dessine sur un canvas
// hors-écran, retourne l'ImageBitmap prêt pour map.addImage(..., {sdf: true}).
```

- Les icônes Lucide sont des traits monochromes (`currentColor`) : chargées
  avec `sdf: true` (Signed Distance Field), ce qui permet à MapLibre de les
  teindre par `icon-color` — non exploité dans cette spec (une seule teinte
  par défaut), mais évite de re-rasteriser si une future teinte par valeur
  est demandée. **Une icône personnalisée uploadée n'a pas cette garantie**
  (logo, PNG multicolore) : `sdf` la réduirait à un masque alpha et lui
  ferait perdre sa couleur. Les icônes `custom` sont donc chargées **sans**
  `sdf` (`map.addImage(id, bitmap)`, RGBA telle quelle) — `icon-color` n'a
  alors aucun effet dessus, ce qui est le comportement voulu.
- Chargement dans `MapView` : au montage d'une couche avec `symbology.icon`,
  toutes les images référencées par `icon.mapping`/`icon.fallback`
  (lucide **et** custom, §ci-dessous) sont chargées et ajoutées via
  `map.addImage` — `sdf` posé par branche selon `source` (ci-dessus) —
  **avant** l'ajout de la couche `symbol`, même ordre que l'ajout de
  source-avant-couche déjà respecté par `applyLayers`.
- **Bibliothèque d'icônes personnalisées, tenant-scoped** (cœur) : nouveau
  module `core/app/mapicons/` (positionné dans le contrat de couches
  import-linter comme `app.tileset3d`/`app.terrain3d` — importe
  `app.ingestion.storage` pour le presign, `app.sharing.authorization` pour
  `can()`, `app.audit` pour l'écriture) :
  - Table `map_icons(id uuid pk, tenant_id, title, category, s3_key,
    content_type, created_at)` — migration **0029**.
  - `POST /map-icons/presign` (auth requise, tout utilisateur — pas
    admin-only, comme l'upload de pièce jointe) → `{uploadUrl, s3Key}`
    (réutilise `generate_presigned_put_url`, contraint `content_type` à
    `image/svg+xml`/`image/png`, taille max ~200 Ko côté presign).
  - `POST /map-icons` (`{title, category, s3Key, contentType}`) — écrit la
    ligne, audité (`write_audit`).
  - `GET /map-icons` — liste tenant-scopée (RLS via `tenant_id`).
  - `DELETE /map-icons/{id}` — supprime la ligne + l'objet S3, audité.
  - `GET /map-icons/{id}/file` — proxy de lecture authentifié, même porte
    `can()` que le reste (un icône appartient au tenant, pas à un item
    précis — lisible par tout utilisateur du tenant, cohérent avec un
    usage transverse « bibliothèque »). **Pas de garde de coût dédiée**
    (fichiers <200 Ko, contrairement au proxy tileset3d) — décision
    assumée, taille déjà bornée au presign.
  - `MapView` attache le jeton de session (`getAuthToken`/`getCoreUrl`,
    précédent SP-24 `isHostedCoreUrl`) sur toute requête vers
    `/map-icons/`, pour qu'une icône personnalisée reste visible sur une
    carte publique **sans** rendre le fichier public au sens S3 (même
    raisonnement que les tuiles MVT).
- Picker dans `MapSymbologyEditor` : grille d'icônes groupées par
  catégorie (Lucide) + section « Mes icônes » listant `GET /map-icons`,
  avec un bouton d'upload (presign → PUT direct → `POST /map-icons`) et un
  bouton de suppression par icône.

### 3.5 — `MapSymbologyEditor` étendu

Le composant partagé (SP-25 §3.6) gagne trois nouveaux blocs, chacun
optionnel (un bouton « Ajouter un contour »/« Ajouter une étiquette »/
« Ajouter des icônes », symétrique du bloc couleur/taille existant) :

- **Contour** : même UI que le bloc couleur (champ, mode, classification,
  palette, bouton « Recalculer ») dupliquée pour `stroke.color`, plus un
  sélecteur d'épaisseur (même UI que le bloc taille) pour `stroke.width`,
  plus un `<select>` fixe pour `stroke.style`.
- **Opacité** : un simple curseur 0-100, pas de recalcul (valeur fixe,
  écrite directement).
- **Étiquette** : un `<textarea>` pour le gabarit (même patron
  d'affichage/validation d'erreur que `PopupEditor` pour son
  `template` — un aperçu du texte rendu sur un enregistrement d'exemple,
  si disponible, sinon rien), plus taille/couleur/halo.
- **Icône** : sélecteur de champ catégoriel (réutilise le domaine déjà
  calculé par `color` si le même champ est choisi, sinon un calcul dédié
  identique à `computeColorDomain` en mode catégoriel), puis pour chaque
  valeur du domaine un picker d'icône (grille Lucide + bibliothèque
  personnalisée), plus un fallback.

Sites d'appel inchangés dans leur principe (§3.7 SP-25) : `LayersPanel.tsx`
(couches `vector` avec `collectionId`) et `mapWidget.tsx`'s `PropsPanel`
(résolution `datasetId`) passent tous deux par le même composant.

## 4. Décisions prises en session (2026-08-27)

1. **Un seul SP pour 4.4 et 4.5**, comme SP-25 a bundlé 4.2+4.3 — même lot
   Carte, effort cumulé plus proche d'un SP que de deux fragments.
2. **Clustering hors périmètre** — chemin technique distinct (ne s'applique
   pas au rendu tuilé MVT, le chemin qui passe à l'échelle depuis SP-24),
   non nommé par le titre du chantier 4.4 malgré sa mention dans le constat
   E4 source.
3. **Icônes : set curaté Lucide (≥150, catégorisé) + bibliothèque
   personnalisée tenant-scoped uploadée**, plutôt qu'un set fermé sans
   upload (option initialement recommandée, écartée par Tanguy) ou un
   upload libre sans set curaté.
4. **Icônes data-driven par valeur catégorielle**, pas une icône fixe par
   couche — symétrique du modèle couleur catégorielle déjà livré.
5. **Contour en encodage indépendant** (son propre champ/classification/
   palette pour la couleur, sa propre classification numérique pour
   l'épaisseur) plutôt que dérivé du remplissage — permet par ex.
   remplissage par catégorie + contour par une valeur numérique différente.
6. **Opacité et style de contour (plein/pointillé) restent fixes**, jamais
   data-driven — écarté pour ne pas ajouter un cinquième/sixième encodage
   numérique à un modèle déjà riche (color, size, stroke.color,
   stroke.width) pour un besoin non demandé par la preuve de sortie du plan.
7. **Étiquettes en CEL complet via `feature-state`**, sur les deux kinds
   (`vector` et `feature`) — option la plus coûteuse des trois proposées,
   retenue en connaissance de cause après que le mécanisme exact (recalcul
   JS continu par entité visible à chaque pan/zoom, `promoteId` requis) a
   été explicité et confirmé. Alternative écartée : interpolation de champs
   simples compilée en expression MapLibre native (`concat`/`get`, coût
   quasi nul mais pas de conditions).
8. **Mesure/croquis maison** (haversine, aire sphérique, clics MapLibre
   natifs) — pas de `turf.js` ni de `mapbox-gl-draw`/`terra-draw`. Cohérent
   avec le précédent établi du dépôt (`jenksBreaks`, `popupTemplate`,
   primitives de quoting SQL).
9. **Croquis riche** : tracé libre + formes (rectangle/cercle/polygone) +
   texte + couleur + effacer tout — pas seulement les formes basiques.
10. **Mesure/croquis limités au widget carte runtime + `/sites/{slug}`**,
    absents de l'éditeur de cartes standalone — la preuve de sortie du plan
    cible explicitement un lecteur « sans droit d'écriture », un contexte
    qui n'existe pas dans `MapEditorPage` (toujours un auteur).
11. **Barre mesure/croquis non masquée pendant `?exportRender=1`** — un
    défaut cosmétique documenté (§2, §7) plutôt qu'une plomberie
    `exportRender` nouvelle à travers `WidgetContext`.

## 5. Ordre d'exécution recommandé

1. **Contour, opacité** (4.4, partie basse) — extension pure de
   `mapSymbology.ts`/`MapSymbologyEditor`, aucun nouveau module, réutilise
   `computeColorDomain`/`computeSizeDomain` tels quels. TDD sur
   `buildMapPaint`/`buildLegend` (nouvelles branches `stroke`/`opacity`).
2. **Icônes Lucide (sans upload)** — `iconLibrary.ts` (liste curatée,
   rasterisation), câblage `icon-image`/`match` dans `buildMapPaint`,
   chargement d'images dans `MapView`, picker dans `MapSymbologyEditor`
   (grille Lucide seule).
3. **Bibliothèque d'icônes personnalisées (cœur)** — migration 0029,
   `app/mapicons/` (modèle, repository, routes, presign), régénération
   OpenAPI/TS, section « Mes icônes » du picker.
4. **Étiquettes** — `labelFeatureState.ts` (TDD, module pur), câblage
   `promoteId`/`setFeatureState`/couche `symbol` dans `MapView.tsx`, bloc
   étiquette dans `MapSymbologyEditor`. La tâche la plus risquée du SP —
   à isoler, avec une preuve de perf informelle (nombre de features
   visibles raisonnable, ex. quelques centaines, recalculées sans geler le
   pan) avant de la considérer close.
5. **Mesure** — `measureSketch.ts` (haversine, aire sphérique, TDD sur des
   cas connus), interaction de dessin + affichage live dans un nouveau
   composant monté par `MapView` (comme `MapPopup`).
6. **Croquis** — mêmes fondations d'interaction que la mesure, primitives
   supplémentaires (main levée, formes, texte, couleur, effacer).
7. **Câblage `mapWidget.tsx`** — `interactiveTools={ctx.mode !== "edit"}`
   sur `MapView`.
8. **Preuves de sortie E2E** (§6).

## 6. Validation & preuves de sortie

1. **Preuve de sortie 4.4** (E2E) : couche de communes stylée avec une
   étiquette `${nom}`, une icône par catégorie et un contour, exportée en
   PNG/PDF (SP-17a) — le rendu capturé porte les mêmes étiquettes/icônes/
   contour que la visionneuse.
2. **Preuve de sortie 4.5** (E2E) : sur une app publiée en mode runtime,
   mesurer une distance sans session authentifiée (mode démo lecture
   seule ou visiteur anonyme sur `/sites/{slug}`) — la valeur affichée est
   correcte à une tolérance fixée, et aucune requête d'écriture n'est
   émise.
3. `mapSymbology.test.ts` : nouvelles branches `buildMapPaint`/
   `buildLegend` pour `stroke`/`opacity`/`icon` ; cas dégénérés (domaine de
   contour vide, épaisseur constante) passent par `normalizeDomain` sans
   régression des cas couleur existants.
4. `labelFeatureState.test.ts` : `computeLabelStateUpdates` contre un jeu
   de features connu, gabarit avec condition CEL (`${pop > 10000 ? "grande
   ville" : "commune"}`), valeur `record.*` absente (repli sur chaîne
   vide, précédent `popupContent.ts`).
5. `iconLibrary.test.ts` : `LUCIDE_ICONS` a bien ≥150 entrées réparties sur
   les 7 catégories, aucun nom en double, chaque nom résout un fichier
   `lucide-static` réel (test qui échoue si un nom est mal orthographié).
6. `measureSketch.test.ts` : haversine contre des distances connues
   (ex. deux points à 1° de longitude sur l'équateur), aire sphérique
   contre un polygone de superficie connue (ex. un carré aux coordonnées
   rondes), tolérance documentée.
7. Cœur : `core/tests/test_mapicons_routes.py` — presign, création,
   liste tenant-scopée (un tenant ne voit pas les icônes d'un autre),
   suppression (ligne + objet S3), lecture proxy via `can()`, audit sur
   création/suppression. `test_deployability.py` étendu si une nouvelle
   variable d'environnement/bucket est introduite (ex.
   `S3_MAPICONS_BUCKET`).
8. Portes habituelles. Cœur : `uv run pytest` sans baisse par rapport à la
   référence de fin de SP-26 (1896 passed / 5 skipped / 1 failed
   préexistant sans rapport), `ruff check`, `ruff format --check`, `mypy
   --strict` (4 modules), `lint-imports`, couverture ≥ 85. Shell : `npm run
   lint`, `format:check`, `test` (référence 162 fichiers / 1463 tests),
   `build`, `e2e` (référence 108 passed / 4 skipped), couverture ≥ 88
   (mesurée après nettoyage de `dist/`/`dist-export/`, piège documenté
   SP-22/23/24/25/26). Garde-fou de déployabilité (`test_deployability.py`)
   sans régression si un nouveau bucket/variable est ajouté.
9. OpenAPI et types TS régénérés, diff non vide et committé (nouvelles
   routes `map-icons`).

## 7. Risques et limites connues

- **Étiquettes : coût de recalcul continu non mesuré avant
  l'implémentation.** Sur une couche dense (plusieurs milliers de features
  visibles), le recalcul JS à chaque `moveend` pourrait geler
  perceptiblement l'interaction. Aucune limite dure n'est posée dans cette
  spec (pas de plafond « désactiver l'étiquette au-delà de N features
  visibles ») — à mesurer en tâche, et à durcir si nécessaire (suivi non
  bloquant si le durcissement n'est pas fait dans ce SP).
- **Barre mesure/croquis visible pendant une capture d'export** — défaut
  cosmétique assumé (§2, §4-11).
- **Icônes SDF monochromes** — `sdf: true` autorise une teinte unique par
  `icon-color`, non exploitée ici (icône rendue dans sa couleur d'origine
  au chargement, pas de variation par valeur au-delà du choix de
  pictogramme lui-même). Une future demande « icône rouge si alerte, verte
  sinon » resterait hors périmètre.
- **Aucune garde de coût dédiée sur le proxy `/map-icons/{id}/file`**,
  contrairement au proxy tileset3d — jugé inutile pour des fichiers bornés
  à ~200 Ko au presign, mais à revisiter si la limite de taille change.
- **Mesure géodésique approximative sur de grandes distances** — haversine
  suppose une Terre sphérique (erreur ~0,3% face à un ellipsoïde WGS84),
  acceptable pour un outil de lecture, pas pour un usage géodésique
  professionnel. À documenter dans l'UI si jugé nécessaire (non tranché
  ici).
- **Clustering, opacité/dash data-driven, mesure/croquis dans l'éditeur
  standalone** — tous explicitement hors périmètre (§2), à re-proposer
  comme chantiers séparés si un besoin réel émerge.
