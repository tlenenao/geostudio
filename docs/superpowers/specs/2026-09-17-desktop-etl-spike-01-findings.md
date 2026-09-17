# Desktop ETL — Spike 01 : résultats du freeze PyInstaller

> Date : 2026-09-17 · Suite de
> [`2026-09-17-desktop-etl-standalone-design.md`](2026-09-17-desktop-etl-standalone-design.md)
> §9. Plan exécuté :
> [`2026-09-17-desktop-etl-spike-01-pyinstaller-freeze.md`](../plans/2026-09-17-desktop-etl-spike-01-pyinstaller-freeze.md).

## Verdict

**GO** — le freeze PyInstaller fonctionne bout-en-bout sur les deux plateformes cibles (Linux poste de dev, Windows CI) sans changement d'architecture. Une seule itération de correction a été nécessaire sur Linux (flag `--collect-all dlt`) ; ce même flag a suffi sans modification sur Windows. La recette est reproductible et stable.

## Ce qui a été prouvé

### Linux (poste de dev) — Task 3

Deux itérations d'essai-erreur :

1. **Freeze naïf** (`--onefile --name pipeline-sidecar-spike --paths . scripts/pipeline_sidecar_spike.py`) : succès au freeze, **échec à l'exécution**.

   Erreur observée :
   ```
   dlt/common/configuration/plugins.py:89: UserWarning: Plugin dlt from dlt failed to load: No module named 'dlt.__plugins__'
   ...
   File "dlt/common/configuration/specs/pluggable_run_context.py", line 255, in _plug
   AssertionError: plug_run_context hook returned None
   ```

   **Diagnostic** : `dlt` déclare son propre plugin interne (`dlt.__plugins__`) via un entry point setuptools chargé au runtime par `importlib.metadata` + `pluggy`, jamais par un `import` statique. PyInstaller ne peut pas découvrir par analyse de graphe que ce module doit être embarqué. Résultat : à l'exécution du binaire, le plugin n'est pas trouvé et `PluggableRunContext._plug()` lève `AssertionError`.

2. **Avec `--collect-all dlt`** : succès au freeze et **succès à l'exécution**, stable sur 4 exécutions consécutives.

   Sortie du binaire exécuté :
   ```
   OK: 3 rows materialized via reader.connector.rest
   ```
   Code de sortie : 0.

### Windows (`windows-latest`, CI) — Task 4

Run vert : https://github.com/tlenenao/geostudio/actions/runs/35266807922

Première itération (run initial) : **échec pré-PyInstaller** — l'étape « Script de contrôle (non gelé) » levait `ModuleNotFoundError: No module named 'app'`. Diagnostic : le YAML du brief omettait la variable d'environnement `PYTHONPATH=.` (conventionnelle pour tous les scripts du dépôt `core/scripts/`, documentée dans `CLAUDE.md`). Reproduit et corrigé localement sur Linux avant itération Windows. Correction appliquée sans re-demander.

Deuxième itération (run vert) : **aucune modification de la recette PyInstaller requise**. Le flag `--collect-all dlt` validé sur Linux a fonctionné du premier coup sur `windows-latest` sans :
- DLL manquante
- Problème de wheel native (psycopg[binary], pyarrow)
- Chemin ou séparateur cassé

Sortie du binaire gelé sur `windows-latest` :
```
OK: 3 rows materialized via reader.connector.rest
```

Durée totale du job : 3m4s. Les 7 étapes du job (checkout, setup uv, sync, script de contrôle, freeze, exécution du binaire, post) toutes vertes.

## Recette PyInstaller retenue

Fichier : `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt`

```
--collect-all dlt
```

**Commande complète** :
```bash
cd core && uv run pyinstaller --onefile --name pipeline-sidecar-spike \
  --paths . --collect-all dlt scripts/pipeline_sidecar_spike.py
```

**Justification du flag** :

Le freeze naïf échoue avec :
```
dlt/common/configuration/plugins.py:89: UserWarning: Plugin dlt from dlt failed to load: No module named 'dlt.__plugins__'
...
AssertionError: plug_run_context hook returned None
```

`dlt` embarque une architecture de plugins basée sur setuptools entry points (groupe `"dlt"`, nom `"dlt"`, valeur `"dlt.__plugins__"` — vérifiable via `importlib.metadata.distribution("dlt").entry_points`). Le chargement se fait au runtime via `importlib.metadata` + `pluggy`, jamais par un `import` statique du code Python. PyInstaller, qui analyse le graphe d'imports du code source, ne peut donc pas découvrir automatiquement que `dlt.__plugins__` (et plus généralement les sous-modules de `dlt` chargés dynamiquement) doivent être embarqués dans le binaire. `--collect-all dlt` force l'embarquement de tout le paquet `dlt` (code + métadonnées de distribution setuptools), ce qui restaure la découverte du plugin à l'exécution du binaire.

## Taille observée

- **Linux** : 161 Mo (`-rwxr-xr-x 1 lenen lenen 161M Sep 17 21:38 dist/pipeline-sidecar-spike`)
- **Windows** : non mesurée côté CI (le run GitHub Actions ne sortait pas la taille de l'artefact ; le binaire `.exe` a été exécuté avec succès mais non archivé pour comparaison)

La taille de 161 Mo sur Linux est attendue pour un onefile embarquant :
- `dlt` + ses dépendances (data integration)
- `pyarrow`, `pandas`, `numpy` (tirés transitivement par `dlt`/`duckdb`)
- `duckdb` (moteur analytique)
- `sqlalchemy` (ORM)
- Toutes les transitivités du runtime Python

À titre de comparaison avec l'estimation du design (§8 du document `2026-09-17-desktop-etl-standalone-design.md`) : ce spike n'embarque qu'un sous-ensemble (une opération connecteur seule, pas l'éditeur UI, pas FastAPI complet, pas Postgres), donc sa taille donne un ordre de grandeur prudent par paquet inclus — le socle sidecar complet sera probablement plus lourd de 50-100 Mo pour y ajouter `reader.file`, `writer.file`, et les stabilisateurs hors dépendances (icônes, assets).

## Impact sur le découpage du design (§11)

**La phase « socle sidecar » peut démarrer sans changement d'architecture.**

Aucune restriction d'architecture n'est nécessaire :

- Pas de fallback sur un dossier de données PyInstaller plutôt qu'un onefile — la taille reste raisonnable pour une distribution desktop Windows.
- Pas de dépendance Windows-spécifique dans la recette — le flag `--collect-all dlt` s'applique identiquement sur toutes les plateformes. Windows a été prouvé (CI `windows-latest`, run vert) ; macOS n'a jamais été tenté et reste hors périmètre v1 (le design, §8, fixe « Cible v1 : Windows uniquement »).
- Ce qui a été prouvé porte sur `dlt` + `duckdb` + `sqlalchemy` + le chemin `reader.connector.rest`, avec `pyarrow`/`pandas`/`numpy` tirés transitivement (vérifié dans `Analysis-00.toc` du build : `pyarrow` 1383 modules, `pandas` 692, `numpy` 397). **`geopandas`, `shapely` et `pyproj` n'ont jamais fait partie du graphe gelé** — `Analysis-00.toc` les montre à 0 occurrence (le seul texte « pyproj » du dépôt est dans `app/pipelines/egress.py`, et c'est le mot « pyproject.toml », pas le paquet). Ces trois paquets vivent sous `app/ingestion/parsers.py` et `app/cdc/{parquet_writer,compaction}.py`, jamais importés par `app/pipelines/connector_runtime.py`. C'est un **risque résiduel non prouvé** : `pyproj` a besoin de son répertoire de données PROJ (`proj.db`, typiquement `--collect-data pyproj`) et `shapely` de sa bibliothèque native GEOS, particulièrement fragile sous Windows — ce point restera à prouver quand la phase suivante ajoutera `reader.file`/le support de formats géospatiaux.

Le déploiement du sidecar dans un runtime Tauri et sa communication HTTP loopback avec la webview (détaillée en §2 du design) restent à valider. La faisabilité de geler et exécuter le moteur pipeline pour la stack déjà testée (`dlt`/`duckdb`/`sqlalchemy`/REST) est de-risquée ; le freeze de la manipulation géospatiale (`geopandas`/`shapely`/`pyproj`) ne l'est pas encore.
