# Audit multi-agents — Vague 0 (outillage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser tout l'outillage qui rend l'audit multi-agents exécutable et vérifiable (worker stable, validateur de findings, reset de stack, config Playwright sur stack réelle, personas, prompts générés) — sans lancer aucun agent d'audit.

**Architecture:** Spec : `docs/superpowers/specs/2026-09-29-audit-multi-agents-design.md` (§5 amendé : agents Playwright séquentiels, reset de base entre chacun). Le validateur est un script Python pur (pydantic) testé sous `core/tests/`; le reset est un script bash prouvé par un auto-test à marqueurs; les prompts sont rendus depuis un gabarit + `agents.yml` par un générateur testé.

**Tech Stack:** Python 3.12 + pydantic 2.13 + pytest (core, `uv run`), bash + docker compose (stack locale `geostudio-*`), Playwright (shell), Keycloak `kcadm.sh`, PyYAML.

## Global Constraints

- Docs et messages en français ; code/identifiants en anglais (CLAUDE.md).
- Commits conventional, petits, un sujet ; chaque commit se termine par la ligne `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Branche `dev` uniquement, en local ; jamais de branche `main` locale.
- Ruff : `line-length = 100`, règles `E,F,I,UP,B` ; `core/pyproject.toml` a `filterwarnings = ["error", …]` (tout warning fait échouer pytest).
- Commande core : `cd core && PYTHONPATH=. uv run …` ; `pythonpath = ["."]` est déjà configuré pour pytest.
- Stack locale : shell `http://localhost:8300`, core `http://localhost:8200`, Keycloak `http://localhost:8180` (realm `geostudio`, admin `admin` / `$KC_PASSWORD` de `.env`), Postgres base `gis` (contient aussi Keycloak), MinIO 7 buckets (liste identique à `deploy/backup/restore.sh`).
- Aucun agent d'audit n'est lancé par ce plan. Les prompts rendus sont **montrés à Tanguy avant tout lancement** (fin de la Task 6).
- Un correctif de filet de test se vérifie par falsification (piège n°10) : injecter le défaut visé, voir le test échouer, retirer.
- Ne jamais lancer `purge_tenant` sur la stack (un seul tenant `default` : ça effacerait l'instance).

## File Structure

| Fichier | Rôle |
|---|---|
| `core/app/jobs/__init__.py` (modifié) | connecteur procrastinate sans autoprepare psycopg (Task 1) |
| `core/scripts/ensure_procrastinate_schema.py` (modifié) | idem sur le connecteur du schéma |
| `core/tests/test_jobs.py` (modifié) | test de non-régression du connecteur |
| `core/scripts/audit_findings.py` (créé) | schéma pydantic `Finding`, `validate`, `dedup`, CLI |
| `core/tests/test_audit_findings.py` (créé) | tests du validateur |
| `scripts/audit/stack-reset.sh` (créé) | `snapshot` / `reset` de la stack (Postgres+MinIO) |
| `scripts/audit/stack-reset-selftest.sh` (créé) | preuve par marqueurs que reset restaure bien |
| `scripts/audit/seed-personas.sh` (créé) | 4 utilisateurs Keycloak de rôle + env `CORE_*_SUBS` |
| `shell/playwright.journeys.config.ts` (créé) | projet Playwright stack réelle, `workers: 1` |
| `shell/e2e/journeys/_fixtures/env.ts` (créé) | constantes, personas, `loginOidc`, `stamp` |
| `shell/e2e/journeys/_witness/witness.spec.ts` (créé) | parcours témoin (mock) |
| `docs/revue/audit-2026-09-29/agents.yml` (créé) | catalogue des 29 agents |
| `docs/revue/audit-2026-09-29/prompt-template.md` (créé) | gabarit de prompt commun |
| `core/scripts/audit_prompts.py` (créé) | rend un prompt par agent |
| `core/tests/test_audit_prompts.py` (créé) | tests du générateur |
| `docs/revue/audit-2026-09-29/ORCHESTRATION.md` (créé) | ordre d'exécution et procédure de reset |
| `docs/revue/audit-2026-09-29/prompts/*.md` (généré) | 29 prompts rendus |

---

### Task 1: Worker — supprimer l'autoprepare psycopg derrière PgBouncer

**Contexte vérifié le 2026-09-29 :** `docker inspect geostudio-worker-1` → 26 redémarrages ; les logs montrent, toutes les 1 à 2 minutes, `prepared statement "_pg3_0" already exists` / `Database error.` puis « Stopped worker ». PgBouncer est en `POOL_MODE: transaction` ; `core/app/db.py:96` désactive déjà l'autoprepare pour le moteur SQLAlchemy (`connect_args["prepare_threshold"] = None`), mais le connecteur procrastinate (`core/app/jobs/__init__.py:59`) et celui de `ensure_procrastinate_schema.py:34` ne le font pas. `PsycopgConnector.__init__(**kwargs)` stocke `self._pool_args = kwargs` (procrastinate 3.9.0), et `AsyncConnectionPool(kwargs=…)` transmet ces `kwargs` à chaque connexion.

**Files:**
- Modify: `core/app/jobs/__init__.py:59`
- Modify: `core/scripts/ensure_procrastinate_schema.py:34`
- Test: `core/tests/test_jobs.py` (ajout en fin de fichier)

**Interfaces:**
- Produces: `app.jobs.app.connector._pool_args["kwargs"] == {"prepare_threshold": None}` ; constante `app.jobs.CONNECTION_KWARGS: dict[str, object]`.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `core/tests/test_jobs.py` :

```python
def test_procrastinate_connector_disables_psycopg_autoprepare():
    """Le worker tourne derrière PgBouncer en POOL_MODE=transaction : sans
    prepare_threshold=None, psycopg3 nomme des statements côté serveur
    (`_pg3_N`) qui entrent en collision d'un backend à l'autre
    (DuplicatePreparedStatement) — observé le 2026-09-29 : 26 redémarrages
    du service worker, un toutes les 1-2 minutes. Même correctif que
    app/db.py pour le moteur SQLAlchemy."""
    assert jobs.CONNECTION_KWARGS == {"prepare_threshold": None}
    pool_args = jobs.app.connector._pool_args  # type: ignore[attr-defined]
    assert pool_args["kwargs"] == {"prepare_threshold": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_jobs.py::test_procrastinate_connector_disables_psycopg_autoprepare -v`
Expected: FAIL with `AttributeError: module 'app.jobs' has no attribute 'CONNECTION_KWARGS'`

- [ ] **Step 3: Write minimal implementation**

Dans `core/app/jobs/__init__.py`, juste après la fonction `_conninfo()` (avant `app = procrastinate.App(`), ajouter :

```python
# PgBouncer en pool transaction (docker-compose.yml, POOL_MODE=transaction) :
# l'autoprepare de psycopg3 nomme des statements côté serveur qui entrent en
# collision d'un backend à l'autre. Même raison et même remède que
# app/db.py (connect_args["prepare_threshold"] = None).
CONNECTION_KWARGS: dict[str, object] = {"prepare_threshold": None}
```

et remplacer la ligne `connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),` par :

```python
    connector=procrastinate.PsycopgConnector(
        conninfo=_conninfo(), kwargs=dict(CONNECTION_KWARGS)
    ),
```

Dans `core/scripts/ensure_procrastinate_schema.py`, ajouter `from app.jobs import CONNECTION_KWARGS` après les imports tiers, et remplacer la ligne 34 par :

```python
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=database_url, kwargs=dict(CONNECTION_KWARGS)
        )
    )
```

Vérifier que l'import de `app.jobs` depuis ce script ne crée pas de cycle : `cd core && PYTHONPATH=. uv run python -c "import scripts.ensure_procrastinate_schema"` doit sortir sans erreur. S'il échoue (import de `app.jobs` trop lourd hors conteneur), définir plutôt la constante littérale `{"prepare_threshold": None}` dans le script et laisser le test de la Step 1 vérifier seulement `app.jobs`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_jobs.py tests/test_ensure_procrastinate_schema.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Vérification par falsification**

Remplacer temporairement `{"prepare_threshold": None}` par `{}` dans `CONNECTION_KWARGS`, relancer le test de la Step 1 : il doit échouer. Restaurer.

- [ ] **Step 6: Vérification réelle sur la stack**

```bash
cd /home/lenen/projets/geostudio
docker compose up -d --build worker
sleep 240
docker inspect geostudio-worker-1 --format '{{.RestartCount}}'
docker logs --since 4m geostudio-worker-1 2>&1 | grep -c 'prepared statement'
```
Expected : `RestartCount` identique entre deux relevés à 2 minutes d'intervalle (le compteur repart à 0 à la recréation du conteneur : il doit rester 0) et `0` occurrence de `prepared statement`. Si l'erreur persiste : ne pas empiler d'hypothèses — lire la trace complète (`docker logs geostudio-worker-1 2>&1 | grep -B15 'prepared statement' | head -60`) et corriger la vraie source (autre connexion psycopg hors procrastinate, ex. code des tâches) avant de continuer.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/jobs/__init__.py core/scripts/ensure_procrastinate_schema.py core/tests/test_jobs.py
git commit -m "fix(core): désactive l'autoprepare psycopg du connecteur procrastinate derrière PgBouncer

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Validateur et dédoublonneur de findings

**Files:**
- Create: `core/scripts/audit_findings.py`
- Test: `core/tests/test_audit_findings.py`

**Interfaces:**
- Produces (utilisées par Task 6 et par l'orchestration) :
  - `class Finding(BaseModel)` (champs du spec §3)
  - `validate_lines(text: str, agent_id: str, repo_root: Path) -> list[str]` — liste d'erreurs lisibles, vide si OK
  - `validate_agent_dir(agent_dir: Path, repo_root: Path) -> list[str]` — exige `findings.jsonl` et `resume.md`, `agent_id = agent_dir.name`
  - `dedup(agent_dirs: list[Path]) -> list[dict[str, object]]`
  - `main(argv: list[str] | None = None) -> int` ; CLI : `validate <dir>… [--repo-root R]`, `dedup <root> --out FILE [--repo-root R]`

- [ ] **Step 1: Write the failing tests**

Créer `core/tests/test_audit_findings.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Validateur des findings d'audit (spec 2026-09-29 §3)."""

import json
from pathlib import Path

import pytest

from scripts import audit_findings as af


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("\n".join(f"line {i}" for i in range(1, 11)) + "\n")
    return tmp_path


def make(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "j03-001",
        "kind": "bug",
        "severity": "S2",
        "effort": "S",
        "journey": "j03-createur-carte",
        "locations": [{"file": "src/a.py", "line_start": 2, "line_end": 4, "symbol": "f"}],
        "observed": "le bouton ne réagit pas",
        "expected": "le bouton ouvre le panneau",
        "evidence": {"type": "playwright-run", "ref": "e2e/journeys/j03/a.spec.ts::ouvre"},
        "repro": "npx playwright test -c playwright.journeys.config.ts a.spec.ts",
        "proposed_fix": "câbler onClick dans src/a.py",
        "confidence": "verified",
    }
    base.update(over)
    return base


def lines(*findings: dict[str, object]) -> str:
    return "\n".join(json.dumps(f) for f in findings) + "\n"


def test_valid_finding_has_no_errors(repo: Path) -> None:
    assert af.validate_lines(lines(make()), "j03", repo) == []


def test_bug_requires_a_location(repo: Path) -> None:
    errs = af.validate_lines(lines(make(locations=[])), "j03", repo)
    assert any("locations" in e for e in errs)


def test_feature_may_have_no_location(repo: Path) -> None:
    f = make(kind="feature", locations=[], confidence="hypothesis", evidence={
        "type": "doc-read", "ref": "docs/vision/x.md"})
    assert af.validate_lines(lines(f), "j03", repo) == []


def test_verified_requires_executed_evidence(repo: Path) -> None:
    f = make(evidence={"type": "code-read", "ref": "src/a.py"})
    errs = af.validate_lines(lines(f), "j03", repo)
    assert any("verified" in e for e in errs)


def test_verified_requires_repro(repo: Path) -> None:
    errs = af.validate_lines(lines(make(repro=None)), "j03", repo)
    assert any("repro" in e for e in errs)


def test_probable_may_rely_on_code_read(repo: Path) -> None:
    f = make(confidence="probable", repro=None, evidence={"type": "code-read", "ref": "src/a.py"})
    assert af.validate_lines(lines(f), "j03", repo) == []


def test_id_prefix_must_match_agent(repo: Path) -> None:
    errs = af.validate_lines(lines(make(id="j04-001")), "j03", repo)
    assert any("préfixe" in e for e in errs)


def test_duplicate_ids_rejected(repo: Path) -> None:
    errs = af.validate_lines(lines(make(), make()), "j03", repo)
    assert any("dupliqué" in e for e in errs)


def test_unknown_field_rejected(repo: Path) -> None:
    errs = af.validate_lines(lines(make(surprise=1)), "j03", repo)
    assert any("surprise" in e for e in errs)


def test_line_range_must_be_ordered(repo: Path) -> None:
    loc = [{"file": "src/a.py", "line_start": 5, "line_end": 3, "symbol": "f"}]
    assert af.validate_lines(lines(make(locations=loc)), "j03", repo)


def test_location_file_must_exist(repo: Path) -> None:
    loc = [{"file": "src/nope.py", "line_start": 1, "line_end": 1, "symbol": "f"}]
    errs = af.validate_lines(lines(make(locations=loc)), "j03", repo)
    assert any("introuvable" in e for e in errs)


def test_location_line_must_exist_in_file(repo: Path) -> None:
    loc = [{"file": "src/a.py", "line_start": 9, "line_end": 11, "symbol": "f"}]
    errs = af.validate_lines(lines(make(locations=loc)), "j03", repo)
    assert any("11" in e and "10" in e for e in errs)


def test_invalid_json_line_reported_with_line_number(repo: Path) -> None:
    errs = af.validate_lines(lines(make()) + "{pas du json\n", "j03", repo)
    assert any(e.startswith("ligne 2") for e in errs)


def test_agent_dir_requires_resume(repo: Path) -> None:
    d = repo / "out" / "j03"
    d.mkdir(parents=True)
    (d / "findings.jsonl").write_text(lines(make()))
    errs = af.validate_agent_dir(d, repo)
    assert any("resume.md" in e for e in errs)


def _agent_dir(repo: Path, agent: str, *findings: dict[str, object]) -> Path:
    d = repo / "out" / agent
    d.mkdir(parents=True)
    (d / "findings.jsonl").write_text(lines(*findings))
    (d / "resume.md").write_text("# résumé\n")
    return d


def test_dedup_merges_same_file_symbol_kind_and_keeps_worst_severity(repo: Path) -> None:
    a = _agent_dir(repo, "j03", make(id="j03-001", severity="S2"))
    b = _agent_dir(repo, "t01", make(id="t01-001", severity="S1", journey="transverse"))
    merged = af.dedup([a, b])
    assert len(merged) == 1
    assert merged[0]["id"] == "t01-001"
    assert merged[0]["merged_from"] == ["j03-001"]
    assert merged[0]["agents"] == ["j03", "t01"]


def test_dedup_keeps_distinct_symbols(repo: Path) -> None:
    other = [{"file": "src/a.py", "line_start": 6, "line_end": 7, "symbol": "g"}]
    a = _agent_dir(repo, "j03", make(id="j03-001"), make(id="j03-002", locations=other))
    assert len(af.dedup([a])) == 2


def test_cli_validate_exit_codes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = _agent_dir(repo, "j03", make())
    assert af.main(["validate", str(good), "--repo-root", str(repo)]) == 0
    bad = _agent_dir(repo, "j04", make(id="j03-001"))
    assert af.main(["validate", str(bad), "--repo-root", str(repo)]) == 1
    assert "préfixe" in capsys.readouterr().out


def test_cli_dedup_writes_jsonl(repo: Path) -> None:
    _agent_dir(repo, "j03", make())
    out = repo / "merged.jsonl"
    assert af.main(["dedup", str(repo / "out"), "--out", str(out), "--repo-root", str(repo)]) == 0
    assert json.loads(out.read_text().splitlines()[0])["id"] == "j03-001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_audit_findings.py -v`
Expected: FAIL/ERROR at collection with `ImportError: cannot import name 'audit_findings' from 'scripts'`

- [ ] **Step 3: Write the implementation**

Créer `core/scripts/audit_findings.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Validateur et dédoublonneur des findings d'audit multi-agents
(spec docs/superpowers/specs/2026-09-29-audit-multi-agents-design.md §3).

Un agent écrit `findings.jsonl` (un finding par ligne) et `resume.md` dans
`docs/revue/audit-2026-09-29/<agent-id>/`. Ce script rejette tout fichier non
conforme — y compris une localisation (`file:line`) qui ne pointe sur aucune
ligne réelle du dépôt : « détail jusqu'à la ligne » est vérifié, pas déclaré.

    PYTHONPATH=. uv run python scripts/audit_findings.py validate <dir>… [--repo-root R]
    PYTHONPATH=. uv run python scripts/audit_findings.py dedup <root> --out FILE [--repo-root R]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Kind = Literal[
    "bug", "gap", "improvement", "feature", "debt", "security", "a11y", "perf", "test-gap"
]
Severity = Literal["S1", "S2", "S3", "S4"]
Effort = Literal["XS", "S", "M", "L", "XL"]
Confidence = Literal["verified", "probable", "hypothesis"]
EvidenceType = Literal["playwright-run", "command-output", "code-read", "doc-read"]

EXECUTED_EVIDENCE: frozenset[str] = frozenset({"playwright-run", "command-output"})
ID_RE = re.compile(r"^(?P<agent>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<n>\d{3})$")
SEVERITY_ORDER = {"S1": 0, "S2": 1, "S3": 2, "S4": 3}
CONFIDENCE_ORDER = {"verified": 0, "probable": 1, "hypothesis": 2}


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    symbol: str = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> Location:
        if self.line_end < self.line_start:
            raise ValueError("line_end < line_start")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EvidenceType
    ref: str = Field(min_length=1)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_RE.pattern)
    kind: Kind
    severity: Severity
    effort: Effort
    journey: str = Field(min_length=1)
    locations: list[Location] = Field(default_factory=list)
    observed: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    evidence: Evidence
    repro: str | None = None
    proposed_fix: str = Field(min_length=1)
    confidence: Confidence
    depends_on: list[str] = Field(default_factory=list)
    related_gap: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Finding:
        if self.kind != "feature" and not self.locations:
            raise ValueError("locations est obligatoire sauf pour kind=feature")
        if self.confidence == "verified":
            if self.evidence.type not in EXECUTED_EVIDENCE:
                raise ValueError("verified exige une evidence exécutée (playwright-run/command-output)")
            if not (self.repro and self.repro.strip()):
                raise ValueError("verified exige un repro")
        return self


def agent_of(finding_id: str) -> str:
    m = ID_RE.match(finding_id)
    return m.group("agent") if m else ""


def _format_pydantic(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors():
        where = ".".join(str(p) for p in e["loc"]) or "(finding)"
        parts.append(f"{where}: {e['msg']}")
    return "; ".join(parts)


def _line_count(path: Path, cache: dict[Path, int]) -> int:
    if path not in cache:
        cache[path] = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return cache[path]


def validate_lines(text: str, agent_id: str, repo_root: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    counts: dict[Path, int] = {}
    for n, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"ligne {n}: JSON invalide ({exc.msg})")
            continue
        try:
            finding = Finding.model_validate(data)
        except ValidationError as exc:
            errors.append(f"ligne {n}: {_format_pydantic(exc)}")
            continue
        if agent_of(finding.id) != agent_id:
            errors.append(
                f"ligne {n}: préfixe d'id {agent_of(finding.id)!r} ≠ agent {agent_id!r}"
            )
        if finding.id in seen:
            errors.append(f"ligne {n}: id dupliqué {finding.id}")
        seen.add(finding.id)
        for loc in finding.locations:
            target = repo_root / loc.file
            if not target.is_file():
                errors.append(f"ligne {n}: fichier introuvable {loc.file}")
                continue
            total = _line_count(target, counts)
            if loc.line_end > total:
                errors.append(
                    f"ligne {n}: {loc.file} a {total} lignes, localisation jusqu'à {loc.line_end}"
                )
    return errors


def validate_agent_dir(agent_dir: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    findings = agent_dir / "findings.jsonl"
    if not findings.is_file():
        errors.append(f"{agent_dir}: findings.jsonl manquant")
    if not (agent_dir / "resume.md").is_file():
        errors.append(f"{agent_dir}: resume.md manquant")
    if findings.is_file():
        errors.extend(
            validate_lines(findings.read_text(encoding="utf-8"), agent_dir.name, repo_root)
        )
    return errors


def _key(f: Finding) -> tuple[str, ...]:
    if f.locations:
        loc = f.locations[0]
        return (f.kind, loc.file, loc.symbol)
    return (f.kind, f.journey, f.observed.strip().lower())


def dedup(agent_dirs: list[Path]) -> list[dict[str, object]]:
    groups: dict[tuple[str, ...], list[Finding]] = {}
    for d in sorted(agent_dirs):
        for raw in (d / "findings.jsonl").read_text(encoding="utf-8").splitlines():
            if raw.strip():
                f = Finding.model_validate(json.loads(raw))
                groups.setdefault(_key(f), []).append(f)
    merged: list[dict[str, object]] = []
    for members in groups.values():
        members.sort(
            key=lambda m: (SEVERITY_ORDER[m.severity], CONFIDENCE_ORDER[m.confidence], m.id)
        )
        winner, rest = members[0], members[1:]
        out: dict[str, Any] = winner.model_dump()
        out["merged_from"] = sorted(m.id for m in rest)
        out["agents"] = sorted({agent_of(m.id) for m in members})
        merged.append(out)
    merged.sort(key=lambda o: (SEVERITY_ORDER[o["severity"]], o["id"]))
    return merged


def _cmd_validate(dirs: list[Path], repo_root: Path) -> int:
    failed = 0
    for d in dirs:
        errors = validate_agent_dir(d, repo_root)
        if errors:
            failed += 1
            print(f"✗ {d.name}: {len(errors)} erreur(s)")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"✓ {d.name}")
    return 1 if failed else 0


def _cmd_dedup(root: Path, out: Path, repo_root: Path) -> int:
    dirs = sorted(p for p in root.iterdir() if (p / "findings.jsonl").is_file())
    if _cmd_validate(dirs, repo_root) != 0:
        print("dedup refusé : corriger d'abord les rapports non conformes")
        return 1
    merged = dedup(dirs)
    out.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in merged) + "\n")
    print(f"{len(merged)} finding(s) après dédoublonnage → {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit_findings")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("dirs", nargs="+", type=Path)
    v.add_argument("--repo-root", type=Path, default=Path(".."))
    d = sub.add_parser("dedup")
    d.add_argument("root", type=Path)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--repo-root", type=Path, default=Path(".."))
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _cmd_validate(args.dirs, args.repo_root)
    return _cmd_dedup(args.root, args.out, args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_audit_findings.py -v && uv run ruff check scripts/audit_findings.py tests/test_audit_findings.py && uv run ruff format scripts/audit_findings.py tests/test_audit_findings.py`
Expected: tous PASS ; ruff sans erreur (le `format` peut reformater ; relancer pytest ensuite).

- [ ] **Step 5: Vérification par falsification**

Dans `validate_lines`, remplacer temporairement `if loc.line_end > total:` par `if False:`, relancer `test_location_line_must_exist_in_file` : il doit échouer. Restaurer. Faire de même avec `if agent_of(finding.id) != agent_id:` → `if False:` et `test_id_prefix_must_match_agent`.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/scripts/audit_findings.py core/tests/test_audit_findings.py
git commit -m "feat(audit): validateur et dédoublonneur des findings d'audit

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Snapshot/reset de la stack, prouvé par marqueurs

**Files:**
- Create: `scripts/audit/stack-reset.sh`
- Create: `scripts/audit/stack-reset-selftest.sh`
- Modify: `.gitignore` (ajouter `.audit-snapshot/`)

**Interfaces:**
- Produces : `scripts/audit/stack-reset.sh snapshot` (écrit `.audit-snapshot/postgres.dump` + `.audit-snapshot/minio/<bucket>/…`) ; `scripts/audit/stack-reset.sh reset [--auth mock|oidc]` (restaure, redémarre core/shell dans le mode demandé, attend `healthy`). Variable optionnelle `AUDIT_SNAPSHOT_DIR`. En mode `oidc`, source `.audit-snapshot/personas.env` (Task 5) s'il existe.

- [ ] **Step 1: Vérifier les faits de la stack (piège n°3)**

```bash
cd /home/lenen/projets/geostudio
docker network ls --format '{{.Name}}' | grep gis-net
docker compose ps --format '{{.Service}} {{.Status}}' | sort
docker run --rm --entrypoint sh minio/mc -c 'mc --version' | head -1
grep -n "S3_.*BUCKET" .env .env.example | head
```
Expected : un réseau `geostudio_gis-net` (noter le nom exact, il remplace `NET` ci-dessous s'il diffère) ; services `postgis`, `pgbouncer`, `minio`, `core`, `worker`, `cdc-worker`, `keycloak`, `shell` présents ; `mc` répond. Si le nom du réseau diffère, corriger `NET` dans le script de la Step 2.

- [ ] **Step 2: Écrire `scripts/audit/stack-reset.sh`**

```bash
#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Snapshot / reset de la stack locale entre deux agents d'audit Playwright
# (spec 2026-09-29 §5). Un seul tenant `default` existe : l'isolation entre
# agents passe par la restauration de la base (qui contient aussi Keycloak)
# et des 7 buckets MinIO — même voie que deploy/backup/restore.sh (SP-59).
#
#   scripts/audit/stack-reset.sh snapshot
#   scripts/audit/stack-reset.sh reset [--auth mock|oidc]
set -euo pipefail

cd "$(dirname "$0")/../.."
SNAP="${AUDIT_SNAPSHOT_DIR:-$PWD/.audit-snapshot}"
NET="${AUDIT_COMPOSE_NETWORK:-geostudio_gis-net}"
BUCKETS=(geostudio-thumbnails geostudio-uploads geostudio-cdc geostudio-tileset3d
         geostudio-terrain3d geostudio-mapicons geostudio-attachments)

set -a
# shellcheck disable=SC1091
. ./.env
set +a

mc_run() { # $1 = commande shell exécutée dans minio/mc, dossier snapshot monté sur /snap
  docker run --rm --network "$NET" -v "$SNAP/minio:/snap" \
    -e MINIO_USER="$MINIO_USER" -e MINIO_PASSWORD="$MINIO_PASSWORD" \
    --entrypoint sh minio/mc -c \
    "mc alias set l http://minio:9000 \"\$MINIO_USER\" \"\$MINIO_PASSWORD\" >/dev/null && $1"
}

cmd_snapshot() {
  mkdir -p "$SNAP/minio"
  docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
    pg_dump -h localhost -U gis -Fc gis > "$SNAP/postgres.dump"
  for b in "${BUCKETS[@]}"; do
    mc_run "mc mb --ignore-existing l/$b >/dev/null && mkdir -p /snap/$b && mc mirror --overwrite --remove --quiet l/$b /snap/$b"
  done
  echo "[audit] snapshot écrit dans $SNAP ($(du -sh "$SNAP" | cut -f1))"
}

cmd_reset() {
  local auth="mock"
  while [ $# -gt 0 ]; do
    case "$1" in
      --auth) auth="$2"; shift 2 ;;
      *) echo "option inconnue: $1" >&2; exit 2 ;;
    esac
  done
  [ -f "$SNAP/postgres.dump" ] || { echo "aucun snapshot : lancer 'snapshot' d'abord" >&2; exit 1; }

  # cdc-worker arrêté aussi : son slot de réplication logique ne doit pas
  # lire la restauration comme du trafic métier.
  docker compose stop shell core worker cdc-worker keycloak
  local errs
  errs=$(docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
    pg_restore -h localhost -U gis -d gis --clean --if-exists --no-owner \
    < "$SNAP/postgres.dump" 2>&1 >/dev/null | grep -c '^pg_restore: error' || true)
  echo "[audit] pg_restore : $errs erreur(s) rapportée(s) (les erreurs d'objets d'extension postgis sont attendues ; le marqueur de l'auto-test fait foi)"
  for b in "${BUCKETS[@]}"; do
    [ -d "$SNAP/minio/$b" ] || continue
    mc_run "mc mb --ignore-existing l/$b >/dev/null && mc mirror --overwrite --remove --quiet /snap/$b l/$b"
  done

  if [ "$auth" = "oidc" ] && [ -f "$SNAP/personas.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$SNAP/personas.env"
    set +a
  fi
  CORE_AUTH_MODE="$auth" VITE_AUTH_MODE="$auth" CORE_ENV=development \
    docker compose up -d keycloak core worker cdc-worker shell

  for svc in core worker shell keycloak; do
    for _ in $(seq 1 60); do
      state=$(docker inspect "$(docker compose ps -q "$svc")" --format '{{.State.Health.Status}}' 2>/dev/null || echo none)
      [ "$state" = "healthy" ] && break
      sleep 3
    done
    [ "$state" = "healthy" ] || { echo "[audit] $svc jamais healthy (état: $state)" >&2; exit 1; }
  done
  echo "[audit] stack restaurée, mode auth=$auth"
}

case "${1:-}" in
  snapshot) cmd_snapshot ;;
  reset) shift; cmd_reset "$@" ;;
  *) echo "usage: $0 snapshot | reset [--auth mock|oidc]" >&2; exit 2 ;;
esac
```

Puis : `chmod +x scripts/audit/stack-reset.sh` et ajouter `.audit-snapshot/` à `.gitignore`.

- [ ] **Step 3: Écrire l'auto-test `scripts/audit/stack-reset-selftest.sh`**

```bash
#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Prouve que `reset` restaure vraiment l'état du snapshot : on pose un
# marqueur Postgres et un marqueur MinIO APRÈS le snapshot, on reset, et les
# deux doivent avoir disparu. Sans cette preuve, « reset » pourrait n'être
# qu'un redémarrage (l'assertion « les tests passent » ne prouve rien).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
NET="${AUDIT_COMPOSE_NETWORK:-geostudio_gis-net}"
B=geostudio-uploads

psql_q() { docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -tAc "$1"; }
mc_q() {
  docker run --rm --network "$NET" -e U="$MINIO_USER" -e P="$MINIO_PASSWORD" --entrypoint sh minio/mc -c \
    "mc alias set l http://minio:9000 \"\$U\" \"\$P\" >/dev/null && $1"
}

scripts/audit/stack-reset.sh snapshot

psql_q "CREATE TABLE audit_reset_marker(x int); INSERT INTO audit_reset_marker VALUES (1);" >/dev/null
mc_q "echo hi | mc pipe l/$B/audit-reset-marker.txt" >/dev/null
[ "$(psql_q "SELECT count(*) FROM audit_reset_marker")" = "1" ] || { echo "FAIL: marqueur PG non posé"; exit 1; }
mc_q "mc stat l/$B/audit-reset-marker.txt" >/dev/null || { echo "FAIL: marqueur MinIO non posé"; exit 1; }

scripts/audit/stack-reset.sh reset --auth mock

[ "$(psql_q "SELECT to_regclass('audit_reset_marker') IS NULL")" = "t" ] \
  || { echo "FAIL: le marqueur Postgres a survécu au reset"; exit 1; }
if mc_q "mc stat l/$B/audit-reset-marker.txt" >/dev/null 2>&1; then
  echo "FAIL: le marqueur MinIO a survécu au reset"; exit 1
fi
[ "$(docker inspect geostudio-worker-1 --format '{{.RestartCount}}')" -le 1 ] \
  || echo "AVERTISSEMENT: worker redémarré plusieurs fois après reset (vérifier Task 1)"
echo "OK: reset restaure Postgres et MinIO, stack healthy"
```

`chmod +x scripts/audit/stack-reset-selftest.sh`.

- [ ] **Step 4: Run — l'auto-test doit passer**

Run: `cd /home/lenen/projets/geostudio && scripts/audit/stack-reset-selftest.sh`
Expected : dernière ligne `OK: reset restaure Postgres et MinIO, stack healthy`. Si `pg_restore` rapporte des erreurs mais que les marqueurs disparaissent, c'est acceptable (noter le compte). Si le marqueur PG survit : `--clean` n'a pas supprimé une table hors dump — dans ce cas remplacer, dans `cmd_reset`, la restauration par `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` exécuté via `psql` avant `pg_restore` (et recréer les extensions `postgis`, `vector`, `pg_trgm` : `pg_restore` les recrée via le dump) puis relancer l'auto-test. Si le cdc-worker ne redevient jamais healthy : lire `docker logs geostudio-cdc-worker-1`, et si c'est le slot de réplication, dropper le slot (`SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE NOT active`) dans `cmd_reset` avant `up`.

- [ ] **Step 5: Falsification**

Commenter temporairement la ligne `pg_restore …` dans `cmd_reset`, relancer l'auto-test : il doit sortir en `FAIL: le marqueur Postgres a survécu au reset`. Restaurer.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add scripts/audit/stack-reset.sh scripts/audit/stack-reset-selftest.sh .gitignore
git commit -m "feat(audit): snapshot/reset de la stack entre agents, prouvé par marqueurs

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Projet Playwright « journeys » sur stack réelle + parcours témoin

**Files:**
- Create: `shell/playwright.journeys.config.ts`
- Create: `shell/e2e/journeys/_fixtures/env.ts`
- Create: `shell/e2e/journeys/_witness/witness.spec.ts`
- Modify: `shell/package.json` (script `e2e:journeys`)
- Modify: `shell/playwright.config.ts` (exclure `journeys/` de la suite mockée)

**Interfaces:**
- Produces (`shell/e2e/journeys/_fixtures/env.ts`) : `SHELL_URL: string`, `CORE_URL: string`, `PERSONAS: Record<"admin"|"creator"|"analyst"|"reader", {username: string; password: string}>`, `loginOidc(page: Page, persona: keyof typeof PERSONAS): Promise<void>`, `stamp(agentId: string): string` (préfixe `aud-<agentId>-<epoch36>`).

- [ ] **Step 1: Vérifier les faits (piège n°3)**

```bash
cd /home/lenen/projets/geostudio/shell
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8300/
curl -s -w '\n%{http_code}\n' http://localhost:8200/health | tail -3
grep -n "e2e\"" package.json
grep -n "testIgnore" playwright.config.ts
```
Expected : `200`, health `200` (si le chemin `/health` diffère, utiliser celui que `docker-compose.yml` déclare dans le healthcheck de `core`), et le script `e2e` existant. Noter le chemin de health réel pour la Step 3.

- [ ] **Step 2: Isoler `journeys/` de la suite mockée**

Dans `shell/playwright.config.ts`, dans le projet `chromium`, remplacer `testIgnore: /map-touch\.spec\.ts/,` par `testIgnore: [/map-touch\.spec\.ts/, /journeys\//],` ; dans le projet `mobile-touch`, `testMatch` reste inchangé (déjà restreint à `map-touch`).

- [ ] **Step 3: Écrire la config, les fixtures et le témoin**

`shell/playwright.journeys.config.ts` :

```ts
import { defineConfig } from "@playwright/test";

// Parcours d'audit sur STACK RÉELLE (spec 2026-09-29 §5) : pas de webServer,
// pas de mock réseau — la stack docker compose doit tourner
// (scripts/audit/stack-reset.sh reset --auth mock|oidc). Un seul worker : les
// agents partagent l'unique tenant `default`, l'isolation vient du reset de
// base entre agents, pas du parallélisme.
export default defineConfig({
  testDir: "./e2e/journeys",
  use: {
    baseURL: process.env.SHELL_URL ?? "http://localhost:8300",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: "test-results/journeys.json" }]],
});
```

`shell/e2e/journeys/_fixtures/env.ts` :

```ts
import type { Page } from "@playwright/test";

export const SHELL_URL = process.env.SHELL_URL ?? "http://localhost:8300";
export const CORE_URL = process.env.CORE_URL ?? "http://localhost:8200";

// Personas de rôle : créées par scripts/audit/seed-personas.sh (mode oidc).
// En mode mock, il n'existe qu'un utilisateur admin implicite (`mockuser`).
export const PERSONAS = {
  admin: { username: "audit-admin", password: "Demo1234!" },
  creator: { username: "audit-creator", password: "Demo1234!" },
  analyst: { username: "audit-analyst", password: "Demo1234!" },
  reader: { username: "audit-reader", password: "Demo1234!" },
} as const;

export type PersonaName = keyof typeof PERSONAS;

export async function loginOidc(page: Page, persona: PersonaName): Promise<void> {
  const { username, password } = PERSONAS[persona];
  await page.goto("/");
  await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('input[type="submit"], button[type="submit"]');
  await page.waitForURL(`${SHELL_URL}/**`);
}

// Préfixe unique pour tout objet qu'un agent crée (traçabilité dans les logs
// et l'audit_log, jamais utilisé pour le nettoyage : c'est le reset qui nettoie).
export function stamp(agentId: string): string {
  return `aud-${agentId}-${Date.now().toString(36)}`;
}
```

`shell/e2e/journeys/_witness/witness.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";

// Parcours témoin (mode mock) : prouve que la config journeys atteint la
// stack RÉELLE (shell servi sur :8300, cœur sur :8200), sans mock réseau.
test.describe("témoin stack réelle (auth mock)", () => {
  test("le cœur répond et le shell affiche le catalogue", async ({ page, request }) => {
    const health = await request.get(`${CORE_URL}/health`);
    expect(health.ok()).toBeTruthy();

    await page.goto("/");
    await expect(page.getByText(/catalogue|catalog/i).first()).toBeVisible({ timeout: 15_000 });
  });

  test("aucune requête réseau n'est interceptée (pas de mock)", async ({ page }) => {
    const hosts = new Set<string>();
    page.on("request", (r) => hosts.add(new URL(r.url()).host));
    await page.goto("/");
    await expect(page.getByText(/catalogue|catalog/i).first()).toBeVisible({ timeout: 15_000 });
    expect([...hosts].some((h) => h.startsWith("core.test"))).toBe(false);
    expect(stamp("witness")).toMatch(/^aud-witness-[0-9a-z]+$/);
  });
});
```

Dans `shell/package.json`, section `scripts`, ajouter : `"e2e:journeys": "playwright test -c playwright.journeys.config.ts"`.

- [ ] **Step 4: Run — le témoin doit passer sur la stack en mode mock**

```bash
cd /home/lenen/projets/geostudio && scripts/audit/stack-reset.sh reset --auth mock
cd shell && npm run e2e:journeys
```
Expected : 2 passed. Si `/health` diffère ou si le texte « catalogue » n'apparaît pas en mode mock, corriger l'URL/le sélecteur d'après ce que la stack sert réellement (ouvrir la page via `mcp__plugin_playwright_playwright__browser_navigate` si besoin) et consigner l'écart — ne pas affaiblir l'assertion.

- [ ] **Step 5: Vérifier que la suite mockée n'a pas bougé**

Run: `cd shell && npx playwright test --list | grep -c journeys`
Expected : `0` (aucun test `journeys/` dans la liste de la suite mockée).

- [ ] **Step 6: Lint/format puis commit**

```bash
cd /home/lenen/projets/geostudio/shell
npm run lint && npm run format:check
git add playwright.journeys.config.ts playwright.config.ts package.json e2e/journeys
git commit -m "test(audit): projet Playwright journeys sur stack réelle + parcours témoin

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Si `format:check` échoue : `npx prettier --write` sur les fichiers ajoutés, relancer, puis commit.

---

### Task 5: Personas OIDC par rôle

**Contexte :** Keycloak n'a que `alice` et `bob` (`deploy/keycloak/geostudio-realm.json`). Le rôle core d'un utilisateur OIDC vient de `CORE_ADMIN_SUBS` / `CORE_ANALYST_SUBS` (subs Keycloak, `core/app/auth/dependency.py:146-158`) ou de `PATCH /users/{id}` `{roleId}` (`core/app/auth/routes.py:140`). Les subs ne sont connus qu'après création des utilisateurs Keycloak, d'où le script.

**Files:**
- Create: `scripts/audit/seed-personas.sh`

**Interfaces:**
- Produces : 4 utilisateurs Keycloak `audit-admin|creator|analyst|reader` (mot de passe `Demo1234!`) ; fichier `.audit-snapshot/personas.env` contenant `CORE_ADMIN_SUBS=<sub audit-admin>` et `CORE_ANALYST_SUBS=<sub audit-analyst>` (lu par `stack-reset.sh reset --auth oidc`) ; les rôles `creator`/`reader` sont posés en base après leur première connexion.

- [ ] **Step 1: Vérifier `kcadm` empiriquement avant d'écrire le script**

```bash
cd /home/lenen/projets/geostudio && set -a && . ./.env && set +a
K="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$K config credentials --server http://localhost:8080 --realm master --user admin --password "$KC_PASSWORD"
$K get users -r geostudio --fields username,id
docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -c '\d users' | head -25
docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -tAc "select slug, tenant_id from roles order by slug"
```
Expected : `config credentials` sans erreur ; la liste montre `alice` et `bob` avec leur `id` ; `\d users` liste `oidc_sub`, `username`, `role_id` ; `roles` liste au moins `admin`, `analyst`, `reader` et le slug du rôle « Créateur » (noter son slug exact — le script ci-dessous suppose `creator`, corriger si différent). Si un chemin de serveur `/auth` est requis (`--server http://localhost:8080/auth`), l'utiliser.

- [ ] **Step 2: Écrire `scripts/audit/seed-personas.sh`**

```bash
#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Crée les 4 personas de rôle dans le realm Keycloak `geostudio` (spec
# 2026-09-29 §5) et écrit .audit-snapshot/personas.env. À lancer UNE fois,
# stack en marche, AVANT `stack-reset.sh snapshot` (le snapshot contient
# alors les utilisateurs Keycloak, la base gis étant partagée).
#
# Sans effet destructeur : idempotent (un utilisateur existant est conservé).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
SNAP="${AUDIT_SNAPSHOT_DIR:-$PWD/.audit-snapshot}"
mkdir -p "$SNAP"

K="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$K config credentials --server http://localhost:8080 --realm master \
  --user admin --password "$KC_PASSWORD" >/dev/null

sub_of() { $K get users -r geostudio -q "username=$1" --fields id --format csv --noquotes | tr -d '\r'; }

for u in audit-admin audit-creator audit-analyst audit-reader; do
  if [ -z "$(sub_of "$u")" ]; then
    $K create users -r geostudio -s "username=$u" -s enabled=true \
      -s "email=$u@audit.local" -s emailVerified=true -s firstName=Audit -s "lastName=$u"
  fi
  $K set-password -r geostudio --username "$u" --new-password 'Demo1234!'
done

cat > "$SNAP/personas.env" <<EOF
CORE_ADMIN_SUBS=$(sub_of audit-admin)
CORE_ANALYST_SUBS=$(sub_of audit-analyst)
EOF
echo "[audit] personas créées ; $SNAP/personas.env écrit"
echo "[audit] étape suivante : première connexion de audit-creator/audit-reader puis"
echo "[audit]   scripts/audit/seed-personas.sh --set-roles"
```

Puis ajouter, avant le `case`/fin de fichier, la commande `--set-roles` (les lignes `users` n'existent qu'après la première connexion de chaque persona) — remplacer les deux dernières lignes `echo` par ce bloc de fin de script, et faire commencer le script par `if [ "${1:-}" = "--set-roles" ]; then … exit 0; fi` :

```bash
# --set-roles : à lancer après une première connexion de audit-creator et
# audit-reader dans le shell (mode oidc). Pose leur role_id en base ;
# admin/analyst passent par CORE_*_SUBS (logique de rôle, is_admin synchronisé).
if [ "${1:-}" = "--set-roles" ]; then
  psql_q() { docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -tAc "$1"; }
  for pair in "audit-creator:creator" "audit-reader:reader"; do
    u="${pair%%:*}"; slug="${pair##*:}"
    n=$(psql_q "UPDATE users SET role_id=(SELECT id FROM roles WHERE slug='$slug' AND tenant_id='default') WHERE username='$u' RETURNING 1" | wc -l)
    [ "$n" -ge 1 ] || { echo "[audit] $u introuvable en base : se connecter une première fois" >&2; exit 1; }
  done
  psql_q "SELECT u.username, r.slug FROM users u JOIN roles r ON r.id=u.role_id WHERE u.username LIKE 'audit-%' ORDER BY 1"
  exit 0
fi
```
(`--set-roles` doit être le premier bloc exécutable après la définition de `SNAP`, pour ne pas recréer les utilisateurs.) `chmod +x scripts/audit/seed-personas.sh`.

- [ ] **Step 3: Exécuter et prouver chaque persona**

```bash
cd /home/lenen/projets/geostudio
scripts/audit/seed-personas.sh
scripts/audit/stack-reset.sh snapshot            # écrase le snapshot précédent : personas KC inclus
scripts/audit/stack-reset.sh reset --auth oidc   # applique CORE_ADMIN_SUBS / CORE_ANALYST_SUBS
```
Puis, pour chacun des 4 personas, une connexion réelle via la fixture (script jetable dans le scratchpad, jamais commité) :

```bash
cd shell && cat > /tmp/claude-1000/-home-lenen-projets-geostudio/15112fd1-50f8-4d7b-906b-a21bebeb098f/scratchpad/personas-login.spec.ts <<'EOF'
import { test, expect } from "@playwright/test";
import { loginOidc, type PersonaName } from "/home/lenen/projets/geostudio/shell/e2e/journeys/_fixtures/env";
for (const p of ["admin", "creator", "analyst", "reader"] as PersonaName[]) {
  test(`connexion ${p}`, async ({ page }) => {
    await loginOidc(page, p);
    await expect(page.getByText(/catalogue|catalog/i).first()).toBeVisible({ timeout: 15_000 });
  });
}
EOF
npx playwright test -c playwright.journeys.config.ts --config-dir . \
  /tmp/claude-1000/-home-lenen-projets-geostudio/15112fd1-50f8-4d7b-906b-a21bebeb098f/scratchpad/personas-login.spec.ts || true
cd .. && scripts/audit/seed-personas.sh --set-roles
```
Expected : 4 connexions réussies ; `--set-roles` affiche `audit-creator|creator` et `audit-reader|reader`. Vérifier ensuite les deux autres rôles : `docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -tAc "select u.username, r.slug from users u join roles r on r.id=u.role_id where username like 'audit-%' order by 1"` doit montrer `audit-admin|admin` et `audit-analyst|analyst`. Si la connexion échoue (fichier hors `testDir`) : copier temporairement le spec sous `shell/e2e/journeys/_witness/` et le supprimer après — ne pas le commiter.

- [ ] **Step 4: Re-snapshot avec les rôles posés**

Run: `scripts/audit/stack-reset.sh snapshot && scripts/audit/stack-reset.sh reset --auth oidc`
Expected : stack healthy ; la requête SQL de la Step 3 renvoie toujours les 4 lignes (les rôles survivent au reset).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add scripts/audit/seed-personas.sh
git commit -m "feat(audit): personas Keycloak par rôle pour les parcours OIDC

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Catalogue d'agents, gabarit de prompt, générateur, orchestration

**Files:**
- Create: `docs/revue/audit-2026-09-29/agents.yml`
- Create: `docs/revue/audit-2026-09-29/prompt-template.md`
- Create: `core/scripts/audit_prompts.py`
- Test: `core/tests/test_audit_prompts.py`
- Create: `docs/revue/audit-2026-09-29/ORCHESTRATION.md`
- Generate: `docs/revue/audit-2026-09-29/prompts/<agent-id>.md` (29 fichiers)

**Interfaces:**
- Produces : `load_agents(path: Path) -> list[dict[str, Any]]` ; `render_prompt(agent: dict[str, Any], template: str) -> str` ; `main(argv=None) -> int` (CLI `render --out DIR`) ; chaque agent a `id, group, title, mode, scope, budget_tests` (`group ∈ {A,B,C,D,V,K}`, `mode ∈ {mock,oidc,none}`).

- [ ] **Step 1: Écrire `agents.yml`** (29 agents ; 13 A + 4 B + 9 C + 1 D + V + K)

```yaml
# Catalogue des agents d'audit (spec 2026-09-29 §4). id = préfixe d'id des findings.
# mode : mock = auth mock (mockuser admin) ; oidc = personas Keycloak ; none = pas de stack.
agents:
  - {id: j01, group: A, title: "Visiteur anonyme", mode: mock, budget_tests: 30,
     scope: ["catalogue public, recherche, facettes, tri", "site /sites/{slug}, fiche dataset publique", "embed /embed/:token", "SEO : sitemap.xml, robots.txt, aperçu social", "lien de partage à échéance (déconnecté)"]}
  - {id: j02, group: A, title: "Lecteur connecté", mode: oidc, budget_tests: 30,
     scope: ["connexion OIDC (persona reader), recherche sémantique", "fiche dataset, carte en lecture, popups, pièces jointes", "bookmarks (création, ouverture, partage)", "notifications in-app", "ce qu'un lecteur NE doit PAS voir ni pouvoir faire"]}
  - {id: j03, group: A, title: "Créateur de carte", mode: oidc, budget_tests: 40,
     scope: ["import (GeoJSON, CSV, GPKG, Shapefile, XLSX, KML, GeoParquet) → collection → carte", "symbologie (catégoriel/continu/classé, icônes, étiquettes)", "popups CEL, mesure/croquis, terrain 3D, tilesets 3D", "publication et historique de versions/rollback", "erreurs d'import : fichier vide, CRS absent, gros fichier, quota"]}
  - {id: j04, group: A, title: "Créateur d'app / dashboard", mode: oidc, budget_tests: 40,
     scope: ["AppBuilder : widgets, pages, conteneurs, variables typées, expressions CEL", "actions composées, visibleWhen, filtres inter-widgets, cross-filter", "undo/redo, suppression de widget avec purge de câblage, garde de brouillon non enregistré", "formulaires depuis le schéma de collection, widgetCarte multi-couches", "runtime vs preview vs edit : divergences de comportement"]}
  - {id: j05, group: A, title: "Analyste", mode: oidc, budget_tests: 35,
     scope: ["SQL Lab (CodeMirror, erreurs DuckDB, sandbox, résultats volumineux)", "requête visuelle Filtrer→Joindre→Résumer", "agrégats, grains temporels, contexte global temps×emprise", "exports CSV/XLSX/GeoJSON/GPKG", "génération de requête en langage naturel (copilote) avec revue humaine"]}
  - {id: j06, group: A, title: "Data engineer (pipelines)", mode: oidc, budget_tests: 40,
     scope: ["pipeline builder : palette (57 op), connexion de nœuds, undo/redo, zones annotées", "aperçu, exécution, détail par run, planification cron, webhook entrant", "connecteurs et coffre de secrets (REST, Postgres, Snowflake, BigQuery, blob…)", "reader.file/writer.file derrière leur flag", "erreurs : secret absent, SSRF, schéma qui change, plafonds"]}
  - {id: j07, group: A, title: "Data steward (moissonnage et métadonnées)", mode: oidc, budget_tests: 30,
     scope: ["sources de moissonnage (STAC, ArcGIS FS, WMS/WFS/WMTS, CSW, CKAN) : création, sondage, erreurs", "API STAC native, export DCAT-AP, pagination", "licences et métadonnées ouvertes par collection/item", "masquage de champ sensible par collection", "collection cassée : dégradation gracieuse"]}
  - {id: j08, group: A, title: "Admin de tenant", mode: oidc, budget_tests: 35,
     scope: ["utilisateurs (rôle par ligne, recherche, pagination), rôles sur mesure et 18 privilèges", "quotas de stockage visibles et bloquants", "conformité RGPD : anonymisation d'utilisateur (PAS purge de tenant), reçus", "usage (/tasks), collections admin, extensions", "SettingsNav : les 7 destinations admin selon les privilèges"]}
  - {id: j09, group: A, title: "Ops / instance", mode: oidc, budget_tests: 25,
     scope: ["passerelle /admin/martin|titiler|grafana (jeton de lancement, cookie)", "jobs : libellés, statuts, reprise, troncature MVT", "notifications, alertes (AlertRule webhook/email), rapports planifiés", "état d'instance, santé des services, page infrastructure"]}
  - {id: j10, group: A, title: "Sites, storytelling, export d'apps", mode: oidc, budget_tests: 30,
     scope: ["sites et portails : widgets de contenu, fiche dataset, édition d'item Site", "storytelling (mode story), PageManager", "export d'apps : Statique, Connecté, Autoporté", "rapports PDF (printLayout, ReportSchedule) si CORE_EXPORT_ENABLED"]}
  - {id: j11, group: A, title: "Copilote IA et MCP", mode: oidc, budget_tests: 25,
     scope: ["copilote du builder (6 outils allowlistés, historique)", "MCP : /mcp OAuth 2.1+PKCE, outils, permissions de l'utilisateur, audit", "parité REST ↔ MCP observable depuis le shell", "comportement sans CORE_LLM_PROVIDER : message d'indisponibilité"]}
  - {id: j12, group: A, title: "Terrain : mobile et tactile", mode: oidc, budget_tests: 30,
     scope: ["viewports 360/768/900/1280, TriptychLayout étroit/large", "carte tactile (tap, pinch), popups, mesure au doigt", "navigation clavier virtuel, zones de tap ≥ 44 px", "prefers-reduced-motion, thème clair/sombre"]}
  - {id: j13, group: A, title: "Partage et permissions", mode: oidc, budget_tests: 40,
     scope: ["partage d'items et groupes, publication, liens à échéance", "matrice rôle × action (admin/creator/analyst/reader) sur chaque type d'item", "tentatives d'accès direct par URL / id d'un autre utilisateur (IDOR côté UI)", "garde côté serveur vs masquage côté UI : cohérence"]}
  - {id: t01, group: B, title: "Accessibilité", mode: oidc, budget_tests: 40,
     scope: ["axe-core sur toutes les routes du shell (pas seulement les 9 déjà couvertes)", "parcours clavier complet : focus visible, ordre, pièges, Drawer/Dialog/Popover", "labels, erreurs de formulaire, aria-expanded/aria-controls sur panneaux", "contrastes AA en clair et sombre"]}
  - {id: t02, group: B, title: "Résilience et erreurs", mode: oidc, budget_tests: 40,
     scope: ["401/403/404/409/422/429/500 sur chaque famille d'appel (page.route pour injecter)", "réseau coupé et retour, CoreUnreachableError, bannière de connectivité", "quotas atteints, rate limit, timeouts 15 s", "double soumission, retours arrière, onglets multiples", "docker stop ciblé d'un service (worker, martin) : dégradations visibles"]}
  - {id: t03, group: B, title: "Performance perçue", mode: oidc, budget_tests: 25,
     scope: ["taille de bundle et découpage par route", "LCP/CLS sur catalogue, carte, builder (mesures réelles)", "jeux de données de 50k à 500k entités sur carte et tableau", "boucles de sondage (notifications 45 s) et fuites au démontage"]}
  - {id: t04, group: B, title: "Cohérence visuelle et i18n", mode: oidc, budget_tests: 30,
     scope: ["tokens sémantiques : aucune couleur/taille brute résiduelle", "français en dur hors i18n, pluriels, formats de date/nombre", "captures comparées entre pages similaires (espacements, hauteurs h-9, Button vs <button>)", "états vides/chargement/erreur uniformes"]}
  - {id: c01, group: C, title: "Authz, RLS, IDOR (code)", mode: none, budget_tests: 0,
     scope: ["chaque route de core/app/**/routes.py : garde can()/require_privilege effectivement appelée (suivre le chemin d'exécution, pas grep)", "RLS PostGIS, rls_scope, MVT, OGC API Features, STAC, DCAT", "MCP : permissions de l'utilisateur, audit, outils d'écriture", "liens de partage/embed : portée recoupée avec les droits réels"]}
  - {id: c02, group: C, title: "Correctness backend (code)", mode: none, budget_tests: 0,
     scope: ["gestion d'erreurs, transactions, commits partiels, TOCTOU", "jobs procrastinate : idempotence, reprise, écriture best-effort séparée", "concurrence asyncio/sync, ressources non fermées", "validateurs REST vs MCP (save_app_config saute des validateurs, REV-174)"]}
  - {id: c03, group: C, title: "Migrations et données (code)", mode: none, budget_tests: 0,
     scope: ["core/alembic/versions : upgrade/downgrade sur base NON vide", "migrations sans test round-trip (0029, 0030, 0031, 0034, 0037…)", "tenant_id et audit_log sur toute écriture", "index manquants, contraintes, cascades"]}
  - {id: c04, group: C, title: "Qualité du shell (code)", mode: oidc, budget_tests: 0,
     scope: ["shell/src : code mort, duplication, types lâches, any, casts", "toFrontLayer() : champs de config qui ne round-trippent pas (piège n°5)", "ItemClient comme seul sas vers le cœur", "composants > 500 lignes, hooks instables, fuites d'effets"]}
  - {id: c05, group: C, title: "Qualité des tests (code)", mode: none, budget_tests: 0,
     scope: ["tests flaky connus et candidats, mocks E2E périmés (shell/e2e/mocks.ts)", "trous de couverture par module (pytest coverage.xml, vitest)", "assertions qui ne prouvent rien (durée pour la concurrence, piège n°7)", "skips silencieux (tests postgis sans CORE_TEST_DATABASE_URL)"]}
  - {id: c06, group: C, title: "CI, déploiement, ops (code)", mode: none, budget_tests: 0,
     scope: [".github/workflows/*, protection de branche, publication d'images", "docker-compose*.yml par valeur : variable câblée dans le bon service (piège n°2)", "deploy/** : backup/restore, install.sh, Proxmox, OCI, Ansible", "secrets, images non épinglées, healthchecks"]}
  - {id: c07, group: C, title: "Dérive doc et inventaire (code)", mode: none, budget_tests: 0,
     scope: ["CLAUDE.md §Livré vs code réel (piège n°12)", "docs/revue/inventaire-fonctionnalites.jsonl vs routes/outils/pages réels", "backlog REV-nnn et GAP-nn : états contredits par le code", "OpenAPI/types TS générés à jour (piège n°1)"]}
  - {id: c08, group: C, title: "Parité REST / MCP / ItemClient (code)", mode: none, budget_tests: 0,
     scope: ["chaque capacité REST a-t-elle son outil MCP et sa méthode ItemClient ?", "schémas AppConfig/MapConfig : une seule source de vérité", "services partagés REST↔MCP : divergences de validation", "erreurs RFC 7807 propagées de bout en bout"]}
  - {id: c09, group: C, title: "Performance backend (code)", mode: none, budget_tests: 0,
     scope: ["N+1 SQL, index absents, requêtes sans pagination", "DuckDB : plafonds, matérialisation, sandbox SQL", "tuiles MVT (plafond 5000 lignes), agrégats, lakehouse CDC", "balayages cron : batching, verrous"]}
  - {id: d01, group: D, title: "Benchmark produit", mode: none, budget_tests: 0,
     scope: ["comparer GeoStudio à Felt, ArcGIS (Online/Experience Builder), QGIS Server, Kepler.gl/CARTO, FME", "sources : docs/vision/*, inventaire-fonctionnalites.jsonl, sites publics des concurrents (WebSearch)", "produire des findings kind=feature|gap avec evidence doc-read, effort estimé, différenciateur produit (horizontal, parité connecteurs)", "ne rien proposer qui contredise les 40 arbitrages de la feuille de route §8"]}
  - {id: v01, group: V, title: "Vérificateur S1/S2", mode: oidc, budget_tests: 0,
     scope: ["rejouer 100 % des findings S1/S2 confidence=verified par leur champ `repro`, après un reset de stack", "verdict par finding : confirmed | not-reproduced | changed, avec la sortie brute", "écrire un findings.jsonl de statut (mêmes règles de format), id préfixé v01"]}
  - {id: k01, group: K, title: "Consolidateur", mode: none, budget_tests: 0,
     scope: ["lire merged.jsonl (sortie de `audit_findings.py dedup`) et les verdicts de v01", "produire PLAN-CONSOLIDE.md : état des lieux par parcours, matrice de couverture, 30 tâches en 6 phases de 5, traçabilité S1/S2", "chaque tâche : findings couverts, fichiers/lignes, effort, dépendances, test d'acceptation"]}
```

- [ ] **Step 2: Écrire `prompt-template.md`**

Les champs entre doubles accolades sont substitués par le générateur (`{{id}}`, `{{title}}`, `{{group}}`, `{{mode}}`, `{{scope}}`, `{{budget_tests}}`, `{{group_rules}}`).

````markdown
# Audit GeoStudio — agent `{{id}}` : {{title}}

Tu es l'agent d'audit `{{id}}` (groupe {{group}}). Tu **ne corriges rien** : tu identifies ce
qu'il faut corriger, combler, améliorer ou ajouter, et tu le prouves.

## Règles non négociables

1. **Lecture seule sur le code source.** Tu n'écris que dans
   `docs/revue/audit-2026-09-29/{{id}}/` et, si ton groupe fait des tests, dans
   `shell/e2e/journeys/{{id}}/`. Jamais ailleurs. Aucun `git commit`, aucun `git push`.
2. **Preuve exécutée.** Un finding `confidence: "verified"` cite une exécution réelle
   (`playwright-run` ou `command-output`) et un `repro` rejouable. Le récit d'un document
   (CLAUDE.md, specs, plans) n'est jamais une preuve : relis le code (piège n°12). Un
   garde ou un privilège se vérifie en suivant le chemin d'exécution réel, pas par `grep`
   d'un nom (piège n°11).
3. **Localisation à la ligne.** Tout finding (sauf `kind: "feature"`) porte au moins une
   `locations[]` `{file, line_start, line_end, symbol}` dont les lignes existent. Le
   validateur le vérifie.
4. **Déjà connu.** Lis `docs/revue/2026-09-29-audit-pre-release.md` : ne re-signale pas ses
   items (référence-les via `related_gap` si utile). Idem pour `docs/revue/2026-09-04-backlog.md`
   (REV-nnn) et `docs/revue/2026-09-04-analyse-gaps.md` (GAP-nn) : cite l'identifiant plutôt
   que de dupliquer.
5. **Ne te fie ni aux plans ni aux briefs** sur les interfaces tierces : vérifie contre le
   code ou une exécution (piège n°3).
6. **Ne touche jamais** à `purge_tenant`, à la base de données de production, ni à la stack
   (pas de `docker compose down`, pas de reset : l'orchestrateur s'en charge).

## Ton périmètre

{{scope}}

## Environnement

{{env}}

{{group_rules}}

## Format de sortie (obligatoire)

Dans `docs/revue/audit-2026-09-29/{{id}}/` :

- `findings.jsonl` — une ligne JSON par finding, champs exacts :
  `id` (`{{id}}-001`, `{{id}}-002`…), `kind` (bug|gap|improvement|feature|debt|security|a11y|perf|test-gap),
  `severity` (S1 bloquant, S2 majeur, S3 mineur, S4 cosmétique), `effort` (XS|S|M|L|XL),
  `journey` (identifiant de parcours ou `transverse`),
  `locations` (liste de `{file, line_start, line_end, symbol}`, chemins relatifs à la racine du dépôt),
  `observed`, `expected` (une phrase chacun), `evidence` (`{type: playwright-run|command-output|code-read|doc-read, ref}`),
  `repro` (spec+nom du test, ou commande exacte ; obligatoire si verified),
  `proposed_fix` (pistes + fichiers à toucher), `confidence` (verified|probable|hypothesis),
  `depends_on` (liste d'ids), `related_gap` (GAP-nn / REV-nnn ou null).
  Aucun champ supplémentaire.
- `resume.md` — périmètre couvert, périmètre NON couvert (et pourquoi), méthode, commandes lancées.

Avant de terminer, exécute et corrige jusqu'à sortie verte :

```bash
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/{{id}} --repo-root ..
```

Ta réponse finale tient en 5 lignes : nombre de findings par sévérité, chemin du dossier,
résultat du validateur. **Ne recopie pas les findings dans ta réponse.**
````

- [ ] **Step 3: Write the failing tests**

Créer `core/tests/test_audit_prompts.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Générateur de prompts d'audit (spec 2026-09-29 §4, plan vague 0 Task 6)."""

from pathlib import Path

import pytest

from scripts import audit_prompts as ap

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "docs/revue/audit-2026-09-29/agents.yml"
TEMPLATE = REPO / "docs/revue/audit-2026-09-29/prompt-template.md"


@pytest.fixture(scope="module")
def agents() -> list[dict]:
    return ap.load_agents(CATALOG)


def test_catalog_has_29_agents_with_unique_ids(agents: list[dict]) -> None:
    ids = [a["id"] for a in agents]
    assert len(ids) == 29 and len(set(ids)) == 29


def test_group_counts_match_spec(agents: list[dict]) -> None:
    by = {g: sum(1 for a in agents if a["group"] == g) for g in "ABCDVK"}
    assert by == {"A": 13, "B": 4, "C": 9, "D": 1, "V": 1, "K": 1}


def test_every_agent_has_required_fields(agents: list[dict]) -> None:
    for a in agents:
        assert {"id", "group", "title", "mode", "scope", "budget_tests"} <= set(a), a["id"]
        assert a["mode"] in {"mock", "oidc", "none"}
        assert a["scope"], a["id"]


def test_render_substitutes_every_placeholder(agents: list[dict]) -> None:
    template = TEMPLATE.read_text()
    for a in agents:
        out = ap.render_prompt(a, template)
        assert "{{" not in out, a["id"]
        assert f"docs/revue/audit-2026-09-29/{a['id']}/" in out


def test_playwright_groups_get_journey_rules_and_code_groups_do_not(agents: list[dict]) -> None:
    template = TEMPLATE.read_text()
    for a in agents:
        out = ap.render_prompt(a, template)
        has_pw = "shell/e2e/journeys/" in out and "test.fixme" in out
        assert has_pw == (a["group"] in {"A", "B"}), a["id"]


def test_every_prompt_carries_the_read_only_rule_and_validator(agents: list[dict]) -> None:
    template = TEMPLATE.read_text()
    for a in agents:
        out = ap.render_prompt(a, template)
        assert "Lecture seule sur le code source" in out
        assert "audit_findings.py validate" in out


def test_env_block_matches_mode(agents: list[dict]) -> None:
    template = TEMPLATE.read_text()
    by_id = {a["id"]: a for a in agents}
    assert "audit-reader" in ap.render_prompt(by_id["j02"], template)
    assert "mockuser" in ap.render_prompt(by_id["j01"], template)
    assert "aucune stack" in ap.render_prompt(by_id["c01"], template).lower()


def test_cli_renders_one_file_per_agent(tmp_path: Path) -> None:
    assert ap.main(["render", "--out", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*.md"))) == 29
```

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_audit_prompts.py -v`
Expected : FAIL/ERROR (`ImportError: cannot import name 'audit_prompts'`)

- [ ] **Step 4: Écrire `core/scripts/audit_prompts.py`**

```python
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
        "Stack réelle, **auth mock** : shell `http://localhost:8300`, cœur `http://localhost:8200`. "
        "Un seul utilisateur implicite `mockuser` (admin). Aucun mock réseau : les tests "
        "Playwright ciblent la vraie stack. L'orchestrateur a déjà fait "
        "`scripts/audit/stack-reset.sh reset --auth mock` ; ne le relance pas."
    ),
    "oidc": (
        "Stack réelle, **auth OIDC (Keycloak)** : shell `http://localhost:8300`, cœur "
        "`http://localhost:8200`. Personas (mot de passe `Demo1234!`) : `audit-admin`, "
        "`audit-creator`, `audit-analyst`, `audit-reader` (fixtures : "
        "`shell/e2e/journeys/_fixtures/env.ts`, `loginOidc(page, persona)`). L'orchestrateur a déjà "
        "fait `scripts/audit/stack-reset.sh reset --auth oidc` ; ne le relance pas."
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
- Budget : jusqu'à {budget_tests} tests, sans limite sur le nombre de findings. Couvre le nominal, les
  erreurs, les états vides, les cas limites et les droits (rôle non autorisé).
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
- `findings.jsonl` de ton dossier peut être vide ; `resume.md` décrit ta méthode."""


def load_agents(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data["agents"])


def _group_rules(agent: dict[str, Any]) -> str:
    group = agent["group"]
    if group in {"A", "B"}:
        return PLAYWRIGHT_RULES.format(id=agent["id"], budget_tests=agent["budget_tests"])
    return {"C": CODE_RULES, "D": BENCH_RULES, "V": VERIFIER_RULES, "K": CONSOLIDATOR_RULES}[
        group
    ]


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
```

Vérifier d'abord que PyYAML est disponible : `cd core && uv run python -c "import yaml"`. S'il échoue, `uv add --dev pyyaml` puis committer `pyproject.toml` + `uv.lock` avec cette tâche.

- [ ] **Step 5: Run tests — PASS, puis lint**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_audit_prompts.py tests/test_audit_findings.py -v && uv run ruff check scripts/audit_prompts.py tests/test_audit_prompts.py && uv run ruff format scripts/audit_prompts.py tests/test_audit_prompts.py`
Expected : tous PASS ; `test_env_block_matches_mode` exige que le rendu de `c01` contienne « aucune stack » (présent dans `ENV_BY_MODE["none"]`).

- [ ] **Step 6: Falsification**

Retirer temporairement `"Lecture seule sur le code source"` du gabarit : `test_every_prompt_carries_the_read_only_rule_and_validator` doit échouer. Restaurer. Changer temporairement un agent de groupe `C` en `A` dans `agents.yml` : `test_group_counts_match_spec` doit échouer. Restaurer.

- [ ] **Step 7: Écrire `ORCHESTRATION.md`**

```markdown
# Orchestration de l'audit — 2026-09-29

Spec : `docs/superpowers/specs/2026-09-29-audit-multi-agents-design.md`. Plan vague 0 : `docs/superpowers/plans/2026-09-29-audit-multi-agents-vague0.md`.

## Pré-requis (une fois)

1. `docker compose up -d` : 11 services healthy ; `docker inspect geostudio-worker-1 --format '{{.RestartCount}}'` stable.
2. `scripts/audit/seed-personas.sh`, puis `stack-reset.sh snapshot` (voir Task 5 du plan).
3. `cd core && PYTHONPATH=. uv run python scripts/audit_prompts.py render --out ../docs/revue/audit-2026-09-29/prompts`.

## Ordre d'exécution

| Vague | Agents | Parallélisme |
|---|---|---|
| 1 | c01…c09, d01 (sans stack, lecture seule) | jusqu'à 4 en parallèle |
| 2 | j01, j02, …, j13 (séquentiels ; j01 en mock, les autres en oidc) | **1 à la fois** |
| 3 | t01…t04 (séquentiels ; t02 en dernier : `docker stop` ciblés) | **1 à la fois** |
| 4 | v01 (rejeu 100 % des S1/S2 verified) | 1 |
| 5 | k01 (consolidation) | 1 |

Les vagues 1 et 2 peuvent se chevaucher (les agents C ne touchent pas la stack). Les agents
Playwright (2, 3) sont strictement séquentiels.

## Cycle d'un agent Playwright (A/B)

1. `scripts/audit/stack-reset.sh reset --auth <mode de l'agent>`
2. Worktree éphémère : branche `audit/<id>` (voir `superpowers:using-git-worktrees`).
3. Dispatcher l'agent avec `docs/revue/audit-2026-09-29/prompts/<id>.md`.
4. À la fin : `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/<id> --repo-root ..` ; si rouge, renvoyer l'erreur à l'agent.
5. Fusionner la branche dans `dev`, supprimer le worktree et la branche.

## Après la vague 3

`cd core && PYTHONPATH=. uv run python scripts/audit_findings.py dedup ../docs/revue/audit-2026-09-29 --out ../docs/revue/audit-2026-09-29/merged.jsonl --repo-root ..`
```

- [ ] **Step 8: Générer les prompts et vérifier**

```bash
cd /home/lenen/projets/geostudio/core
PYTHONPATH=. uv run python scripts/audit_prompts.py render --out ../docs/revue/audit-2026-09-29/prompts
ls ../docs/revue/audit-2026-09-29/prompts | wc -l
grep -L "audit_findings.py validate" ../docs/revue/audit-2026-09-29/prompts/*.md | wc -l
```
Expected : `29` puis `0`.

- [ ] **Step 9: Commit**

```bash
cd /home/lenen/projets/geostudio
git add docs/revue/audit-2026-09-29 core/scripts/audit_prompts.py core/tests/test_audit_prompts.py
git commit -m "feat(audit): catalogue de 29 agents, gabarit et générateur de prompts

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 10: Présenter à Tanguy (point d'arrêt obligatoire)**

Ne lancer aucun agent. Montrer à Tanguy : `agents.yml` (périmètres), `prompt-template.md`, deux prompts rendus en exemple (`j03.md` et `c01.md`) et `ORCHESTRATION.md`. Attendre son accord explicite avant la vague 1.

---

## Self-review (fait à l'écriture)

- **Couverture du spec §6 :** worker (Task 1), validateur (2), reset + preuve par marqueur (3), config Playwright + témoin (4), personas (5), gabarit + `agents.yml` + générateur + prompts montrés avant lancement (6). §3 format : Task 2. §5 séquentiel + deux modes d'auth : Tasks 3-5. §4 : 29 agents (13+4+9+1+V+K) dans `agents.yml`, vérifié par `test_group_counts_match_spec`.
- **Placeholders :** aucun « TBD » ; les seules branches conditionnelles (nom de réseau docker, slug du rôle créateur, chemin de health, PyYAML) sont précédées d'une étape de vérification à sortie attendue.
- **Cohérence des types :** `validate_lines`/`validate_agent_dir`/`dedup`/`main` (Task 2) sont ceux appelés par le prompt (`audit_findings.py validate …`) et par `ORCHESTRATION.md` ; `PERSONAS`/`loginOidc`/`stamp` (Task 4) sont ceux cités dans `ENV_BY_MODE` et `PLAYWRIGHT_RULES` (Task 6) ; `CONNECTION_KWARGS` (Task 1) est utilisé par le test et par `ensure_procrastinate_schema.py`.
- **Écart connu vs spec :** aucun tenant par agent (amendement du 2026-09-29) ; parallélisme Playwright ramené à 1 (agents A/B séquentiels).
