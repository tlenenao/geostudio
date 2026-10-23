# SPDX-License-Identifier: Apache-2.0
"""Liste blanche de types par contenu, partagée par les pièces jointes et la soumission publique."""

import pytest

from app.upload_sniff import allowed_for_kind, looks_executable, sniff_content_type

HEADS = {
    "image/jpeg": b"\xff\xd8\xff\xe0" + bytes(28),
    "image/png": b"\x89PNG\r\n\x1a\n" + bytes(24),
    "image/gif": b"GIF89a" + bytes(26),
    "image/webp": b"RIFF\x00\x00\x00\x00WEBPVP8 " + bytes(16),
    "application/pdf": b"%PDF-1.7" + bytes(24),
    "audio/ogg": b"OggS\x00\x02" + bytes(26),
    "audio/mpeg": b"ID3\x04\x00" + bytes(27),
    "audio/wav": b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(16),
    "audio/mp4": b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + bytes(16),
    "video/mp4": b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00" + bytes(16),
    "video/quicktime": b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00" + bytes(16),
    "video/3gpp": b"\x00\x00\x00\x14ftyp3gp4\x00\x00\x00\x00" + bytes(16),
    "video/webm": b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81" + bytes(24),
}


@pytest.mark.parametrize(("expected", "head"), HEADS.items())
def test_known_types_are_recognised_by_content(expected, head):
    assert sniff_content_type(head) == expected


def test_mpeg_frame_sync_and_adts_are_audio():
    assert sniff_content_type(b"\xff\xfb\x90\x00" + bytes(28)) == "audio/mpeg"
    assert sniff_content_type(b"\xff\xf1\x50\x80" + bytes(28)) == "audio/aac"


@pytest.mark.parametrize(
    "head",
    [b"MZ\x90\x00" + bytes(28), b"\x7fELF\x02\x01" + bytes(26), b"#!/bin/sh\n" + bytes(22)],
)
def test_executables_are_neither_recognised_nor_tolerated(head):
    assert sniff_content_type(head) is None
    assert looks_executable(head)
    assert not allowed_for_kind(sniff_content_type(head), None)


def test_html_and_empty_are_not_whitelisted():
    assert sniff_content_type(b"<html>x</html>") is None
    assert sniff_content_type(b"") is None


def test_kind_restricts_families_and_audio_accepts_browser_containers():
    assert allowed_for_kind("image/png", "image")
    assert not allowed_for_kind("audio/mpeg", "image")
    assert allowed_for_kind("video/webm", "audio")  # MediaRecorder sous Chrome
    assert allowed_for_kind("video/mp4", "audio")  # MediaRecorder sous Safari
    assert not allowed_for_kind("application/pdf", "video")
    assert allowed_for_kind("application/pdf", "file")
    assert allowed_for_kind("image/jpeg", None)  # champ historique : toute la liste blanche
    assert not allowed_for_kind(None, "file")
