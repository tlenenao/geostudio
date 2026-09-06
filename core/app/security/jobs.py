# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate périodique : recalcule l'allowlist CSP dynamique
(SP-48/GAP-72) et écrit le fragment de configuration Traefik (provider
fichier) qui la porte. Reproduit le patron exact des tâches @app.periodic
existantes (app/reports/jobs.py::sweep_report_schedules_task) — même
queue ("etl"), même cadence ("*/5 * * * *"), même app.jobs.common.
session_factory().

CSP_DYNAMIC_CONF_PATH est une CONSTANTE, pas un réglage d'environnement
(spec SP-48 §2.4, décision explicite : « pas de nouvelle variable
d'environnement, juste une constante de chemin partagée entre la tâche
périodique et la commande Traefik ») — le chemin doit être identique des
deux côtés du volume nommé csp-dynamic-conf, jamais reréglable
indépendamment l'un de l'autre."""

import logging
import os

from app.db import request_scoped_session
from app.jobs import app
from app.jobs.common import session_factory as _session_factory
from app.security.service import compute_csp_allowlist
from app.security.traefik_render import render_dynamic_conf

logger = logging.getLogger(__name__)

CSP_DYNAMIC_CONF_PATH = "/csp-dynamic/dynamic-conf.yml"


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def refresh_csp_dynamic_conf_task(timestamp: int) -> None:
    mode = os.environ.get("CORE_CSP_MODE", "report-only")
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        allowlist = compute_csp_allowlist(session)
    rendered = render_dynamic_conf(allowlist, mode=mode)
    os.makedirs(os.path.dirname(CSP_DYNAMIC_CONF_PATH), exist_ok=True)
    with open(CSP_DYNAMIC_CONF_PATH, "w") as f:
        f.write(rendered)
    logger.info(
        "allowlist CSP recalculée (mode=%s) : %d hôte(s) img/connect, %d hôte(s) script "
        "(calculés, jamais enforcés — blocage 3 ouvert)",
        mode,
        len(allowlist.img_hosts),
        len(allowlist.script_hosts),
    )
