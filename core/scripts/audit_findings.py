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
        doc_read_gap = self.kind == "gap" and self.evidence.type == "doc-read"
        if self.kind != "feature" and not doc_read_gap and not self.locations:
            raise ValueError(
                "locations est obligatoire (sauf kind=feature, ou kind=gap avec evidence doc-read)"
            )
        if self.confidence == "verified":
            if self.evidence.type not in EXECUTED_EVIDENCE:
                msg = "verified exige une evidence exécutée (playwright-run/command-output)"
                raise ValueError(msg)
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
            errors.append(f"ligne {n}: préfixe d'id {agent_of(finding.id)!r} ≠ agent {agent_id!r}")
        if finding.id in seen:
            errors.append(f"ligne {n}: id dupliqué {finding.id}")
        seen.add(finding.id)
        for loc in finding.locations:
            target = (repo_root / loc.file).resolve()
            if not target.is_relative_to(repo_root.resolve()):
                errors.append(f"ligne {n}: chemin hors du dépôt {loc.file}")
                continue
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
        out["merged_details"] = [
            {"id": m.id, "observed": m.observed, "proposed_fix": m.proposed_fix}
            for m in sorted(rest, key=lambda m: m.id)
        ]
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
    subdirs = [p for p in root.iterdir() if p.is_dir() and p.name != "prompts"]
    missing = sorted(p.name for p in subdirs if not (p / "findings.jsonl").is_file())
    if missing:
        print(f"dedup refusé : findings.jsonl manquant pour {', '.join(missing)}")
        return 1
    dirs = sorted(subdirs)
    if _cmd_validate(dirs, repo_root) != 0:
        print("dedup refusé : corriger d'abord les rapports non conformes")
        return 1
    merged = dedup(dirs)
    body = "\n".join(json.dumps(o, ensure_ascii=False) for o in merged)
    out.write_text(body + "\n" if merged else "")
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
