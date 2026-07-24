# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta

from retention import select_files_to_delete


def _name(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S") + ".tar.gz.age"


def test_daily_window_of_7_is_never_deleted():
    now = datetime(2026, 7, 24, 3, 0, 0)
    names = [_name(now - timedelta(days=i)) for i in range(7)]
    assert select_files_to_delete(names, now) == []


def test_keeps_4_most_recent_distinct_older_weeks_deletes_rest():
    now = datetime(2026, 7, 24, 3, 0, 0)
    # 14, 21, ..., 63 jours en arrière — 8 semaines ISO distinctes, toutes
    # hors de la fenêtre quotidienne de 7 jours.
    names = [_name(now - timedelta(weeks=w)) for w in range(2, 10)]
    deleted = select_files_to_delete(names, now)
    kept = [n for n in names if n not in deleted]
    assert set(kept) == set(names[:4])
    assert set(deleted) == set(names[4:])


def test_ignores_filenames_not_matching_the_naming_pattern():
    now = datetime(2026, 7, 24, 3, 0, 0)
    assert select_files_to_delete(["notes.txt", "backup.tar.gz"], now) == []
