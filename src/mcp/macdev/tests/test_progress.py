# -*- coding: utf-8 -*-
"""ScanBudget（扫描进度 + 超时截断子集汇报）单测。"""
import time

from macdev.core.progress import ScanBudget


def test_tick_progress_reports_total_once(capsys):
    b = ScanBudget(3, "t")
    for _ in range(3):
        b.tick()
    out = capsys.readouterr().out
    assert "t: 3/3" in out
    # 超过 total 不再重复打印 total 行
    b.tick()
    out2 = capsys.readouterr().out
    assert "3/3" not in out2


def test_tick_progress_interval(capsys):
    b = ScanBudget(1000, "t", interval=200)
    for i in range(1, 201):
        b.tick()
    out = capsys.readouterr().out
    assert "t: 200/1000" in out


def test_quiet_no_output(capsys):
    b = ScanBudget(3, "t", quiet=True)
    for _ in range(3):
        b.tick()
    assert capsys.readouterr().out == ""


def test_expired_after_timeout():
    b = ScanBudget(100, "t", timeout=0.01)
    time.sleep(0.02)
    assert b.expired() is True
    assert b.truncated is True


def test_not_expired_within_timeout():
    b = ScanBudget(100, "t", timeout=5)
    assert b.expired() is False


def test_reset():
    b = ScanBudget(3, "a")
    for _ in range(3):
        b.tick()
    assert b.done == 3
    b.reset(10, "b")
    assert b.done == 0 and b.label == "b" and b.total == 10
    assert b.truncated is False


def test_summary_clamps_scanned():
    b = ScanBudget(3, "t")
    for _ in range(6):
        b.tick()
    s = b.summary()
    assert s["scanned"] == 3 and s["total"] == 3 and s["truncated"] is False
