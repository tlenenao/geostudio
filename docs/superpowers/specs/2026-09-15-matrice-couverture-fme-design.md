# Matrice de couverture FME→GeoStudio — design

## Contexte et motivation

Décision produit actée le 2026-09-15 (Q2 du comparatif, `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` §9 point 7, reflétée dans `CLAUDE.md`) : GeoStudio vise un produit horizontal, mature et personnalisable pour des collectivités/structures de taille variable — pas un déploiement nommé unique. Conséquence directe sur `GAP-29` (`docs/revue/2026-09-04-analyse-gaps.md`, écart de couverture face aux 450+ connecteurs FME, jusqu'ici « non fermable par du code ») : la posture retenue est de **viser la parité de couverture comme différenciateur produit**.

Une proposition externe (ChatGPT, relayée par Tanguy) recommandait de ne pas viser « QGIS comme remplacement de FME », mais plutôt DuckDB comme moteur relationnel/spatial par défaut + un catalogue d'opérations GeoStudio + des moteurs spécialisés (GDAL/PDAL/OTB/Rust) derrière une interface d'opération unique (`OperationContract`), et de produire d'abord une matrice de couverture FME→GeoStudio pour prioriser ce travail plutôt que de deviner.

Ce document spécifie **uniquement le premier sous-projet** de ce chantier plus large : la matrice de couverture elle-même. Les autres sous-projets identifiés (`OperationContract`, premier moteur natif additionnel, IPC GPKG→Arrow/GeoParquet, moteurs suivants) sont explicitement **hors périmètre** et attendent les résultats de cette matrice pour être priorisés et spécifiés à leur tour.

## Objectif

Produire un inventaire structuré, rejouable et vérifiable mécaniquement sur son seul point factuel (« GeoStudio couvre-t-il déjà ce besoin aujourd'hui ? ») des transformers FME, avec pour chacun : catégorie FME, équivalent GeoStudio proposé ou existant, moteur candidat, licence de ce moteur, statut de couverture, fréquence d'usage estimée.

## Non-objectifs (hors périmètre de ce sous-projet)

- Aucune modification de `core/app/pipelines/` (pas de nouvel op, pas d'`OperationContract`, pas de nouveau moteur intégré).
- Aucune décision de priorisation des sous-projets suivants n'est prise ici — elle attend les résultats de la matrice.
- Le remplissage réel des lignes (recherche, catégorisation, jugement moteur/licence pour chaque transformer) est un travail d'**exécution** du plan qui suivra ce design, pas énuméré dans ce document.
- Aucune porte CI n'est ajoutée : ce livrable est un document d'analyse stratégique, pas une surface produit.

## Source de la liste des transformers FME

Recherche web sur la documentation publique de Safe Software (galerie de transformers, `safe.com/transformers` et pages équivalentes) — aucune licence FME requise, contenu de documentation publique. Limite assumée : la couverture dépend de ce que cette documentation publique expose et de sa fraîcheur ; ce n'est pas un export exhaustif garanti à 100 % du catalogue FME réel.

## Politique de licence pour les moteurs candidats

**Filtre strict MIT/BSD/Apache/EDL uniquement.** Un outil dont la seule implémentation open-source connue est GPL (ou plus restrictif) est marqué `license_blocked` — **y compris s'il serait techniquement isolable en sidecar séparé** comme QGIS aujourd'hui (arbitrage A39). Ce patron de sidecar isolé n'est **pas** reconduit pour de nouveaux moteurs GPL : c'est une exception historique, pas une politique répétable.

Le sidecar QGIS existant (50 algorithmes, GPL) est traité comme une **exception historique figée** :
- il continue d'exister tel quel, aucun changement de ce sous-projet ne le touche ;
- mais **aucun nouveau transformer FME n'est routé vers lui** dans cette matrice — tout nouveau besoin est catégorisé vers un moteur MIT/BSD/Apache/EDL ou marqué `license_blocked`/`unknown`/`out_of_scope`.

## Schéma JSONL

Fichier : `docs/revue/matrice-couverture-fme.jsonl`, une ligne JSON par transformer FME.

```json
{
  "fme_transformer": "Reprojector",
  "fme_category": "Geometry",
  "fme_description": "Reprojects features to a different coordinate system",
  "geostudio_equivalent": "transform.reproject",
  "engine": "duckdb",
  "engine_license": "MIT",
  "coverage_status": "implemented",
  "usage_frequency": "courant",
  "notes": ""
}
```

Champs :
- `fme_transformer` (str) : nom exact du transformer FME.
- `fme_category` (str) : catégorie telle que documentée par Safe Software (ex. `"Geometry"`, `"Attribute"`, `"Filtering & Routing"`, `"Readers/Writers"`).
- `fme_description` (str) : description courte, reprise/reformulée depuis la doc publique.
- `geostudio_equivalent` (str | null) : nom d'op réel si `coverage_status == "implemented"` (doit exister dans `ops_catalog()` ou `QGIS_ALGORITHMS`, vérifié mécaniquement) ; nom **proposé** (pas encore un op réel) si le statut est `planned_*` ; `null` si `out_of_scope`/`license_blocked`/`unknown`.
- `engine` (enum) : `"duckdb" | "gdal" | "pdal" | "otb" | "rust:<crate>" | "qgis" | "n/a"`.
- `engine_license` (str) : licence du moteur proposé (ex. `"MIT"`, `"BSD-3-Clause"`, `"Apache-2.0"`, `"GPL-3.0"` pour documenter un `license_blocked`).
- `coverage_status` (enum) : voir taxonomie ci-dessous.
- `usage_frequency` (enum) : `"courant" | "niche" | "inconnu"` — signal faible tiré de la mise en avant du transformer dans la doc FME elle-même, sert uniquement à prioriser un futur sous-projet, jamais une mesure fiable d'usage réel.
- `notes` (str) : libre, peut rester vide.

Pour les statuts `out_of_scope`/`unknown`/`license_blocked`/`capability_removed` sans moteur candidat clair : `engine: "n/a"`, `engine_license: ""` (chaîne vide, pas `null`) — le script de vérification n'exige rien sur ces deux champs quand `coverage_status` ∈ `{"out_of_scope", "unknown"}` ; pour `license_blocked`/`capability_removed`, `engine_license` doit documenter la licence bloquante (ou l'ex-licence retirée) trouvée (ex. `"GPL-3.0"`, `"GPL-2.0-or-later (QGIS, retiré)"`), jamais rester vide.

## Taxonomie `coverage_status`

| Statut | Sens |
|---|---|
| `implemented` | Un op GeoStudio existe déjà et couvre ce besoin — vérifié mécaniquement contre `ops_catalog()`/`QGIS_ALGORITHMS`, jamais déclaratif |
| `planned_duckdb` | Pas encore implémenté, couvrable par une op SQL/spatiale DuckDB à écrire |
| `planned_gdal` | Couvrable via un moteur GDAL/OGR pas encore intégré |
| `planned_pdal` | Couvrable via un moteur PDAL (nuages de points) pas encore intégré |
| `planned_otb` | Couvrable via un moteur OTB (télédétection raster) pas encore intégré |
| `planned_rust` | Couvrable via une crate Rust dédiée (`engine: "rust:<crate>"`) pas encore intégrée |
| `qgis_frozen` | Déjà couvert par l'allowlist QGIS gelée existante — jamais attribué à un nouveau besoin, uniquement pour documenter l'existant |
| `license_blocked` | Seule implémentation open-source connue = GPL ou plus restrictif, aucune alternative MIT/BSD/Apache/EDL connue |
| `capability_removed` | Une solution existait (sidecar QGIS) et a été retirée pour raison de licence (GPL-2.0-or-later, cf. retrait du sidecar) — distinct d'`unknown` : la recherche a abouti, la capacité a existé, elle n'existe plus par choix explicite |
| `out_of_scope` | Hors périmètre produit GeoStudio (EDI, bases legacy propriétaires, notions FME sans rapport avec la géospatiale) |
| `unknown` | Pas encore catégorisé (recherche insuffisante à date) |

## Script de vérification — `core/scripts/fme_coverage_cli.py`

Patron similaire à `core/scripts/feature_health_cli.py` (SP-61), en **beaucoup plus simple** : pas de scoring, pas de notion de santé, pas de porte CI.

**Ce qu'il vérifie mécaniquement** (seul point factuel rejouable depuis le dépôt) :
- Toute ligne `coverage_status: "implemented"` avec `engine: "duckdb"` → `geostudio_equivalent` doit être une clé réelle de `ops_catalog()` (`app.pipelines.ops.schemas`). Sinon : erreur bloquante au `--check`.
- Toute ligne `engine: "qgis"` (donc normalement `coverage_status: "qgis_frozen"`) → `geostudio_equivalent` doit être une clé réelle de `QGIS_ALGORITHMS` (`app.pipelines.ops.qgis_algorithms`).
- Toute ligne `coverage_status: "implemented"` avec `engine` ∈ `{"gdal", "pdal", "otb"}` ou `engine` commençant par `"rust:"` → **erreur** : aucun de ces moteurs n'existe encore dans `core/app/pipelines/` à la date de ce design ; empêche de déclarer une couverture par anticipation avant qu'un sous-projet moteur correspondant n'ait réellement livré.
- Tout le reste (`fme_category`, `fme_description`, `usage_frequency`, `notes`, la licence elle-même) n'est **jamais** vérifié mécaniquement — jugement humain non rejouable depuis le dépôt.

**Ce qu'il génère** : `--write` régénère `docs/revue/matrice-couverture-fme.md` (table complète + résumé de comptage par `coverage_status` et par `engine`) depuis le JSONL — source unique, comme `bilan-fonctionnalites.{html,md}`.

**Ce qu'il ne fait pas** : `--check` existe mais n'est appelé dans aucun job de `ci.yml` — ce n'est pas une surface produit, une erreur ici ne casse rien pour un utilisateur final, donc pas de justification à bloquer une PR dessus.

**Gotcha connu à documenter dans le script lui-même** (docstring, pas seulement `CLAUDE.md`) : la commande nue échouera en `ModuleNotFoundError` sans `PYTHONPATH=.` — même piège déjà vécu sur `feature_health_cli.py`/`export_openapi.py`, à ne pas répéter une 3e fois sans avertissement inline.

Invocation : `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --check` (ou `--write`).

## Emplacement, nommage, processus de mise à jour

- `docs/revue/matrice-couverture-fme.jsonl` (source) + `docs/revue/matrice-couverture-fme.md` (rendu généré) — **pas de date dans le nom** : document vivant, régénéré à chaque évolution (même patron que `bilan-fonctionnalites.{jsonl,html,md}` de SP-61), jamais un instantané figé façon `2026-09-04-matrice-fonctionnalites.md` (qui a explicitement dérivé de la réalité pendant des mois, piège n°12).
- Mise à jour : quand un nouvel op/moteur est livré dans `core/app/pipelines/`, ou quand la recherche FME progresse, on édite le JSONL et on relance `--write`. Si un futur SP touche ce périmètre, l'ajouter au réflexe de clôture de SP dans `CLAUDE.md` (comme `feature_health_cli.py --write` déjà obligatoire).

## Risques et limites assumés

- La documentation publique FME peut ne pas exposer une liste unique et exhaustive des ~500 transformers en un seul endroit — le remplissage pourra nécessiter plusieurs passes de recherche par catégorie, sans garantie d'exhaustivité totale à la première itération.
- `usage_frequency` est un signal faible (déduit de la mise en avant éditoriale de Safe Software), jamais une mesure d'usage réel — à ne pas sur-interpréter lors de la priorisation des sous-projets suivants.
- Le script de vérification ne peut rien garantir sur les colonnes de jugement humain (catégorie, description, moteur proposé, licence) — seule la colonne « déjà implémenté aujourd'hui » est mécaniquement fiable.
