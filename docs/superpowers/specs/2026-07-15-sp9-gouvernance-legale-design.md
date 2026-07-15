# SP-9 — Gouvernance & légal : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormée le
> 2026-07-15, en même temps que le reste de SP-9 (ci-publique-release,
> install-secrets, sécurité minimale, démo lecture seule) — chaque sous-partie
> est planifiable et exécutable indépendamment, comme
> `2026-07-13-sp9-gestion-collections-design.md`.

## 1. Contexte et objectif

**Constat.** Deux bullets de la roadmap SP-9 sont déjà couverts par du travail
antérieur, vérifié en explorant l'état actuel du dépôt :
- **Licence** : `LICENSE` (Apache-2.0) existe déjà à la racine depuis la
  création du fork (2026-07-05).
- **Consolidation documentaire** : `docs/archive/` contient déjà
  `IMPLEMENTATION_PLAN.md` et les 4 documents G1/G2
  (`plateforme-modulaire.md`, `stack3-modern-web-gis.md`,
  `stacks-comparatif.md`, `stacks-production.md`, `synthese.md`) ; le
  `README.md` racine est déjà réécrit autour de GeoStudio (statut, ce qui
  existe, feuille de route). Rien à refaire ici.

**Ce qui manque réellement** : `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, et les
en-têtes de licence (SPDX) sur les fichiers source — absents aujourd'hui
(vérifié : aucun fichier `core/app/**/*.py` ni `shell/src/**/*.tsx` ne porte
d'en-tête). Ce sont les seuls livrables réels de cette sous-partie.

**Objectif.** Un inconnu qui découvre le dépôt sur GitHub comprend en une
minute qu'il peut légalement réutiliser/forker le code (licence claire par
fichier, pas seulement à la racine), et sait comment proposer une
contribution ou signaler un comportement problématique — même si, à ce jour,
le projet n'a pas encore reçu de contribution externe.

## 2. Périmètre

**Dans le périmètre v1 :**
- `CONTRIBUTING.md` (racine) : processus réel, pas un placeholder — comment
  lancer les tests (`shell`/`core`, commandes déjà documentées dans
  `CLAUDE.md`), convention de commits (conventional commits, déjà en usage
  dans ce dépôt — pas une nouvelle règle), attentes de PR (description,
  tests verts), comment ouvrir une issue.
- `CODE_OF_CONDUCT.md` (racine) : Contributor Covenant v2.1, en anglais (cf.
  §2 — convention GitHub habituelle pour ce document), adresse de contact
  pour signaler une violation.
- En-têtes SPDX sur les fichiers source applicatifs (`core/app/**/*.py`,
  `shell/src/**/*.{ts,tsx}`) : `# SPDX-License-Identifier: Apache-2.0` (Python)
  / `// SPDX-License-Identifier: Apache-2.0` (TS/TSX), appliqués une fois par
  script idempotent, pas de logique cachée.
- Un paragraphe « Contribuer » ajouté au `README.md`, pointant vers
  `CONTRIBUTING.md` (le README lui-même n'a pas besoin d'être réécrit
  davantage, il l'a déjà été).

**Hors périmètre v1 (explicitement différé) :**
- CLA/DCO (« Developer Certificate of Origin ») — prématuré tant qu'il n'y a
  aucun contributeur externe ; à réévaluer si des PR externes arrivent.
- Vérification automatique des en-têtes en CI (un linter d'en-têtes est un
  outil de plus à opérer pour un projet à un seul committer humain
  aujourd'hui — YAGNI, cf. arbitrage similaire ailleurs dans ce projet sur ne
  pas outiller avant le besoin réel). La convention (nouveaux fichiers =
  en-tête) est documentée dans `CONTRIBUTING.md`, appliquée par relecture.
- Traduction complète de `CODE_OF_CONDUCT.md`/`CONTRIBUTING.md` en français —
  ces deux documents s'adressent en priorité à un lectorat OSS international
  ; le reste de la doc du projet reste en français (règle déjà actée dans
  `CLAUDE.md`), mais ces deux fichiers de gouvernance communautaire suivent
  la convention GitHub habituelle (anglais), pour rester lisibles par un
  contributeur non francophone découvrant le dépôt.

## 3. Architecture

### 3.1 `CONTRIBUTING.md`

Sections : Prérequis (Docker, Node 20, Python 3.12 via `uv`) ; Lancer le
projet en local (`docker compose up`, renvoie vers le futur guide d'install
de `sp9-install-secrets`) ; Lancer les tests (`shell` : `npm run test`,
`npm run e2e`, `npm run build` ; `core` : `uv run pytest`,
`uv run lint-imports`) ; Convention de commits (`type(scope): résumé`,
exemples tirés de l'historique réel du dépôt) ; Process de PR (branche depuis
`dev`, tests verts, description du changement) ; Où trouver le contexte
(`CLAUDE.md`, `docs/vision/`, `docs/superpowers/`) ; Comment signaler un bug
ou proposer une feature (issue GitHub, gabarit minimal).

### 3.2 `CODE_OF_CONDUCT.md`

Contributor Covenant v2.1 texte standard tel quel (pas de réécriture — c'est
un texte communautaire largement reconnu, le personnaliser affaiblirait sa
valeur), avec `lenenaon.tanguy@gmail.com` comme email de contact en pied de
page (même adresse réutilisée par le futur `SECURITY.md` de la spec
sécurité minimale, pour ne pas multiplier les canaux de signalement).

### 3.3 En-têtes SPDX

Script `scripts/add-license-headers.py` (nouveau, exécuté une fois puis
laissé dans le dépôt pour un usage futur ponctuel — pas un hook, pas un job
CI) :
- Parcourt `core/app/**/*.py`, `core/tests/**/*.py`, `shell/src/**/*.{ts,tsx}`
  (tests inclus — même statut légal que le code applicatif, couverture
  uniforme sans exception à retenir).
- Insère l'en-tête en première ligne (après un éventuel shebang, aucun cas ici)
  si absent ; idempotent (ne duplique jamais un en-tête déjà présent, testé
  en le relançant deux fois de suite).
- N'touche pas aux fichiers générés (`shell/src/api/generated/`,
  exclusion explicite).

## 4. Flux et gestion d'erreurs

Aucun flux utilisateur runtime — ce sont des fichiers statiques et un script
d'outillage à usage ponctuel. Le seul « échec » possible est un fichier oublié
par le script (extension non couverte) : acceptable, corrigible à la main,
pas un cas à tester automatiquement.

## 5. Tests

Pas de suite de tests applicative pour cette sous-partie (pas de code
runtime). Vérification manuelle en fin de tâche :
- `CONTRIBUTING.md`/`CODE_OF_CONDUCT.md` présents à la racine, liens internes
  valides (vers `CLAUDE.md`, commandes citées vérifiées en les exécutant une
  fois).
- Script d'en-têtes exécuté, `git diff --stat` montre uniquement des ajouts
  de lignes (une par fichier touché), aucun fichier de contenu applicatif
  modifié au-delà de l'en-tête (diff relu intégralement, pas seulement le
  stat).
- Relancer le script une deuxième fois produit un diff vide (idempotence
  vérifiée empiriquement, pas supposée).
- `npm run build` (shell) et `uv run pytest` (core) restent verts après
  insertion des en-têtes (aucune régression de syntaxe).

## 6. Critères d'acceptation

- Un visiteur du dépôt trouve `CONTRIBUTING.md` et `CODE_OF_CONDUCT.md` à la
  racine, avec un contenu réel et actionnable (pas un squelette).
- Tout fichier source applicatif (`core/app/`, `shell/src/`, hors généré)
  porte un en-tête SPDX Apache-2.0.
- `README.md` pointe vers `CONTRIBUTING.md`.
- Aucune régression : `npm run test`/`npm run build` (shell),
  `uv run pytest`/`uv run lint-imports` (core) restent verts.
