"""Tests for soma.store — InMemoryStore and JSONFileStore."""

import json
import pytest
from soma.store import InMemoryStore, JSONFileStore


# ---------------------------------------------------------------------------
# InMemoryStore
# ---------------------------------------------------------------------------

def test_inmemory_set_and_get():
    s = InMemoryStore()
    s.set("foo", 42)
    assert s.get("foo") == 42


def test_inmemory_missing_returns_none():
    s = InMemoryStore()
    assert s.get("nope") is None


def test_inmemory_overwrite():
    s = InMemoryStore()
    s.set("k", "first")
    s.set("k", "second")
    assert s.get("k") == "second"


def test_inmemory_delete():
    s = InMemoryStore()
    s.set("k", "v")
    s.delete("k")
    assert s.get("k") is None


def test_inmemory_delete_missing_no_error():
    s = InMemoryStore()
    s.delete("nonexistent")  # should not raise


def test_inmemory_keys():
    s = InMemoryStore()
    s.set("a", 1)
    s.set("b", 2)
    assert set(s.keys()) == {"a", "b"}


def test_inmemory_keys_after_delete():
    s = InMemoryStore()
    s.set("a", 1)
    s.set("b", 2)
    s.delete("a")
    assert s.keys() == ["b"]


# ---------------------------------------------------------------------------
# JSONFileStore
# ---------------------------------------------------------------------------

def test_jsonfile_roundtrip(tmp_path):
    path = tmp_path / "store.json"
    s = JSONFileStore(path)
    s.set("hello", "world")
    s.set("num", 99)
    s.save()

    # Re-open from disk
    s2 = JSONFileStore(path)
    assert s2.get("hello") == "world"
    assert s2.get("num") == 99


def test_jsonfile_auto_load(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text(json.dumps({"pre": "loaded"}))

    s = JSONFileStore(path)
    assert s.get("pre") == "loaded"


def test_jsonfile_missing_key_returns_none(tmp_path):
    path = tmp_path / "empty.json"
    s = JSONFileStore(path)
    assert s.get("absent") is None


def test_jsonfile_delete(tmp_path):
    path = tmp_path / "store.json"
    s = JSONFileStore(path)
    s.set("x", 1)
    s.delete("x")
    assert s.get("x") is None


def test_jsonfile_keys(tmp_path):
    path = tmp_path / "store.json"
    s = JSONFileStore(path)
    s.set("a", 1)
    s.set("b", 2)
    assert set(s.keys()) == {"a", "b"}


def test_jsonfile_overwrite(tmp_path):
    path = tmp_path / "store.json"
    s = JSONFileStore(path)
    s.set("k", "old")
    s.set("k", "new")
    s.save()

    s2 = JSONFileStore(path)
    assert s2.get("k") == "new"
