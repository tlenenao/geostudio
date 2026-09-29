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


def test_committed_prompts_are_in_sync_with_generator(agents: list[dict]) -> None:
    """Verify that each committed prompt file matches the current generator output."""
    template = TEMPLATE.read_text(encoding="utf-8")
    prompts_dir = REPO / "docs/revue/audit-2026-09-29/prompts"

    for agent in agents:
        prompt_file = prompts_dir / f"{agent['id']}.md"
        assert prompt_file.exists(), f"Missing prompt file: {prompt_file}"

        committed_content = prompt_file.read_text(encoding="utf-8")
        rendered_content = ap.render_prompt(agent, template)

        assert committed_content == rendered_content, (
            f"Prompt {agent['id']} is out of sync. "
            f"Run: cd core && PYTHONPATH=. uv run python scripts/audit_prompts.py render "
            f"--out ../docs/revue/audit-2026-09-29/prompts"
        )


def test_k01_prompt_carries_plan_consolide_exception(agents: list[dict]) -> None:
    by_id = {a["id"]: a for a in agents}
    text = ap.render_prompt(by_id["k01"], TEMPLATE.read_text())
    assert "Exception à la règle 1" in text
    assert "PLAN-CONSOLIDE.md" in text
