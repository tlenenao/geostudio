# SPDX-License-Identifier: Apache-2.0
import pytest

from app.items.storage import InMemoryThumbnailStore


def test_in_memory_store_round_trips_content():
    store = InMemoryThumbnailStore()
    store.upload("item-1.bin", b"fake-bytes", "image/png")
    content, content_type = store.read("item-1.bin")
    assert content == b"fake-bytes"
    assert content_type == "image/png"


def test_in_memory_store_read_missing_key_raises():
    store = InMemoryThumbnailStore()
    with pytest.raises(KeyError):
        store.read("nope")
