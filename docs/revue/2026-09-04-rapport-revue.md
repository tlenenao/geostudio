# Rapport de revue — SP-42, revue globale de GeoStudio

**Date :** 2026-09-04 (rédigé 2026-09-05). **Tâche 14 de SP-42** (plan
`docs/superpowers/plans/2026-09-04-sp42-revue-globale.md`, lignes 1086-1149).
**Base de revue :** `dev` à `aef9e65e` ou plus récent (SP-41 figé et inclus
dans le périmètre). Commit HEAD au moment d'écrire ce rapport : `d28412ba`.

Ce document est la trace de **ce que la revue a réellement établi** —
méthode, comptes, ce qui a été corrigé et par quel commit, ce qui a été
déclassé et pourquoi. Il ne porte pas ce qui reste à faire : c'est le rôle du
backlog séparé, `docs/revue/2026-09-04-backlog.md` (les entrées `REV-nnn`).
C'est un onzième livrable, ajouté par le plan d'exécution en écart assumé par
rapport à la spec de référence (`docs/superpowers/specs/2026-09-04-sp42-revue-
globale-design.md`), consigné comme tel plutôt que d'amender la spec.

Tous les comptes ci-dessous ont été **recalculés directement depuis
`.superpowers/sdd/sp42-findings.jsonl` et `.superpowers/sdd/sp42-
correctifs.json`** pour cette tâche, pas recopiés d'un rapport d'agent
antérieur — un agent précédent s'est déjà trompé une fois sur ce point
(confusion entre « 74 confirmées au total » et « 43 confirmées non
corrigées »).

## 1. Méthode

La revue s'est déroulée en **trois vagues** :

1. **Cartographie** — 8 cartographes, chacun un fragment de la matrice de
   fonctionnalités, verbatim vérifiée `chemin:ligne` pour chaque ligne
   (« rien dérivé de `CLAUDE.md` » — `CLAUDE.md`, les specs et les plans sont
   des récits d'intention, jamais une source de vérité). Consolidée en
   `docs/revue/2026-09-04-matrice-fonctionnalites.md` : **304 lignes**, 247
   `livre`, 38 `partiel`, 13 `inerte`, 3 `absent`, 3 `prévu`.
2. **Revue par axe** — 16 réviseurs, chacun un axe (sécurité-autorisation,
   sécurité-tenant-RLS, sécurité-surfaces, cœur-contenu, cœur-fédération,
   cœur-analytique, cœur-automatisation, shell-api, shell-builder,
   shell-carte, shell-pages, i18n-a11y, infra-ci, migrations, performances,
   tests), chacun produisant ses propres trouvailles avec preuve
   `chemin:ligne` et scénario d'échec concret.
3. **Falsification obligatoire par un agent tiers** — aucune trouvaille
   `critical`/`important` n'a été envoyée en correction sans qu'un agent
   distinct de celui qui l'a écrite ne reproduise réellement le défaut (une
   preuve de reproduction par trouvaille, `.superpowers/sdd/sp42-
   falsification-<id>.md`) avant tout correctif.

Les 138 trouvailles brutes des 16 réviseurs ont été consolidées en **110**
(Tâche 6) : 20 groupes de fusion (28 trouvailles absorbées), 10 arbitrages de
sévérité internes à la consolidation (5 déclassements par la règle du brief,
3 déplacements critical→important, 2 promotions minor→important — à ne pas
confondre avec la déclassification post-falsification du §3, qui est un
mécanisme distinct et n'en compte qu'une seule).

## 2. Comptes — vérifiés dans `sp42-findings.jsonl`

`sp42-findings.jsonl` compte **110 lignes**. Répartition par sévérité :

| Sévérité | Nombre |
|---|---|
| `critical` | 5 |
| `important` | 70 |
| `minor` | 35 |
| **Total** | **110** |

Répartition par `statut` :

| Statut | Nombre | Détail |
|---|---|---|
| `confirme` | 74 | 5 `critical` + 69 `important` |
| `declasse` | 1 | 1 `important` (F-coeur-federation-12, cf. §4) |
| `backlog` | 35 | les 35 `minor` — jamais envoyées en falsification (méthode : seuls `critical`/`important` le sont) |

Les **75** trouvailles `critical`+`important` (5+70) ont donc toutes été
envoyées en falsification ; **74 confirmées, 1 déclassée** — c'est
l'arithmétique exacte de `74 + 1 = 75`, pas « 74 confirmées et une 75ᵉ en
plus ». Des 74 confirmées, **31 ont été corrigées** (`sp42-correctifs.json`
compte exactement 31 entrées, chacune avec un `lot_correctif`) et **43 restent
non corrigées** : `74 - 31 = 43`, vérifié en recalculant directement (les 43
`id` de `sp42-findings.jsonl` avec `statut: confirme` et absents de
`sp42-correctifs.json` — script de vérification exécuté pour cette tâche,
liste exacte en annexe du backlog §1-7).

## 3. Falsification — 74 confirmées, 1 déclassée (pas 75 confirmées)

74 des 75 trouvailles `critical`/`important` envoyées en falsification ont
été **confirmées par reproduction réelle** : un agent tiers a reproduit
concrètement le scénario d'échec (une requête HTTP qui renvoie le mauvais
code, un test qui échoue pour la raison annoncée, une valeur mesurée qui
diverge de ce qui est attendu) — pas une relecture du code.

**Une seule trouvaille a été déclassée** : `F-coeur-federation-12` (intervalle
temporel STAC/DCAT servant une date nue au lieu d'un datetime RFC 3339).
**Ce point mérite d'être dit précisément, parce que « déclassée » et « fermée
par un tiers » ne racontent pas la même chose du dépôt :**

- La trouvaille était **réelle et confirmée** — le mécanisme de
  falsification avait identifié un vrai chemin de reproduction mécanique (un
  modèle de validation Pydantic STAC rejetant le document produit).
- Elle a été refermée par le **commit `b1da7188`**
  (`fix(core): l'emprise temporelle STAC émet un instant RFC 3339 valide
  (SP-41)`), appartenant à une **session concurrente SP-41** travaillant sur
  le même dépôt pendant la revue SP-42 — pas par un correctif SP-42, pas
  parce que la revue s'était trompée.
- Une « trouvaille fausse » dirait quelque chose de la qualité de la revue
  (un défaut de méthode). Une « trouvaille vraie fermée par un tiers » dit
  quelque chose du dépôt (plusieurs chantiers concurrents peuvent converger
  sur le même défaut sans le savoir) — c'est ce second fait qui est vrai ici,
  vérifié par lecture directe du commit et du code actuel
  (`core/app/stac/routes.py` appelle désormais `_rfc3339()` sur les deux
  bornes, plus aucun `.isoformat()` nu sur `temporal_start`/`temporal_end`).

Le détail complet (avec preuve, raison, état) est consigné au backlog,
section 8 (« Déclassée — fermée par un tiers, pas par cette revue »),
`REV-084`.

## 4. Correctifs — 31 trouvailles corrigées, périmètre arbitré par Tanguy

Le périmètre de correction (arbitré par Tanguy à l'issue de la Tâche 7) était
: **les 5 `critical`**, plus **les `important` touchant la sécurité,
l'isolation tenant, l'intégrité et la correction des données**. Les 43
`important` restants (hors ce périmètre) entrent au backlog tels quels —
avec leur preuve de reproduction et leur correctif minimal recommandé,
directement reprenables.

**31 trouvailles corrigées** (5 `critical` + 26 `important`), en **41
commits** répartis en **7 lots** + **2 vagues de revue des correctifs**
(recompté depuis `git log --oneline --grep="(SP-42)"` : 39 commits `fix(...)`
+ 1 `test(...)` + 1 `docs(deploy)` documentant une décision de périmètre —
ce dernier fait bien partie de l'effort de correction, pas de la
documentation de clôture). Le nombre de commits (41) dépasse le nombre de
trouvailles (31) parce que **plusieurs trouvailles ont nécessité plus d'un
commit** pour être réellement fermées, et inversement un même commit a parfois
fermé deux trouvailles distinctes partageant un seul mécanisme (ex.
`b9575dcf` ferme à la fois `F-securite-autorisation-08` et
`F-shell-pages-03`, même fichier `capabilities.ts`/`domainRoutes.ts`).

Chaque lot a été **revu séparément** (revue de qualité, pas seulement de
conformité), et les défauts trouvés par ces revues ont eux-mêmes été
corrigés et re-vérifiés — voir §5 pour le cas le plus significatif.

### Correctifs par lot (31 trouvailles, commit(s) de clôture)

| Lot | Trouvailles fermées | Commit(s) |
|---|---|---|
| 1/7 (autorisation cœur) | F-securite-autorisation-01 (partiel, cf. §5), F-securite-autorisation-07, F-securite-autorisation-13, F-securite-surfaces-03 | `eafb02cc`, `cdf08b9f`, `151d2ba0`, `22661a14` |
| revue du lot 1 | F-securite-autorisation-01 — 3 volets supplémentaires de la même trouvaille : MCP (6 sites), mapping `bookmark`→`analytics.view`, filet `[pipeline]` élargi à 11 kinds, garde sur `POST /configs/{id}/rollback` | `25400206`, `c8750725`, `4f559de4` (test), `4d69e0a5` |
| 2/7 (MCP) | F-coeur-federation-07 (run_pipeline read-only), F-securite-autorisation-03 (CORE_ANALYST_SUBS), F-coeur-federation-05 (\_require_collection_read) | `a0b9ed3e`, `a0d82e96`, `696c7db8` |
| 3/7 (infra, 2 critical) | F-infra-ci-01 (CORE_SECRETS_MASTER_KEY), F-infra-ci-02 (Keycloak middlewares + bruteForceProtected) | `87201679`, `f2a4969e`, `af136bcc` |
| 3bis (2 reliquats critical) | F-securite-autorisation-01 (`/collections/empty`, `/uploads`), F-coeur-federation-08 (URLs MCP inutilisables) | `00fac3c4`, `1deb2d47` |
| revue des lots 2/3/3bis | F-securite-autorisation-01 (terrain3d/tileset3d, 3ᵉ porte), pipeline `writer.dataset` sans data.manage, garde de kind sur update_config, `bruteForceProtected` inerte (documentaire), `READ_ONLY_TOOLS` faux | `3cb4be20`, `03099482`, `7e9d2901`, `c3a5f4b2` (docs), `76098392` |
| 4/7 (tenant/intégrité) | F-coeur-contenu-01, F-securite-tenant-rls-01, F-securite-tenant-rls-02, F-securite-tenant-rls-03, F-coeur-contenu-04, F-coeur-contenu-03 | `f2b02651`, `185a7921`, `312ea7e8`, `1446cecd`, `cebf3de6`, `5f343c8d` |
| 5/7 (analytique + jobs) | F-coeur-analytique-01, F-coeur-analytique-02, F-coeur-analytique-04, F-coeur-automatisation-03, F-coeur-contenu-02 | `20d05827`, `1915462c`, `9403555b`, `37854206`, `a75a8fd4` |
| 6/7 (autorisation shell) | F-shell-pages-01, F-securite-autorisation-06, F-shell-pages-04, F-securite-autorisation-08 + F-shell-pages-03 | `eed41304`, `9415d2ba`, `4df37004`, `b9575dcf` |
| 7/7 (données shell) | F-shell-api-07, F-shell-carte-01, F-shell-carte-02, F-shell-carte-05, F-shell-pages-05 | `328ed513`, `d38037ff`, `07abe620`, `dff3849f`, `233f2e17` |

## 5. Le fait marquant — le critical d'autorisation rouvert trois fois, et une 4ᵉ porte trouvée par cette tâche

**Un même critical (10 des 18 privilèges du catalogue de rôles ne gardaient
aucune route d'écriture — un rôle « Lecteur », 0 privilège, créait librement
n'importe quel type de config) a été déclaré clos trois fois, et rouvert
trois fois**, avant d'être réellement complet :

1. **REST d'abord** (`POST /configs`, `PUT /configs/{id}`,
   `PUT /configs/by-item/{id}` — commit `eafb02cc`, lot 1).
2. **Rouvert côté MCP** : `create_item`, `save_app_config`,
   `create_form_app`, `create_dataset`, `create_bookmark`, `create_pipeline`
   n'avaient aucune garde équivalente — la revue du lot 1 a trouvé que le
   scénario exact de la trouvaille (Lecteur, 0 privilège, crée un item)
   restait reproductible via `/mcp` (commit `25400206`).
3. **Rouvert une troisième fois sur `terrain3d`/`tileset3d`** :
   `POST /terrain3d/uploads` et `POST /tileset3d/uploads` créaient une config
   `kind="terrain3d"/"tileset3d"` sans consulter le privilège
   correspondant — trouvé par la revue des lots 2/3/3bis, qui a d'abord cru
   le critical clos avant de le retrouver ouvert une nouvelle fois
   (commit `3cb4be20`).
4. **Une 4ᵉ porte, trouvée par cette tâche (Tâche 14) elle-même, et NON
   corrigée** : le balayage cron des pipelines planifiés
   (`run_pipeline_sweep_task`, `core/app/pipelines/jobs.py:226-241`) exécute
   un pipeline en appelant `run_pipeline_task.defer(...)` directement, sans
   jamais passer par `POST /pipelines/{id}/run` ni par l'outil MCP
   `run_pipeline` — les deux seuls points où le privilège `data.manage` est
   désormais vérifié pour un pipeline portant un nœud `writer.dataset`
   (commit `03099482`). Un pipeline planifié dont le nœud `writer.dataset`
   était légitime au moment de la planification continue de créer/muter des
   datasets à chaque déclenchement cron même si son propriétaire a perdu
   `data.manage` entre-temps — vérifié par lecture directe du code
   (`jobs.py`, `runtime.py`, `routes.py`, `mcp/tools.py`), pas supposé.
   Consignée au backlog, `REV-001` (critical, ouvert au commit `d28412ba`).
   **Note ajoutée en dernière minute, pendant la rédaction même de ce
   rapport** : `git status` montre une session concurrente en train de
   modifier (non commité) exactement `core/app/pipelines/runtime.py` et
   `core/tests/test_pipeline_jobs.py`, avec un `require_privilege(...,
   Privilege.DATA_MANAGE.value)` ajouté dans `_write_dataset` et un
   commentaire citant explicitement ce même constat (« run_pipeline_sweep_task
   ... défère run_pipeline_task directement, sans passer par aucune des deux
   routes »). Non vérifié ni commité au moment d'écrire cette phrase — REV-001
   reste `ouvert` dans le backlog, avec cette observation consignée pour
   qu'une session future revérifie avant de le clore.

**La cause est structurelle, pas un oubli isolé** : il n'existe **aucun point
de passage unique** pour l'écriture d'une config dans ce dépôt — chaque
route REST, chaque outil MCP et chaque tâche de fond réimplémente sa propre
garde d'autorisation avant d'écrire, et chaque passe de revue ne ferme que
les portes qu'elle regarde. C'est précisément ce constat qui ouvre la spec
SP-43 (refactorisation structurelle) : un point de passage unique
(`require_privilege_for_config_write(session, user, kind)` appelé par les
trois surfaces — REST, MCP, jobs — plutôt que trois implémentations
parallèles) fermerait la classe entière plutôt qu'une porte à la fois.

## 6. SP-42 a lui-même rejoué un défaut qu'il reprochait à SP-41

Le correctif `F-shell-api-07` (`328ed513`) a ajouté un nouveau champ
`ItemRead.updatedAt` à la surface **publique et anonyme** du cœur
(`GET /public/items`, `GET /public/configs/by-item/{id}`) — un champ qui
n'existait pas avant ce correctif. La revue avait elle-même reproché à SP-41
(dans son propre historique d'exécution) d'avoir laissé un champ nouveau
échapper au test de liste blanche qui garde cette surface (le filet censé
faire échouer toute addition de champ non explicitement revue avant
publication anonyme). **Le même mécanisme s'est reproduit ici** : l'ajout
d'`updatedAt` n'a, au moment du correctif, pas été accompagné d'une mise à
jour explicite du test de liste blanche des champs publics — le correctif
`F-shell-api-07` documente avoir vérifié l'impact (seuls 4 sites shell lisent
`Item.date`, aucun autre consommateur ne dépend de la sémantique actuelle) et
avoir régénéré l'OpenAPI/les types TS, mais ne documente pas explicitement le
passage par le test de liste blanche de la surface publique. Ce fait est
consigné ici en toute honnêteté : ce n'est pas une régression fonctionnelle
démontrée (aucune fuite de donnée sensible constatée — `updatedAt` est une
métadonnée de fraîcheur, pas une donnée privée), mais c'est la même classe de
défaut de discipline que la revue elle-même a nommée ailleurs, reproduite
sous ses propres yeux pendant sa propre exécution.

## 7. Ce qui n'a délibérément pas été corrigé (décisions de périmètre, pas des oublis)

Plusieurs trouvailles confirmées ont été **laissées ouvertes par décision
explicite**, pas par manque de temps :

- **F-coeur-federation-08** (URLs `fileUrl`/`thumbnailUrl` des tools MCP
  garanties 401, audiences OAuth disjointes par design) : deux options
  proposées par la falsification impliquaient toutes deux d'élargir une
  garde d'authentification (audience MCP acceptée sur une route REST, ou
  nouveau mécanisme de jeton porteur) — refusé par l'implémenteur du lot 2,
  qui a escaladé plutôt que de trancher seul. **Tanguy a choisi une 3ᵉ voie**
  (cesser de servir les URLs inutilisables plutôt qu'ouvrir une surface),
  implémentée au lot 3bis (`1deb2d47`).
- **`ST_Extent` vs `ST_EstimatedExtent`** (F-securite-tenant-rls-02) :
  correctif retenu (`ST_Extent`, filtré par RLS) scanne la table entière,
  plus coûteux que l'ancien mécanisme non sécurisé. Aucune voie hybride
  connue ne préserve les deux propriétés — signalé, pas tranché seul.
- **Bookmark → `analytics.view`** : arbitré explicitement par Tanguy après
  qu'une revue a trouvé un commentaire factuellement faux justifiant
  `catalog.manage` pour ce kind.
- **`bruteForceProtected` sur une instance déjà déployée** : le realm
  Keycloak vit dans un volume Docker persistant, jamais resynchronisé par un
  redémarrage — corrigé pour toute nouvelle instance, documenté par un
  runbook pour une instance existante plutôt que de forcer un réimport qui
  écraserait des réglages faits à la main en prod.

## 8. Le rôle exact des trois autres documents produits par la revue

Ce rapport ne recopie pas ces documents ; il renvoie vers eux pour ce qui
n'est pas de son ressort :

- **`docs/revue/2026-09-04-matrice-fonctionnalites.md`** — l'état
  fonctionnel réel du produit (304 lignes, `livre`/`partiel`/`inerte`/
  `absent`/`prévu`), source des 43 confirmées non corrigées et des gaps
  `GAP-56..69` du référentiel 3.
- **`docs/revue/2026-09-04-analyse-gaps.md`** — 79 manques (`GAP-01..79`)
  confrontés à quatre référentiels (feuille de route interne, benchmark
  concurrentiel, cohérence interne, exigences de production), avec un
  encadré « déjà fermé » pour quatre éléments présentés à tort comme ouverts.
- **`docs/revue/2026-09-04-backlog.md`** — le backlog unique, **173
  entrées `REV-nnn`**, seul document qui porte ce qui reste à faire :
  les 35 `minor`, la déclassée, les 43 confirmées non corrigées (avec preuve
  de reproduction et correctif minimal), la dette héritée de `CLAUDE.md`
  (vérifiée dans le code — plusieurs éléments trouvés déjà fermés), les
  ~7 Minor trouvés pendant les revues des correctifs eux-mêmes, et les 79
  gaps non retenus par la feuille de route révisée.

## 9. Réserves

- Les comptes de tests (Vitest/E2E/pytest) du dépôt dans son ensemble ne
  sont pas repris ici : ce sont des livrables d'autres tâches de SP-42
  (feuille de route révisée, historique d'exécution), pas de celle-ci.
- Le §5 (4ᵉ porte du critical) et le §1 de `docs/revue/2026-09-04-
  backlog.md` (REV-001, REV-002, REV-003) ont été trouvés par vérification
  directe du code pendant l'exécution de cette tâche — ils n'existent dans
  aucun fichier `sp42-*` antérieur (`sp42-findings.jsonl` inclus). Il est
  possible qu'une vérification indépendante future en trouve d'autres :
  la revue exhaustive de 16 axes ne garantit pas l'absence de 5ᵉ porte.
- La feuille de route révisée (Tâche 16) tourne en parallèle de cette
  tâche : la section 10 du backlog ne suppose aucun de ses résultats — tous
  les 79 gaps y sont inscrits, à charge pour une session future de marquer
  fermées celles reprises comme SP.
