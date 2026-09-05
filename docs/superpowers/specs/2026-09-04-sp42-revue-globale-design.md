# SP-42 — Revue globale du projet, matrice de fonctionnalités et refonte du README

**Date** : 2026-09-04
**Statut** : spec validée, plan à écrire
**Demandeur** : Tanguy
**Documents liés** : `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (vagues 0-6),
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` (SP-1→SP-20, 40 arbitrages),
`docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`.

---

## 1. Motivation

Le dépôt a livré quarante et un chantiers SP en deux mois. Chacun a été revu
individuellement, mais **rien n'a jamais regardé l'ensemble** :

- le `README.md` date du 2026-08-29 et décrit encore un projet « pré-v0.1 »,
  fork de GeoNode, avec des jalons M1→M10 — alors que la v0.1.0 est publiée,
  que M1/M2/M4/M5/M11/M12/M13/M15/M16 sont atteints et que le cœur compte
  38 modules ;
- il n'existe **aucun inventaire des fonctionnalités réellement livrées**. La
  seule source est `CLAUDE.md`, qui est un récit d'exécution : il dit ce que
  chaque plan a tenté, pas ce qu'un utilisateur peut faire aujourd'hui dans un
  déploiement par défaut ;
- ce dépôt a payé au moins cinq fois la classe de défaut « livré + testé +
  mergé ≠ câblé » (une capacité entière inactivable, de la plomberie inerte sur
  `/sites/{slug}`, un écran livré sans lien de navigation). Aucun mécanisme ne
  détecte cette classe autrement qu'au hasard d'une revue ;
- la dette Minor s'accumule depuis SP-29b sans jamais être arbitrée : elle
  gonfle `CLAUDE.md`, chargé à chaque session, sans jamais être consommée.

## 2. Objectifs

1. Une **revue de code de tout le dépôt** (cœur, shell, infra), à profondeur
   maximale, dont les défauts Critical et Important sont corrigés et vérifiés
   dans cette même session.
2. Une **matrice de fonctionnalités** exhaustive et prouvée, disant pour chaque
   fonctionnalité son état réel, ses surfaces d'accès, sa couverture de test et
   ses prérequis d'activation.
3. Une **analyse des manques** sur quatre référentiels distincts.
4. Un **`README.md` réécrit** pour un visiteur GitHub d'un projet open-source
   public.
5. Quatre suites opérationnelles : backlog unique, spec de refactorisation
   structurelle, feuille de route révisée, `CLAUDE.md` dégonflé.

## 3. Non-objectifs

Explicitement hors périmètre, décidés avec Tanguy :

- **Aucun refactor structurel n'est exécuté.** SP-42 produit l'inventaire et la
  spec design d'un futur SP-43 ; il ne redécoupe aucun fichier.
- **Aucun défaut Minor n'est corrigé.** Tous partent au backlog.
- **Aucun document de `docs/vision/` existant n'est modifié.** La feuille de
  route révisée est un document neuf qui les cite.
- Aucune fonctionnalité nouvelle n'est ajoutée.
- SP-41 (métadonnées ouvertes / licence), en cours sur `dev` avec 12 commits et
  non clos, est **figé et inclus tel quel** dans le périmètre de revue. Aucun
  travail SP-41 nouveau n'est engagé pendant SP-42 ; les défauts trouvés dans
  ses commits remontent au rapport comme les autres.

## 4. Base de revue

`dev` à son état d'ouverture de SP-42 (`aef9e65e`), arbre propre hors deux
entrées non suivies connues et documentées (`deploy/postgis/pg_hba.conf`,
inerte ; `test-results/`).

Surface : 30 routeurs / 129 endpoints FastAPI, 33 migrations Alembic,
~26 700 lignes Python sous `core/app`, ~75 800 lignes TypeScript sous
`shell/src`, 54 widgets de builder, 66 specs Playwright, 105 specs et 144 plans
sous `docs/superpowers/`.

## 5. Architecture de la revue — trois vagues

Le choix d'une cartographie **avant** la revue est délibéré : les réviseurs
partent d'une carte des surfaces, des flags éteints et des zones sans filet E2E,
au lieu de redécouvrir le terrain. C'est ce qui doit faire remonter la classe
« inerte », qu'une revue de code seule ne voit pas (le code y est correct — c'est
son absence de consommateur qui est le défaut).

### 5.1 Vague 1 — cartographie (8 agents parallèles)

Chaque agent balaie une tranche et rend un fragment de matrice au format
normalisé du §6.

| # | Tranche |
|---|---|
| 1 | Cœur — identité : `auth`, `roles`, `users`, `tenants`, `sharing`, `audit`, `instance` |
| 2 | Cœur — contenu : `items`, `collections`, `features`, `configs`, `catalog`, `public`, `schemas_routes` |
| 3 | Cœur — données/fédération : `analytics`, `cdc`, `dcat`, `stac`, `harvest`, `search` |
| 4 | Cœur — automatisation et annexes : `pipelines`, `ingestion`, `jobs`, `export`, `appexport`, `reports`, `alerts`, `notifications`, `secrets`, `attachments`, `mapicons`, `terrain3d`, `tileset3d`, `extensions`, `admin_tools`, `copilot`, `mcp`, `ratelimit` |
| 5 | Shell — pages, routes, chrome, `capabilities`, i18n |
| 6 | Shell — builder : widgets, runtime, actions, CEL, variables, export d'apps |
| 7 | Shell — carte et couche API : `MapView`, symbologie, popup, `itemClient`, `hooks`, `types` |
| 8 | Infra — `docker-compose`, overlay prod, CI, scripts, `test_deployability`, `.env.example`, release |

**Règle de preuve, non négociable** : toute ligne de matrice porte une référence
`chemin:ligne` vérifiée. Aucune ligne ne peut être dérivée de `CLAUDE.md`, des
specs ou des plans — ce sont des récits d'intention. Une fonctionnalité qu'un
agent ne sait pas prouver dans le code est marquée comme telle, jamais supposée
livrée.

### 5.2 Vague 2 — revue (16 agents, armés de la matrice consolidée)

**Sécurité et autorisation (3)** — la porte unique `can()`/`decide()` et le
modèle de privilèges ; l'isolation multi-tenant et la RLS PostGIS ; les surfaces
sortantes et entrantes (egress/SSRF, uploads, coffre de secrets, cookie admin,
CSP, rate limiting).

**Correction fonctionnelle du cœur (4)** — items/collections/features ;
analytics et lakehouse (CDC, DuckDB, SQL sandboxé) ; pipelines, ingestion, jobs
et workers ; fédération (harvest, STAC, DCAT) et MCP.

**Correction fonctionnelle du shell (4)** — builder et runtime d'apps ; carte,
symbologie et popup ; pages, chrome et application des permissions ;
`itemClient` / hooks / types générés.

**Transverse (5)** — migrations Alembic éprouvées dans les deux sens sur base
non vide ; fiabilité des tests, avec chasse explicite aux **filets vacants** et
aux faux verts ; performances (N+1, requêtes par page, taille de bundle,
plafonds) ; i18n et accessibilité ; infrastructure, CI, déployabilité,
observabilité.

### 5.3 Vague 3 — vérification, correction, rédaction

1. **Falsification.** Chaque trouvaille Critical ou Important est vérifiée par
   un agent **distinct de celui qui l'a trouvée** : reproduire le défaut,
   confirmer l'échec, restaurer. Une trouvaille non reproduite est déclassée en
   observation, pas corrigée. Cette règle vient d'un défaut déjà payé trois fois
   ici : un correctif de filet de test qui « passe » ne prouve rien.
2. **Correction** en TDD des Critical et Important confirmés, un commit
   conventional par sujet.
3. **Rédaction** des livrables du §8.
4. **Vérification finale** : suites complètes cœur et shell, suite E2E complète,
   portes de qualité, régénération OpenAPI/types si une route ou un modèle a
   bougé.

## 6. Format de la matrice

Une ligne par **fonctionnalité utilisateur** — pas par module, pas par endpoint.

| Colonne | Contenu |
|---|---|
| Domaine | l'un des neuf domaines produit du shell, ou « Infrastructure » |
| Fonctionnalité | libellé court, du point de vue de l'utilisateur |
| État | `livré` / `partiel` / `inerte` / `prévu` / `absent` (§6.1) |
| Surfaces | UI · API REST · MCP · CLI/worker — ce par quoi c'est atteignable |
| Tests | unitaire · intégration · E2E, avec le fichier de référence |
| Activation | flag `CORE_*`, profil compose, dépendance externe (Keycloak, S3, sidecar QGIS, LLM) |
| Preuve | `chemin:ligne` |
| Origine | le SP qui l'a livrée |

### 6.1 Taxonomie d'état

- **livré** — atteignable par un utilisateur dans un déploiement par défaut ;
- **partiel** — présent sur une surface, absent sur sa jumelle (typiquement
  éditeur oui / widget non, ou API oui / MCP non) ;
- **inerte** — le code existe, est testé et mergé, mais rien ne l'atteint : flag
  jamais câblé dans le compose, hook sans consommateur, écran sans lien de
  navigation, plomberie dont la branche n'est jamais prise ;
- **prévu** — spec ou arbitrage écrit, code absent ;
- **absent** — identifié par le benchmark concurrentiel, jamais envisagé ici.

La valeur `inerte` est le cœur de l'exercice : c'est la classe de défaut que ce
dépôt reproduit et qu'aucun de ses filets actuels ne détecte.

## 7. Analyse des manques — quatre référentiels

Chaque manque reçoit un identifiant `GAP-nn`, un impact, un coût estimé et son
référentiel d'origine.

1. **Feuille de route interne** — ce que promettent les SP-1→SP-20, les 40
   arbitrages du §8 et les vagues 0-6, et qui n'est pas livré ou l'est
   partiellement.
2. **Benchmark concurrentiel** — GeoNode, Felt, ArcGIS Online/Enterprise,
   Superset, Metabase, FME, CKAN. Les constats de benchmark sont marqués comme
   tels : ils reposent sur de la documentation externe, pas sur du code
   vérifiable.
3. **Cohérence interne** — asymétries et trous logiques : un type d'item sans
   historique de versions, une action en API sans équivalent MCP, un domaine
   sans écran d'administration, une capacité sans écran de réglage.
4. **Exigences de production** — restauration de sauvegarde jamais rejouée de
   bout en bout, CSP jamais basculée en enforcing, absence de quotas, purge et
   droit à l'effacement, rétention de l'`audit_log`, procédure de rotation de
   secrets.

## 8. Livrables

Commits conventional sur `dev`, sans PR, préfixe `(SP-42)` — SP-41 est pris.

| Livrable | Chemin |
|---|---|
| Cette spec | `docs/superpowers/specs/2026-09-04-sp42-revue-globale-design.md` |
| Correctifs Critical/Important | commits `fix(core...)` / `fix(shell...)` … (SP-42) |
| Matrice de fonctionnalités | `docs/revue/2026-09-04-matrice-fonctionnalites.md` |
| Matrice, version consultable | Artifact HTML filtrable et triable |
| Analyse des manques | `docs/revue/2026-09-04-analyse-gaps.md` |
| Backlog unique `REV-nnn` | `docs/revue/2026-09-04-backlog.md` |
| Spec de refactorisation structurelle | `docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md` |
| Feuille de route révisée SP-43+ | `docs/vision/2026-09-04-feuille-de-route-revisee.md` |
| README vitrine | `README.md` |
| `CLAUDE.md` dégonflé | historique détaillé versé dans `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md` |

### 8.1 Le README

Public cible : **visiteur GitHub d'un projet open-source public**. Il doit
comprendre en trente secondes ce qu'est GeoStudio, voir à quoi ça ressemble,
savoir l'installer et l'essayer. Le détail technique renvoie vers `docs/` ; la
mise en route contributeur renvoie vers `CONTRIBUTING.md`, qui existe déjà.

Le README actuel est faux sur au moins quatre points : statut « pré-v0.1 »,
tableau de jalons M1→M10 périmé, description du cœur comme « naissant », liste
de fonctionnalités qui s'arrête au builder. Il est réécrit, pas rapiécé.

### 8.2 La spec de refactorisation structurelle

Inventaire seulement, à destination d'un futur SP-43 : fichiers dont la taille
signale qu'ils font trop de choses (`mcp/tools.py` 1058 l., `itemClient.ts`
1741 l., `MapView.tsx` 1425 l., `pipelines/runtime.py` 894 l., …), patrons
divergents entre pages sœurs, abstractions dupliquées trois fois ou plus, ordre
de découpage proposé, risques de régression et filet de test requis pour chaque
étape. La spec est écrite, pas exécutée.

### 8.3 Le backlog

Un document unique remplace la liste de suivis non bloquants qui gonfle
`CLAUDE.md`. Chaque entrée porte un identifiant `REV-nnn` citable par une future
session, une sévérité, un coût estimé et un renvoi vers sa preuve. Il absorbe
les Minor de cette revue, les Minor hérités SP-29b→SP-40 encore ouverts, et les
`GAP-nn` non retenus pour la feuille de route.

## 9. Critères de sortie

1. Les huit fragments de matrice sont fusionnés, sans ligne dépourvue de preuve
   `chemin:ligne`.
2. Toute trouvaille Critical ou Important est soit corrigée et vérifiée par
   falsification, soit déclassée avec sa raison écrite.
3. Suite cœur, suite shell et suite E2E complètes relancées après le dernier
   commit, comptes relevés et comparés à la référence d'ouverture — mesurés,
   jamais recopiés d'un rapport d'agent.
4. Portes de qualité vertes : `ruff`, `mypy --strict` sur les modules concernés,
   `lint-imports`, seuils de couverture, `eslint`, `prettier`, `tsc --noEmit`.
5. Diff OpenAPI/types vérifié — vide s'il doit l'être, régénéré sinon.
6. Les dix livrables du §8 existent et sont commités.
7. `CLAUDE.md` porte une entrée SP-42 dans `### Livré` et ne contient plus
   l'historique détaillé déplacé.

## 10. Risques

- **Volume.** Vingt-quatre agents en vagues 1-2, plus une vague de vérification
  proportionnelle au nombre de trouvailles. Coût en tokens et en temps assumé
  par le choix « profondeur maximale ».
- **Faux positifs d'agents.** Un rapport d'agent n'est pas une preuve : d'où la
  falsification obligatoire du §5.3 avant tout correctif.
- **Contamination de ledgers.** Sessions concurrentes possibles sur cet arbre :
  tous les fichiers de travail sont nommés `.superpowers/sdd/sp42-*`, jamais
  d'un nom générique.
- **Dérive de périmètre.** La tentation de corriger les Minor au fil de l'eau
  est réelle ; le §3 l'interdit explicitement.
- **Régénération OpenAPI.** Classe d'oubli n°1 du dépôt : vérifiée au critère de
  sortie 5, avec l'incantation complète (`PYTHONPATH=.` et clé de test).
