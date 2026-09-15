# SPDX-License-Identifier: Apache-2.0
import json
import pathlib

import pytest

from scripts.fme_coverage_cli import Row, check_rows, load_rows


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
