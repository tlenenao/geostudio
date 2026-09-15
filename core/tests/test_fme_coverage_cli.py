# SPDX-License-Identifier: Apache-2.0
import json
import pathlib

import pytest

from scripts.fme_coverage_cli import Row, load_rows


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
