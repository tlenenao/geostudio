# Desktop ETL — Spike 01 : freeze PyInstaller de `app.pipelines.connector_runtime` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prouver, avant d'écrire la moindre ligne de Tauri, que `app.pipelines.connector_runtime` (et tout son graphe d'imports transitif : `dlt`, `duckdb`, `sqlalchemy`, `geopandas`, `pyarrow`, `shapely`, `pyproj`) peut être gelé en binaire autonome par PyInstaller et exécuter un vrai `reader.connector.rest` de bout en bout — sur Linux (poste de dev) et sur Windows (CI), la cible réelle du produit.

**Architecture:** Un script Python autonome (`core/scripts/pipeline_sidecar_spike.py`) sert de point d'entrée PyInstaller ET de script exécutable directement. Il monte un serveur HTTP local, neutralise ponctuellement la garde d'egress (même patron que la fixture `_no_ssrf_guard` de `tests/test_pipeline_connector_runtime.py`, la garde bloquant légitimement le loopback), appelle `materialize_rest_connector` réel, et vérifie le résultat dans DuckDB. Le script tourne d'abord non gelé (contrôle), puis gelé en local (Linux), puis gelé sur un runner `windows-latest` (CI) — trois preuves croissantes.

**Tech Stack:** Python (uv, déjà en place dans `core/`), PyInstaller (nouvelle dépendance dev), DuckDB, dlt, GitHub Actions (`windows-latest`).

## Global Constraints

- Aucune dépendance QGIS/copyleft dans cette chaîne (design §1, §8) — ce spike ne touche que `connector_runtime.py` et son graphe, jamais `transform.qgis`.
- Le script doit tourner **offline** : serveur HTTP local + neutralisation ciblée de `assert_egress_allowed` (jamais un affaiblissement permanent de la garde — c'est un patch en mémoire, dans un process jetable, pas une modification de `core/app/pipelines/egress.py`).
- `session=None` passé à `materialize_rest_connector` n'est valide **que** parce que `params.secretName` reste `None` dans ce spike — `_resolve_secret` court-circuite avant tout accès DB (`connector_runtime.py:_resolve_secret`, `if secret_name is None: return None`). Ne pas généraliser ce court-circuit ailleurs : c'est le seam `SecretResolver` du design §3/§6 qui traite le cas général, hors périmètre de ce spike.
- Outillage CI identique à l'existant, versions exactes copiées de `.github/workflows/ci.yml` (piège n°3 du dépôt — vérifier contre la source réelle, pas la mémoire) : `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `defaults.run.working-directory: core`, `uv sync`.
- Ce spike est strictement additif : aucun fichier de production de `core/app/pipelines/` n'est modifié. Uniquement : un script neuf, une dépendance dev, un fichier de config PyInstaller, un workflow CI neuf, un `.gitignore` complété.

---

### Task 1: Ajouter PyInstaller comme dépendance dev du cœur

**Files:**
- Modify: `core/pyproject.toml` (bloc `[dependency-groups]` `dev = [...]`, après la dernière entrée `"pip>=26.2"`)

**Interfaces:**
- Consumes: rien.
- Produces: la commande `uv run pyinstaller` disponible dans l'environnement `core/`, utilisée par les Tasks 3 et 4.

- [ ] **Step 1: Ajouter la dépendance**

Dans `core/pyproject.toml`, dans le tableau `dev = [...]` du bloc `[dependency-groups]`, ajouter après la dernière entrée (`"pip>=26.2",`) :

```toml
    "pyinstaller>=6.11",  # Spike desktop-etl (docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md
    # §9) : outil de dev/build uniquement, jamais embarqué dans une image
    # core (même statut que ruff/mypy ci-dessus).
```

- [ ] **Step 2: Synchroniser l'environnement**

Run: `cd core && uv sync`
Expected: la sortie liste l'installation de `pyinstaller` (et ses dépendances `altgraph`, `pyinstaller-hooks-contrib`, etc.), se termine sans erreur.

- [ ] **Step 3: Vérifier que le binaire est disponible**

Run: `cd core && uv run pyinstaller --version`
Expected: une chaîne de version (ex. `6.11.1`), code de sortie 0.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/pyproject.toml core/uv.lock
git commit -m "build(core): ajoute pyinstaller en dépendance dev (spike desktop-etl)"
```

---

### Task 2: Script de contrôle — `reader.connector.rest` réel, non gelé

**Files:**
- Create: `core/scripts/pipeline_sidecar_spike.py`

**Interfaces:**
- Consumes: `app.pipelines.connector_runtime.materialize_rest_connector(conn, *, session, tenant_id, node_id, params, view_name) -> None` (signature exacte, `core/app/pipelines/connector_runtime.py:217`) ; `app.pipelines.ops.schemas.ReaderConnectorRestParams(baseUrl: str, path: str = "", ...)` ; `app.pipelines.egress.assert_egress_allowed(url: str) -> None` (module-level, monkeypatchable).
- Produces: un script exécutable en deux modes (interprété via `uv run python`, ou gelé via PyInstaller en Task 3) qui écrit `OK: <n> rows materialized via reader.connector.rest` sur stdout et sort avec le code 0 en cas de succès, ou un message `FAIL: ...` sur stderr avec le code 1 sinon. Consommé tel quel par la Task 3 (freeze) et la Task 4 (CI Windows).

- [ ] **Step 1: Écrire le script**

Créer `core/scripts/pipeline_sidecar_spike.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Spike PyInstaller (design docs/superpowers/specs/2026-09-17-desktop-etl-
standalone-design.md §9) : fige app.pipelines.connector_runtime — et tout
son graphe d'imports transitif (dlt, duckdb, sqlalchemy, geopandas, pyarrow,
shapely, pyproj) — en binaire autonome, puis exécute un reader.connector.rest
réel contre un serveur HTTP local (aucun réseau externe requis) pour confirmer
que le freeze n'a rien perdu.

Sert de point d'entrée PyInstaller (Task 3 du plan) ET de script exécutable
directement pour la vérification "non gelé" de contrôle (Task 2)."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb

from app.pipelines import egress as pipelines_egress
from app.pipelines.connector_runtime import materialize_rest_connector
from app.pipelines.ops.schemas import ReaderConnectorRestParams

_RECORDS = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}, {"id": 3, "name": "gamma"}]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(_RECORDS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:  # silence stderr par défaut
        pass


def main() -> int:
    # Même rationale que la fixture `_no_ssrf_guard` de
    # tests/test_pipeline_connector_runtime.py : la garde bloque
    # légitimement 127.0.0.1 (loopback) — neutralisation ponctuelle en
    # mémoire, dans ce process jetable, pour taper un serveur local offline.
    pipelines_egress.assert_egress_allowed = lambda url: None

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = duckdb.connect(":memory:")
        params = ReaderConnectorRestParams(baseUrl=f"http://127.0.0.1:{port}/", path="items")
        materialize_rest_connector(
            conn,
            # secretName reste None (défaut) => _resolve_secret court-circuite
            # avant tout accès DB : session=None est donc valide ICI
            # uniquement (cf. Global Constraints du plan).
            session=None,  # type: ignore[arg-type]
            tenant_id="spike",
            node_id="n1",
            params=params,
            view_name="v1",
        )
        count = conn.execute("SELECT count(*) FROM v1").fetchone()[0]
    finally:
        server.shutdown()

    expected = len(_RECORDS)
    if count != expected:
        print(f"FAIL: expected {expected} rows, got {count}", file=sys.stderr)
        return 1
    print(f"OK: {count} rows materialized via reader.connector.rest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Exécuter en contrôle (non gelé)**

Run: `cd core && uv run python scripts/pipeline_sidecar_spike.py`
Expected: stdout `OK: 3 rows materialized via reader.connector.rest`, code de sortie 0.

- [ ] **Step 3: Vérifier le cas d'échec (falsification, piège n°10 du dépôt)**

Modifier temporairement `_RECORDS` pour n'avoir que 2 éléments, relancer, confirmer `FAIL: expected 2 rows, got 2` ne s'affiche PAS et que le test échoue correctement si on force un décalage — concrètement : changer la ligne de comparaison en dur `if count != expected + 1:` un instant, relancer, confirmer que ça imprime bien `FAIL: expected 4 rows, got 3` sur stderr avec code 1, puis **annuler ce changement de test avant de continuer**. Ceci confirme que le script détecte réellement un désaccord, pas seulement qu'il « passe toujours ».

Run: `cd core && uv run python scripts/pipeline_sidecar_spike.py; echo "exit=$?"`
Expected (après le changement temporaire) : `FAIL: expected 4 rows, got 3` sur stderr, `exit=1`. Revenir ensuite au code du Step 1 tel quel.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/scripts/pipeline_sidecar_spike.py
git commit -m "test(core): script de contrôle spike PyInstaller — reader.connector.rest réel"
```

---

### Task 3: Geler avec PyInstaller et faire tourner le binaire (Linux, poste de dev)

**Files:**
- Create: `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt` (une option par ligne, la recette de freeze qui a fonctionné)
- Modify: `core/.gitignore` (ajouter `dist/`, `build/`, `*.spec`)

**Interfaces:**
- Consumes: `core/scripts/pipeline_sidecar_spike.py` (Task 2), `uv run pyinstaller` (Task 1).
- Produces: `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt` — liste d'arguments PyInstaller réutilisée telle quelle par la Task 4 (CI Windows) et par le futur socle sidecar (§11 du design, phase « socle sidecar »).

- [ ] **Step 1: Premier essai de freeze, sans option spéciale**

Run: `cd core && uv run pyinstaller --onefile --name pipeline-sidecar-spike --paths . scripts/pipeline_sidecar_spike.py`
Expected: un binaire produit à `core/dist/pipeline-sidecar-spike`. Le log PyInstaller peut afficher des `WARNING: Hidden import ... not found` — les noter mais ne pas s'arrêter dessus tant que le Step 2 n'a pas confirmé un échec réel à l'exécution.

- [ ] **Step 2: Exécuter le binaire gelé**

Run: `cd core && ./dist/pipeline-sidecar-spike`
Expected (cas favorable) : `OK: 3 rows materialized via reader.connector.rest`, code de sortie 0 — identique au Step 2 de la Task 2.

- [ ] **Step 3: Boucle de correction si le Step 2 échoue**

Si le binaire lève une `ModuleNotFoundError`, une erreur de résolution de plugin `dlt` (recherche de destination via `importlib.metadata`), ou une erreur `PackageNotFoundError` : lire le message d'erreur exact, identifier le module/paquet manquant, ajouter l'option PyInstaller correspondante à la commande du Step 1 :
  - `ModuleNotFoundError: No module named 'X'` → ajouter `--hidden-import X`
  - erreur de métadonnées de paquet (`importlib.metadata.PackageNotFoundError`) → ajouter `--copy-metadata X`
  - erreur de découverte de plugin/sous-module d'un paquet à l'architecture dynamique (ex. `dlt.destinations.*`) → ajouter `--collect-all X`

Relancer le Step 1 (commande augmentée) puis le Step 2, jusqu'à obtenir `OK: 3 rows...`. Documenter chaque option ajoutée et pourquoi (message d'erreur exact qui l'a motivée) — cette trace va dans le rapport de la Task 5. Si après 8 itérations le binaire échoue toujours pour une raison non résolue par `--hidden-import`/`--copy-metadata`/`--collect-all` (ex. une dépendance C native qui ne se gèle pas du tout), **arrêter la boucle** : c'est un résultat de spike légitime (no-go ou go-avec-réserve), pas un échec de tâche — le documenter tel quel dans la Task 5.

- [ ] **Step 4: Sauvegarder la recette qui fonctionne**

Une fois le Step 2 vert, créer `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt` avec, une option par ligne, exactement les arguments qui ont fait passer le Step 2 (hors `--onefile --name ... --paths . scripts/pipeline_sidecar_spike.py`, qui restent fixes). Exemple si aucune option supplémentaire n'a été nécessaire :

```
# Aucune option supplémentaire nécessaire — le freeze naïf
# (--onefile --name pipeline-sidecar-spike --paths . scripts/pipeline_sidecar_spike.py)
# a suffi sur Linux (vérifié 2026-09-17).
```

(Remplacer ce contenu par la liste réelle d'options si le Step 3 en a ajouté.)

- [ ] **Step 5: Ignorer les artefacts de build**

Dans `core/.gitignore`, ajouter à la fin :

```
dist/
build/
*.spec
```

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt core/.gitignore
git commit -m "build(core): recette PyInstaller validée (Linux) pour le spike sidecar desktop-etl"
```

---

### Task 4: Preuve sur la cible réelle — freeze + exécution sur `windows-latest` (CI)

**Files:**
- Create: `.github/workflows/desktop-etl-spike.yml`

**Interfaces:**
- Consumes: `core/scripts/pipeline_sidecar_spike.py` (Task 2), `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt` (Task 3).
- Produces: un run GitHub Actions vert sur `windows-latest`, preuve que le freeze fonctionne aussi sur la plateforme cible du produit (pas seulement sur le poste de dev Linux).

- [ ] **Step 1: Écrire le workflow**

Créer `.github/workflows/desktop-etl-spike.yml` :

```yaml
name: desktop-etl spike (PyInstaller freeze)

on:
  workflow_dispatch: {}
  push:
    paths:
      - "core/scripts/pipeline_sidecar_spike.py"
      - "core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt"
      - "core/app/pipelines/**"
      - ".github/workflows/desktop-etl-spike.yml"

jobs:
  freeze-windows:
    runs-on: windows-latest
    defaults:
      run:
        working-directory: core
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync
      - name: Script de contrôle (non gelé)
        run: uv run python scripts/pipeline_sidecar_spike.py
      - name: Freeze PyInstaller
        shell: bash
        run: |
          extra_args=$(grep -v '^#' scripts/pipeline_sidecar_spike.pyinstaller-args.txt | tr '\n' ' ')
          uv run pyinstaller --onefile --name pipeline-sidecar-spike --paths . $extra_args scripts/pipeline_sidecar_spike.py
      - name: Exécuter le binaire gelé
        run: .\dist\pipeline-sidecar-spike.exe
```

- [ ] **Step 2: Déclencher le workflow et observer le run**

Run: `cd /home/lenen/projets/geostudio && git add .github/workflows/desktop-etl-spike.yml && git commit -m "ci(desktop-etl): job windows-latest — spike freeze PyInstaller" && git push origin dev`

Puis : `gh workflow run "desktop-etl spike (PyInstaller freeze)" --ref dev` et `gh run watch $(gh run list --workflow="desktop-etl-spike.yml" --limit 1 --json databaseId --jq '.[0].databaseId')`

Expected: le job `freeze-windows` se termine en succès (✓), le log de l'étape « Exécuter le binaire gelé » affiche `OK: 3 rows materialized via reader.connector.rest`.

- [ ] **Step 3: Si le job échoue sur Windows mais passait sur Linux**

Revenir à la Task 3 Step 3 avec le message d'erreur du log Windows (souvent différent de Linux : DLL manquantes, chemins avec antislash, extensions binaires spécifiques à la plateforme comme les wheels `psycopg`/`pyarrow`). Répéter la boucle hidden-import/copy-metadata/collect-all, mettre à jour `pipeline_sidecar_spike.pyinstaller-args.txt`, repousser, reboucler sur ce Step 2 jusqu'à un run vert ou un no-go documenté (Task 5).

---

### Task 5: Rapport de spike — go/no-go pour la suite du design

**Files:**
- Create: `docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md`

**Interfaces:**
- Consumes: résultats des Tasks 3 et 4 (recette PyInstaller, éventuels blocages, taille du binaire observée).
- Produces: le document qui débloque (ou non) la phase « socle sidecar » du §11 du design ; référencé par le prochain plan de ce chantier.

- [ ] **Step 1: Mesurer la taille du binaire gelé**

Run: `cd core && ls -lh dist/pipeline-sidecar-spike` (Linux) — noter la taille en Mo pour comparaison avec l'estimation du design (§8, 150-300 Mo pour le sidecar complet ; ce spike n'embarque qu'un sous-ensemble donc sera plus petit, mais donne un ordre de grandeur par Mo/dépendance).

- [ ] **Step 2: Écrire le rapport**

Créer `docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md` :

```markdown
# Desktop ETL — Spike 01 : résultats du freeze PyInstaller

> Date : 2026-09-17 (à mettre à jour à la date réelle d'exécution) · Suite de
> [`2026-09-17-desktop-etl-standalone-design.md`](2026-09-17-desktop-etl-standalone-design.md)
> §9. Plan exécuté :
> [`2026-09-17-desktop-etl-spike-01-pyinstaller-freeze.md`](../plans/2026-09-17-desktop-etl-spike-01-pyinstaller-freeze.md).

## Verdict

[GO / GO AVEC RÉSERVE / NO-GO] — remplacer par le résultat réel, ne pas
laisser ce texte tel quel.

## Ce qui a été prouvé

- Linux (poste de dev) : [détail du résultat Task 3]
- Windows (`windows-latest`, CI) : [détail du résultat Task 4, lien vers le
  run GitHub Actions]

## Recette PyInstaller retenue

[Contenu de `core/scripts/pipeline_sidecar_spike.pyinstaller-args.txt`, avec
pour chaque option ajoutée le message d'erreur exact qui l'a motivée.]

## Taille observée

[Taille du binaire gelé sur chaque OS.]

## Impact sur le découpage du design (§11)

[Si GO : la phase « socle sidecar » peut démarrer sans changement
d'architecture. Si GO AVEC RÉSERVE ou NO-GO : quel ajustement ça implique
pour §2/§3 du design — ex. passer par un dossier de données PyInstaller
plutôt qu'un onefile, exclure tel connecteur de la v1, etc.]
```

- [ ] **Step 3: Remplir le rapport avec les résultats réels**

Remplacer chaque section entre crochets par les résultats effectivement obtenus aux Tasks 3 et 4 — ne jamais committer ce fichier avec un texte de gabarit non rempli (piège « placeholder »).

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md
git commit -m "docs(superpowers): résultats spike 01 — freeze PyInstaller desktop-etl"
```
