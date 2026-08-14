# SPDX-License-Identifier: Apache-2.0
"""Lecture/écriture S3 en flux vers/depuis un fichier scratch local — jamais
une charge complète en mémoire (design §3 : un DEM peut faire plusieurs
centaines de Mo, contrairement aux petits objets que
app.ingestion.storage.download_object charge entièrement). rio_cogeo a de
toute façon besoin d'un chemin de fichier local (GDAL), pas d'un flux."""
_CHUNK_BYTES = 8 * 1024 * 1024  # 8 MiB


def download_to_file(client, *, bucket: str, key: str, dest_path: str) -> None:
    obj = client.get_object(Bucket=bucket, Key=key)
    with open(dest_path, "wb") as f:
        for chunk in obj["Body"].iter_chunks(_CHUNK_BYTES):
            f.write(chunk)


def upload_file(client, *, bucket: str, key: str, src_path: str) -> None:
    client.upload_file(Filename=src_path, Bucket=bucket, Key=key)
