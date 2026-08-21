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


def _run(xml_content: str, threshold: str, tmp_path):
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(xml_content)
    threshold_path = tmp_path / ".coverage-threshold"
    threshold_path.write_text(threshold)
    return subprocess.run(
        [sys.executable, "scripts/check_coverage.py", str(xml_path), str(threshold_path)],
        capture_output=True,
        text=True,
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
