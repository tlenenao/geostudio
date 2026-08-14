# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_etl_enabled, is_export_enabled, is_read_only_mode, is_tileset3d_enabled

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
    }
