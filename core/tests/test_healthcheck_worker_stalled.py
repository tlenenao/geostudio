# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité pour worker/export-worker (GAP-76, SP-49).

Contrairement à `procrastinate --app app.jobs.app healthchecks` (connexion +
schéma seulement), cette sonde détecte un job resté en 'doing' plus
longtemps qu'un seuil — même limite que celle documentée pour cdc-worker
avant sa propre sonde dédiée (scripts/healthcheck_cdc.py). L'API réelle
`JobManager.get_stalled_jobs` est `async def` sans variante synchrone
exposée sur cette version verrouillée de procrastinate (3.9.0, vérifié par
introspection en session — cf. commentaire du module) : le script encapsule
`asyncio.run(...)`, mais reste un `main()` synchrone testable comme
`healthcheck_cdc.main`."""

import scripts.healthcheck_worker_stalled as healthcheck


def test_main_returns_1_when_jobs_are_stalled(monkeypatch):
    async def _fetch(threshold_seconds, queue):
        return ["job-1", "job-2"]

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    assert healthcheck.main() == 1


def test_main_returns_0_when_no_job_is_stalled(monkeypatch):
    async def _fetch(threshold_seconds, queue):
        return []

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    assert healthcheck.main() == 0


def test_main_returns_1_and_does_not_raise_on_connection_error(monkeypatch):
    async def _fetch(threshold_seconds, queue):
        raise RuntimeError("connexion refusée")

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    assert healthcheck.main() == 1  # une sonde ne doit jamais lever, seulement échouer


def test_main_reads_threshold_and_queue_from_environment(monkeypatch):
    captured = {}

    async def _fetch(threshold_seconds, queue):
        captured["threshold_seconds"] = threshold_seconds
        captured["queue"] = queue
        return []

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    monkeypatch.setenv("HEALTHCHECK_STALLED_SECONDS", "120")
    monkeypatch.setenv("HEALTHCHECK_QUEUE", "export")
    assert healthcheck.main() == 0
    assert captured == {"threshold_seconds": 120, "queue": "export"}


def test_main_defaults_heartbeat_threshold_to_five_minutes_and_queue_to_none(monkeypatch):
    captured = {}

    async def _fetch(threshold_seconds, queue):
        captured["threshold_seconds"] = threshold_seconds
        captured["queue"] = queue
        return []

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    monkeypatch.delenv("HEALTHCHECK_STALLED_SECONDS", raising=False)
    monkeypatch.delenv("HEALTHCHECK_QUEUE", raising=False)
    assert healthcheck.main() == 0
    assert captured == {"threshold_seconds": 300, "queue": None}


def test_fetch_uses_worker_heartbeats_not_job_start_time(monkeypatch):
    """AUD-016 : `nb_seconds` (déprécié) compte depuis le démarrage du job — un job sain
    de plus d'une heure rendait la sonde rouge (CrashLoop Helm)."""
    import asyncio

    seen = {}

    class _JobManager:
        async def get_stalled_jobs(self, **kwargs):
            seen.update(kwargs)
            return []

    class _Opened:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(healthcheck.app, "open_async", lambda: _Opened())
    monkeypatch.setattr(healthcheck.app, "job_manager", _JobManager())
    assert asyncio.run(healthcheck._fetch_stalled(300, "export")) == []
    assert seen == {"queue": "export", "seconds_since_heartbeat": 300}
