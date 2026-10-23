# SPDX-License-Identifier: Apache-2.0
"""AUD-123 : les budgets de débit sont verrouillés par valeur (mutant survivant)."""

import pytest

from app.ratelimit.limiter import _BUDGETS, RateLimiter

# Valeurs attendues : tout changement de budget est une décision à acter ici.
EXPECTED = {
    "sql": 10,
    "analytics": 120,
    "llm": 120,
    "jobs": 15,
    "harvest": 10,
    "collections_empty": 5,
    "webhook-trigger": 30,
    "share-link": 60,
    "geocode": 60,
    "public-submit": 20,
    "ogc-read": 600,
    "discovery": 120,
    "tiles": 3000,
    "zonal": 10,
    "routing": 100,
}


def test_every_budget_is_pinned():
    assert _BUDGETS == EXPECTED


@pytest.mark.parametrize("group", sorted(EXPECTED))
def test_budget_plus_one_is_refused(group):
    lim = RateLimiter()
    budget = EXPECTED[group]
    results = [lim.allow("Bearer t", group) for _ in range(budget + 1)]
    assert results == [True] * budget + [False]
