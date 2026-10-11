# SPDX-License-Identifier: Apache-2.0
"""REV-324 : CSV/GeoJSON écrits page par page (mémoire O(page)), mêmes octets que
la sérialisation en mémoire."""

import tracemalloc

import pytest

from app.analytics.export import StreamingFeatureWriter, features_to_format

N, PAGE = 50_000, 1000


def _page(start, n):
    return [
        {
            "type": "Feature",
            "id": i,
            "properties": {"name": f"p{i}", "v": i},
            "geometry": {"type": "Point", "coordinates": [i % 180, i % 90]},
        }
        for i in range(start, start + n)
    ]


def _pages(total):
    return (_page(s, min(PAGE, total - s)) for s in range(0, total, PAGE))


def _stream(path, fmt, total):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = StreamingFeatureWriter(fh, format=fmt)
        for p in _pages(total):
            w.write(p)
        w.close()


@pytest.mark.parametrize("fmt", ["csv", "geojson"])
def test_streamed_bytes_equal_in_memory(tmp_path, fmt):
    out = tmp_path / "o"
    _stream(out, fmt, 2500)
    assert out.read_bytes() == features_to_format(_page(0, 2500), format=fmt)


@pytest.mark.parametrize("fmt", ["csv", "geojson"])
def test_streamed_peak_is_far_below_in_memory(tmp_path, fmt):
    tracemalloc.start()
    feats = [f for p in _pages(N) for f in p]  # l'implémentation d'avant accumulait tout
    features_to_format(feats, format=fmt)
    _, legacy = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del feats

    tracemalloc.start()
    _stream(tmp_path / "o", fmt, N)
    _, streamed = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"{fmt}: legacy={legacy / 1e6:.1f} Mo streamed={streamed / 1e6:.1f} Mo")
    assert streamed < 0.25 * legacy


def test_job_max_defaults_depend_on_streamability(monkeypatch):
    from app.analytics.export import export_job_max

    monkeypatch.delenv("CORE_EXPORT_JOB_MAX", raising=False)
    assert export_job_max("csv") == export_job_max("geojson") == 1_000_000
    assert export_job_max("gpkg") == export_job_max("xlsx") == 200_000
    monkeypatch.setenv("CORE_EXPORT_JOB_MAX", "5")
    assert export_job_max("csv") == export_job_max("gpkg") == 5
