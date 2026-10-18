# SPDX-License-Identifier: Apache-2.0
"""Type d'un fichier téléversé reconnu par son CONTENU (magic numbers), jamais par l'en-tête
déclaré. Source unique des jumelles « pièces jointes » (confirm authentifié) et « soumission
publique » (anonyme) — piège n°14 : un durcissement posé sur l'une se reporte sur l'autre.
L8 (AUD-071) : audio/vidéo en plus des images et du PDF."""

# Familles acceptées par `attachment_fields[].kind`. Les conteneurs (webm, mp4, ogg) sont
# ambigus audio/vidéo : un champ « audio » accepte aussi ceux qu'un navigateur produit pour
# un enregistrement audio (MediaRecorder : webm sous Chrome, mp4 sous Safari).
_IMAGE = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_AUDIO = {"audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4", "audio/aac"}
_VIDEO = {"video/mp4", "video/webm", "video/quicktime", "video/3gpp"}
_DOC = {"application/pdf"}
KIND_TYPES: dict[str, frozenset[str]] = {
    "image": frozenset(_IMAGE),
    "audio": frozenset(_AUDIO | {"video/webm", "video/mp4"}),
    "video": frozenset(_VIDEO),
    "file": frozenset(_IMAGE | _AUDIO | _VIDEO | _DOC),
}
ALL_TYPES = KIND_TYPES["file"]

HEAD_BYTES = 32

_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"OggS", "audio/ogg"),
    (b"ID3", "audio/mpeg"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),  # EBML (webm ; matroska assimilé)
)
# Entêtes de trames MPEG audio (sync 11 bits) et ADTS AAC.
_MP3_SYNC = (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
_ADTS = (b"\xff\xf1", b"\xff\xf9")

# Signatures d'exécutables : refusées même là où la liste blanche n'est pas imposée.
_EXECUTABLE_MAGIC = (
    b"MZ",  # PE (exe, dll)
    b"\x7fELF",
    b"#!",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",  # Mach-O universel / classe Java
)


def sniff_content_type(head: bytes) -> str | None:
    if head[:4] == b"RIFF":
        if head[8:12] == b"WEBP":
            return "image/webp"
        if head[8:12] == b"WAVE":
            return "audio/wav"
        return None
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"M4A ":
            return "audio/mp4"
        if brand == b"qt  ":
            return "video/quicktime"
        if brand.startswith(b"3gp"):
            return "video/3gpp"
        return "video/mp4"
    for magic, ctype in _MAGIC:
        if head.startswith(magic):
            return ctype
    if head[:2] in _MP3_SYNC:
        return "audio/mpeg"
    if head[:2] in _ADTS:
        return "audio/aac"
    return None


def looks_executable(head: bytes) -> bool:
    return head.startswith(_EXECUTABLE_MAGIC)


def allowed_for_kind(content_type: str | None, kind: str | None) -> bool:
    """`kind` absent (champ historique) : toute la liste blanche."""
    return content_type is not None and content_type in KIND_TYPES.get(kind or "file", ALL_TYPES)
