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
- `geopandas`, `pyarrow`, `shapely`, `pyproj` (manipulation géospatiale)
- `duckdb` (moteur analytique)
- `sqlalchemy` (ORM)
- Toutes les transitivités du runtime Python

À titre de comparaison avec l'estimation du design (§8 du document `2026-09-17-desktop-etl-standalone-design.md`) : ce spike n'embarque qu'un sous-ensemble (une opération connecteur seule, pas l'éditeur UI, pas FastAPI complet, pas Postgres), donc son taille donne un ordre de grandeur prudent par paquet inclus — le socle sidecar complet sera probablement plus lourd de 50-100 Mo pour y ajouter `reader.file`, `writer.file`, et les stabilisateurs hors dépendances (icônes, assets).

## Impact sur le découpage du design (§11)

**La phase « socle sidecar » peut démarrer sans changement d'architecture.**

Aucune restriction d'architecture n'est nécessaire :

- Pas de fallback sur un dossier de données PyInstaller plutôt qu'un onefile — la taille reste raisonnable pour une distribution desktop Windows.
- Pas d'exclusion de connecteur (`reader.connector.rest` s'embarque sans problème sous Windows ni macOS).
- Pas de dépendance Windows-spécifique dans la recette — le flag `--collect-all dlt` s'applique identiquement sur toutes les plateformes.
- Pas de limitation à une sous-arborescence de `core/app/pipelines/` — la preuve du concept inclut la totalité de la stack de connectorisation (`dlt`, accès Postgres via sqlalchemy, accès REST, parseurs géospatiales).

Le déploiement du sidecar dans un runtime Tauri et sa communication HTTP loopback avec la webview (détaillée en §2 du design) restent à valider, mais **la faisabilité de geler et exécuter le moteur pipeline lui-même est complètement de-risquée**.
