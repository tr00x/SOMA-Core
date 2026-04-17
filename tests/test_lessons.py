"""Tests for cross-session lesson memory."""

from soma.lessons import LessonStore


def test_record_and_query(tmp_path):
    store = LessonStore(path=tmp_path / "lessons.json")
    store.record(
        pattern="permission_denied",
        error_text="Permission denied: /etc/shadow",
        fix_text="Used sudo",
        tool="Bash",
    )
    lessons = store.query(error_text="Permission denied: /etc/foo")
    assert len(lessons) == 1
    assert "sudo" in lessons[0]["fix"]


def test_no_match(tmp_path):
    store = LessonStore(path=tmp_path / "lessons.json")
    store.record(pattern="permission_denied", error_text="Permission denied", fix_text="sudo", tool="Bash")
    lessons = store.query(error_text="SyntaxError: unexpected indent")
    assert len(lessons) == 0


def test_persistence(tmp_path):
    path = tmp_path / "lessons.json"
    store1 = LessonStore(path=path)
    store1.record(pattern="timeout", error_text="Timeout error occurred", fix_text="increased timeout", tool="Bash")
    store2 = LessonStore(path=path)  # reload
    assert len(store2.query(error_text="Timeout error occurred")) == 1


def test_max_lessons(tmp_path):
    store = LessonStore(path=tmp_path / "lessons.json", max_lessons=5)
    for i in range(10):
        store.record(pattern=f"p{i}", error_text=f"err{i} problem", fix_text=f"fix{i}", tool="Bash")
    assert len(store._lessons) == 5  # oldest evicted
