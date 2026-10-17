# SPDX-License-Identifier: Apache-2.0
"""AUD-034 / AUD-184 : backup.sh refuse tôt sans destinataire age, vérifie
l'espace libre, chiffre en flux (jamais d'archive en clair sur /tmp) et prend
ses hôtes en paramètre."""

import os
import subprocess
from pathlib import Path

BACKUP_SH = Path(__file__).resolve().parents[2] / "deploy/backup/backup.sh"

STUBS = {
    "pg_dump": 'echo "pg_dump $*" >> "$LOG"; '
    'for a in "$@"; do case "$a" in --file=*) echo dump > "${a#--file=}";; esac; done',
    "mc": 'echo "mc $*" >> "$LOG"; exit 0',
    "curl": 'out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; '
    'if [ -n "$out" ]; then echo \'{"realm":"geostudio"}\' > "$out"; '
    'else echo \'{"access_token":"tok"}\'; fi',
    # lit son entrée : sinon `curl | jq` prend SIGPIPE (sortie 141 sous pipefail)
    "jq": '[ "$1" = -r ] && { cat >/dev/null; echo tok; }; exit 0',
    # age -r R -o OUT : chiffre l'entrée standard (flux, pas de fichier en clair)
    "age": 'echo "age $*" >> "$LOG"; cat > "$4"',
    "python3": "echo",
}


def _run(tmp_path: Path, **extra: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stubs = {**STUBS, **{k[5:]: v for k, v in extra.items() if k.startswith("stub_")}}
    for name, body in stubs.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    archives = tmp_path / "archives"
    archives.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LOG": str(log),
        "TMPDIR": str(tmp_path / "tmp"),
        "BACKUP_ARCHIVES_DIR": str(archives),
        "BACKUP_WORK_DIR": str(tmp_path / "work"),
        "BACKUP_AGE_RECIPIENT": "age1test",
        "PG_PASSWORD": "p",
        "MINIO_USER": "u",
        "MINIO_PASSWORD": "p",
        "KEYCLOAK_ADMIN": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "p",
    }
    env.update({k: v for k, v in extra.items() if not k.startswith("stub_")})
    r = subprocess.run(["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True)
    return r, archives, log


def test_refuses_before_dumping_anything_without_age_recipient(tmp_path):
    r, archives, log = _run(tmp_path, BACKUP_AGE_RECIPIENT="")
    assert r.returncode == 1
    assert "BACKUP_AGE_RECIPIENT" in r.stderr
    assert log.read_text() == ""  # ni pg_dump, ni mc : rien de fait pour rien
    assert not list(archives.glob("*.age"))


def test_streams_tar_into_age_with_parametrised_hosts(tmp_path):
    r, archives, log = _run(
        tmp_path, PG_HOST="db.interne", PG_PORT="6543", BACKUP_MINIO_URL="http://s3.interne:9100"
    )
    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert "pg_dump -h db.interne -p 6543 " in calls
    assert "mc alias set local http://s3.interne:9100 " in calls
    assert "age -r age1test -o " in calls
    (archive,) = archives.glob("*.tar.gz.age")
    # le stub age recopie son entrée : c'est bien l'archive tar.gz en flux
    assert archive.read_bytes()[:2] == b"\x1f\x8b"
    assert not list(archives.glob("*.partial"))
    assert (archives / ".last_success").exists()
    tmp = tmp_path / "tmp"
    assert not tmp.exists() or not list(tmp.iterdir())


def test_refuses_to_package_when_archives_disk_is_too_small(tmp_path):
    # df -Pk : 6 colonnes, la 4e = disponible (en Kio)
    low_df = (
        'echo "Filesystem 1024-blocks Used Available Capacity Mounted"; echo "x 100 99 0 99% /"'
    )
    r, archives, log = _run(tmp_path, stub_df=low_df)
    assert r.returncode == 1
    assert "espace" in r.stderr.lower()
    assert "age " not in log.read_text()
    assert not list(archives.glob("*.age*"))
