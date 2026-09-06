# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.configs.schemas import app_config_json_schema

router = APIRouter()


@router.get("/schemas/app-config")
def get_app_config_schema() -> dict:
    return app_config_json_schema()
