# Undo/redo général du builder (SP-19)

> Spec issue du brainstorm du 2026-08-05, déclenchée en creusant la spec du
> copilote IA embarqué (SP-20) : le copilote a besoin d'un moyen d'annuler une
> suggestion malvenue, et le builder n'a aujourd'hui **aucun** mécanisme
> d'undo/redo, pour aucune édition — manuelle ou assistée. Plutôt que de
> construire un undo scopé au seul copilote, ce chantier livre l'undo/redo
> général du builder, utile à toute édition manuelle, et dont SP-20 devient un
> simple consommateur. Inscrit comme **SP-19** dans la feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md`), sans dépendance
> amont ; SP-20 en dépend.

## 1. Contexte & motivation

Le builder (`shell/src/builder/`) édite un unique objet déclaratif,
`BuilderConfig` (règle d'architecture n°2 du CLAUDE.md), au travers de
plusieurs panneaux : `PropsPanel`, `ActionsPanel`, `DataSourcePanel`,
`ThemePanel`, `VariablesPanel`, `NavigationPanel`, et le canvas lui-même
(`GridCanvas`, glisser-déposer/redimensionnement de widgets, gestion des pages
via `PageManager`). Aucun de ces panneaux ne s'appuie sur un historique
d'annulation : une erreur de manipulation (widget supprimé par erreur, prop
mal éditée, page effacée) n'a aujourd'hui d'autre remède qu'une correction
manuelle ou l'abandon des éditions non enregistrées en rechargeant la page.

Ce manque est resté invisible tant que le builder n'était édité qu'à la main,
un geste à la fois. Il devient bloquant dès qu'un agent (le copilote SP-20)
peut appliquer plusieurs changements en un seul prompt : sans undo, la seule
façon de revenir en arrière après une suggestion malvenue est de désassembler
le résultat manuellement, ou de tout perdre en rechargeant.

## 2. Décision d'architecture : une pile, pas un mécanisme par panneau

Puisque tous les panneaux éditent le **même** objet `BuilderConfig`, un seul
mécanisme d'annulation — une pile d'instantanés de cette config — couvre
uniformément layout, props, sources de données, thème, variables et
navigation. Alternative écartée : une pile de commandes avec fonction inverse
par type de mutation (déplacer, redimensionner, changer une prop…) — plus
économe en mémoire, mais impose d'écrire et maintenir un inverse à chaque
nouvelle capacité du builder ; rejetée pour son coût récurrent face à des
configs de taille modeste (quelques Ko à quelques dizaines de Ko en JSON) où
le surcoût mémoire d'un instantané complet est négligeable.

## 3. Composants

- **`UndoContext`** (`shell/src/builder/UndoContext.tsx`), aux côtés des
  contextes existants (`VariablesContext`, `DataContext`,
  `ActionBusContext`) : expose `pushSnapshot(config: BuilderConfig)`,
  `undo(): BuilderConfig | null`, `redo(): BuilderConfig | null`, `canUndo`,
  `canRedo`. Pile en mémoire (deux tableaux, passé/futur, purgés l'un de
  l'autre à chaque nouveau `pushSnapshot`), plafonnée à **50 pas** (le plus
  ancien est éliminé au-delà). Éphémère : perdue à la sortie de l'éditeur ou
  au rechargement — aucune persistance, cohérent avec le choix similaire fait
  pour l'historique de conversation du copilote (SP-20).
- **Point de commit unique.** L'éditeur (`AppRenderer` en mode `edit`) détient
  déjà le setter React qui reçoit toute nouvelle version de la config, quel
  que soit le panneau d'origine — c'est le seul endroit modifié : avant
  d'appliquer un nouveau `BuilderConfig`, il appelle `pushSnapshot` avec la
  version précédente. Aucun panneau individuel n'est touché.
- **Granularité des actions continues — corrigé au moment du plan
  (2026-08-15), contre le code réel.** L'hypothèse d'origine ci-dessus
  (panneaux gardant déjà un état local « en cours » séparé de la config
  commitée) est fausse pour ce dépôt : `GridCanvas` n'a pas de glisser-
  déposer (déplacement par boutons flèche discrets, un clic = un cran, déjà
  un commit atomique correct, rien à changer) ; en revanche **tous** les
  champs texte du builder (les ~20 `PropsPanel` de widgets sous
  `shell/src/builder/widgets/`, plus `PropsPanel`'s `visibleWhen`,
  `ThemePanel`, `VariablesPanel`, `ActionsPanel`, `NavigationPanel`,
  `DataSourcePanel`) appellent `onChange` — donc `setDraft` — à chaque
  frappe, sans aucun état local. Pousser une capture undo à chaque appel
  ferait exploser la pile (un pas par caractère) ; boucler un état local +
  commit au blur sur chacun de ces ~20-25 fichiers est un diff invasif
  disproportionné et régresserait l'aperçu live pendant la frappe.
  **Décision (arbitrage tranché avec Tanguy au moment du plan) : coalescing
  centralisé par minuterie d'inactivité**, implémenté une seule fois dans le
  point de commit unique (jamais dans les panneaux individuels) : le premier
  `setDraft` d'une rafale capture la config d'avant-rafale comme candidat de
  `pushSnapshot` ; les appels suivants dans la même rafale ne recapturent
  rien ; un minuteur d'inactivité (~400ms sans nouvel appel) déclenche le
  push effectif. `draft` lui-même continue de se mettre à jour à chaque
  frappe (aucune régression de l'aperçu live) — seul le moment du
  `pushSnapshot` est différé. Ceci **remplace** le mécanisme « blur du champ »
  décrit ci-dessus (aucun champ n'a besoin d'être modifié) et **abroge**
  explicitement l'exclusion de la fusion par proximité temporelle en §4
  ci-dessous, dont la justification d'origine ne tenait plus une fois
  l'hypothèse de bufferisation locale invalidée.
- **UI.** Boutons Annuler/Rétablir dans la barre d'outils du builder
  (`GridCanvas` ou le conteneur qui l'englobe), désactivés selon
  `canUndo`/`canRedo`. Raccourcis clavier `Ctrl+Z` / `Ctrl+Shift+Z`
  (`Cmd` sur macOS), actifs uniquement quand le focus est dans le builder et
  pas dans un champ de saisie de texte (pour ne pas intercepter l'undo natif
  du navigateur dans un `<input>`).
- **Consommateur SP-20.** Le bouton « Annuler » affiché par le copilote sur un
  message contenant des `clientOps` appelle `undo()` de ce même contexte —
  aucun mécanisme dédié au copilote.

## 4. Hors périmètre v1

- Undo/redo à travers un rechargement de page (pas de persistance de la
  pile).
- Undo/redo qui traverserait plusieurs items différents (un seul builder
  ouvert = une seule pile, portée à l'item en cours d'édition).
- ~~Fusion intelligente de pas consécutifs proches dans le temps~~ —
  **abrogé, cf. §3** : c'est devenu le mécanisme central de granularité
  (minuterie d'inactivité ~400ms), pas une amélioration optionnelle, une
  fois l'hypothèse de bufferisation locale par champ invalidée contre le
  code réel.
- Indicateur visuel du contenu de chaque pas (type de changement, diff) —
  les boutons Annuler/Rétablir restent muets sur ce qu'ils vont faire au-delà
  du contexte déjà visible à l'écran (v1 minimal, à enrichir si le besoin est
  démontré).

## 5. Risques

Le risque principal est **un panneau qui contournerait le point de commit
unique** — modifierait le state de config par un autre chemin que le setter
central, rendant certaines de ses éditions invisibles à la pile d'undo. Ce
risque doit être traité explicitement dans le plan : un audit de chaque
panneau (`PropsPanel`, `ActionsPanel`, `DataSourcePanel`, `ThemePanel`,
`VariablesPanel`, `NavigationPanel`, `GridCanvas`) pour confirmer qu'il
n'existe qu'une seule voie de mutation de la config en édition, avec un test
dédié par panneau si un contournement est trouvé et corrigé.

## 6. Tests & critères d'acceptation

- **Unitaire** : `UndoContext` — push/undo/redo, plafond de profondeur (le
  51ᵉ `pushSnapshot` élimine le plus ancien pas), purge du futur après un
  nouveau push suivant un undo.
- **Intégration** (au moins 3 panneaux représentatifs) : déplacer un widget
  dans `GridCanvas` puis `Ctrl+Z` restaure sa position ; éditer une prop dans
  `PropsPanel` puis annuler restaure l'ancienne valeur ; ajouter une page dans
  `NavigationPanel` puis annuler la retire.
- **E2E (Playwright)** : dans le builder, une action (ex. ajout de widget
  depuis la palette) suivie de `Ctrl+Z` restaure l'état précédent visible à
  l'écran ; `Ctrl+Shift+Z` la rétablit.

**Critères d'acceptation** :
1. Toute mutation de config commitée dans n'importe quel panneau est
   annulable par `Ctrl+Z`.
2. Un drag ou une saisie de texte ne produit qu'un seul pas d'undo, pas un
   pas par événement intermédiaire.
3. Le plafond de 50 pas est respecté (pas de fuite mémoire sur une longue
   session d'édition).
4. `Ctrl+Z` dans un champ de saisie de texte ne déclenche pas l'undo du
   builder (comportement natif du champ préservé).
