# SPDX-License-Identifier: Apache-2.0
"""P27.07 : `backup.sh --upload-only` (relance après échec d'envoi hors-site) ne
refait aucun dump, code 2 si l'envoi échoue, et ne touche `.last_success`
(sonde de fraîcheur du healthcheck) qu'en cas de succès."""

import os
import subprocess
from pathlib import Path

BACKUP_SH = Path(__file__).resolve().parents[2] / "deploy/backup/backup.sh"


def _run(tmp_path, mc_exit):
    arch = tmp_path / "archives"
    arch.mkdir(exist_ok=True)
    (arch / "20260101-030000.tar.gz.age").write_text("x")
    (arch / "20260102-030000.tar.gz.age").write_text("x")
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    mc = bindir / "mc"
    mc.write_text(
        f'#!/bin/sh\necho "$@" >> "{tmp_path}/mc.log"\n[ "$1" = alias ] || exit {mc_exit}\n'
    )
    mc.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BACKUP_ARCHIVES_DIR": str(arch),
        "BACKUP_S3_ENDPOINT": "http://offsite",
        "BACKUP_S3_ACCESS_KEY": "a",
        "BACKUP_S3_SECRET_KEY": "s",
        "BACKUP_S3_BUCKET": "b",
    }
    r = subprocess.run(
        ["bash", str(BACKUP_SH), "--upload-only"], env=env, capture_output=True, text=True
    )
    return r, arch


def test_upload_failure_exits_2_without_marking_success(tmp_path):
    r, arch = _run(tmp_path, mc_exit=1)
    assert r.returncode == 2, r.stderr
    assert not (arch / ".last_success").exists()


def test_upload_success_sends_newest_archive_and_marks_success(tmp_path):
    r, arch = _run(tmp_path, mc_exit=0)
    assert r.returncode == 0, r.stderr
    assert (arch / ".last_success").exists()
    assert "20260102-030000.tar.gz.age" in (tmp_path / "mc.log").read_text()
