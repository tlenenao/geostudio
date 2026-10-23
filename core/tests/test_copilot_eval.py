# SPDX-License-Identifier: Apache-2.0
"""AUD-104 : le jeu d'évaluation hors ligne du copilote tient son plancher (100 %)."""

from scripts import copilot_eval


def test_offline_eval_floor_is_100_percent():
    cases = copilot_eval.load_cases()
    assert len(cases) >= 25
    failures = [(cid, detail) for cid, ok, detail in copilot_eval.run_offline(cases) if not ok]
    assert not failures, failures


def test_eval_detects_a_regressed_guard(monkeypatch):
    # Falsification : un validateur qui accepte tout doit faire échouer le jeu.
    monkeypatch.setattr(copilot_eval, "check", lambda case, reply: None)
    results = copilot_eval.run_offline(copilot_eval.load_cases())
    assert any(not ok for _, ok, _ in results)
