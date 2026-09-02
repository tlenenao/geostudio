# SP-34 — Dette de tokens `LayersPanel`/`MapSymbologyEditor` et voisins

Date : 2026-09-03
Statut : validé (brainstorming), prêt pour plan d'exécution

## Motivation

`CLAUDE.md` identifie explicitement ce chantier, depuis SP-30c, comme prêt à
ouvrir une fois SP-30 complètement clos (fait par SP-33, 2026-09-02) : « son
propre chantier … à ouvrir après la clôture complète de SP-30 … pas fusionné
dans une tâche SP-30 existante, pas improvisé en aparté. »

Ce n'est pas une fonctionnalité nouvelle. Les fichiers concernés utilisent
encore des couleurs Tailwind brutes (`slate-*`, `red-*`, `amber-*`,
`blue-700`, `white`) héritées d'avant SP-29a, là où le reste du shell
(post-SP-29a/29b/30) utilise les tokens sémantiques
(`ink`/`ink-2`/`ink-3`/`rule`/`danger`/`warn`/`accent`/`surface`/`sunken`,
`styles/tokens.css`) et le composant `Button` du kit pour les actions
autonomes. Le volume (~48 occurrences de couleurs en dur sur ~2060 lignes,
8 fichiers) et la densité des invariants déjà documentés dans ces fichiers
(bugs I2–I16, M2, M7 des revues finales SP-25/SP-27, chacun avec un
commentaire expliquant pourquoi le code est écrit ainsi) justifient un plan
dédié plutôt qu'un correctif improvisé.

## Périmètre — 8 fichiers, tous sous `shell/src/map/`

1. `LayersPanel.tsx`
2. `MapSymbologyEditor.tsx`
3. `PopupEditor.tsx`
4. `FieldClassificationPicker.tsx`
5. `formFieldStyles.ts`
6. `MapMeasureSketchToolbar.tsx`
7. `MapPopup.tsx`
8. `MapLegend.tsx`

Les trois derniers (6–8) sont des superpositions flottantes **au-dessus du
canevas carte** (`position: absolute`, rendues par-dessus les tuiles de fond
de carte, pas sur une surface d'app) — catégorie distincte des cinq premiers
(éditeurs de formulaire montés dans les onglets Inspecter/Propriétés de
`MapEditorPage`/`PropsPanel`). Question posée et tranchée explicitement en
brainstorming : ces trois fichiers **sont inclus** et **tokénisés
complètement** (pas d'exception de fond figé en blanc), parce que :

- l'ambiance sombre de `tokens.css` répond déjà à
  `prefers-color-scheme: dark` sans bascule in-app requise — un utilisateur
  dont l'OS est en mode sombre voit donc déjà tout le chrome de l'app
  (TopBar, panneaux, formulaires) en ambiance sombre aujourd'hui ;
- ces trois composants peignent leur propre fond avant tout texte
  (`bg-white/90` → `bg-surface/90`, etc.) : il n'y a donc aucun risque de
  contraste contre les tuiles de fond de carte elles-mêmes (le texte ne
  repose jamais directement sur la carte, toujours sur la boîte) ;
- le dépôt n'a établi nulle part ailleurs de précédent « ce composant
  s'exclut délibérément de l'ambiance » — introduire la première exception
  ici serait un choix de design isolé, pas une convention reconduite.

## Hors périmètre, explicitement

- **`LayerPicker.tsx`** — porte sa propre dette de `border-t` non tokenisé
  (notée séparément par la revue finale SP-30c, lignes ~143/173). Pas dans
  la liste nommée par `CLAUDE.md` pour ce chantier ; reste un suivi
  distinct, non traité ici.
- **Conversion des `<select>`/`<input list=…>` (datalist) vers
  `Select`/`Combobox` du kit** — `Select`/`Combobox` du kit sont bâtis sur
  Radix (jsdom : `ResizeObserver`/`hasPointerCapture`/`scrollIntoView`,
  piège n°10 de `CLAUDE.md`), et le motif `<input list=…>` (saisie libre +
  suggestions dynamiques, utilisé pour tous les champs "Champ couleur/
  taille/icône/du contour" et le champ titre de popup) n'a pas d'équivalent
  direct dans le kit — une conversion changerait le comportement (liste
  fermée vs saisie libre), pas seulement l'apparence. Reste natif,
  tokenisé.
- **Conversion du toggle "Couleur de contour fixe/par attribut" vers
  `Segmented` du kit** — resterait un changement structurel (le composant
  actuel encapsule une logique de garde anti-reclic et de reset d'erreur
  documentée comme Important en revue finale SP-27) plutôt qu'une passe
  purement visuelle. Reste natif, tokenisé.
- **Tout changement de comportement.** Aucune des logiques déjà corrigées
  (invariants I2, I3, I4, I5, I9, I13, I16, M2, M7 documentés en commentaire
  dans `MapSymbologyEditor.tsx`/`MapMeasureSketchToolbar.tsx`) n'est
  touchée. Cette passe ne change que `className` et, quand éligible,
  `<button>` natif → `Button` du kit (signature préservée : `type`,
  `onClick`, `disabled`, `aria-*` passent tels quels).

## Règles de conversion

Ces règles appliquent les conventions déjà tranchées le 2026-09-01 dans
`CLAUDE.md` (« Conventions tranchées ») ; elles ne les redéfinissent pas.

### Couleurs → tokens

| Brut | Token |
|---|---|
| `border-slate-300` | `border-rule` |
| `border-slate-200` (séparateurs `border-l-2`) | `border-rule-2` |
| `bg-slate-200` | `bg-sunken` |
| `text-slate-500` | `text-ink-3` |
| `text-slate-400` | `text-ink-3` |
| `text-red-700` / `text-red-600` | `text-danger` |
| `text-amber-600` | `text-warn` |
| `text-blue-700` | `text-accent` |
| `bg-white` / `bg-white/90` | `bg-surface` / `bg-surface/90` |

Toute couleur Tailwind brute rencontrée en cours d'exécution et non listée
ci-dessus se résout par analogie avec ce tableau (ex. une nuance de rouge
non répertoriée → `danger`), jamais en laissant une classe brute.

### `<button>` natif vs `Button` du kit

**Passent au kit `Button`** (`variant="outline" size="sm"` par défaut, ou
`variant="default"` si l'action est la seule action principale isolée d'une
section) — actions autonomes, non répétées :
- `MapSymbologyEditor.tsx` : "Recalculer la taille", "Recalculer le
  contour" (via `FieldClassificationPicker`, le bouton "Recalculer les
  classes"/"Recalculer le contour" partagé), "Recalculer les valeurs"
  (icônes), "Ajouter un contour", "Ajouter des icônes", "Ajouter une
  étiquette".
- `PopupEditor.tsx` : "Ajouter le champ".
- `FieldClassificationPicker.tsx` : le bouton de recalcul partagé
  (labellisé dynamiquement par `labels.recompute`).

**Restent natifs**, deux raisons distinctes déjà actées par la convention
du 2026-09-01 :

1. *Style lien inline* (`text-danger underline` ou équivalent) : tous les
   "Retirer la couleur/taille/contour/icônes/étiquette"
   (`MapSymbologyEditor.tsx`), "Avancé (gabarit)"/"Liste de champs"
   (`PopupEditor.tsx`), "Supprimer l'icône …" (bouton `×` par icône
   personnalisée).
2. *Répété par ligne/item dans une liste dense* : les 4 boutons ↑/↓/👁/✕ par
   couche (`LayersPanel.tsx`) ; chaque bouton de la grille d'icônes
   Lucide/tenant (`MapSymbologyEditor.tsx`, jusqu'à ~140 boutons) ; chaque
   checkbox + libellé par champ disponible (`PopupEditor.tsx`) ; le toggle
   "Couleur de contour fixe/par attribut" (2 boutons `aria-pressed`, hors
   périmètre de conversion structurelle de toute façon, cf. ci-dessus) ; les
   boutons de mode/outil de `MapMeasureSketchToolbar.tsx` (Mesurer/Surface/
   Effacer tout/Croquis + les 5 outils de croquis) — tokenisés en place
   (`border-rule`, `bg-surface/90`), gardés natifs car c'est une barre
   d'outils compacte à état `aria-pressed`, pas un panneau de formulaire.

### Hauteur des contrôles

`formFieldStyles.ts` (`inputCls`) passe de `h-8` à `h-9` (défaut désormais
tranché pour tout contrôle de formulaire non dense). `PopupEditor.tsx`
cesse de dupliquer sa propre copie locale de `labelCls`/`inputCls` et
importe `formFieldStyles.ts` — fermant la duplication que le commentaire de
ce fichier signalait déjà comme un risque de divergence.

**Exception** : les `<input>` internes à une ligne de liste dense restent
`h-8`, même raisonnement que les boutons denses ci-dessus — le champ
"Libellé de {f}" par champ disponible dans `PopupEditor.tsx` (`w-28`,
répété une fois par champ de la collection).

## Vérification & garde-fous

**Aucun changement de comportement attendu.** Les 13 fichiers de test de
`shell/src/map/` ne référencent aucune classe Tailwind en dur (vérifié par
grep avant cette spec) — la suite Vitest existante de ces fichiers doit
rester verte **sans aucune modification**, ce qui sert de garde-fou de
non-régression comportementale : si un test doit changer, c'est le signal
qu'un comportement (pas seulement une classe) a bougé, à traiter comme une
alerte, pas comme un ajustement de routine.

Vérifications de clôture (à détailler dans le plan d'exécution) :

- `grep` de couleurs Tailwind en dur sur les 8 fichiers → doit revenir
  vide. Couvrir explicitement `text-white`/`text-black` sans suffixe
  numérique (angle mort déjà identifié par la revue finale SP-30f, à ne pas
  répéter ici).
- Suite Vitest complète (pas seulement les 13 fichiers de `map/`) + suite
  E2E complète avant de clore le plan (piège n°6 de `CLAUDE.md`) — les
  specs E2E touchant la symbologie/popup/mesure-croquis doivent rester
  verts sans modification de sélecteur.
- Contrôle visuel manuel (serveur de dev, les deux ambiances via
  `prefers-color-scheme`) sur au minimum : l'éditeur de symbologie complet
  (couleur classée + contour + icônes + étiquette), l'éditeur de popup, et
  les trois superpositions carte (légende, barre de mesure/croquis, popup
  au clic) — seul moyen de confirmer que `bg-surface`/`text-ink-*` reste
  lisible en ambiance sombre, aucun test automatisé ne couvrant le rendu
  visuel réel.
- Pas de nouvelle infrastructure de test introduite : `expectTokenizedClasses()`
  reste réservé aux primitives du kit lui-même (son usage actuel) ; le grep
  ci-dessus tient lieu de filet pour ces fichiers consommateurs, comme pour
  les pages SP-30 (SP-30f note explicitement ce même choix).

## Risques identifiés

- `MapSymbologyEditor.tsx` (797 lignes) porte la plus grande densité
  d'invariants documentés du lot — toute conversion `<button>`→`Button` doit
  être vérifiée un par un contre le commentaire adjacent avant de la faire,
  pas déduite du seul motif visuel.
- Le remplacement de la copie locale `labelCls`/`inputCls` de
  `PopupEditor.tsx` par l'import de `formFieldStyles.ts` change la hauteur
  de tous ses contrôles de `h-8` à `h-9` (sauf l'exception dense notée
  ci-dessus) — vérifier visuellement que la liste de champs (checkbox +
  libellé tronqué + input `w-28`) ne casse pas son alignement avec ce
  changement de hauteur mixte (h-9 pour le champ titre/gabarit, h-8 pour le
  libellé par ligne).
