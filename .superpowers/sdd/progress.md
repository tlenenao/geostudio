# SP-14l — MCP analytique — Progress Ledger

Plan: docs/superpowers/plans/2026-08-04-sp14l-mcp-analytique.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@4f95f43 (ledger SP-14k committé en amont par hygiène de dépôt ;
SP-14k lui-même READY TO MERGE mais pas encore intégré à `main`).

Note : ce fichier remplace le ledger SP-14k (complet, READY TO MERGE, HEAD=9f4ef1b
puis commit de ledger 4f95f43) — même fichier scratch réutilisé par convention du
dépôt ; contenu SP-14k préservé dans l'historique git (commit 4f95f43).

## Pré-vol

Scan des 4 tâches (1: `create_dataset` — mirror `POST /configs` kind=dataset ;
2: `run_analytics_query` — mirror `POST /collections/{id}/aggregate` +
`POST /datasets/{id}/arcgis/aggregate` ; 3: `explain_dataset` — description de
champs sans stats ni échantillonnage ; 4: vérification complète + doc) contre
les contraintes globales (exactement 3 outils, pas de `run_sql`, pas de requête
visuelle, pas de per-field stats dans `explain_dataset` ; `run_analytics_query`
= accès lecture dataset seul, pas de rôle analyste ; `create_dataset` gated par
`is_read_only_mode()` + `READ_ONLY_TOOLS` ; exceptions domaine → `ValueError`
jamais `HTTPException` ; helpers privés réimplémentés en miroir, jamais
cross-importés ; docs FR / code EN ; commits conventionnels ; suite complète +
lint-imports verts en fin de tâche) :

Aucune lacune ni contradiction trouvée. Le plan fournit du code complet et
littéral pour chaque tâche (imports, helpers privés, corps d'outil MCP, tests
unitaires — deux variantes source `collection`/`arcgis` par outil de lecture) —
transcription + tests, pas de conception à faire, même style que SP-14k.
Dépendances d'interface notées : Task 2 consomme `create_dataset` (Task 1)
pour construire ses fixtures et réutilise le voisinage de `_validate_dataset`
(nouveaux helpers `_resolve_dataset_payload`/`_resolve_arcgis_external_url`) ;
Task 3 consomme les deux helpers de Task 2. Task 4 est vérification seule
(suite complète, lint-imports, smoke-test comptage d'outils à 15, mise à jour
`CLAUDE.md` — jugement à porter sur le retrait ou non de la ligne SP-14
"À venir" en comparant à la feuille de route, la requête visuelle restant
bloquée sur SP-15/16 donc SP-14 dans son ensemble n'est pas complet).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 4f95f43
Task 1: complete (commit a6eaf75, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor cosmétique déjà
présent tel quel dans le texte littéral du plan). `create_dataset` : mirror
fidèle de `POST /configs` kind=dataset, `_validate_dataset` réutilise
`validate_dataset_payload` inchangé (HTTPException→ValueError), gate
`is_read_only_mode()` posé avant toute session DB, `READ_ONLY_TOOLS` étendu à
5 entrées. Absence de `_validate_extension_scope` vérifiée inerte pour les
configs dataset (pas de layout/pages) par le reviewer — conforme au design,
pas un écart. 13/13 tests (6 nouveaux + 7 read-only mode), aucune régression.

Base Task 2: a6eaf75
Task 2: complete (commit d877944, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor cosmétiques).
`run_analytics_query` : miroir ligne-à-ligne des deux routes REST existantes
(`POST /collections/{id}/aggregate` et `POST /datasets/{id}/arcgis/aggregate`),
double vérification indépendante dataset+couche pour arcgis
(`_resolve_arcgis_external_url`, vérifiée par le reviewer contre
`_resolve_arcgis_dataset`), rejet explicite bucket/split/bins côté arcgis,
`translate_aggregate_query` réutilisé intact (fix injection SP-14k hérité
sans modification). Absent de `READ_ONLY_TOOLS` (outil lecture seule,
confirmé). 2 bugs trouvés et corrigés par l'implémenteur dans le code de
test **littéral du plan** (pas dans `tools.py`) : double `with app_client:`
(contrainte dure de la lib MCP, un seul run par instance) et un test de
révocation d'accès rendu inopérant par le short-circuit propriétaire de
`can()` (collection possédée par l'appelant plutôt qu'un tiers) — les deux
corrections vérifiées indépendamment par le reviewer comme un renforcement
des tests, pas un affaiblissement, aucune ligne pré-existante de `tools.py`
touchée. 7/7 tests nouveaux (4 postgis réels + 3 SQLite) + 25/25 régression,
lint-imports vert.

Base Task 3: d877944
Task 3: complete (commit a1dc72a, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables).
`explain_dataset` : réutilise intact `_resolve_dataset_payload`/
`_resolve_arcgis_external_url` (Task 2, double vérification permission
préservée), `introspect_table`/`table_info_to_schema` côté collection
(même chemin que `create_form_app`), `harvest_routes.get_arcgis_http_client()`
guardé côté arcgis (pas d'appel httpx nu). Aucune stat/échantillonnage par
champ (vérifié champ par champ par le reviewer — seuls `name`/`type`
retournés, `alias`/`required`/`maxLength` explicitement écartés). Absent de
`READ_ONLY_TOOLS` (lecture seule). 3/3 tests nouveaux (1 postgis réel + 2
SQLite), 69/69 suite MCP complète.

Base Task 4: a1dc72a
Task 4: complete (commit f8bc295, vérification seule — aucun code applicatif
touché). Suite complète 973/973 verte (0 skip inattendu sur les 13 fichiers
`test_mcp_tools_*`), lint-imports vert (1 kept, 0 broken). **Écart de plan
trouvé et résolu sans bloquer** : le smoke-test de comptage d'outils
(Step 3) attendait 15 (12 existants + 3 nouveaux) mais retourne 14 — vérifié
indépendamment par le contrôleur (`git show 90f6e16:core/app/mcp/tools.py`
+ ré-exécution directe du smoke-test) : la base pré-existante réelle est 11
outils, pas 12 — simple erreur arithmétique du texte du plan, aucun outil
manquant ni dupliqué (les 3 nouveaux + les 11 existants = 14, tous corrects).
CLAUDE.md mis à jour : ligne SP-14l ajoutée à "### Fait" ; ligne SP-14
"### À venir" volontairement laissée telle quelle (requête visuelle non
livrée, bloquée sur SP-15) — SP-14 dans son ensemble reste incomplet.

## SP-14l COMPLET — 4 tâches, 4 commits de tâches (a6eaf75, d877944,
## a1dc72a, f8bc295), 0 round de fix sur les tâches individuelles (3/3
## outils approuvés au premier passage). Seul écart rencontré : une erreur
## arithmétique du texte du plan (Step 3 de Task 4, 12→11 outils pré-
## existants), vérifiée indépendamment et résolue sans toucher au code.
## HEAD=f8bc295, prêt pour la revue finale de branche.

## Revue finale de branche (opus, 4f95f43..f8bc295, 6 commits) — 0 finding
## Critical, 0 Important, 3 Minor (concaténation de chaîne au lieu de
## `params={"f":"json"}` dans `explain_dataset` — conforme au texte du plan
## tel quel, pas un écart implémenteur ; lacune de couverture croisée
## create_dataset→run_analytics_query côté arcgis, couverte de façon
## transitive par le test explain_dataset ; redondance documentée du
## double check dataset-read côté arcgis). Vérifications spécifiques :
## pas d'escalade de privilège par enchaînement d'outils (accès toujours
## réévalué sur l'appelant, jamais sur le propriétaire du dataset) ;
## `tenant_id` fileté de façon cohérente sur les trois outils ; le point
## d'injection SP-14k (`translate_aggregate_query`) reste l'unique endroit
## où des noms de champ arcgis atteignent une clause `where=`, `explain_dataset`
## n'a pas de surface équivalente (GET sans nom de champ utilisateur) ;
## les deux outils de lecture appellent `_resolve_dataset_payload`/
## `_resolve_arcgis_external_url` de façon identique. Deux divergences
## comportementales par rapport aux routes REST relevées, toutes deux dans
## le sens de la sécurité (MCP authentifie toujours ; MCP vérifie l'accès
## avant de rejeter bucket/split/bins, la route REST fait l'inverse et
## fuiterait un 400 avant le check de lecture) — non des défauts.
## **SP-14l READY TO MERGE** — HEAD=f8bc295, prêt pour
## finishing-a-development-branch.
