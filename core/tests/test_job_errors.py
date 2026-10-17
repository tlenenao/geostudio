# SPDX-License-Identifier: Apache-2.0
from app.job_errors import INTERNAL_ERROR_MESSAGE, public_error


def test_unexpected_error_never_reaches_the_user():
    exc = RuntimeError("(psycopg.errors.DuplicateColumn) [SQL: CREATE TABLE public.ingest_x ...]")
    assert public_error(exc) == INTERNAL_ERROR_MESSAGE
    assert "SQL" not in INTERNAL_ERROR_MESSAGE


def test_declared_user_errors_pass_through_bounded():
    assert public_error(ValueError("trop d'entités"), user_errors=(ValueError,)) == "trop d'entités"
    assert len(public_error(ValueError("x" * 2000), user_errors=(ValueError,))) == 500
