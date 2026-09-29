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
    f = make(
        kind="feature",
        locations=[],
        confidence="hypothesis",
        evidence={"type": "doc-read", "ref": "docs/vision/x.md"},
    )
    assert af.validate_lines(lines(f), "j03", repo) == []


def test_gap_with_doc_read_may_have_no_location(repo: Path) -> None:
    f = make(
        kind="gap",
        locations=[],
        confidence="probable",
        evidence={"type": "doc-read", "ref": "docs/vision/x.md"},
    )
    assert af.validate_lines(lines(f), "j03", repo) == []


def test_gap_with_code_read_still_requires_location(repo: Path) -> None:
    f = make(
        kind="gap",
        locations=[],
        confidence="probable",
        evidence={"type": "code-read", "ref": "src/a.py"},
    )
    assert any("locations" in e for e in af.validate_lines(lines(f), "j03", repo))


def test_bug_with_doc_read_still_requires_location(repo: Path) -> None:
    f = make(
        kind="bug",
        locations=[],
        confidence="probable",
        evidence={"type": "doc-read", "ref": "docs/x.md"},
    )
    assert any("locations" in e for e in af.validate_lines(lines(f), "j03", repo))


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


def test_dedup_merged_member_content_survives(repo: Path) -> None:
    a = _agent_dir(repo, "j03", make(id="j03-001", observed="texte perdu ?", proposed_fix="fix A"))
    b = _agent_dir(repo, "t01", make(id="t01-001", severity="S1", journey="transverse"))
    merged = af.dedup([a, b])
    assert merged[0]["merged_details"] == [
        {"id": "j03-001", "observed": "texte perdu ?", "proposed_fix": "fix A"}
    ]


def test_dedup_key_without_location_uses_journey_and_observed(repo: Path) -> None:
    feat = {"kind": "feature", "locations": [], "confidence": "probable"}
    feat["evidence"] = {"type": "code-read", "ref": "x"}
    a = _agent_dir(repo, "j03", make(id="j03-001", observed="Manque X", **feat))
    b = _agent_dir(repo, "j04", make(id="j04-001", observed=" manque x ", **feat))
    c = _agent_dir(repo, "j05", make(id="j05-001", observed="autre chose", **feat))
    assert len(af.dedup([a, b])) == 1
    assert len(af.dedup([a, c])) == 2
    other_journey = _agent_dir(
        repo, "j06", make(id="j06-001", observed="Manque X", journey="z", **feat)
    )
    assert len(af.dedup([a, other_journey])) == 2


def test_location_path_escape_rejected(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("a\nb\nc\n")
    for bad in (str(outside), "../" + outside.parent.name + "/secret.txt", "src/../../x"):
        loc = [{"file": bad, "line_start": 1, "line_end": 1, "symbol": "f"}]
        errs = af.validate_lines(lines(make(locations=loc)), "j03", repo / "src")
        assert any("hors du dépôt" in e for e in errs), bad


def test_dedup_zero_findings_writes_empty_file(repo: Path) -> None:
    _agent_dir(repo, "j03")
    out = repo / "merged.jsonl"
    assert af.main(["dedup", str(repo / "out"), "--out", str(out), "--repo-root", str(repo)]) == 0
    assert out.read_text() == ""


def test_dedup_fails_when_an_agent_dir_has_no_findings(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _agent_dir(repo, "j03", make())
    (repo / "out" / "j04").mkdir()
    (repo / "out" / "prompts").mkdir()
    out = repo / "merged.jsonl"
    assert af.main(["dedup", str(repo / "out"), "--out", str(out), "--repo-root", str(repo)]) == 1
    assert "j04" in capsys.readouterr().out
    assert not out.exists()
