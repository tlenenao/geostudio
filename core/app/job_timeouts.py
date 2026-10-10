# SPDX-License-Identifier: Apache-2.0
"""Seuil unique de reprise d'un job d'export `running` (REV-323 B : 60 min en
dur dans app/export, app/appexport et app/dataexport). Un worker tué ou figé
laisse le job `running` : passé ce délai, le balayage le reprend en erreur."""

import os

DEFAULT_RUNNING_RECLAIM_MINUTES = 60


def running_reclaim_minutes() -> int:
    return int(
        os.environ.get("CORE_EXPORT_RUNNING_TIMEOUT_MINUTES") or DEFAULT_RUNNING_RECLAIM_MINUTES
    )
