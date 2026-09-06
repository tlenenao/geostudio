# SPDX-License-Identifier: Apache-2.0
"""Comportement de deploy/backup/restore.sh (GAP-70, design SP-59 §3.2).

Pas de framework de test shell dans ce dépôt (pas de shellcheck/bats,
vérifié) — double de test : exécutables factices mc/pg_restore sur un PATH
de test, qui journalisent leurs arguments plutôt que de toucher une vraie
base/MinIO. Placé dans core/tests/ (pas deploy/backup/) pour être ramassé
par la CI — deploy/backup/test_retention.py ne l'est pas (vérifié, spec
§3.2), ne pas répéter cette dérive."""

import os
import pathlib
import stat
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
RESTORE_SH = REPO / "deploy/backup/restore.sh"

_FAKE_PG_RESTORE = """#!/bin/sh
echo "pg_restore $*" >> "$FAKE_BIN_LOG"
exit 0
"""

_FAKE_MC = """#!/bin/sh
echo "mc $*" >> "$FAKE_BIN_LOG"
exit 0
"""


@pytest.fixture()
def fake_bin_path(tmp_path):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log_file = tmp_path / "fake-bin.log"
    log_file.write_text("")

    pg_restore = bin_dir / "pg_restore"
    pg_restore.write_text(_FAKE_PG_RESTORE)
    pg_restore.chmod(pg_restore.stat().st_mode | stat.S_IEXEC)

    mc = bin_dir / "mc"
    mc.write_text(_FAKE_MC)
    mc.chmod(mc.stat().st_mode | stat.S_IEXEC)

    return bin_dir, log_file


def _run_restore(tmp_path, fake_bin_path, restore_dir, *, extra_env=None):
    bin_dir, log_file = fake_bin_path
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_BIN_LOG"] = str(log_file)
    env["RESTORE_DIR"] = str(restore_dir)
    env["PG_PASSWORD"] = "test-pg-password"
    env["MINIO_USER"] = "test-minio-user"
    env["MINIO_PASSWORD"] = "test-minio-password"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["sh", str(RESTORE_SH), "20260906-120000"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, log_file.read_text()


def test_restore_sh_calls_pg_restore_with_expected_flags(tmp_path, fake_bin_path):
    restore_dir = tmp_path / "archive"
    restore_dir.mkdir()
    (restore_dir / "postgres.dump").write_bytes(b"fake-dump")
    (restore_dir / "minio").mkdir()

    result, log = _run_restore(tmp_path, fake_bin_path, restore_dir)

    assert result.returncode == 0, result.stderr
    assert "--clean --if-exists --no-owner" in log
    assert str(restore_dir / "postgres.dump") in log


def test_restore_sh_mb_covers_all_seven_buckets(tmp_path, fake_bin_path):
    restore_dir = tmp_path / "archive"
    restore_dir.mkdir()
    (restore_dir / "postgres.dump").write_bytes(b"fake-dump")
    (restore_dir / "minio").mkdir()

    result, log = _run_restore(tmp_path, fake_bin_path, restore_dir)

    assert result.returncode == 0, result.stderr
    for bucket in (
        "geostudio-thumbnails",
        "geostudio-uploads",
        "geostudio-cdc",
        "geostudio-tileset3d",
        "geostudio-terrain3d",
        "geostudio-mapicons",
        "geostudio-attachments",
    ):
        assert f"mb --ignore-existing local/{bucket}" in log


def test_restore_sh_succeeds_when_a_bucket_dir_is_absent_from_archive(tmp_path, fake_bin_path):
    # Archive de test dont minio/<bucket>/ est absent pour tous les buckets
    # (cas réel : aucun fichier n'a jamais été uploadé) — le script doit
    # terminer en code 0, pas planter sur le glob vide (régression du bug
    # déjà documenté par le runbook, spec §1.2).
    restore_dir = tmp_path / "archive"
    restore_dir.mkdir()
    (restore_dir / "postgres.dump").write_bytes(b"fake-dump")
    # Pas de sous-répertoire minio/ du tout.

    result, log = _run_restore(tmp_path, fake_bin_path, restore_dir)

    assert result.returncode == 0, result.stderr
    # mb tenté pour chaque bucket, mais aucun mirror (aucun répertoire) :
    assert "mb --ignore-existing" in log
    assert "mirror" not in log


def test_restore_sh_mirrors_only_buckets_present_in_archive(tmp_path, fake_bin_path):
    restore_dir = tmp_path / "archive"
    restore_dir.mkdir()
    (restore_dir / "postgres.dump").write_bytes(b"fake-dump")
    minio_dir = restore_dir / "minio"
    minio_dir.mkdir()
    # Un seul bucket présent dans l'archive — les 6 autres restent absents.
    present_bucket_dir = minio_dir / "geostudio-uploads"
    present_bucket_dir.mkdir()
    (present_bucket_dir / "file.txt").write_text("contenu")

    result, log = _run_restore(tmp_path, fake_bin_path, restore_dir)

    assert result.returncode == 0, result.stderr
    assert f"mirror --overwrite --quiet {present_bucket_dir} local/geostudio-uploads" in log
    # Les autres buckets ont eu leur `mb` mais pas de `mirror`.
    mirror_lines = [line for line in log.splitlines() if line.startswith("mc mirror")]
    assert len(mirror_lines) == 1
