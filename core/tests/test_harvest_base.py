# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.base import HarvestedRecord


def test_copy_filename_defaults_to_none():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url=None,
    )
    assert rec.copy_filename is None


def test_copy_filename_can_be_set():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url="https://x/data.gpkg",
        copy_filename="harvest.gpkg",
    )
    assert rec.copy_filename == "harvest.gpkg"
