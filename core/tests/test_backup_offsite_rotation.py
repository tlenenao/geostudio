# SPDX-License-Identifier: Apache-2.0
"""REV-281f : un envoi hors-site en échec n'empêche plus la rotation hors-site
(sinon le bucket distant grossit sans fin pendant toute la panne)."""

import os
import subprocess
from pathlib import Path

BACKUP_SH = Path(__file__).resolve().parents[2] / "deploy/backup/backup.sh"
OLD = "20250101-030000.tar.gz.age"

STUBS = {
    # pg_dump : crée le fichier --file=… (du -h le mesure ensuite)
    "pg_dump": 'for a in "$@"; do case "$a" in --file=*) : > "${a#--file=}";; esac; done',
    # mc : alias/rm réussissent, cp/ls/mirror échouent (envoi hors-site en panne)
    "mc": 'echo "$@" >> "$LOG"; case "$1" in alias|rm) exit 0;; *) exit 1;; esac',
    # curl : jeton admin sur stdout, export de realm vers -o
    "curl": 'out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; '
    'if [ -n "$out" ]; then echo \'{"realm":"geostudio"}\' > "$out"; '
    'else echo \'{"access_token":"tok"}\'; fi',
    "jq": '[ "$1" = -r ] && echo tok; exit 0',
    # age -r R -o OUT IN : copie IN vers OUT
    "age": 'cp "$5" "$4"',
    # retention.py : désigne l'ancienne archive à supprimer
    "python3": f"echo {OLD}",
}


def test_offsite_rotation_runs_even_when_upload_fails(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in STUBS.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    archives = tmp_path / "archives"
    archives.mkdir()
    (archives / OLD).write_text("x")
    log = tmp_path / "mc.log"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LOG": str(log),
        "BACKUP_ARCHIVES_DIR": str(archives),
        "BACKUP_WORK_DIR": str(tmp_path / "work"),
        "BACKUP_AGE_RECIPIENT": "age1test",
        "BACKUP_S3_ENDPOINT": "http://offsite",
        "BACKUP_S3_ACCESS_KEY": "a",
        "BACKUP_S3_SECRET_KEY": "s",
        "BACKUP_S3_BUCKET": "b",
        "PG_PASSWORD": "p",
        "MINIO_USER": "u",
        "MINIO_PASSWORD": "p",
        "KEYCLOAK_ADMIN": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "p",
    }
    r = subprocess.run(["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True)
    assert r.returncode == 75, r.stderr
    assert f"rm --quiet offsite/b/{OLD}" in log.read_text()
    assert not (archives / OLD).exists()  # rotation locale (déjà le cas avant)
    assert not (archives / ".last_success").exists()
