# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from botocore.exceptions import ClientError

from app.tileset3d.storage import S3RangeFile, Tileset3DValidationError, validate_tileset_zip


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        data = self.objects[Key]
        if Range is None:
            body = data
        else:
            start, end = Range.removeprefix("bytes=").split("-")
            body = data[int(start):int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(body)}


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _valid_tileset_entries() -> dict[str, bytes]:
    tileset_json = json.dumps({"asset": {"version": "1.0"}, "root": {}}).encode()
    return {"tileset.json": tileset_json, "tiles/0.b3dm": b"\x00" * 32}


def test_s3rangefile_reads_full_content_via_ranged_gets():
    data = b"0123456789" * 100
    client = _FakeS3Client({"k": data})
    f = S3RangeFile(client, bucket="b", key="k")
    assert f.read(10) == data[:10]
    assert f.tell() == 10
    f.seek(0)
    assert f.read() == data


def test_s3rangefile_supports_zipfile_random_access():
    zip_bytes = _zip_bytes(_valid_tileset_entries())
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with zipfile.ZipFile(f) as zf:
        assert zf.read("tileset.json") == _valid_tileset_entries()["tileset.json"]


def test_validate_tileset_zip_accepts_a_valid_archive():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    result = validate_tileset_zip(
        f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000,
    )
    assert result.entry_count == 2
    assert result.total_bytes == len(entries["tileset.json"]) + len(entries["tiles/0.b3dm"])


def test_validate_tileset_zip_rejects_missing_tileset_json():
    zip_bytes = _zip_bytes({"other.txt": b"x"})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="tileset.json"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_invalid_tileset_json_content():
    zip_bytes = _zip_bytes({"tileset.json": b"not json"})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="JSON"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_tileset_json_missing_asset_version():
    zip_bytes = _zip_bytes({"tileset.json": json.dumps({"root": {}}).encode()})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="asset.version"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_too_many_entries():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="entrées"):
        validate_tileset_zip(f, max_entries=1, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_total_size_over_cap():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="totale"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=1, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_single_entry_over_cap():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="volumineuse"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=1)


def test_validate_tileset_zip_rejects_path_traversal_entry_name():
    entries = _valid_tileset_entries()
    entries["../../etc/passwd"] = b"x"
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="non sûr"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_a_non_zip_object():
    client = _FakeS3Client({"k": b"not a zip file at all"})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="zip invalide"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)
