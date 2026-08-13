# SPDX-License-Identifier: Apache-2.0
"""Lecture d'un tileset 3D Tiles hébergé sans jamais l'extraire ni le
télécharger en entier (design §3) : S3RangeFile expose une interface
fichier (read/seek/tell) à zipfile.ZipFile, chaque accès se traduisant en
GET S3 avec un en-tête Range. zipfile ne lit ainsi que l'EOCD + la table
centrale à l'ouverture — coût constant, indépendant du volume de données du
tileset."""
import json
import zipfile
from dataclasses import dataclass


class Tileset3DValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    entry_count: int
    total_bytes: int


class S3RangeFile:
    def __init__(self, client, *, bucket: str, key: str):
        self._client = client
        self._bucket = bucket
        self._key = key
        self._pos = 0
        self._size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        else:
            raise ValueError(f"unsupported whence: {whence}")
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def read(self, size: int | None = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        end = self._size - 1 if size is None or size < 0 else min(self._pos + size, self._size) - 1
        obj = self._client.get_object(
            Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}",
        )
        data = obj["Body"].read()
        self._pos += len(data)
        return data


def _is_unsafe_entry_name(name: str) -> bool:
    return name.startswith("/") or ".." in name.split("/")


def validate_tileset_zip(
    range_file: S3RangeFile, *, max_entries: int, max_total_bytes: int, max_entry_bytes: int,
) -> ValidationResult:
    try:
        zf = zipfile.ZipFile(range_file)
    except zipfile.BadZipFile as exc:
        raise Tileset3DValidationError(f"archive zip invalide : {exc}") from exc

    infos = zf.infolist()
    if len(infos) > max_entries:
        raise Tileset3DValidationError(
            f"trop d'entrées dans l'archive ({len(infos)} > {max_entries})"
        )

    total_bytes = 0
    for info in infos:
        if _is_unsafe_entry_name(info.filename):
            raise Tileset3DValidationError(f"nom d'entrée non sûr : {info.filename!r}")
        if info.file_size > max_entry_bytes:
            raise Tileset3DValidationError(
                f"entrée trop volumineuse une fois décompressée : {info.filename!r} "
                f"({info.file_size} > {max_entry_bytes})"
            )
        total_bytes += info.file_size

    if total_bytes > max_total_bytes:
        raise Tileset3DValidationError(
            f"taille décompressée totale trop grande ({total_bytes} > {max_total_bytes})"
        )

    if "tileset.json" not in zf.namelist():
        raise Tileset3DValidationError("aucun tileset.json à la racine de l'archive")

    raw = zf.read("tileset.json")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Tileset3DValidationError(f"tileset.json n'est pas un JSON valide : {exc}") from exc
    if not isinstance(parsed, dict) or "version" not in parsed.get("asset", {}):
        raise Tileset3DValidationError(
            "tileset.json ne respecte pas le schéma 3D Tiles (asset.version manquant)"
        )

    return ValidationResult(entry_count=len(infos), total_bytes=total_bytes)
