# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.csw import CswConnector
from app.harvest.connectors.ogc_records import OgcRecordsConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wfs import WfsConnector
from app.harvest.connectors.wms import WmsConnector
from app.harvest.connectors.wmts import WmtsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
    "wfs": WfsConnector(),
    "wmts": WmtsConnector(),
    "csw": CswConnector(),
    "ogc-records": OgcRecordsConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
