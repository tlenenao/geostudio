# LayersPanel : la colonne browse ne clippe plus son contenu (SP-37)

> Referme définitivement le lot « Carte » noté dans CLAUDE.md « À venir »
> depuis SP-28 (bug UI, pas une fonctionnalité manquante) — dernier
> mécanisme ouvert après la clôture du mécanisme (b) par SP-36. Spec
> brainstormée et validée avec Tanguy le 2026-09-04, à la suite de la
> clôture de SP-36.

## 1. Contexte & objectif

`shell/e2e/triptych-narrow.spec.ts` documente, depuis SP-33/SP-36, un
`wideBoundaryKnownIssue` sur l'écran Cartes à 900px (juste au-dessus du seuil
`NARROW_QUERY = "(max-width: 899px)"` posé par SP-33) : 1 offenseur mesuré,
`DIV.overflow-y-auto.border-r.border-rule` (scrollWidth 290 > clientWidth
249) — la colonne `browse` de `TriptychLayout.tsx` (`minmax(220px,280px)`,
rendue à ~249px dans cette bande) trop étroite pour le contenu de
`LayersPanel`. Le mécanisme (b), historiquement bundlé avec celui-ci (titre
de couche à largeur nulle), est fermé par SP-36 ; seul (a) restait à
diagnostiquer.

**Diagnostic fait par expérimentation directe dans le navigateur (pas
supposé), falsifié avant d'être retenu :**

Avec la fixture `map-1` (couche `vector` « Communes », popup+symbologie
actifs) rendue à 900px, l'inspection des largeurs en place de chaque
input/select sous le conteneur offenseur montre qu'ils sont TOUS étirés à
exactement 270px — pas leur propre plancher individuel (mesuré isolément
entre 182px et 200px chacun), mais un plancher commun imposé par un élément
tiers. En isolant chaque candidat, l'élément responsable est
`PopupEditor.tsx:160` :

```tsx
<div className="flex items-center gap-2">
  <input aria-label="Nom du champ à ajouter" className={`${inputCls} flex-1`} ... />
  <Button type="button" size="sm" variant="outline" onClick={addDraftField}>
    Ajouter le champ
  </Button>
</div>
```

Cette ligne est un flex-row **sans** `flex-wrap`. L'input `flex-1` n'annule
pas le plancher automatique (`min-width: auto`) : comme il n'est pas en
`overflow: hidden` (pas de `truncate`), son plancher automatique reste égal à
son min-content (~192px, mesuré). Additionné au bouton (~70-78px selon son
état) et au `gap-2` (8px), la ligne ne peut légalement descendre sous
~270px — plus large que les ~249px offerts par la colonne `browse` dans la
bande 900-959px. Comme cette ligne est la plus exigeante de tout le bloc
éditeur empilé en `flex-col`, sa largeur plancher se propage à TOUS ses
voisins (Champ titre, Champ couleur, Palette, Champ taille, Opacité), qui
héritent tous du même 270px bien qu'individuellement plus étroits.

**Vérifié par falsification en direct** : forcer `flex-wrap: wrap` sur cette
ligne via `page.evaluate` fait tomber l'overflow mesuré de scrollWidth 290 à
exactement 249 (= clientWidth, 0 offenseur) — confirmation sans ambiguïté du
mécanisme, avant d'écrire cette spec.

**Deuxième pattern structurellement identique repéré pendant l'investigation,
non encore prouvé** : `MapSymbologyEditor.tsx:575`, la ligne d'assignation
d'icône par valeur de domaine catégoriel :

```tsx
<div key={v} className="flex items-center gap-2">
  <span className="text-xs font-medium">{v}</span>
  <button ...>{/* nom de l'icône assignée, ou "Aucune" */}</button>
</div>
```

Même absence de `flex-wrap`, mêmes ingrédients (texte + bouton côte à côte,
sans plancher annulé). Non exercé par la fixture `map-1` actuelle (pas
d'encodage icône catégoriel configuré dessus) — à vérifier réellement avant
de décider s'il faut le corriger (§2, §4).

## 2. Périmètre

**Dans le périmètre :**

1. `shell/src/map/PopupEditor.tsx:160` — ajouter `flex-wrap` à la ligne
   d'ajout de champ (correctif confirmé, §1).
2. `shell/src/map/MapSymbologyEditor.tsx:575` — reproduire réellement l'état
   qui exerce cette ligne (une couche avec encodage icône catégoriel assigné,
   valeur de domaine et nom d'icône assez longs pour approcher le budget de
   ~249px) à 900px, mesurer. Si l'overflow est réellement observé, corriger
   par le même `flex-wrap`. Si non reproduit, ne rien changer et documenter
   « vérifié, non reproduit à ce jour » dans le commentaire de
   `triptych-narrow.spec.ts` plutôt que de laisser un silence ambigu.
3. `shell/src/map/LayerPicker.tsx:143` et `:173` — ajouter `border-rule` aux
   deux `border-t` non tokenisés (dette notée SP-30c, explicitement exclue du
   périmètre de SP-34 comme « chantier séparé », reprise ici à la demande de
   Tanguy). `className` seul, aucun changement de comportement.
4. `shell/e2e/triptych-narrow.spec.ts` — une fois §2.1 (et §2.2 si confirmé)
   corrigés : retirer `wideBoundaryKnownIssue` de l'écran Cartes, le test à
   900px rejoint les 7 autres écrans (plus de `test.skip()`). Mettre à jour
   le commentaire du bloc `SCREENS` (lignes ~179-197) et le commentaire
   d'en-tête (~142-151) en conséquence.
5. CLAUDE.md — clore entièrement le lot « Carte » dans `### À venir` (plus
   aucun sous-mécanisme ouvert), entrée `### Livré` datée SP-37.

**Hors périmètre, explicitement :**

- Toucher `TriptychLayout.tsx` (largeur des colonnes) ou
  `useNarrowViewport.ts` (seuil `NARROW_QUERY`) — le contenu tient dans le
  plancher actuel de la colonne `browse` une fois corrigé ; élargir la
  colonne pour toute la famille de 9 écrans n'est pas nécessaire et
  réintroduirait la question du seuil partagé (SP-33).
- Toute restructuration de `PopupEditor.tsx`/`MapSymbologyEditor.tsx`/
  `FieldClassificationPicker.tsx` au-delà des classes `flex-wrap`/
  `border-rule` ci-dessus.
- Audit exhaustif de tout pattern flex-row du dépôt en dehors des fichiers
  consommés par la colonne `browse` de l'écran Cartes — seuls les deux
  patterns identifiés en §1 sont dans le périmètre.

## 3. Mécanisme

Identique à SP-36 : ajout de `flex-wrap` au(x) conteneur(s) flex-row
identifié(s), sans restructuration. Avec `flex-wrap`, le bouton (« Ajouter le
champ », ou le bouton d'icône si §2.2 confirme le second cas) est rejeté sur
sa propre ligne dès que l'input/span voisin ne peut plus tenir à côté à sa
largeur normale — l'input/span, seul élément restant sur la première ligne,
récupère l'espace disponible sans plancher partagé avec le bouton. Aucun
changement visuel aux largeurs où tout tenait déjà côte à côte (≥270px de
colonne disponible) : le retour à la ligne ne se déclenche que sous ce seuil.

```diff
- <div className="flex items-center gap-2">
+ <div className="flex flex-wrap items-center gap-2">
    <input aria-label="Nom du champ à ajouter" className={`${inputCls} flex-1`} ... />
    <Button ...>Ajouter le champ</Button>
  </div>
```

Pour `LayerPicker.tsx`, changement sans rapport mécaniquement (dette de
token de couleur, pas de layout) :

```diff
- <div className="border-t pt-2">
+ <div className="border-t border-rule pt-2">
```

## 4. Tests

1. **Falsification obligatoire** (piège n°10) pour chaque `flex-wrap`
   ajouté : retirer temporairement la classe, confirmer sur un run
   Playwright réel que la mesure `expectNoClippedContent`
   (`triptych-narrow.spec.ts`) échoue bien avec un offenseur non-vide,
   remettre. Pour le fix #1 (`PopupEditor.tsx`), déjà pré-vérifié
   manuellement pendant le brainstorming — à rejouer formellement dans le
   plan, pas à supposer acquis.
2. **Reproduction réelle du second pattern (§2.2)** avant toute décision de
   correctif : construire un état où `MapSymbologyEditor.tsx` a un encodage
   icône catégoriel assigné avec des valeurs/labels assez longs, à 900px,
   mesurer avec la même fonction `measureClipOffenders`/
   `expectNoClippedContent` que `triptych-narrow.spec.ts`. Ne pas corriger à
   l'aveugle si non reproduit.
3. `triptych-narrow.spec.ts` : re-mesurer l'écran Cartes à 900px après
   correctif(s) — 0 offenseur attendu, retirer `wideBoundaryKnownIssue` et
   son commentaire.
4. Pas d'assertion Vitest/jsdom sur la classe CSS ajoutée (jsdom ne fait pas
   de layout — même doctrine que SP-36). Vérifier simplement, par lecture
   directe, qu'aucun test existant de `PopupEditor.test.tsx`/
   `MapSymbologyEditor.test.tsx`/`LayerPicker.test.tsx` n'assertait une
   classe exacte qui casserait avec ces ajouts.
5. `npm run test` et `npm run e2e` verts, couverture shell non régressée
   (seuil 88, mesurée après nettoyage de `dist/`/`dist-export/`).
6. Régénération OpenAPI/types TS : **non nécessaire** — aucune route ni
   modèle cœur ne change (CSS + tests shell/E2E purs).

## 5. Critères de sortie

1. Écran Cartes à 900px : 0 offenseur mesuré par
   `expectNoClippedContent` ; `test.skip()` retiré de
   `triptych-narrow.spec.ts` pour cet écran.
2. Les deux `border-t` de `LayerPicker.tsx` portent `border-rule`.
3. CLAUDE.md : le lot « Carte » est intégralement retiré de `### À venir`
   (plus aucun sous-mécanisme ouvert), avec une entrée `### Livré` datée
   SP-37.
4. Suites shell (`npm run test`) et E2E (`npm run e2e`) vertes, sans
   régression, couverture non régressée.

## 6. Risques et limites connues

- **Second pattern (§2.2) conditionnel** : si la reproduction échoue à
  démontrer un overflow réel, il ne sera pas corrigé par ce plan — pas un
  défaut d'exécution, une décision prise sur preuve (§2).
- **Portée limitée aux deux fichiers consommés par la colonne `browse` de
  l'écran Cartes** : un pattern similaire ailleurs dans le shell (hors
  périmètre de cette spec) resterait non détecté par ce travail.
