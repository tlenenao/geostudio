# Diagnostic UI/UX GeoStudio — conception du workflow d'audit

> Statut : **proposition** (2026-09-24), non exécutée. Adapte et enrichit la
> grille « Diagnostic UI/UX GeoStudio — grille pour workflow subagents » fournie
> par Tanguy. Lecture seule sur le dépôt ; tout artefact produit pendant l'audit
> (scripts Playwright jetables, captures) va dans le scratchpad, jamais dans
> `shell/`.

## 1. Ce que l'analyse de la grille d'origine a montré

La grille est bonne sur le fond (10 axes, 59 points, format de sortie
normalisé) mais présente quatre faiblesses qui feraient produire à un
workflow des résultats **faux ou redondants** sur ce dépôt :

1. **Exemples périmés présentés comme des hypothèses de défaut.** Vérifié ce
   jour dans le code :
   - caméra pitch/bearing et sélection de basemap sur le widget carte →
     livrés par SP-51 (`shell/src/builder/widgets/mapWidget.tsx:206-217`) ;
   - couche `deck` heatmap/hexbin/column créable dans `LayerPicker` →
     livrée (SP-51, GAP-36, `shell/src/map/LayerPicker.tsx:50-52`) ;
   - opacité raster → livrée (GAP-35) ; `haloColor`/`haloWidth` → présents
     dans `MapSymbologyEditor.tsx` ;
   - `showScaleBar`/`showNorthArrow` → consommés par `PrintLayoutPanel`,
     `MapEditorPage`, `AppRuntimePage`.
   Un agent amorcé avec « ex. pitch forcé à 0 » a un biais de confirmation
   (piège n°12 : le récit prime sur le code). **Correctif : les points
   deviennent des questions neutres, et chaque auditeur doit d'abord lire
   l'historique de la surface** (`historique-execution-continu.md`,
   `analyse-gaps.md`, `backlog.md`) pour qualifier un point de
   *régression*, *résidu connu* (REV/GAP existant) ou *nouveau*.
2. **Aucune dédup avec l'existant.** 23 GAP encore ouverts, 17 REV ouverts
   (dont REV-176 contraste `--gs-ink-3`, REV-177/178 i18n/a11y, REV-088
   aria-expanded). La sortie doit référencer ces identifiants, pas les
   redécouvrir.
3. **Preuve uniquement statique.** Or « lien absent », « 403 visible »,
   « colonne qui clippe », « focus invisible » sont des propriétés
   *rendues* : lire le code ne suffit pas (piège n°11 : un grep ne prouve
   pas l'absence d'un comportement). Il faut une passe dynamique.
4. **Pas de vérification adversariale ni de matrice rôle × flag.** Or la
   moitié des défauts de découvrabilité de ce dépôt (SP-46, SP-35) étaient
   des asymétries *par privilège* ou *par flag*, invisibles depuis un seul
   profil.

Premiers signaux mesurés (à confirmer par l'audit, pas des conclusions) :
`EmptyState` du kit utilisé dans **4** fichiers seulement ; **56**
occurrences de « Chargement… » texte ; **158** classes Tailwind de couleur
brute (dont une partie légitime en ambiance) ; **56** fichiers sur le kit
contre **41** encore sur l'ancien `ui/*`.

## 2. Grille enrichie

Les 59 points d'origine sont conservés (IDs 1-59 inchangés pour la
traçabilité), reformulés en questions neutres là où ils étaient amorcés.
Ajouts : IDs **60-88**, trois axes nouveaux (11-13) et des points dans les
axes existants.

### Reformulations des points amorcés

| ID | Formulation neutre |
|----|--------------------|
| 7 | Champs de `AppConfig`/`MapConfig`/`printLayout` (schéma JSON + types générés) sans contrôle d'édition dans aucun host — dériver la liste mécaniquement depuis le schéma, pas depuis des exemples |
| 8 | Kinds de couches rendus par `MapView` vs créables par `LayerPicker` vs créables par le copilote/MCP — matrice complète |
| 12-19 | Pour chaque propriété de carte : éditable dans `MapEditorPage` ? dans le panneau du widget ? rendue identiquement ? Matrice propriété × host, pas des cas choisis |

### Ajouts aux axes existants

| ID | Axe | Point |
|----|-----|-------|
| 60 | 1 Nav | Deep-link : chaque éditeur restaure-t-il son état (onglet, sélection, nœud) depuis l'URL ; bouton retour navigateur cohérent |
| 61 | 1 Nav | Recherche globale / palette de commandes (`Kbd` existe dans le kit) : présence, portée |
| 62 | 1 Nav | Matrice **rôle × flag** : pour les 4 rôles prédéfinis × flags `CORE_*_ENABLED` on/off, liste des entrées visibles / fonctionnelles / 403 |
| 63 | 2 Inerte | Clés i18n définies jamais référencées, et composants `ui/*` legacy encore montés à côté de leur équivalent kit |
| 64 | 4 Empty | Taux d'adoption de `ui/kit/EmptyState` : chaque liste/grille a-t-elle un état vide *avec action suivante* (CTA créer/importer) |
| 65 | 5 Feedback | Actions destructives : confirmation (`ConfirmDialog`) systématique ? annulation possible ? libellé nommant l'objet ? |
| 66 | 5 Feedback | Perte de travail : garde de navigation sur brouillon non sauvegardé (builder, carte, pipeline, SQL Lab) |
| 67 | 5 Feedback | Mise à jour optimiste vs attente serveur ; états « enregistré / enregistrement… / échec » visibles |
| 68 | 5 Feedback | Perte réseau / cœur injoignable : message, reprise, pas d'écran blanc (`AppErrorBoundary`) |
| 69 | 6 Formulaires | Tables de données (`DataTable`) : tri, pagination, filtrage, sélection, largeur de colonnes — homogènes entre admin, aperçu pipeline, SQL Lab, widget table |
| 70 | 6 Formulaires | Saisie de valeurs typées (dates, nombres FR, couleurs, CEL) : aide, exemples, erreurs de syntaxe CEL localisées |
| 71 | 7 A11y | Navigation clavier sur la carte (zoom, sélection d'entité, fermeture popup) et dans le canevas DAG pipeline |
| 72 | 7 A11y | `prefers-reduced-motion`, taille de cible ≥ 24 px, zoom navigateur 200 % sans perte |
| 73 | 7 A11y | Couverture axe-core : pages hors des 9 auditées par `a11y-audit.spec.ts` (REV-178) |
| 74 | 8 Onboarding | Texte d'interface : ton, cohérence terminologique (glossaire), troncature, pluriels, formats de date/nombre `fr-FR` |

### Axe 11 — Expérience cartographique (nouveau)

| ID | Point |
|----|-------|
| 75 | Légende : présente, synchronisée avec la symbologie, lisible dans les deux thèmes |
| 76 | Attributions de fond de carte et de sources : affichées, conformes |
| 77 | Interaction tactile / mobile (pinch, popups, barre de mesure) sur le runtime et les sites publics |
| 78 | Retour visuel de chargement des tuiles / couches lourdes ; message au plafond MVT de 5000 lignes (SP-24) |
| 79 | Zoom sur l'emprise des données à l'ouverture (emprise persistée SP-55) |

### Axe 12 — Performance perçue (nouveau)

| ID | Point |
|----|-------|
| 80 | LCP / TTI des routes principales (catalogue, éditeur de carte, builder, site public) en build prod |
| 81 | Taille de chunk par route vs `.bundle-size-threshold` ; routes lourdes non `lazy()` |
| 82 | Latence d'interaction : saisie dans les panneaux du builder, déplacement de nœud pipeline, tri de table 10k lignes |
| 83 | Requêtes redondantes (React Query : clés, `staleTime`, cascades séquentielles évitables) |

### Axe 13 — Cohérence du système de design (nouveau)

| ID | Point |
|----|-------|
| 84 | Migration kit : inventaire des écrans encore sur `ui/*` legacy, par famille triptyque |
| 85 | Respect des conventions tranchées du 2026-09-01 (`h-9` par défaut, `Button` vs `<button>`, `aria-expanded`) |
| 86 | Espacements / typographie : échelle de tokens respectée ou valeurs ad hoc (`px-[13px]`, `text-[11px]`) |
| 87 | Iconographie : bibliothèque unique, tailles et libellés accessibles |
| 88 | Hiérarchie des actions : une action primaire par vue, placement constant (en-tête de colonne vs pied de panneau) |

## 3. Référentiel de notation

Chaque ligne de sortie :

```text
| id | statut | preuve | niveau de preuve | persona | sévérité | fréquence | effort | lien existant | note |
```

- **statut** : `ok | partiel | ko | n/a`
- **preuve** : `chemin:ligne`, route, ou capture (`scratchpad/…/NN-route-largeur-theme.png`)
- **niveau de preuve** : `lu` (code) · `exécuté` (Playwright/test) · `capturé` (rendu observé). Un `ko` d'impact élevé doit être au moins `exécuté` ou `capturé`, sinon il est rétrogradé `à confirmer`.
- **persona** : Administrateur · Créateur · Analyste · Lecteur · Visiteur anonyme · Intégrateur (embed/SDK)
- **sévérité** (échelle Nielsen) : 0 cosmétique → 4 bloquant (tâche impossible ou perte de données)
- **fréquence** : 1 rare · 2 parcours secondaire · 3 parcours principal
- **impact** = sévérité × fréquence (0-12) — remplace H/M/L, plus discriminant pour le classement
- **effort** : `S` (<½ j, un fichier) · `M` (1-2 j, plusieurs fichiers) · `L` (SP à part entière, spec)
- **lien existant** : `GAP-nn` / `REV-nnn` / SP de livraison, ou `nouveau` / `régression`

## 4. Workflow proposé

### Vue d'ensemble

```text
Phase 0  Cartographie déterministe        1 agent
   │  (inventaires mécaniques partagés par tous)
   ▼
Phase 1  Audit statique par domaine       5 agents en parallèle ──┐
Phase 1b Parcours dynamiques par persona  1 agent (Playwright)  ──┤ pipeline
   ▼                                                               │
Phase 2  Vérification adversariale        1 agent par domaine ◄───┘
   │  (uniquement ko/partiel d'impact ≥ 6)
   ▼
Phase 3  Consolidation + vagues + filets  1 agent
```

~13 agents au total (au-dessus du repère « medium » de 10 : variante
compacte à 9 agents en fusionnant la vérification en un seul agent en fin
de phase 1).

### Phase 0 — Cartographie (1 agent, sortie JSON)

Produit des inventaires **mécaniques** (scripts/greps dans le scratchpad),
que tous les auditeurs consomment au lieu de re-scanner :

- routes de `shell/src/shell/routes.tsx` + pour chacune : liens entrants
  (nav triptyque, `DomainBar`, `SettingsNav`, `BottomNav`, `ItemActions`,
  `NewItemButton`, liens in-page), garde `capabilities`/privilège ;
- flags `CORE_*_ENABLED` : exposition côté shell (`ConfigContext`), écrans
  concernés ;
- privilèges (18) → routes/entrées qui les exigent ;
- kinds d'item (12 visibles) → parcours de création, éditeur, runtime ;
- méthodes `ItemClient` → sites d'appel ; outils MCP → équivalent UI ;
- champs du schéma `AppConfig`/`MapConfig` → contrôles d'édition trouvés ;
- surfaces de `inventaire-fonctionnalites.jsonl` de type route shell ;
- GAP/REV ouverts touchant l'UI (pour la dédup).

### Phase 1 — Audit statique (5 agents)

| Agent | IDs | Focus |
|-------|-----|-------|
| `nav-inert` | 1-11, 60-63 | Routes, menus, création d'items, rôle × flag, schémas orphelins, ItemClient/MCP |
| `map-dual-host` | 12-19, 75-79 | Matrice propriété × host, UX cartographique |
| `states-feedback` | 20-33, 64-68 | Empty/loading/erreur/429/jobs/readonly/destructif/perte de travail |
| `forms-a11y-design` | 34-46, 69-73, 84-88 | Formulaires, tables, a11y statique, tokens, conventions, kit |
| `journeys-power` | 47-59, 74 | Onboarding, libellés, partage/embed/sites, SQL Lab, pipeline, harvest, copilote, export |

Consignes communes injectées dans chaque prompt :
- lire d'abord l'historique de la surface (archive + gaps + backlog) ;
- suivre le chemin d'exécution réel (primitives `Gate`, `hasPermission`,
  `capabilities.ts`), jamais conclure d'un grep négatif ;
- ne rien modifier sous `shell/` ou `core/` ;
- sortie structurée (schéma JSON = colonnes du §3).

### Phase 1b — Parcours dynamiques (1 agent)

Script Playwright **jetable dans le scratchpad**, réutilisant
`shell/e2e/mocks.ts` et `fixtures/` (mode `VITE_AUTH_MODE=mock`, aucun
cœur requis) :

- 8 parcours scénarisés : premier usage Créateur (catalogue vide → carte →
  app → partage → publication), Analyste (dataset → requête visuelle → SQL
  Lab → rapport), Lecteur (catalogue → runtime), Admin (utilisateurs,
  rôles, collections, harvest), Visiteur anonyme (site public, embed,
  lien de partage expiré), mode démo lecture seule, erreurs forcées
  (500, 403, 429, timeout), flags éteints ;
- chaque écran capturé à **360 / 900 / 1440 px × clair / sombre** ;
- axe-core sur toutes les routes atteintes (pas seulement les 9 de
  `a11y-audit.spec.ts`) ;
- parcours clavier seul (Tab/Shift-Tab/Échap/Entrée) sur 3 parcours
  critiques, focus visible vérifié par capture ;
- Lighthouse (build prod via `npm run build && vite preview`) sur 4 routes
  pour l'axe 12.

Ses constats nourrissent les 5 domaines avec niveau de preuve `capturé`.

### Phase 2 — Vérification adversariale (par domaine, en pipeline)

Pour chaque `ko`/`partiel` d'impact ≥ 6 : un vérificateur tente de
**réfuter** le constat (le lien existe-t-il ailleurs ? le flag masque-t-il
bien ? est-ce un REV déjà fermé ?). Verdict `confirmé | réfuté |
reclassé`. Les domaines vérifient dès que leur audit se termine
(pipeline, pas de barrière globale).

### Phase 3 — Consolidation (1 agent)

1. Fusion, dédup (même cause racine → une ligne, IDs multiples), liaison
   GAP/REV.
2. Classement impact × effort : **gains rapides** (impact ≥ 6, effort S),
   **chantiers** (impact ≥ 6, effort M/L), **finitions** (impact < 6).
3. **Trois vagues** de correctifs, chacune découpable en SP :
   - Vague A — bloquants et découvrabilité (sévérité 3-4, parcours
     principaux, matrice rôle × flag) ;
   - Vague B — états système et cohérence (empty states avec CTA, pattern
     unique de chargement/erreur, confirmations, garde de perte de
     travail, migration kit du reste) ;
   - Vague C — polish, a11y AA complète, performance perçue, onboarding.
4. **Filets anti-régression** proposés pour chaque classe récurrente
   (culture du dépôt : une classe payée deux fois devient une porte CI) —
   ex. règle ESLint interdisant les couleurs Tailwind brutes hors
   ambiance, test d'inventaire « toute route shell a au moins un lien
   entrant ou est déclarée `deep-link-only` », extension d'axe-core à
   toutes les routes, test de matrice rôle × nav.
5. Livrables : `docs/revue/2026-09-xx-diagnostic-ui-ux.md` (tableau
   consolidé + vagues), captures référencées, nouvelles entrées `REV-nnn`
   proposées (non écrites dans le backlog tant que non validées).

## 5. Hors périmètre

- Aucune correction pendant le diagnostic.
- Pas de test utilisateur réel (le diagnostic est une évaluation experte ;
  une passe de tests utilisateurs pourra valider la vague A).
- Le cœur n'est examiné que pour ce qu'il expose à l'UI (problem+json,
  429, flags).
