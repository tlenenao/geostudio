# SPDX-License-Identifier: Apache-2.0
"""`.defer()` procrastinate tolérant aux pannes brèves du pool (AUD-025)."""

import logging
import time
from collections.abc import Callable

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def defer_resilient(call: Callable[[], object], *, attempts: int = 3, delay: float = 0.2) -> None:
    for i in range(attempts):
        try:
            call()
            return
        except Exception:
            logger.warning("defer échoué (tentative %d/%d)", i + 1, attempts, exc_info=True)
            if i + 1 < attempts:
                time.sleep(delay * 2**i)
    raise HTTPException(status_code=503, detail="File de jobs indisponible, réessayez.")
