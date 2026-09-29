# SPDX-License-Identifier: Apache-2.0
"""Rend un prompt par agent d'audit depuis agents.yml + prompt-template.md
(spec 2026-09-29 §4).

    PYTHONPATH=. uv run python scripts/audit_prompts.py render \
        --out ../docs/revue/audit-2026-09-29/prompts
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO / "docs/revue/audit-2026-09-29"

ENV_BY_MODE = {
    "mock": (
        "Stack réelle, **auth mock** : shell `http://localhost:8300`, cœur "
        "`http://localhost:8200`. Un seul utilisateur implicite `mockuser` (admin). Aucun mock "
        "réseau : les tests Playwright ciblent la vraie stack. Chromium se lance avec "
        "`--disable-web-security` car le shell (:8300) appelle le cœur (:8200) cross-origin sans "
        "CORS. L'orchestrateur a déjà fait "
        "`scripts/audit/stack-reset.sh reset --auth mock` ; ne le relance pas."
    ),
    "oidc": (
        "Stack réelle, **auth OIDC (Keycloak)** : shell `http://localhost:8300`, cœur "
        "`http://localhost:8200`. Personas (mot de passe `Demo1234!`) : `audit-admin`, "
        "`audit-creator`, `audit-analyst`, `audit-reader` (fixtures : "
        "`shell/e2e/journeys/_fixtures/env.ts`, `loginOidc(page, persona)`). Chromium se lance "
        "avec `--disable-web-security` car le shell (:8300) appelle le cœur (:8200) cross-origin "
        "sans CORS. L'orchestrateur a déjà fait "
        "`scripts/audit/stack-reset.sh reset --auth oidc` ; ne le relance pas."
    ),
    "none": (
        "Aucune stack à piloter : tu lis le dépôt (`/home/lenen/projets/geostudio`) et tu peux "
        "lancer des commandes de lecture ou de test unitaire locales (`uv run pytest <fichier>`, "
        "`npx vitest run <fichier>`, `git log`, `grep`). Pas de `docker`, pas d'écriture hors de "
        "ton dossier."
    ),
}

PLAYWRIGHT_RULES = """## Tests Playwright (obligatoires pour ton groupe)

- Écris tes specs dans `shell/e2e/journeys/{id}/*.spec.ts`. Lance-les avec
  `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/{id}` (1 worker :
  les agents partagent le tenant `default`).
- Budget : jusqu'à {budget_tests} tests, sans limite sur le nombre de findings. Couvre le nominal,
  les erreurs, les états vides, les cas limites et les droits (rôle non autorisé).
- Sort des tests : un test qui **passe** reste tel quel (suite de régression). Un test qui
  **révèle un bug** est marqué `test.fixme(...)` avec l'id du finding dans son titre
  (`test.fixme("{id}-007 : …", …)`) et un commentaire renvoyant au finding. Un test
  instable est tagué `@audit-flaky`.
- Utilise `stamp("{id}")` (`_fixtures/env.ts`) pour nommer ce que tu crées. Ne nettoie pas :
  l'orchestrateur reset la base.
- Mémoire limitée (WSL2 ~12 Go) : un seul navigateur à la fois, ferme les pages inutiles.
- Le `repro` d'un finding vérifié est la commande Playwright exacte + le titre du test."""

CODE_RULES = """## Audit de code (ton groupe)

- Chaque finding cite les lignes exactes du code concerné (`locations[]`) après relecture
  directe du fichier ; vérifie un comportement par un test ou une commande dès que possible
  (`evidence.type = command-output`), sinon `code-read` avec `confidence: probable`.
- Pas de test Playwright pour ce groupe."""

BENCH_RULES = """## Benchmark produit (ton groupe)

- Pas de Playwright. Pour chaque écart, un finding `kind: "feature"` ou `"gap"` avec
  `evidence.type = "doc-read"` (URL ou chemin) et `confidence` `probable` ou `hypothesis`.
- Respecte le positionnement produit horizontal et les 40 arbitrages
  (`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §8)."""

VERIFIER_RULES = """## Vérification (ton groupe)

- Entrée : les `findings.jsonl` des agents dont la sévérité est S1 ou S2 avec
  `confidence: "verified"`. Pour chacun, rejoue son `repro` tel quel.
- Sortie : un finding par verdict, `kind` = celui d'origine, `observed` = résultat du rejeu,
  `related_gap` = id du finding rejoué, titre de verdict dans `observed`
  (`confirmed`, `not-reproduced` ou `changed`), preuve brute dans `evidence.ref`."""

CONSOLIDATOR_RULES = """## Consolidation (ton groupe)

- Sors `docs/revue/audit-2026-09-29/PLAN-CONSOLIDE.md` : état des lieux par parcours, matrice
  de couverture des tests, **30 tâches en 6 phases de 5**, table de traçabilité (chaque S1/S2 →
  tâche ou rejet motivé). Ne relis pas les rapports d'agents un par un : travaille sur
  `merged.jsonl` et sur les verdicts de v01.
- Exception à la règle 1 : tu peux écrire `PLAN-CONSOLIDE.md` à la racine de
  `docs/revue/audit-2026-09-29/` (et nulle part ailleurs hors de ton dossier).
- `findings.jsonl` de ton dossier peut être vide ; `resume.md` décrit ta méthode."""


def load_agents(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data["agents"])


def _group_rules(agent: dict[str, Any]) -> str:
    group = agent["group"]
    if group in {"A", "B"}:
        return PLAYWRIGHT_RULES.format(id=agent["id"], budget_tests=agent["budget_tests"])
    return {"C": CODE_RULES, "D": BENCH_RULES, "V": VERIFIER_RULES, "K": CONSOLIDATOR_RULES}[group]


def render_prompt(agent: dict[str, Any], template: str) -> str:
    scope = "\n".join(f"- {s}" for s in agent["scope"])
    values = {
        "id": agent["id"],
        "title": agent["title"],
        "group": agent["group"],
        "mode": agent["mode"],
        "budget_tests": str(agent["budget_tests"]),
        "scope": scope,
        "env": ENV_BY_MODE[agent["mode"]],
        "group_rules": _group_rules(agent),
    }
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit_prompts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    template = (AUDIT_DIR / "prompt-template.md").read_text(encoding="utf-8")
    args.out.mkdir(parents=True, exist_ok=True)
    agents = load_agents(AUDIT_DIR / "agents.yml")
    for agent in agents:
        (args.out / f"{agent['id']}.md").write_text(render_prompt(agent, template), "utf-8")
    print(f"{len(agents)} prompt(s) écrits dans {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
