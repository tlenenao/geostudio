# SP-43 — Refactorisation structurelle : inventaire et ordre d'exécution

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (via SP-42, Tâche 15)
**Documents liés** : `docs/superpowers/specs/2026-09-04-sp42-revue-globale-design.md`,
`.superpowers/sdd/sp42-findings.jsonl` (35 `minor` + 43 `confirme` non corrigées,
74 confirmées au total − 31 corrigées par SP-42),
`CLAUDE.md` §« Conventions tranchées (2026-09-01) » et §« Pièges récurrents ».

**Portée de ce document** : un inventaire argumenté et un ordre d'exécution.
**Aucun code n'est refactorisé ici** — c'est le texte qui deviendra le plan
SP-43, pas son exécution. Les tailles de fichiers ci-dessous ont été mesurées
le 2026-09-05 sur `dev` à `8550f996`, après les 41 commits SP-42 — elles ne
reprennent pas les repères du brief de tâche, obsolètes depuis.

---

## 1. Motivation : ce que la duplication a déjà coûté

Ce dépôt n'a pas de dette de style abstraite. Il a une dette de **duplication
mécanique** — la même règle métier écrite à plusieurs endroits sans lien entre
les copies — et cette dette a déjà produit des défauts réels, trouvés en revue
finale, parfois plusieurs fois de suite. Cette section liste les cas où c'est
prouvé, avec la trace exacte, dans l'ordre de coût décroissant.

### 1.1 Le mapping kind→privilège : quatre implémentations, un critical rouvert deux fois

`core/app/configs/routes.py:127-139` déclare `_KIND_PRIVILEGE`, le dict
`kind -> Privilege` cité comme unique source de vérité par son propre
commentaire (« mapping calé sur le domaine shell », lignes 118-126). Il est
aujourd'hui consommé par **quatre sites distincts**, avec trois formes de
couplage différentes :

1. `core/app/configs/routes.py:142-144` (`_require_privilege_for_kind`) — le
   site d'origine.
2. `core/app/mcp/tools.py:195-208` (`_require_config_privilege`) — importe et
   appelle `_require_privilege_for_kind` **verbatim** (commentaire ligne 197 :
   « Reuses app.configs.routes._require_privilege_for_kind verbatim »).
   Réutilisation correcte, mais elle importe un nom **privé** (préfixe `_`)
   d'un autre module — un renommage local de `_require_privilege_for_kind`
   casserait silencieusement `mcp/tools.py` sans qu'aucun contrat explicite ne
   le signale.
3. `core/app/tileset3d/routes.py:110,182` — importe le dict privé
   `_KIND_PRIVILEGE` lui-même (pas la fonction) et indexe
   `_KIND_PRIVILEGE["tileset3d"]` à la main. Même fragilité que (2), en pire :
   si `tileset3d` disparaissait un jour du dict, l'erreur serait un
   `KeyError` au runtime, pas une erreur de type.
4. `core/app/pipelines/routes.py:56-79` (`_pipeline_writes_dataset` /
   `_require_data_manage_if_pipeline_writes_dataset`) — **ne consulte pas le
   dict du tout** : il rappelle `Privilege.DATA_MANAGE.value` en dur, avec un
   commentaire qui renvoie manuellement vers
   `app.configs.routes::_KIND_PRIVILEGE` (ligne 62) pour affirmer que les deux
   valeurs concordent. Rien ne le vérifie mécaniquement. Réutilisé par
   `core/app/mcp/tools.py:59,959` (import direct de la fonction — correct),
   donc le 4e site n'est dupliqué qu'une fois côté MCP, mais reste la seule
   des quatre implémentations qui ne lit jamais `_KIND_PRIVILEGE`.

Coût réel, documenté par `.superpowers/sdd/sp42-findings.jsonl` (`F-securite-
autorisation-01`, critical, fusion de deux trouvailles sœurs) : avant la
correction apportée pendant SP-42, **aucune** des quatre routes de création de
contenu (`POST /configs`, `POST /collections/empty`, `POST /uploads`) ne
consultait de privilège — 10 des 18 privilèges catalogués n'imposaient rien.
Le CLAUDE.md/ledger de session (rapporté par le contexte de tâche) indique que
ce même défaut « a été déclaré clos trois fois et rouvert deux fois » pendant
la revue — précisément parce que chaque correctif corrigeait un des quatre
sites sans vérifier les trois autres. C'est l'exemple le plus coûteux du
dépôt : une seule règle métier, quatre points d'application, dont un seul
lien mécanique réel (import direct) et deux emprunts fragiles (import de nom
privé, duplication de valeur avec commentaire de synchronisation manuelle).

### 1.2 `toFrontLayer()` : quatre champs perdus, un seul mécanisme jamais construit

`shell/src/api/itemClient.ts:98-145` traduit `RawMapLayer` (forme brute
servie par le cœur) vers `MapLayer` (forme consommée par le shell), par un
`switch (l.kind)` à la main, un bloc par kind, chaque champ optionnel repris
un par un (`...(l.popup ? { popup: l.popup } : {})`, etc.). CLAUDE.md
(« Pièges récurrents » n°5) documente que cette fonction a perdu
**quatre champs successifs** au fil des sessions — `popup`, `symbology`,
`renderAs`, puis `collectionId`/`pkColumn` — parce qu'ajouter un champ à
`RawMapLayer`/`MapLayer` n'oblige à rien côté `toFrontLayer()` : le
compilateur ne signale aucune omission (le retour de chaque branche est un
littéral construit à la main, pas un mapping générique).

`shell/src/api/itemClient.test.ts` porte la preuve du symptôme : quatre
commentaires distincts (lignes 387-388, 438, 536, 578) documentent chacun,
après coup, « toFrontLayer never read X off the raw server JSON » — un test
de régression **ajouté après chaque perte**, jamais un test qui aurait
empêché la cinquième. Aucun test n'affirme aujourd'hui « tout champ optionnel
présent sur `RawMapLayer` pour un kind donné survit à `toFrontLayer()` » — la
propriété qui aurait fermé la classe entière plutôt que ses quatre symptômes.

### 1.3 Boilerplate de job procrastinate : dupliqué sur 5 modules, 2 bugs réels trouvés lors de SP-39

`core/app/reports/jobs.py` et `core/app/alerts/jobs.py` (et, par le même
patron, `core/app/pipelines/jobs.py`, `core/app/ingestion/tasks.py`,
`core/app/appexport/jobs.py`) déclarent chacun leur propre
`_session_factory()`, `_owner_user()` et `_notify(...)` quasi identiques
(`reports/jobs.py:45-50,74` vs `alerts/jobs.py:71-97,197` — mêmes signatures,
même rôle : résoudre une session, résoudre le propriétaire de l'item pour
écrire l'audit, écrire une notification best-effort séparée du commit de
statut). CLAUDE.md (entrée SP-39, `### Livré`) documente que cette
duplication a produit **deux `UnboundLocalError` réels**, trouvés
indépendamment sur `app/ingestion/tasks.py` et `app/pipelines/jobs.py` : dans
les deux cas, une variable référencée par l'appel `_notify` de la branche
d'échec n'était pas garantie liée si l'échec survenait avant son affectation
normale — le même mécanisme de bug, écrit deux fois parce que le code
d'appel de notification est écrit cinq fois plutôt qu'une. Les trois autres
sites (export, export d'app, rapport) ont échappé au bug par chance
d'ordre des affectations, pas par construction.

### 1.4 Privilèges du rôle Créateur : triplement dupliqués, sans lien mécanique

`core/app/roles/privileges.py:64-75` (`BUILT_IN_ROLE_PRIVILEGES["creator"]`,
8 privilèges) est recopié littéralement à l'identique à deux endroits côté
shell : `shell/e2e/mocks.ts` (`DEFAULT_ME.privileges`, la liste des 8 mêmes
chaînes) et `shell/src/auth/capabilities.test.ts:48-60` (fixture `creator`).
Le commentaire de `mocks.ts` (lignes 88-97) le reconnaît explicitement :
« miroir exact de `BUILT_IN_ROLE_PRIVILEGES["creator"]` […] et de la fixture
`creator` de `shell/src/auth/capabilities.test.ts` » — un commentaire qui
documente une duplication au lieu de la supprimer. Coût déjà payé (SP-31,
revue finale) : `DomainBar.test.tsx` portait une **quatrième** copie, dérivée
séparément et devenue fausse (elle figeait « Créateur sans Analytique »,
contredisant `capabilities.test.ts`) — trouvée Important en revue finale
uniquement parce qu'aucun des trois exemplaires listés ci-dessus ne pouvait
la contredire mécaniquement. Le suivi CLAUDE.md ouvert par SP-31 le dit
explicitement : « le prochain privilège ajouté rouvrira la même classe de
défaut ».

### 1.5 Mocks de collection E2E : 12 champs sur 23 absents, un plantage déjà produit

`core/app/collections/routes.py:149-176` (`_collection_json`) sérialise
**toujours** 12 champs (`attachmentFields`, `license`, `licenseUri`,
`producer`, `contact`, `updateFrequency`, `lineage`, `language`, `version`,
`temporalStart`, `temporalEnd`, et le champ ajouté par SP-41) qu'aucun mock
de collection E2E ne porte (`shell/e2e/admin-collections.spec.ts:41-104`,
trois réponses mockées, toutes trois arrêtées au champ `owner` ; grep de
`attachmentFields|licenseUri|temporalStart` sur `shell/e2e/mocks.ts` et
`shell/src/test/msw/handlers.ts` : zéro occurrence). Coût réel déjà payé,
deux fois : la revue finale SP-40 a trouvé que `EditCollectionPanel`
plantait sur `useState(collection.attachmentFields)` avec ces mocks
incomplets — fermé **côté composant** (`?? []`) sans jamais corriger les
mocks à la source ; SP-41 a ensuite ajouté `license`/`language` à la vraie
réponse du cœur, rouvrant exactement le même écart pour le nouvel onglet
« Métadonnées ouvertes ». Le filet E2E de cette page valide donc un contrat
que le cœur ne sert jamais.

### 1.6 Modèle SQLAlchemy vs schéma Alembic : ~27 colonnes divergentes, payé deux fois, aucun filet

`.superpowers/sdd/sp42-findings.jsonl` (`F-migrations-03`, fusion de 5
trouvailles sœurs) établit, colonne par colonne, que 14 modules du cœur
portent un `server_default=` en migration Alembic jamais reporté dans le
`mapped_column(...)` correspondant — `core/app/collections/models.py:33-51`
contre `core/alembic/versions/0008_collections_admin.py`,
`0032_attachments.py`, `0033_metadata.py`, et 3 autres paires modèle/migration
citées par la fusion. Conséquence vérifiée par le code des tests eux-mêmes :
`test_attachments_migration_alembic.py` et `test_metadata_migration_alembic.py`
doivent fournir explicitement chaque colonne dans leurs `INSERT` bruts pour
éviter un `NotNullViolation`, preuve en creux que `Base.metadata.create_all()`
(le schéma de la quasi-totalité de la suite pytest) n'a **aucun** défaut sur
ces colonnes alors que la production (migrée par Alembic) en a un — un même
code se comporte différemment selon la façon dont la base a été construite.
Le CLAUDE.md le confirme : « la classe a été payée deux fois » (commits SP-41
`0139cf74` et `40b91dcb`, fixtures d'abord incomplètes, puis divergence de
`server_default`). `F-tests-01` (même fichier) prouve par **falsification
réelle** qu'aucun filet ne peut voir un nouveau cas : une colonne ajoutée au
modèle sans migration correspondante fait passer toute la suite pytest,
`sp42_probe`, injectée puis retirée pour la preuve.

### 1.7 Une convention tranchée, jamais appliquée mécaniquement : `aria-expanded`

Le 2026-09-01, CLAUDE.md tranche trois divergences répétées sur les neuf
familles SP-30, dont : « `aria-expanded`/`aria-controls` obligatoire sur tout
bouton qui bascule un panneau en ligne ». La revue SP-42 (`F-i18n-a11y-03`)
mesure que cette règle, écrite noir sur blanc depuis quatre jours au moment
de la mesure, **n'est appliquée nulle part** — seul `ui/kit/Combobox.tsx`
(câblé par Radix, pas par un développeur) la respecte. Sept sites listés,
dont deux (`NewItemButton.tsx`, `ImportFileButton.tsx`) livrés par SP-30k,
**après** la décision. Ce n'est pas un oubli isolé : c'est la preuve qu'une
convention documentée en prose, sans primitive partagée qui la porte
mécaniquement, ne change rien à ce qui s'écrit ensuite — exactement le
mécanisme de la section 1.1 (une règle, appliquée à la main à chaque site).

---

## 2. Inventaire par fichier

Convention : chaque entrée dit *ce que le fichier fait de trop* — pas
seulement sa taille — et *ce qui devrait en sortir*. Un fichier n'est cité
que si son volume correspond à un mélange réel de responsabilités, pas à un
nombre de lignes en soi (cf. contrainte du brief).

### 2.1 Cœur (`core/app/`)

| Fichier | Lignes | Ce qu'il fait de trop |
|---|---:|---|
| `mcp/tools.py` | 1134 | Une seule fonction `register_tools()` (lignes 280-1134, ~850 lignes) héberge **22 outils** comme fermetures imbriquées, chacune ré-implémentant en ligne la résolution d'acteur, la validation par kind (`_validate_dataset`/`_validate_bookmark`/`_validate_pipeline`, lignes 161-194) et la mise en forme de réponse — une deuxième surface d'écriture parallèle aux routes REST, avec ses propres copies des mêmes règles (cf. §1.1). Aucune frontière entre « déclaration de l'outil MCP » (schéma, docstring exposée au LLM) et « logique métier » (qui devrait être un appel à la même fonction de service que la route REST). |
| `pipelines/runtime.py` | 894 | Un dispatcher unique sur `node.op`, dupliqué **deux fois** dans le même fichier : une première fois dans `_prepare()` (lignes 244-320, readers) et `_execute_transform_chain()` (lignes 440-520, transforms), une seconde fois dans `run_pipeline()` (lignes 866-882, writers). Trois familles d'opérations (lecture/transformation/écriture) qui ne partagent aucune interface commune, mélangées avec l'exécution QGIS en sidecar (lignes 340-440) et le verrouillage DuckDB (`_lock_down`, ligne 200) dans un seul module procédural. |
| `collections/routes.py` | 698 | Mélange 4 responsabilités indépendantes : gestion DDL réelle (introspection de table, création `POST /collections/empty`, `_core_tables()`), CRUD de métadonnées (`_collection_json`, cf. §1.5), fusion de schéma (pseudo-champs `attachment` dans `get_collection_schema`), et partage (`get_sharing`/`put_sharing`, dupliquant le patron déjà présent dans `configs/routes.py` pour les items). |
| `features/routes.py` | 654 | Mélange le service OGC API Features public (landing page, conformance — RFC-normé, stable) avec l'agrégation analytique (DuckDB, `aggregate_features`/`analytics_sql`, lignes 245-491, logique complètement différente du CRUD OGC) et le CRUD de features (create/put/remove, lignes 535-654). Trois familles de clients différentes (moissonneurs OGC, widgets analytiques, formulaires d'édition) servies par un seul routeur. |
| `configs/routes.py` | 527 | Deux jeux de routes quasi parallèles : `/configs/{id}` et `/configs/by-item/{id}` (create/get/update/rollback/delete, lignes 170-490) partagent la même logique mais sont écrites deux fois avec de légères variations non documentées comme telles. Porte aussi `_KIND_PRIVILEGE` (§1.1), la garde ETL/export par capacité d'instance, et `delete_item` (ligne 492) — la suppression d'un item n'est pas une responsabilité de « config ». |
| `analytics/aggregate.py` | 556 | Non inspecté en détail dans cette passe (hors des repères connus du brief) — signalé pour un futur audit, pas retenu dans l'ordre de découpage ci-dessous faute de trouvaille de duplication qui le justifie aujourd'hui. |
| `harvest/routes.py` | 540 | Idem — hors périmètre de cet inventaire, aucune trouvaille de duplication ne le cite. |

### 2.2 Shell (`shell/src/`)

| Fichier | Lignes | Ce qu'il fait de trop |
|---|---:|---|
| `api/itemClient.ts` | 1743 | La règle d'architecture n°1 de CLAUDE.md (« `ItemClient` est le sas ») est correcte et **ne doit pas changer** : le shell ne doit parler au cœur qu'à travers cette interface. Le défaut n'est pas l'existence d'un point de passage unique, c'est que son **implémentation** (`createItemClient()`, une seule fonction-usine de la ligne 349 à la fin, ~106 méthodes internes) mélange dans un seul fichier/closure : le client HTTP bas niveau (`request()`), la conversion raw↔front par kind (`toFrontLayer`, §1.2), la construction de requêtes d'agrégation, l'introspection GeoJSON, le cache dataset mémoire (`datasetCache`, sans TTL — cf. `F-shell-api-03`), et le CRUD des 9 kinds + rôles + utilisateurs + notifications + pièces jointes + admin-tools. Diviser l'implémentation par domaine, **derrière la même fonction-usine et la même interface `ItemClient` exportée**, ne viole pas la règle n°1 — le sas reste unique côté consommateur. |
| `map/MapView.tsx` | 1425 | ~20 fonctions pures au niveau module (`addTypedLayer`, `addOutlineLayer`, `addIconLayer`, `addLabelLayer`, `buildDeckLayer`, `buildTiles3DLayer`, `applyTerrain`, lignes 101-843) qui ne touchent jamais un hook React, suivies d'un composant à 28 usages de `useState`/`useEffect`/`useMemo`/`useCallback`. Les fonctions pures sont testables indépendamment de React et ne le sont pas aujourd'hui autrement qu'à travers le rendu du composant entier (E2E ou tests d'intégration du composant) — aucun test unitaire direct de `buildDeckLayer` ou `applyTerrain`, par exemple. |
| `api/types.ts` | 974 | 106 déclarations `interface`/`type` dans un seul fichier. Contrairement à `itemClient.ts`, ce volume ne vient pas d'un mélange de responsabilités mais du nombre de kinds/domaines que le shell modélise (9 kinds de config + types transverses). Cité pour mémoire, **non retenu** dans l'ordre de découpage (§4) : aucune trouvaille de duplication ni de bug ne le cite, et un fichier de types purs ne peut pas dériver silencieusement de la même façon qu'un fichier de logique. |
| `api/hooks.ts` | 732 | 64 hooks exportés, un par endpoint/besoin, sans regroupement par domaine — symétrique du même problème qu'`itemClient.ts` côté React Query. Découpage proposé identique (par domaine), à faire dans la foulée du découpage d'`itemClient.ts` puisque chaque groupe de hooks consomme le groupe de méthodes correspondant. |
| `map/MapSymbologyEditor.tsx` | 831 | Un seul composant qui édite séquentiellement 5 encodages indépendants (couleur catégorielle/continue/classée, contour, opacité, icônes, étiquettes). `mapSymbology.ts` (ci-dessous) sépare déjà correctement le calcul (bonne nouvelle : pas de duplication de logique entre l'éditeur et `MapView`/le widget Carte — les deux consomment le même module de calcul) ; c'est la **UI** de l'éditeur elle-même qui n'est pas découpée par encodage. |
| `builder/widgets/mapSymbology.ts` | 771 | Module de calcul pur (bonne séparation, cf. ci-dessus), mais qui accumule 4 algorithmes de classification (quantile/equalInterval/Jenks/normalisation de domaine), la construction d'expressions de peinture MapLibre, et la construction de légende — trois familles d'algorithmes indépendantes dans un seul fichier. Risque de découpage bas (fonctions pures, déjà unitairement testées), mais non retenu en priorité faute de trouvaille de bug qui le justifie (le bug réel documenté, `F-shell-carte-02` sur la réinitialisation de domaine, est un défaut de logique d'appel côté éditeur, pas de structure de ce module). |

### 2.3 Boilerplate de job (transverse, pas un seul fichier)

`core/app/reports/jobs.py`, `core/app/alerts/jobs.py`,
`core/app/pipelines/jobs.py`, `core/app/ingestion/tasks.py`,
`core/app/appexport/jobs.py` : cf. §1.3. Chacun de ces 5 fichiers réimplémente
`_session_factory()`/`_owner_user()`/`_notify()`. Ce n'est pas un fichier trop
gros, c'est une fonction copiée cinq fois — le candidat le plus clair pour une
extraction, indépendamment de la taille de chaque fichier hôte.

---

## 3. Abstractions à extraire

Six abstractions, classées par gain/risque, chacune adossée à un défaut de
la section 1 :

1. **Registre kind→privilège public** (`core/app/roles/kind_registry.py` ou
   équivalent) — remplace `_KIND_PRIVILEGE` privé de `configs/routes.py`.
   Une seule fonction publique `privilege_for_kind(kind: str) -> str`,
   importée par les 4 sites de §1.1 (dont `tileset3d/routes.py`, qui cesse
   d'indexer un dict privé d'un autre module, et `pipelines/routes.py`, qui
   cesse de recopier `Privilege.DATA_MANAGE.value` en dur). Ferme
   définitivement la classe de bug qui a coûté 3 réouvertures.

2. **Convertisseur générique raw↔front pour `MapLayer`** — remplace le
   `switch` manuel de `toFrontLayer()`. Le plus sûr : ne pas viser un mapping
   générique par réflexion (risque de sur-ingénierie sur un type union
   discriminé), mais un **test caractéristique** posé AVANT tout refactor
   (cf. §5, étape 2) qui construise, pour chaque `kind`, un `RawMapLayer`
   avec **tous** ses champs optionnels renseignés et vérifie qu'aucun ne
   disparaît. Une fois ce test posé, la fonction elle-même peut rester un
   `switch` manuel — c'est le filet qui manque, pas nécessairement le code.

3. **Module de support de job partagé** (`core/app/jobs/common.py`) —
   `session_factory()`, `resolve_owner_user()`, `notify_best_effort()`
   génériques, paramétrés par `kind`/`item_id`. Doit préserver l'invariant
   déjà correct sur 3 des 5 sites (le bloc try/except de notification est
   strictement séparé de celui qui committe le statut du job) et le
   restaurer sur les 2 qui ne l'ont pas (dette documentée SP-39, sweep de
   rapports).

4. **Fixture de collection unique côté E2E** (`mockCollection(overrides)`
   dans `shell/e2e/mocks.ts`), construite pour lister explicitement les 23
   champs réels de `_collection_json()` — même remède que `mockMe()`
   (SP-30l) pour la dérive équivalente sur `GET /me`. Un test de contrat
   séparé (§5, étape 1) doit exister en amont pour qu'un futur champ ajouté
   côté cœur ne puisse plus rouvrir cet écart silencieusement.

5. **Filet modèle SQLAlchemy ↔ schéma Alembic** — le test proposé par
   `F-tests-01` (`alembic.autogenerate.compare_metadata` contre une base
   réellement migrée). Ce n'est pas une abstraction de code métier, mais
   c'est un prérequis mécanique absolu avant de toucher aux ~27 colonnes
   divergentes de §1.6 — sans lui, corriger les `server_default` un par un
   reproduit exactement le risque qui a déjà coûté deux fois.

6. **Primitive de panneau en ligne avec `aria-expanded`/`aria-controls`
   câblés** (`shell/src/ui/kit/` — un hook `usePanelTrigger(id)` ou un
   composant `PanelTrigger` qui pose les deux attributs sur le déclencheur et
   l'`id`/`role="region"` sur la cible). Fait de la convention du
   2026-09-01 une propriété du composant plutôt qu'une prose à respecter de
   mémoire — condition nécessaire pour que la classe cesse de se répéter à
   la 6e famille de pages.

---

## 4. Patrons divergents entre pages sœurs, jamais tranchés

CLAUDE.md a déjà tranché trois divergences le 2026-09-01 (hauteur `h-9`,
`Button` du kit vs `<button>` natif, obligation d'`aria-expanded`). Elles
restent citées ici parce que (a) `aria-expanded` s'est révélé non appliqué en
pratique (§1.7, à corriger par l'abstraction §3.6, pas par une nouvelle
décision) et (b) trois autres divergences n'ont **jamais** été tranchées :

| Divergence | Où elle apparaît | Forme unique proposée |
|---|---|---|
| Gestion de `query.isError` sur chargement conditionnel | `PipelineBuilderPage.tsx` (aucune gestion, `F-shell-pages-05`), `ReportEditPage.tsx` (aucune gestion), `VisualQueryWizardPage.tsx` (protégée par un garde différent) — seul `MapEditorPage.tsx:37-42` traite le cas | Généraliser le garde de `MapEditorPage` : `if (pk !== null && query.isError) return <p role="alert">{...} introuvable.</p>;` sur les 3 pages manquantes, un seul patron. C'est la forme déjà choisie par la page qui l'a fait correctement — pas une nouvelle invention. |
| Séparateur `border-t` avant une section optionnelle | Rendu inconditionnellement même quand rien au-dessus n'existe à séparer sur `PipelineBuilderPage`/`ReportEditPage`/`VisualQueryWizardPage` (mode brouillon, `pk === null`) | Gater le `border-t` sur la même condition que les panneaux qu'il sépare (`pk !== null` ou équivalent) — cohérent avec le fait qu'un séparateur sans rien à séparer n'a pas de sens. |
| Ordre alertes de validation / bouton d'action | `ReportEditPage` : alertes puis bouton. `VisualQueryWizardPage`/`PipelineBuilderPage` (famille) : ordres divergents documentés dans CLAUDE.md sans règle commune | Alertes de validation **avant** le bouton d'action partout (l'utilisateur voit pourquoi une action est bloquée avant d'atteindre le contrôle) — reprend la majorité déjà observée. |
| `<main>`/`<aside>`/`<div>` pour les trois colonnes du triptyque | Déjà tranché par SP-30f : `div`/`div`/`div` par défaut, `AppBuilderPage` seule exception documentée (`<main ref={mainRef}>` pour la capture de miniature, `<aside>` sur Propriétés) | Confirmé comme acquis — cité ici pour mémoire, aucune action requise, ne pas rouvrir. |
| Garde `busy` sur la fermeture d'un panneau/tiroir | `Tileset3DUploadButton` la porte (`requestClose()`) ; `ImportFileButton`/`NewItemButton` ne l'ont jamais eue, y compris après SP-30k | Étendre `requestClose()` (annule la fermeture tant qu'une mutation async est en vol) aux deux composants qui ne l'ont pas — patron déjà écrit, à copier, pas à réinventer. |

---

## 5. Ordre de découpage, du moins risqué au plus risqué

Chaque étape nomme le filet de test qui doit **exister et être vérifié vert
avant** de commencer à toucher le code de cette étape — pas après.

**Étape 0 — Filet transverse, avant tout le reste : le comparateur modèle
↔ Alembic (§3.5).**
Aucune étape suivante ne touche à un modèle SQLAlchemy sans lui. Filet
préalable : aucun (c'est lui-même le filet) — mais il doit être **validé par
falsification** avant d'être considéré fiable : injecter une colonne sans
migration (comme `F-tests-01` l'a fait), confirmer qu'il échoue, retirer
l'injection. Risque : nul (ajout pur, aucun code existant modifié).

**Étape 1 — Registre kind→privilège unique (§3.1).**
Filet préalable : le test paramétré sur les 18 privilèges déjà proposé par
`F-securite-autorisation-01` (à vérifier qu'il existe et couvre bien les 4
sites de §1.1 avant de commencer — sinon l'écrire d'abord) + la suite
`test_mcp_configs_privilege_guard.py`/`test_pipeline_connector_runtime.py`
existante. Risque : bas — la valeur ne change pas, seul le point d'accès est
unifié ; les 4 sites appelants ont chacun leur propre test d'intégration.

**Étape 2 — Test caractéristique de `toFrontLayer()` puis nettoyage (§3.2).**
Filet préalable : écrire d'abord le test caractéristique (tous les champs de
`RawMapLayer` par kind survivent) — actuellement absent, seuls 4 tests de
non-régression ponctuels existent (`itemClient.test.ts:387-388,438,536,578`).
Une fois ce test vert sur le code actuel, un futur ajout de champ est protégé
sans qu'aucune ligne de production n'ait besoin de changer maintenant.
Risque : bas — test pur ajouté, aucun changement de comportement dans cette
étape.

**Étape 3 — Fixture de collection E2E unique (§3.4).**
Filet préalable : aucun test existant ne casse (c'est un remplacement de
mocks, pas de code de production) — mais il faut d'abord écrire le test de
contrat qui compare les clés de `mockCollection()` à celles réellement
servies par `_collection_json()` (ex. un test Python qui exporte la liste des
clés et un test TS qui les compare à la fixture), sinon la fixture unique
peut dériver exactement comme les trois copies qu'elle remplace. Risque :
bas — E2E uniquement, aucun code de production touché.

**Étape 4 — Application des `server_default=` manquants (~27 colonnes,
§1.6), maintenant protégée par l'étape 0.**
Filet préalable : étape 0 vert + `test_attachments_migration_alembic.py`/
`test_metadata_migration_alembic.py` existants, rejoués sur une base non
vide réelle (piège n°8 CLAUDE.md) avant et après. Risque : moyen — touche 14
modules de modèles, mais chaque changement est additif (ajout d'un
`server_default` qui doit déjà correspondre à la valeur migrée) et le filet
de l'étape 0 détecte immédiatement un écart résiduel.

**Étape 5 — Module de support de job partagé (§3.3).**
Filet préalable : les 5 suites de test existantes
(`test_reports_jobs.py`/`test_alert_jobs.py`/`test_pipeline_jobs.py`/
`test_ingestion_tasks.py`/`test_appexport_jobs.py` — noms à vérifier
exactement avant de commencer, ne pas supposer) + un nouveau test qui
falsifie l'isolation try/except de `notify_best_effort()` (forcer une
exception dans le chemin de notification, vérifier qu'elle ne remonte
jamais dans le bloc qui committe le statut du job) sur les 5 call sites
après migration. Risque : moyen — 5 fichiers touchés simultanément, mais
chaque fichier garde son test dédié comme oracle de non-régression
comportementale.

**Étape 6 — Primitive `aria-expanded`/`aria-controls` (§3.6), appliquée aux 7
sites de `F-i18n-a11y-03`.**
Filet préalable : le test de chaque page hôte (`CollectionsAdminPage.test.tsx`,
`HarvestSourcesAdminPage.test.tsx`, `RolesAdminPage.test.tsx`, etc.) + un
nouveau test d'assertion générique (`expectAriaWired(trigger, panelId)`)
ajouté au premier site puis réutilisé sur les 6 suivants un par un — pas en
masse, pour que chaque échec de falsification pointe vers une seule page.
Risque : moyen — surface large (7 sites, 5 familles de pages), mais
changement additif (attributs ARIA) sans changement de comportement
fonctionnel testable par ailleurs.

**Étape 7 — Découpage d'`itemClient.ts`/`hooks.ts` par domaine, derrière la
même fonction-usine et la même interface `ItemClient` (§2.2).**
Filet préalable : les 169 tests existants de `itemClient.test.ts` (à
exécuter intégralement avant, pas un sous-ensemble) + le test caractéristique
de l'étape 2, qui doit être répliqué pour toute autre conversion raw↔front
similaire trouvée pendant le découpage (attention au piège n°5 : ne pas
laisser une 5e occurrence apparaître pendant ce découpage lui-même). Risque :
élevé — fichier central de l'architecture (règle n°1 CLAUDE.md), 106
méthodes à répartir sans casser un seul consommateur ; à faire domaine par
domaine (maps, datasets, pipelines, admin, notifications, attachments), un
commit par domaine, suite complète rejouée après chacun.

**Étape 8 — Découpage de `mcp/tools.py` par domaine, chaque outil délégant à
la fonction de service déjà utilisée par la route REST correspondante.**
Filet préalable : les 25 fichiers `test_mcp_*.py` existants, plus un test de
parité outil↔route (pour un échantillon d'un kind par famille : comparer la
réponse de l'outil MCP à celle de la route REST équivalente sur le même
état de base, avant tout changement — s'il n'existe pas déjà, l'écrire
d'abord, il sert d'oracle de régression pour tout le découpage). Risque :
élevé — 22 outils, chacun avec ses propres tests, mais le vrai risque est
architectural (faire dépendre les outils MCP de fonctions de service
partagées avec les routes REST est un changement souhaitable qui touche les
deux surfaces à la fois).

**Étape 9 — Découpage de `pipelines/runtime.py` en registres
readers/transforms/writers.**
Filet préalable : `test_pipeline_runtime.py` + `test_pipeline_connector_runtime.py`
existants, **et** — condition bloquante distincte de ce plan mais à vérifier
avant de commencer cette étape précise — les 5 tests marqués
`@pytest.mark.qgis` réellement exécutés au moins une fois contre un sidecar
QGIS réel (CLAUDE.md : seul point encore bloquant pour le jalon M14).
Refactorer le dispatcher `transform.qgis` sans avoir jamais vu ces 5 tests
tourner pour de vrai serait construire le filet le plus risqué de toute
cette spec sur une hypothèse jamais vérifiée. Risque : le plus élevé de
l'inventaire — moteur d'exécution le plus complexe du cœur (DuckDB + sidecar
QGIS + connecteurs dlt), le seul qui mélange code testé (readers/transforms
DuckDB) et code jamais exécuté en conditions réelles dans cet environnement
(QGIS).

---

## 6. Risques de régression

- **Étape 1 (registre kind→privilège)** : un site oublié dans la migration
  laisserait une route retomber sur l'ancien comportement local — même
  défaut que celui qui a motivé cette étape. Contre-mesure : grep de clôture
  (`grep -rn "_KIND_PRIVILEGE\|DATA_MANAGE.value" core/app --include=*.py`)
  avant de considérer l'étape close, sur le patron déjà utilisé par SP-34/
  SP-37 pour leurs propres grep de clôture.
- **Étape 2 (toFrontLayer)** : le test caractéristique peut lui-même être
  vacant s'il ne couvre que les champs déjà connus comme perdus — vérifier
  qu'il énumère les champs **depuis le type `RawMapLayer` lui-même** (via un
  test qui échoue à la compilation si un champ est ajouté au type sans être
  couvert), pas depuis une liste recopiée à la main qui peut elle aussi
  dater.
- **Étape 4 (server_default)** : un mauvais report de valeur (ex. `"fr"` vs
  `""`) romprait le filet de l'étape 0 en silence si le filet lui-même a un
  bug (cf. piège n°10 : falsifier le filet à chaque usage, pas seulement à
  sa création).
- **Étape 5 (jobs)** : régresser l'isolation try/except pendant l'extraction
  reproduirait exactement les deux bugs déjà trouvés par SP-39 — le test de
  falsification de l'isolation (forcer l'exception) n'est pas optionnel pour
  cette étape.
- **Étape 7 (itemClient split)** : risque principal = un import circulaire
  entre modules de domaine qui partagent aujourd'hui un scope de closure
  unique (ex. `resolveDataset` et le cache dataset consommés par plusieurs
  domaines) — à traiter en extrayant d'abord les dépendances transverses
  (client HTTP, cache) dans un module de base avant de séparer les domaines.
- **Étape 8 (MCP split)** : un outil qui se comportait différemment de la
  route REST équivalente **par accident** (pas par design) pourrait voir ce
  comportement corrigé silencieusement au passage — à documenter
  explicitement si le test de parité révèle un écart, ne jamais le résoudre
  sans decision explicite (cf. les 3 divergences REST/MCP déjà trouvées par
  la revue SP-42, `F-coeur-federation-05`).
- **Étape 9 (pipeline runtime)** : le risque le plus élevé de tout
  l'inventaire est de refactorer un chemin d'exécution (QGIS sidecar) jamais
  vérifié en conditions réelles dans cet environnement — un découpage qui
  « passe les tests » pourrait masquer un défaut d'intégration réel invisible
  aux mocks du sidecar.

---

## 7. Hors périmètre (explicite)

- **Tout changement de comportement fonctionnel.** Cette spec ne propose que
  des déplacements de code et des ajouts de filets ; aucune correction de
  bug métier (les défauts Important/Critical listés en §1 comme motivation
  sont déjà corrigés ou arbitrés par SP-42 lui-même, hors de ce document).
- **`api/types.ts`** (974 lignes, §2.2) : gros par nombre de domaines
  modélisés, pas par mélange de responsabilités — aucune trouvaille ne le
  cite, non retenu.
- **`analytics/aggregate.py`, `harvest/routes.py`** : cités en §2.1 pour
  mémoire (repères de taille) mais non analysés en détail, faute de
  trouvaille de duplication ou de patron divergent qui les justifie dans
  cette passe — un futur audit peut les reprendre, ce document ne les
  planifie pas.
- **`builder/widgets/mapSymbology.ts`** : découpage possible (§2.2) mais non
  priorisé — aucun bug documenté ne le motive, contrairement à `MapView.tsx`
  et `MapSymbologyEditor.tsx`.
- **Les 5 tests `@pytest.mark.qgis` eux-mêmes** : leur exécution réelle est
  un prérequis de l'étape 9, pas un livrable de ce plan — SP-15d/CLAUDE.md
  les tracke déjà comme seul point bloquant du jalon M14, sujet distinct.
- **Les 3 autres divergences déjà tranchées le 2026-09-01** (`h-9`,
  `Button` du kit vs `<button>` natif, principe d'`aria-expanded`) : la
  décision existe déjà, seule son **application mécanique** (§3.6) est
  reprise ici — ne pas rouvrir la décision elle-même.
- **La question `<main>`/`<aside>`/`<div>`** (déjà tranchée SP-30f) : citée
  en §4 pour mémoire, aucune action.
- **Toute nouvelle fonctionnalité** : cette spec ne touche à rien qui ajoute
  une capacité utilisateur — uniquement à la structure interne du code déjà
  livré.
- **La correction du reste des 43 trouvailles `confirme` non corrigées non
  retenues ici**
  (celles qui ne relèvent ni de duplication ni de patron divergent — ex.
  performance N+1 des balayages cron au-delà du patron partagé déjà couvert
  en §1.3/§3.3, index manquants sur `alert_evaluations`/`pipeline_runs`) :
  elles restent au backlog SP-42 (`docs/revue/2026-09-04-backlog.md`), hors
  du périmètre d'une spec de refactorisation structurelle.

---

## 8. Ce que ce document ne tranche pas

Le découpage précis fichier-par-fichier de l'étape 7 (quels domaines exacts,
quels noms de module) et de l'étape 8 (quel service partagé exact par
famille d'outil) est du ressort du plan SP-43 lui-même, pas de cette spec —
cohérent avec la contrainte du brief : produire un inventaire et un ordre,
pas un plan détaillé.
