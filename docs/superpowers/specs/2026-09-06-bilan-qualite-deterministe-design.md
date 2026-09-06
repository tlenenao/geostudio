# Bilan déterministe de qualité des fonctionnalités — design

**Date :** 2026-09-06. **Branche :** `dev`. **Origine :** question de Tanguy —
« est-il possible/pertinent de construire un modèle déterministe de ranking de
la qualité globale de GeoStudio et de ses fonctionnalités pour alimenter
`docs/revue/2026-09-04-matrice-fonctionnalites.md` ? »

## 0. Réponse à la question posée

**Oui, mais pas sous la forme demandée.** Un « ranking de qualité globale »
entièrement déterministe est un faux objectif : il mélangerait des mesures et
des opinions sous une moyenne unique. C'est déjà le défaut du document actuel,
qui l'avoue lui-même (« ce sont des jugements d'agents, pas des mesures »).

Ce qui est possible, et pertinent, c'est de **séparer deux grandeurs** qui
sont aujourd'hui moyennées ensemble :

- une **santé calculée** (0-100), déterministe, rejouable, gardable en CI ;
- une **priorité produit déclarée** (3 niveaux), qui ne bouge que par décision
  explicite.

Et surtout : **le gain principal n'est pas le classement, c'est la
regénérabilité.** La matrice actuelle n'a aucun générateur commité — `grep -rl
"sp42-matrice"` sur les scripts du dépôt ne renvoie rien. Le `.md` de 238 Ko a
été produit une fois par un agent depuis un JSONL, jamais par un script
rejouable. C'est la cause réelle de sa dérive, pas la subjectivité des notes.
Ce chantier transforme une photo qui pourrit en une commande.

### Besoins retenus

Trois des quatre usages possibles, choisis par Tanguy :

1. **Priorisation** du travail restant — trier « quoi attaquer au prochain SP ».
2. **Garde-fou de non-régression** en CI — dans l'esprit de `.coverage-threshold`
   et `.bundle-size-threshold` déjà en place.
4. **Remplacer la revue manuelle** — la matrice se regénère à chaque clôture de
   SP, plus jamais huit cartographes.

Écarté explicitement : **communication externe** de maturité (README, page
publique). Ce n'est pas l'objet, et cela aurait imposé des contraintes de
lisibilité agrégée contradictoires avec le besoin n°2.

## 1. Ce qui est mesurable, et ce qui ne l'est pas

Les six critères actuels de la matrice ne se valent pas devant l'automatisation.

| Critère actuel | Mécanisable ? | Devient |
|---|---|---|
| **découvrabilité** | oui, franchement | sous-score *atteignabilité* |
| **tests** | oui | sous-score *tests* |
| **sécurité** | oui, en négatif | sous-score *garde* |
| **complétude** | oui, par proxy | sous-score *dette ouverte* |
| **qualité du code** | proxys faibles seulement | **sort du score** — reprise de faits (§5) |
| **utilité** | non | **priorité produit déclarée** (§4) |

### Pourquoi `utilité` sort du calcul

Aucun signal du dépôt ne dit si une fonctionnalité sert à quelqu'un. C'est un
arbitrage produit. Le prétendre calculé serait un mensonge, et un mensonge que
la CI ferait respecter.

### Pourquoi `qualité du code` sort du score

Elle est déjà outillée, et mieux : `ruff`, `ruff format`, `mypy --strict`,
`lint-imports` (30 entrées), les deux seuils de couverture, `eslint`,
`prettier`, `pre-commit`. La remesurer par des proxys (taille de fichier,
duplication) ajouterait du bruit dans un score gardé par la CI : un fichier qui
grossit légitimement ferait échouer la build sans qu'aucune qualité n'ait
baissé. Elle reste **affichée** dans le bilan, mais comme fait repris (§5),
jamais comme note.

## 2. Architecture — inventaire hybride avec réconciliation qui échoue

Trois ancrages étaient possibles. Mesures faites en session sur le dépôt réel :

| Surface | Dérivable statiquement ? | Compte réel |
|---|---|---|
| Routes REST | oui — `core/openapi.json` (à jour, porte `/v1/`) | 94 chemins / 122 opérations |
| Outils MCP | oui — `@server.tool(` dans `core/app/mcp/` | 27 outils + 1 ressource |
| Routes shell | oui — `shell/src/shell/routes.tsx` | 28 déclarations `path=` (27 chemins + le joker) |
| Widgets builtin | **non** — registre peuplé à l'exécution par `registerWidget()` | indéterminable statiquement |

Soit **~150 surfaces techniques dérivables**, contre **304 lignes** dans la
matrice actuelle. L'écart n'est pas du bruit : « undo/redo du builder »,
« symbologie catégorielle », « cross-filter » n'ont ni route ni tool — elles
vivent dans un composant et resteraient invisibles à tout inventaire dérivé.
Un modèle 100 % automatique perdrait la moitié du produit, et les parties les
plus travaillées.

**Approche retenue : hybride.**

```
  surfaces dérivées du code            inventaire déclaratif
  (openapi.json, @server.tool,         (docs/revue/inventaire-
   routes.tsx)                          fonctionnalites.jsonl)
            \                                   /
             \                                 /
              +----> réconciliation <---------+
                          |
             +------------+------------+
             |                         |
      échec CI si une         calcul des 4 sous-scores
      surface dérivée         (couverture, atteignabilité,
      n'a aucune entrée       garde, dette ouverte)
                                        |
                              rendu du bilan (.md)
```

L'inventaire déclaratif porte **toutes** les fonctionnalités, y compris celles
sans surface technique. Les surfaces dérivées ne servent pas à construire
l'inventaire : elles servent à **prouver qu'il est complet**. Une route neuve
non rattachée à une entrée fait échouer la CI.

C'est le seul des trois ancrages qui transforme la péremption silencieuse en
échec bruyant. Il dégrade proprement : si l'inventaire n'est pas tenu, la CI le
dit ; il ne ment jamais en silence.

## 3. Axe 1 — la santé (calculée, 0-100)

Quatre sous-scores, tous dérivés du dépôt, agrégés par moyenne pondérée. Les
pondérations vivent dans `scripts/feature_health_thresholds.json`, versionnées
et modifiables sans toucher au code.

### 3.1 `tests`

Couverture lignes/branches des fichiers de preuve, plus l'existence d'une spec
E2E qui touche la surface.

Sources : `core/coverage.xml` (274 entrées par fichier) et
`shell/coverage/coverage-summary.json` (289 entrées).

**Piège vérifié en session, à ne pas rejouer :** `coverage.xml` déclare
`<sources><source>/…/core/app</source></sources>` — ses `filename` sont
relatifs à **`core/app/`**, pas à `core/`. Une première tentative de
rattachement avec le mauvais préfixe donnait 165/304 ; corrigée, elle donne
**256/304 (84 %)**.

Les **32 lignes sans aucun chemin `core/`/`shell/`** sont les lignes
Infrastructure (`docker-compose.yml`, `deploy/`, `.github/`). Elles n'auront
jamais de couverture : leur sous-score `tests` est calculé autrement — une
règle de `core/tests/test_deployability.py` (19 règles, 35 tests) qui couvre
la ligne, ou aucune. Ce n'est pas une exception ad hoc : c'est le signal
naturel de cette famille.

### 3.2 `atteignabilité`

La surface est-elle réellement atteignable depuis un usage normal du produit ?

- route REST : présente dans `openapi.json` (généré depuis l'app — y figurer
  *est* la preuve du montage) ;
- outil MCP : `@server.tool(` dans `core/app/mcp/` ;
- route shell : `<Route path=…>` dans `routes.tsx` **et** au moins une mention
  du chemin ailleurs dans `shell/src` (hors `routes.tsx` et hors fichiers de
  test) — lien, `navigate()`, ou entrée de nav.

C'est le calcul qui a produit l'état `inerte` — les 13 lignes qui sont la
trouvaille phare de SP-42 — aujourd'hui fait à la main, une fois, par huit
agents.

**Validé en session, avec une trouvaille réelle :** appliquée aux 28 routes du
shell, la méthode signale `/bookmarks` comme n'ayant **aucun lien entrant**.
Vérification manuelle : le chemin `/bookmarks` n'apparaît qu'une seule fois
dans tout `shell/src` — sa propre déclaration `routes.tsx:315`. Or
`useCreateBookmark` est bien câblé (`pages/AppRuntimePage.tsx:114`) : un
utilisateur peut **créer** des signets et n'a ensuite aucun moyen de les
retrouver. C'est une 14ᵉ ligne `inerte`, sur une fonctionnalité livrée par
SP-14m au jalon M11, absente des 13 recensées par SP-42. Deux minutes de calcul
mécanique ont trouvé ce que huit cartographes avaient manqué.

**Contrainte de méthode (piège n°11 de `CLAUDE.md`) :** un `grep` sur un mot ne
prouve pas l'absence d'un comportement. Ici le calcul porte sur un **littéral
de chemin de route**, pas sur un nom de fonction — c'est ce qui le rend fiable.
Les chemins construits dynamiquement (un `navigate()` sur gabarit, par
exemple vers `/items/<pk>`) sont détectés par leur préfixe littéral, vérifié en
session sur les 27 chemins réels.

### 3.3 `garde`

Présence d'une garde d'autorisation sur le **chemin d'exécution réel** :
`require_privilege` / `require_any_privilege` / `rls_scope` / garde d'egress /
`can()`. Jamais un `grep` sur un nom de garde — une notation de la revue SP-42
s'est déjà trompée ainsi (piège n°11). Le calcul suit les dépendances FastAPI
déclarées sur la route, résolues depuis `openapi.json` et le module qui la
définit.

Une route publique par conception (`GET /share-links/{token}`, `/sitemap.xml`,
`/health`) est déclarée telle dans l'inventaire et n'est pas pénalisée.

### 3.4 `dette ouverte`

Nombre de `GAP-nn` (79, `analyse-gaps.md`) et `REV-nnn` (178, `backlog.md`)
**encore ouverts** dont la description cite un des fichiers de preuve de la
ligne. Ces deux documents sont déjà tenus à jour à chaque clôture de SP —
obligation inscrite dans `CLAUDE.md` depuis le 2026-09-06. Ce sous-score les
consomme sans les dupliquer.

## 4. Axe 2 — la priorité produit (déclarée)

Trois niveaux : `haute` / `moyenne` / `basse`. Champ de l'inventaire, modifié
seulement par décision explicite de Tanguy — jamais recalculé.

**Amorçage** pour ne pas imposer 304 arbitrages d'un coup : dérivée une fois
des notes `utilite` existantes du JSONL SP-42 (≥8 → haute, 5-7 → moyenne, ≤4 →
basse), puis corrigée à la main là où c'est faux. L'amorçage est un point de
départ, pas une vérité : il est marqué comme tel dans l'inventaire
(`priorite_source: "amorcage-sp42"`) et bascule à `"declaree"` dès qu'un humain
la confirme ou la change.

**Le tri de priorisation** (besoin n°1) est `priorité × (100 − santé)` : ce qui
compte le plus et qui va le moins bien. Aucune moyenne des deux axes n'est
jamais calculée ni affichée — ce sont des grandeurs de nature différente.

## 5. La qualité du code — reprise, pas remesure

Le bilan affiche des faits de qualité par fonctionnalité, **lus** dans les
portes existantes. Aucun nouveau calcul, aucun doublon.

Le tri est net entre deux sortes de portes.

**Portes binaires à l'échelle du dépôt** — `ruff`, `ruff format`, `eslint`,
`prettier`, `tsc --noEmit`, `pre-commit` : toujours vertes (sinon la CI est
rouge et il n'y a pas de bilan à faire). Les afficher par fonctionnalité serait
une colonne constante. **Non reprises.**

**Portes discriminantes par module ou par fichier**, déjà écrites, gratuites à
lire — comptes mesurés en session :

| Reprise | Où c'est déjà écrit | Discriminant |
|---|---|---|
| typage strict | `.github/workflows/ci.yml:60` — `mypy --strict` ne couvre que **6 modules sur 42** de `core/app` (`auth`, `secrets`, `analytics`, `copilot`, `admin_tools`, `roles`) | fortement |
| dette d'architecture avouée | `ignore_imports` de `core/pyproject.toml` — chaque exemption nomme une arête précise (`app.quotas.service -> app.collections.models`, `app.configs.bbox -> app.collections.extent`…) avec sa justification | par module |
| dette de lint avouée | `eslint-disable` — **10 fichiers** de `shell/src` | par fichier |
| échappatoire de typage | `@ts-expect-error` / `: any` — **7 fichiers** de `shell/src` | par fichier |

L'allowlist i18n (`shell/scripts/i18n-coverage-allowlist.json`) est **vide**
(`[]`) : rien à reprendre de ce côté, ce qui est en soi un résultat.

Ces reprises sont des **dettes déjà avouées par leur auteur**, pas des
jugements neufs. Les remonter rend visible, par fonctionnalité, ce qui n'était
lisible qu'en ouvrant un `pyproject.toml` de 300 lignes.

**Elles n'entrent pas dans le score de santé.** Sinon ajouter une exemption
`ignore_imports` légitime et documentée ferait échouer la build — cela
punirait exactement le geste honnête qu'on veut encourager.

## 6. Le garde-fou CI

Deux portées, cumulées. Une troisième a été examinée et écartée.

### 6.1 Retenu — surface non inventoriée

Une route REST, un outil MCP ou une `<Route>` shell qui n'est rattachée à
aucune entrée de l'inventaire fait **échouer la CI**.

C'est le cœur du besoin n°2 : le geste qu'on veut rendre impossible, c'est de
livrer une fonctionnalité sans la déclarer. Sans cela, l'inventaire repérit
exactement comme la matrice l'a fait — 17 SP pendant lesquels rien ne signalait
sa péremption (piège n°12 de `CLAUDE.md`, déjà payé une fois).

### 6.2 Retenu — plancher

Deux seuils, dans `scripts/feature_health_thresholds.json` :

- aucune fonctionnalité de priorité **haute** ne descend sous un seuil de santé ;
- la santé médiane du dépôt ne recule pas.

Grossier, robuste, exactement l'esprit de `.coverage-threshold` et
`.bundle-size-threshold` déjà en place — et comme eux, relevable par un commit
explicite quand la baisse est assumée.

### 6.3 Écarté pour l'instant — régression par ligne

Faire échouer dès qu'une fonctionnalité déjà inventoriée perd de la santé est
plus fin, mais bruyant : un refactor qui déplace du code ferait bouger des
scores sans qu'aucune qualité n'ait baissé. SP-43 a découpé `itemClient.ts`
(1743→53 lignes) et `mcp/tools.py` — sous cette règle, la CI aurait hurlé sur
un travail qui améliorait le dépôt. À rajouter si le plancher se révèle trop
lâche, pas avant.

## 7. Artefacts et emplacements

| Artefact | Chemin | Rôle |
|---|---|---|
| Inventaire | `docs/revue/inventaire-fonctionnalites.jsonl` | source déclarative, une ligne par fonctionnalité, `id` stable |
| Générateur | `scripts/feature_health.py` | calcule les 4 sous-scores, réconcilie, rend le `.md` |
| Seuils/pondérations | `scripts/feature_health_thresholds.json` | versionné, modifiable sans toucher au code |
| Garde-fou | `core/tests/test_feature_inventory.py` | échec CI (§6.1 et §6.2) |
| Rendu | `docs/revue/2026-09-04-matrice-fonctionnalites.md` | regénéré, plus jamais écrit à la main |

**Emplacement du garde-fou.** `core/tests/` est le bon endroit malgré la portée
inter-dépôt : `core/tests/test_deployability.py:65` fait déjà exactement cela
(`REPO = pathlib.Path(__file__).resolve().parents[2]`, puis lecture de
`docker-compose.yml`, `.github/workflows/release.yml`, `.env.example`).
Précédent vérifié dans le code, pas supposé.

**Emplacement du générateur.** `scripts/` à la racine, qui héberge déjà les
scripts inter-dépôt (`add-license-headers.py`, `bootstrap-env.sh`) — il doit
lire `core/coverage.xml`, `shell/coverage/coverage-summary.json`,
`core/openapi.json` et `shell/src/shell/routes.tsx`.

**Langue.** Noms de fichiers et de fonctions en anglais (code) ; clés du JSONL
en français, pour rester homogènes avec le fichier d'amorçage
(`.superpowers/sdd/sp42-matrice-notee.jsonl` : `domaine`, `fonctionnalite`,
`etat`, `preuve`) et éviter une traduction mécanique de 304 lignes sans
bénéfice. Sortie rendue en français, conformément à `CLAUDE.md`.

## 8. Amorçage

L'inventaire n'est pas collecté de zéro : il est **migré** depuis les 304
lignes de `.superpowers/sdd/sp42-matrice-notee.jsonl`, dont la qualité
d'ancrage a été mesurée en session.

- **286/304** ont tous leurs chemins de preuve qui existent encore, deux jours
  et 17 SP plus tard. L'ancrage **par chemin de fichier** tient ; l'ancrage par
  `chemin:ligne` ne tient pas (les numéros dérivent immédiatement) — l'inventaire
  ne conserve donc que le chemin, et le symbole quand il est stable.
- **8** ont perdu un chemin (SP-43 a découpé `itemClient.ts` et `mcp/tools.py`),
  **10** n'ont aucun chemin parsable, **16** ne se rattachent à aucune entrée de
  couverture (dont 5 qui donnent un fichier de *test* comme preuve).

Soit **une trentaine de lignes à reprendre à la main**, une fois. C'est le coût
d'entrée réel du chantier, et il est faible.

Les états `inerte`/`partiel`/`absent` du JSONL sont ceux du 2026-09-04 et sont
**périmés** — SP-43 à SP-60 en ont fermé la plupart. Ils ne sont pas migrés
tels quels : l'état de chaque ligne est **recalculé** par le générateur au
premier passage. C'est précisément ce que le chantier apporte.

## 9. Hors périmètre

- **Communication externe** de maturité (besoin n°3, écarté par Tanguy).
- **Régression de santé par ligne** en CI (§6.3), à reconsidérer plus tard.
- **Inventaire des widgets builtin** : le registre est peuplé à l'exécution par
  `registerWidget()`, sans table statique. Les widgets restent inventoriés
  déclarativement, sans réconciliation automatique. Rendre le registre
  statiquement énumérable est un chantier distinct, non justifié par ce besoin.
- **Régénération de la note qualitative en prose** de chaque ligne (le champ
  `note` du JSONL SP-42) : conservée telle quelle, datée, jamais recalculée.

## 10. Quand

**Après la fusion de SP-53**, qui a cinq worktrees non fusionnés au 2026-09-06 :
amorcer l'inventaire sur un dépôt dont cinq tracks sont en vol garantirait une
trentaine de lignes fausses dès le premier jour.

**Mais sans attendre davantage.** Le garde-fou §6.1 est ce qui arrête la
dérive ; chaque SP livré avant lui est un SP dont les fonctionnalités devront
être rattrapées à la main plus tard. Le coût d'entrée mesuré (§8) est d'une
trentaine de lignes à reprendre — il ne fera que croître.

Taille estimée : un SP de 6 à 8 tâches. L'ordre naturel est de poser d'abord
les quatre calculs de sous-score avec leur falsification (l'atteignabilité en
premier : c'est elle qui a déjà prouvé sa valeur en trouvant `/bookmarks`),
puis la réconciliation et le garde-fou, puis le rendu — le rendu en dernier,
parce que c'est la partie qui n'apprend rien.
