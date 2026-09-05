# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends

from app.auth.dependency import get_current_user
from app.catalog import metadata
from app.catalog.schemas import (
    FrequencyCatalogEntry,
    LanguageCatalogEntry,
    LicenseCatalogEntry,
    MetadataCatalog,
)
from app.users.models import User

router = APIRouter()


@router.get("/metadata-catalog", response_model=MetadataCatalog)
def get_metadata_catalog(user: User = Depends(get_current_user)) -> MetadataCatalog:
    return MetadataCatalog(
        licenses=[
            LicenseCatalogEntry(id=e.id, label=e.label, dcatUri=e.dcat_uri, spdxId=e.spdx_id)
            for e in metadata.LICENSES
        ],
        frequencies=[FrequencyCatalogEntry(id=e.id, label=e.label) for e in metadata.FREQUENCIES],
        languages=[LanguageCatalogEntry(id=e.id, label=e.label) for e in metadata.LANGUAGES],
    )
