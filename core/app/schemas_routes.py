from fastapi import APIRouter

from app.configs.schemas import BuilderConfig

router = APIRouter()


@router.get("/schemas/app-config")
def get_app_config_schema() -> dict:
    return BuilderConfig.model_json_schema()
