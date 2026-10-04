import os
import subprocess
import sys
import textwrap

COVERAGE_XML = textwrap.dedent(
    """\
    <?xml version="1.0" ?>
    <coverage line-rate="0.85">
    </coverage>
    """
)


def _run(xml_content: str, threshold: str, tmp_path, env=None):
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(xml_content)
    threshold_path = tmp_path / ".coverage-threshold"
    threshold_path.write_text(threshold)
    return subprocess.run(
        [sys.executable, "scripts/check_coverage.py", str(xml_path), str(threshold_path)],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def test_passes_when_coverage_meets_threshold(tmp_path):
    result = _run(COVERAGE_XML, "80", tmp_path)
    assert result.returncode == 0
    assert "85.00%" in result.stdout


def test_fails_when_coverage_below_threshold(tmp_path):
    result = _run(COVERAGE_XML, "90", tmp_path)
    assert result.returncode == 1
    assert "ÉCHEC" in result.stderr


def test_passes_when_coverage_exactly_at_threshold(tmp_path):
    result = _run(COVERAGE_XML, "85", tmp_path)
    assert result.returncode == 0


PACKAGES_XML = textwrap.dedent(
    """\
    <?xml version="1.0" ?>
    <coverage line-rate="0.85">
      <packages>
        <package name="app.alerts" line-rate="0.95"/>
        <package name="app.pipelines" line-rate="0.62"/>
      </packages>
    </coverage>
    """
)


def test_reports_per_package_coverage_lowest_first(tmp_path):
    """REV-281a : rapport par module, non bloquant, aussi dans le résumé CI."""
    summary = tmp_path / "summary.md"
    result = _run(PACKAGES_XML, "80", tmp_path, env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 0
    assert result.stdout.index("app.pipelines") < result.stdout.index("app.alerts")
    assert "| app.pipelines | 62.0 % |" in result.stdout
    assert "| app.alerts | 95.0 % |" in summary.read_text()
