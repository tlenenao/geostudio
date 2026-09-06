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
s'est déjà trompée ainsi (piège n°11).

**Vérifié en session, et cela change la méthode :** ces gardes ne sont **pas**
des dépendances FastAPI. Elles sont appelées dans le **corps** de la fonction de
route (`core/app/collections/routes.py:224` :
`require_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)`),
et `items/routes.py` ne déclare que `Depends(get_current_user)` en s'appuyant
sur `can()` à l'intérieur. Elles sont donc **invisibles depuis `openapi.json`**
— une lecture de la signature de route ne les verrait jamais. Le calcul exige un
**résolveur AST** sur le corps de chaque fonction de route.

Précédent à suivre : `core/tests/test_deployability.py` a fait exactement cette
bascule (« trouvées en passant la règle 3 d'un grep à un résolveur AST »), avec
une docstring qui énumère honnêtement les limites du résolveur. Ce chantier
reprend ce patron, docstring de limites comprise.

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

Le chantier produit **deux rendus d'une même source**, plus un journal.

| Artefact | Chemin | Rôle |
|---|---|---|
| Inventaire | `docs/revue/inventaire-fonctionnalites.jsonl` | source déclarative, une ligne par fonctionnalité, `id` stable |
| Journal de santé | `docs/revue/historique-sante.jsonl` | append-only, un instantané par régénération (§7.2) |
| Générateur | `core/scripts/feature_health/` (package) + `core/scripts/feature_health_cli.py` | calcule, réconcilie, rend les deux sorties |
| Seuils/pondérations | `core/scripts/feature_health_thresholds.json` | versionné, modifiable sans toucher au code |
| Garde-fou | `core/tests/test_feature_inventory.py` | échec CI (§6.1 et §6.2) |
| **Rendu HTML** | `docs/revue/bilan-fonctionnalites.html` | **le produit de suivi central** (§7.1) |
| Rendu Markdown | `docs/revue/bilan-fonctionnalites.md` | forme greppable et diffable en revue de commit |

**Emplacement du garde-fou.** `core/tests/` est le bon endroit malgré la portée
inter-dépôt : `core/tests/test_deployability.py:65` fait déjà exactement cela
(`REPO = pathlib.Path(__file__).resolve().parents[2]`, puis lecture de
`docker-compose.yml`, `.github/workflows/release.yml`, `.env.example`).
Précédent vérifié dans le code, pas supposé.

**Emplacement du générateur.** `core/scripts/`, et non `scripts/` à la racine :
`core/scripts/` est un **package** (`__init__.py`) que `core/tests/` importe
déjà — quatre précédents vérifiés (`test_rotate_secrets_master_key_script.py`,
`test_ensure_procrastinate_schema.py`, `test_healthcheck_worker_stalled.py`,
`test_healthcheck_cdc.py`), rendus possibles par `pythonpath = ["."]`
(`core/pyproject.toml:107`). Un générateur posé dans `scripts/` à la racine ne
serait ni importable par un test ni exécuté par la CI. Il remonte à la racine du
dépôt par `parents[N]`, comme `test_deployability.py`, pour lire
`shell/coverage/coverage-summary.json` et `shell/src/shell/routes.tsx`.

**Langue.** Noms de fichiers et de fonctions en anglais (code) ; clés du JSONL
en français, pour rester homogènes avec le fichier d'amorçage
(`.superpowers/sdd/sp42-matrice-notee.jsonl` : `domaine`, `fonctionnalite`,
`etat`, `preuve`) et éviter une traduction mécanique de 304 lignes sans
bénéfice. Sortie rendue en français, conformément à `CLAUDE.md`.

### 7.0 Le couple daté / vivant

`docs/revue/2026-09-04-matrice-fonctionnalites.md` porte une date dans son nom,
une section « Méthode » décrivant huit cartographes, et une section « Limite de
l'exercice » qui l'assume comme une photo. C'est un **document historique** : il
a servi de matière première à `analyse-gaps.md` et au backlog, et il doit le
rester tel quel. Un document vivant regénéré à chaque SP ne peut pas porter la
date de sa première rédaction.

Décision : le couple daté est **gelé**, le produit vivant prend des noms sans
date.

- `docs/revue/2026-09-04-matrice-fonctionnalites.md` — gelé, plus jamais édité.
- `docs/revue/2026-09-04-matrice-fonctionnalites.html` — **rapatrié dans le
  dépôt** (550 Ko, données des 304 + 55 lignes embarquées, vérifiées lisibles).
  Il n'existait jusqu'ici que comme artefact hébergé sur `claude.ai`, cité par
  un document commité : une dépendance externe pour un livrable du dépôt, et un
  lien qui survit mal à l'archivage. C'est aussi la **référence de design** du
  rendu vivant (§7.1).
- `docs/revue/bilan-fonctionnalites.{html,md}` — regénérés, jamais écrits à la
  main.

**Conséquence à traiter dans le plan :** `CLAUDE.md` nomme aujourd'hui
`docs/revue/2026-09-04-matrice-fonctionnalites.md` comme le document à mettre à
jour à la clôture de chaque SP. Ce pointeur doit basculer vers le rendu vivant,
et l'obligation « mettre à jour à la main » devient « régénérer ». C'est une
tâche du plan, pas un effet de bord.

### 7.1 Le bilan HTML — produit de suivi central

Le HTML n'est pas un rendu secondaire du Markdown : c'est **le produit de suivi
central**, celui qu'on ouvre pour décider quoi faire ensuite. Le Markdown reste
utile pour ce que le HTML fait mal — être lu dans un diff de commit et être
grepé.

**Il est regénéré par le même script, depuis la même source, dans le même
passage.** C'est la propriété que l'artefact SP-42 revendiquait déjà en pied de
page (« aucune divergence possible avec les rendus Markdown ») et qu'il faut
préserver : les deux sorties ne peuvent pas se contredire, parce qu'aucune n'est
écrite à la main.

**Contraintes de forme, héritées de l'artefact rapatrié :**

- **Un seul fichier, sans build.** Données embarquées en
  `<script type="application/json">`, CSS et JS inline. Il s'ouvre en
  `file://`, se copie, s'envoie en pièce jointe. Aucune étape de compilation,
  aucun `node_modules`.
- **Aucune dépendance externe bloquante.** L'artefact n'en a qu'une — Google
  Fonts — et chaque famille a une pile de repli réelle (`'Fraunces', Georgia,
  serif`). Hors ligne, il reste lisible. Cette propriété est à conserver, pas à
  étendre : pas de CDN de librairie, pas de graphique tiers.
- **Thème clair/sombre**, déjà traité par l'artefact via `prefers-color-scheme`
  plus un `[data-theme]` explicite.
- **Le design existant est repris, pas réinventé.** L'artefact rapatrié est la
  référence : palette de tokens, badges d'état, tuiles de synthèse, vue par
  famille, contrôles collants, lignes dépliables, tableau à colonnes triables.
  Ce travail est fait et il est bon ; le refaire coûterait cher pour un résultat
  moins abouti.

**Ce qui change par rapport à l'artefact,** en conséquence directe du modèle
(§3-§5) :

- la colonne « Note » (moyenne de six critères) devient **deux colonnes
  distinctes** : *santé* calculée et *priorité* déclarée, jamais moyennées ;
- le détail dépliable montre les **quatre sous-scores** et, pour chacun, **la
  donnée qui l'a produit** — le pourcentage de couverture réel, le lien entrant
  trouvé ou son absence, la garde détectée, la liste des `GAP`/`REV` ouverts.
  Un score dont on ne peut pas voir la source est un score qu'on ne croit pas ;
- un bloc **qualité reprise** (§5) : typage strict oui/non, exemptions de
  couches, `eslint-disable`, `@ts-expect-error` — des faits, sans note ;
- un **tri de priorisation** `priorité × (100 − santé)`, qui est la vue par
  défaut du besoin n°1 ;
- une **vue d'évolution** (§7.2).

### 7.2 Le suivi des améliorations

Sans mémoire, le bilan répond à « où en est-on ? » mais pas à « est-ce que ça
s'améliore ? ». Le journal `docs/revue/historique-sante.jsonl` est **append-only** :
à chaque exécution du générateur, une ligne par fonctionnalité, portant la date,
le commit `HEAD`, la santé et les quatre sous-scores.

Format append-only et non « fichier réécrit » pour trois raisons : le diff git
d'une régénération ne montre que les lignes ajoutées ; deux sessions
concurrentes ne s'écrasent pas ; et l'historique ne peut pas être perdu par un
bug du générateur.

Ce que le HTML en tire :

- **Delta par fonctionnalité** depuis l'instantané précédent (`↑ +12`, `=`,
  `↓ −7`), affiché à côté de la santé ;
- **Ce qui s'est amélioré / dégradé** depuis un instantané choisi — la vue qui
  répond littéralement à « suivi des améliorations », et le moyen de vérifier
  après coup ce qu'un SP a réellement changé, plutôt que de croire son récit de
  clôture (piège n°12 de `CLAUDE.md`) ;
- **Tendance globale** : santé médiane et répartition par état, un point par
  instantané.

**Le journal n'est jamais rétro-calculé.** Il commence au premier passage du
générateur. Les six notes d'agents de SP-42 ne sont pas converties en santé
rétroactive : ce sont des jugements, pas des mesures, et les mélanger à une
série de mesures produirait une courbe fausse à son origine. Le premier point de
la série est le premier point réel.

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
- **Refonte visuelle du bilan HTML** : le design de l'artefact rapatrié est
  repris tel quel (§7.1). Ce chantier lui ajoute des colonnes et une vue
  d'évolution, il ne redessine rien.
- **Rétro-calcul du journal de santé** sur l'historique git (§7.2).

## 10. Quand

**Après la fusion de SP-53.** Au moment d'écrire cette spec, cette fusion est
en cours sur `dev` par une session concurrente — vérifié dans le code, pas
supposé : `core/app/sql_ident.py` existe et les commits `55f0cdcf`/`708ebd8f`/
`9835d0c6`/`5b24e8fb` (GAP-15) viennent de se poser. Amorcer l'inventaire sur un
dépôt dont des tracks sont encore en vol garantirait une trentaine de lignes
fausses dès le premier jour.

**Mais sans attendre davantage.** Le garde-fou §6.1 est ce qui arrête la
dérive ; chaque SP livré avant lui est un SP dont les fonctionnalités devront
être rattrapées à la main plus tard. Le coût d'entrée mesuré (§8) est d'une
trentaine de lignes à reprendre — il ne fera que croître.

Taille estimée : un SP de 6 à 8 tâches. L'ordre naturel est de poser d'abord
les quatre calculs de sous-score avec leur falsification (l'atteignabilité en
premier : c'est elle qui a déjà prouvé sa valeur en trouvant `/bookmarks`),
puis la réconciliation et le garde-fou, puis le rendu — le rendu en dernier,
parce que c'est la partie qui n'apprend rien.

## 11. Contrainte d'exécution — worktree dédié

**Ce chantier s'exécute dans un worktree git dédié, jamais dans le checkout
principal.** Ce n'est pas une préférence de confort : au moment d'écrire cette
spec, une session concurrente committe sur `dev` dans
`/home/lenen/projets/geostudio` (intégration des tracks SP-53, commits `55f0cdcf`
à `5b24e8fb` posés pendant la rédaction). Deux sessions qui écrivent dans le même
arbre de travail se marchent dessus sans le voir.

Trois raisons propres à ce chantier, au-delà de la concurrence :

1. **Le générateur lit des artefacts de build** — `core/coverage.xml`,
   `shell/coverage/coverage-summary.json`, `core/openapi.json`. Ces fichiers sont
   réécrits par toute exécution de suite de tests. Développer le générateur dans
   un arbre où quelqu'un d'autre lance `pytest` ou `npm run test`, c'est le
   développer contre des entrées qui changent sous lui.
2. **Le garde-fou §6.1 échoue par conception** pendant tout le développement,
   tant que l'inventaire est incomplet. Un `core/tests/` rouge dans l'arbre
   partagé bloquerait le travail de l'autre session.
3. **Le journal de santé est append-only** (§7.2) : deux sessions qui le
   génèrent en parallèle dans le même arbre produisent des instantanés
   entrelacés, datés du même commit, indiscernables après coup.

Précédent du dépôt : SP-53 a été exécuté « en 5 subagents parallèles dans des
worktrees git dédiés (isolation garantie) ». Une note de session plus ancienne
(SP-10b, 2026-07-17) affirmait au contraire « PAS de worktree sur ce dépôt » —
cette note est périmée, SP-53 l'a démentie en pratique.

**Retour vers `dev`** : par fusion explicite en fin de chantier, après la revue
finale de branche, jamais par des commits posés au fil de l'eau dans l'arbre
partagé.
