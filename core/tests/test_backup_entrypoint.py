# SPDX-License-Identifier: Apache-2.0
"""REV-281c : un jour de sauvegarde abandonné déclenche une alerte webhook
(aucune règle Grafana possible : l'état Docker n'est pas scrapé)."""

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[2] / "deploy/backup/entrypoint.sh"


def _run(tmp_path, webhook):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stubs = {
        "sleep": "exit 1",  # sort de la boucle infinie après le premier passage
        "curl": f'echo "$@" >> "{tmp_path}/curl.log"',
    }
    for name, body in stubs.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    failing = tmp_path / "backup.sh"
    failing.write_text("#!/bin/sh\nexit 1\n")
    failing.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        # str(int(...)) : « 08 » ferait échouer printf %02d (lu en octal)
        "BACKUP_HOUR": str(int(datetime.now(UTC).strftime("%H"))),
        "BACKUP_MAX_ATTEMPTS": "1",
        "BACKUP_SCRIPT": str(failing),
    }
    if webhook:
        env["BACKUP_ALERT_WEBHOOK_URL"] = webhook
    r = subprocess.run(["bash", str(ENTRYPOINT)], env=env, capture_output=True, text=True)
    log = tmp_path / "curl.log"
    return r, (log.read_text() if log.exists() else "")


def test_abandoned_day_posts_to_alert_webhook(tmp_path):
    r, calls = _run(tmp_path, "https://hooks.example.test/backup")
    assert "abandon" in r.stderr
    assert "https://hooks.example.test/backup" in calls
    assert "sauvegarde abandonnée" in calls


def test_no_webhook_configured_sends_nothing(tmp_path):
    r, calls = _run(tmp_path, None)
    assert "abandon" in r.stderr
    assert calls == ""
