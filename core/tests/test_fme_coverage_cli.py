# SPDX-License-Identifier: Apache-2.0
import json
import pathlib
import re

import pytest

from scripts.fme_coverage_cli import Row, check_rows, load_rows, main, render_md


def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_load_rows_parses_valid_jsonl(tmp_path):
    path = tmp_path / "matrice.jsonl"
    _write_jsonl(
        path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "Reprojects features",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    rows = load_rows(path)
    assert rows == [
        Row(
            fme_transformer="Reprojector",
            fme_category="Geometry",
            fme_description="Reprojects features",
            geostudio_equivalent="transform.reproject",
            engine="duckdb",
            engine_license="MIT",
            coverage_status="implemented",
            usage_frequency="courant",
            notes="",
        )
    ]


def test_load_rows_rejects_unknown_coverage_status(tmp_path):
    path = tmp_path / "matrice.jsonl"
    _write_jsonl(
        path,
        [
            {
                "fme_transformer": "X",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": None,
                "engine": "n/a",
                "engine_license": "",
                "coverage_status": "not_a_real_status",
                "usage_frequency": "inconnu",
                "notes": "",
            }
        ],
    )
    with pytest.raises(ValueError, match="coverage_status inconnu"):
        load_rows(path)


def test_load_rows_reports_malformed_json_with_line_number(tmp_path):
    path = tmp_path / "matrice.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"matrice\.jsonl:1"):
        load_rows(path)


def _row(**overrides) -> Row:
    base = dict(
        fme_transformer="Reprojector",
        fme_category="Geometry",
        fme_description="d",
        geostudio_equivalent="transform.reproject",
        engine="duckdb",
        engine_license="MIT",
        coverage_status="implemented",
        usage_frequency="courant",
        notes="",
    )
    base.update(overrides)
    return Row(**base)


def test_check_rows_accepts_existing_duckdb_op():
    rows = [_row(geostudio_equivalent="transform.reproject")]
    errors = check_rows(rows, ops={"transform.reproject": {}}, qgis_algorithms={})
    assert errors == []


def test_check_rows_rejects_unknown_duckdb_op():
    rows = [_row(geostudio_equivalent="transform.nonexistent")]
    errors = check_rows(rows, ops={"transform.reproject": {}}, qgis_algorithms={})
    assert len(errors) == 1
    assert "transform.nonexistent" in errors[0]


def test_check_rows_accepts_existing_qgis_algorithm():
    rows = [
        _row(
            engine="qgis",
            coverage_status="qgis_frozen",
            geostudio_equivalent="gdal:contour",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={"gdal:contour": {}})
    assert errors == []


def test_check_rows_rejects_unknown_qgis_algorithm():
    rows = [
        _row(
            engine="qgis",
            coverage_status="qgis_frozen",
            geostudio_equivalent="qgis:doesnotexist",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={"gdal:contour": {}})
    assert len(errors) == 1
    assert "qgis:doesnotexist" in errors[0]


def test_check_rows_rejects_premature_gdal_engine_claim():
    rows = [
        _row(
            engine="gdal",
            coverage_status="implemented",
            geostudio_equivalent="reader.gdal.whatever",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert len(errors) == 1
    assert "gdal" in errors[0]


def test_check_rows_rejects_premature_rust_engine_claim():
    rows = [
        _row(
            engine="rust:geo",
            coverage_status="implemented",
            geostudio_equivalent="transform.something",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert len(errors) == 1
    assert "rust:geo" in errors[0]


def test_check_rows_accepts_planned_status_for_new_engine():
    rows = [
        _row(
            engine="gdal",
            coverage_status="planned_gdal",
            geostudio_equivalent="reader.gdal.whatever",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert errors == []


def test_render_md_contains_summary_and_detail():
    rows = [_row()]
    rendered = render_md(rows)
    assert "Reprojector" in rendered
    assert "`implemented`" in rendered
    assert "`duckdb`" in rendered


def test_render_md_escapes_pipe_in_notes():
    rows = [
        _row(
            fme_transformer="StringConcatenator",
            notes="CONCAT(a, '-', b) ou opérateur || — fonction DuckDB",
        )
    ]
    rendered = render_md(rows)
    detail_line = next(line for line in rendered.splitlines() if "StringConcatenator" in line)
    assert "\\|\\|" in detail_line
    # Le tableau markdown ne doit pas gagner de colonnes supplémentaires :
    # seuls les 9 `|` délimiteurs des 8 cellules doivent rester non échappés
    # — le `||` littéral des notes doit apparaître comme `\|\|`, jamais
    # comme un `|` nu qui créerait deux colonnes fantômes.
    unescaped_pipes = re.findall(r"(?<!\\)\|", detail_line)
    # Tableau par catégorie : 7 cellules (Catégorie retirée, portée par le
    # titre de section ### <Catégorie>) → 8 délimiteurs `|` non échappés.
    assert len(unescaped_pipes) == 8


def _make_repo(tmp_path, rows) -> pathlib.Path:
    revue = tmp_path / "docs" / "revue"
    revue.mkdir(parents=True)
    _write_jsonl(revue / "matrice-couverture-fme.jsonl", rows)
    return tmp_path


def test_main_check_passes_with_real_ops_catalog(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--check"]) == 0


def test_main_check_fails_on_unknown_op(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Bogus",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.does_not_exist",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--check"]) == 1


def test_main_write_renders_markdown(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--write"]) == 0
    rendered = (repo / "docs" / "revue" / "matrice-couverture-fme.md").read_text(encoding="utf-8")
    assert "Reprojector" in rendered
