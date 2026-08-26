# SPDX-License-Identifier: Apache-2.0
"""Teste uniquement le mécanisme d'arrêt (signal -> flag -> should_stop),
pas run() en entier — qui exige un DSN CDC_DATABASE_URL et un client S3
réels (cf. main.py::_write_and_upload, testée séparément pour la même
raison)."""

import signal

from app.cdc import main as cdc_main


def test_sigterm_sets_the_stop_flag():
    state = cdc_main._ShutdownState()
    assert state.should_stop() is False
    state.handle_sigterm(signal.SIGTERM, None)
    assert state.should_stop() is True
