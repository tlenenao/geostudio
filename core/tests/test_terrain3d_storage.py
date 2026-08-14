# SPDX-License-Identifier: Apache-2.0
import io
import os

from app.terrain3d.storage import download_to_file, upload_file


class _FakeBody:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def iter_chunks(self, chunk_size: int):
        while True:
            chunk = self._buf.read(chunk_size)
            if not chunk:
                return
            yield chunk


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": _FakeBody(self.objects[Key])}

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        with open(Filename, "rb") as f:
            self.objects[Key] = f.read()


def test_download_to_file_streams_object_to_local_path(tmp_path):
    client = _FakeS3Client()
    client.objects["k"] = b"0123456789" * 1000
    dest = tmp_path / "raw.tif"
    download_to_file(client, bucket="b", key="k", dest_path=str(dest))
    assert dest.read_bytes() == client.objects["k"]


def test_upload_file_puts_local_path_to_object(tmp_path):
    client = _FakeS3Client()
    src = tmp_path / "cog.tif"
    src.write_bytes(b"fake cog bytes")
    upload_file(client, bucket="b", key="k", src_path=str(src))
    assert client.objects["k"] == b"fake cog bytes"


def test_download_to_file_never_loads_whole_object_in_one_read(tmp_path, monkeypatch):
    # Régression : garantit que download_to_file lit par tranches (iter_chunks),
    # pas via Body.read() sans argument (le piège de app.ingestion.storage.download_object,
    # inadapté à un DEM de plusieurs centaines de Mo — cf. Global Constraints).
    client = _FakeS3Client()
    client.objects["k"] = b"x" * (5 * 1024 * 1024)
    dest = tmp_path / "raw.tif"
    seen_chunk_sizes = []
    original_iter_chunks = _FakeBody.iter_chunks

    def spy_iter_chunks(self, chunk_size):
        seen_chunk_sizes.append(chunk_size)
        yield from original_iter_chunks(self, chunk_size)

    monkeypatch.setattr(_FakeBody, "iter_chunks", spy_iter_chunks)
    download_to_file(client, bucket="b", key="k", dest_path=str(dest))
    assert seen_chunk_sizes and all(0 < c <= 8 * 1024 * 1024 for c in seen_chunk_sizes)
    assert os.path.getsize(dest) == 5 * 1024 * 1024
