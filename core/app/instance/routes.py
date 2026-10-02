# SPDX-License-Identifier: Apache-2.0
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependency import (
    get_current_user,
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_quotas_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()
_CDC_SLOT = "geostudio_cdc_slot"


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    return None


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "appExportEnabled": is_appexport_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
        "terrain3dEnabled": is_terrain3d_enabled(),
        "copilotEnabled": is_copilot_enabled(),
        "adminToolsEnabled": is_admin_tools_enabled(),
        "quotasEnabled": is_quotas_enabled(),
    }


def _probe(session: Session, fn) -> dict:
    try:
        return {"ok": True, **(fn() or {})}
    except Exception as exc:  # une sonde ne doit jamais lever, seulement échouer
        session.rollback()  # une requête en échec avorte la transaction
        return {"ok": False, "error": type(exc).__name__}


@router.get("/instance/status")
def get_instance_status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
) -> dict:
    """Vue d'état d'instance (P17.07, j09-009) : Postgres, S3, CDC, files
    procrastinate. Réservée à `settings.instance.manage`."""
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)

    def postgres() -> dict:
        session.execute(text("SELECT 1"))
        return {}

    def object_store() -> dict:
        if s3 is None:
            raise RuntimeError("S3 non configuré")
        s3.list_buckets()
        return {}

    def cdc() -> dict:
        row = session.execute(
            text("SELECT active FROM pg_replication_slots WHERE slot_name = :n"),
            {"n": _CDC_SLOT},
        ).first()
        return {"slotActive": bool(row and row[0])}

    def jobs() -> dict:
        rows = session.execute(
            text(
                "SELECT queue_name, status, COUNT(*) FROM procrastinate_jobs "
                "GROUP BY queue_name, status ORDER BY queue_name, status"
            )
        ).all()
        stalled = session.execute(
            text(
                "SELECT COUNT(*) FROM procrastinate_jobs j WHERE j.status = 'doing' "
                "AND NOT EXISTS (SELECT 1 FROM procrastinate_events e WHERE e.job_id = j.id "
                "AND e.at > now() - interval '1 hour')"
            )
        ).scalar_one()
        return {
            "queues": [{"queue": q, "status": st, "count": n} for q, st, n in rows],
            "stalled": stalled,
        }

    results = {
        "postgres": _probe(session, postgres),
        "s3": _probe(session, object_store),
        "cdc": _probe(session, cdc),
        "jobs": _probe(session, jobs),
    }
    return {
        "checkedAt": datetime.now(UTC).isoformat(),
        # Console MinIO atteignable seulement si son port est publié sur
        # l'hôte (base: oui ; overlay prod: non) — P17.04, j08b-009. Ici et
        # non sur /instance : celui-ci est miroir de /me.capabilities.
        "minioConsolePublished": os.environ.get("CORE_MINIO_CONSOLE_PUBLISHED", "false").lower()
        == "true",
        **results,
    }
