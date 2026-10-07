"""Garde-fou du lot D de clôture des 38 REV : l'orchestrateur et le runbook ne dérivent pas."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "scripts" / "replay" / "run.sh"
RUNBOOK = ROOT / "docs" / "runbooks" / "2026-10-04-rejeu-stack-reelle.md"


def _stages() -> list[str]:
    out = subprocess.run(["bash", str(RUN), "--list"], capture_output=True, text=True, check=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def test_run_sh_lists_expected_stages() -> None:
    assert _stages() == [
        "preflight",
        "up",
        "journeys",
        "e2e-mock",
        "oidc",
        "restore-oidc",
        "smoke",
        "rebuild-images",
        "plans",
        "measure",
        "admin-tools",
        "report",
    ]


def test_every_stage_is_documented_in_runbook() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for stage in _stages():
        assert f"`run.sh {stage}" in text, f"stage {stage} absent du runbook"


def test_runbook_covers_every_letter() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for rev in (164, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286):
        assert re.search(rf"REV-{rev}\b", text), f"REV-{rev} absente du runbook"


def test_run_sh_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(RUN)], check=True)
