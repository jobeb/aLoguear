"""Tests del lock anti-solape (task_lock): multiplataforma, sin GUI."""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import task_lock


def test_acquire_release(tmp_path):
    log_dir = str(tmp_path)
    ok, info = task_lock.acquire("abc123", log_dir=log_dir)
    assert ok and info is None
    assert os.path.exists(os.path.join(log_dir, "abc123.lock"))
    task_lock.release("abc123", log_dir=log_dir)
    assert not os.path.exists(os.path.join(log_dir, "abc123.lock"))


def test_second_acquire_fails_while_first_alive(tmp_path):
    log_dir = str(tmp_path)
    ok, _ = task_lock.acquire("abc123", log_dir=log_dir)
    assert ok
    try:
        ok2, info2 = task_lock.acquire("abc123", log_dir=log_dir)
        assert not ok2
        assert isinstance(info2, dict) and info2["pid"] == os.getpid()
    finally:
        task_lock.release("abc123", log_dir=log_dir)


def test_release_only_removes_own_lock(tmp_path):
    log_dir = str(tmp_path)
    other = {"pid": 987654321, "started_at": datetime.datetime.now().isoformat()}
    path = os.path.join(log_dir, "abc123.lock")
    os.makedirs(log_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(other, f)
    task_lock.release("abc123", log_dir=log_dir)
    assert os.path.exists(path)  # no era nuestro: se respeta


def test_stale_lock_with_dead_pid_is_replaced(tmp_path):
    log_dir = str(tmp_path)
    stale = {"pid": 999999999, "started_at": datetime.datetime.now().isoformat()}
    path = os.path.join(log_dir, "abc123.lock")
    os.makedirs(log_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stale, f)
    ok, _ = task_lock.acquire("abc123", log_dir=log_dir)
    assert ok
    task_lock.release("abc123", log_dir=log_dir)


def test_corrupt_lock_is_replaced(tmp_path):
    log_dir = str(tmp_path)
    path = os.path.join(log_dir, "abc123.lock")
    os.makedirs(log_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("esto no es json{{{")
    ok, _ = task_lock.acquire("abc123", log_dir=log_dir)
    assert ok
    task_lock.release("abc123", log_dir=log_dir)


def test_context_manager_releases(tmp_path):
    log_dir = str(tmp_path)
    with task_lock.held_task_lock("abc123", log_dir=log_dir) as (ok, _info):
        assert ok
        assert os.path.exists(os.path.join(log_dir, "abc123.lock"))
    assert not os.path.exists(os.path.join(log_dir, "abc123.lock"))


def test_is_pid_running_current_process():
    assert task_lock.is_pid_running(os.getpid())
    assert not task_lock.is_pid_running(999999999)
    assert not task_lock.is_pid_running(-5)
    assert not task_lock.is_pid_running("no-un-pid")
