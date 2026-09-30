"""watermark_manager.py: safe watermark handling (spec sections 15, 54)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from notebooks.bronze import watermark_manager as wm
from notebooks.bronze.error_manager import MetadataError, WatermarkConflictError


def test_format_and_parse_round_trip_per_type():
    ts = datetime(2026, 9, 30, 8, 5, 13, 123456)
    assert wm.format_watermark(ts, "DATETIME") == "2026-09-30 08:05:13.123456"
    assert wm.parse_watermark("2026-09-30 08:05:13.123456", "DATETIME") == ts
    assert wm.parse_watermark("2026-09-30T08:05:13", "DATETIME") == datetime(2026, 9, 30, 8, 5, 13)
    aware = datetime(2026, 9, 30, 9, 5, 13, tzinfo=timezone(timedelta(hours=1)))
    assert wm.format_watermark(aware, "DATETIME") == "2026-09-30 08:05:13.000000"   # stored in UTC
    assert wm.format_watermark(Decimal("1E+3"), "NUMERIC") == "1000"
    assert wm.parse_watermark("42.50", "NUMERIC") == Decimal("42.5")
    assert wm.format_watermark("K-0009", "STRING") == "K-0009"
    with pytest.raises(MetadataError):
        wm.parse_watermark("yesterday", "DATETIME")


def test_resolve_never_moves_backwards_and_keeps_value_on_empty_batch():
    before = "2026-09-30 08:00:00.000000"
    assert wm.resolve_watermark_after(before, None, "DATETIME") == before
    assert wm.resolve_watermark_after(before, datetime(2026, 9, 29), "DATETIME") == before
    assert wm.resolve_watermark_after(before, datetime(2026, 9, 30, 9), "DATETIME") == "2026-09-30 09:00:00.000000"
    assert wm.resolve_watermark_after(None, 17, "NUMERIC") == "17"
    assert wm.resolve_watermark_after("9", 10, "NUMERIC") == "10"     # numeric, not lexical, compare


class FakeCursor:
    def __init__(self, stored, exists=True):
        self.stored, self.exists = stored, exists
        self.rowcount = 0
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        if sql.startswith("UPDATE"):
            new, run_id, erid, _now, _eid, expected, _ = params
            if self.exists and self.stored == expected:
                self.stored, self.rowcount = new, 1
            else:
                self.rowcount = 0
        elif sql.startswith("INSERT"):
            self.exists, self.stored = True, params[1]

    def fetchone(self):
        return (self.stored,) if self.exists else None


class FakeConn:
    def __init__(self, cursor):
        self._cursor, self.closed = cursor, False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _manager(cursor):
    return wm.WatermarkManager(lambda: FakeConn(cursor))


def test_commit_is_guarded_by_the_value_read_at_start(customer):
    cursor = FakeCursor("2026-09-01 00:00:00.000000")
    assert _manager(cursor).commit(customer, "2026-09-01 00:00:00.000000", "2026-09-30 00:00:00.000000",
                                   "run-1", "run-1-E101") is True
    assert cursor.stored == "2026-09-30 00:00:00.000000"


def test_commit_conflict_never_overwrites(customer):
    cursor = FakeCursor("2026-09-15 00:00:00.000000")   # another run moved it
    with pytest.raises(WatermarkConflictError):
        _manager(cursor).commit(customer, "2026-09-01 00:00:00.000000", "2026-09-30 00:00:00.000000", "r", "r-E1")
    assert cursor.stored == "2026-09-15 00:00:00.000000"


def test_commit_no_op_and_missing_row(customer):
    cursor = FakeCursor("x")
    assert _manager(cursor).commit(customer, "x", "x", "r", "r-E1") is False
    assert cursor.executed == []

    missing = FakeCursor(None, exists=False)
    assert _manager(missing).commit(customer, None, "2026-09-30 00:00:00.000000", "r", "r-E1") is True
    assert missing.stored == "2026-09-30 00:00:00.000000"


def test_get_reads_current_value(customer):
    assert _manager(FakeCursor("2026-09-01 00:00:00.000000")).get(101) == "2026-09-01 00:00:00.000000"
    assert _manager(FakeCursor(None, exists=False)).get(101) is None
