"""Tests for notification improvements — read context, severity, positive feedback."""

from soma.hooks.notification import _analyze_patterns


class TestReadContextAwareness:
    def test_edit_after_read_same_file_no_warning(self):
        """Editing a file that was recently Read should NOT warn."""
        log = [
            {"tool": "Read", "error": False, "file": "/project/src/auth.py", "ts": 1},
            {"tool": "Read", "error": False, "file": "/project/src/models.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 5},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 6},
        ]
        tips = _analyze_patterns(log)
        assert not any("edit" in t.lower() and "without" in t.lower() for t in tips)
        assert not any("blind" in t.lower() for t in tips)

    def test_edit_without_read_warns(self):
        """Editing files never Read SHOULD warn."""
        log = [
            {"tool": "Edit", "error": False, "file": "/project/src/new.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/project/src/other.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert any("blind" in t.lower() or ("edit" in t.lower() and "without" in t.lower()) for t in tips)

    def test_read_directory_covers_files(self):
        """Reading files in a directory covers edits to other files in same dir."""
        log = [
            {"tool": "Read", "error": False, "file": "/project/src/auth/login.py", "ts": 1},
            {"tool": "Read", "error": False, "file": "/project/src/auth/types.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/middleware.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/login.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/types.py", "ts": 5},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)

    def test_write_new_file_no_warning(self):
        """Write (creating new files) should never trigger 'edit without read'."""
        log = [
            {"tool": "Write", "error": False, "file": "/project/new_file.py", "ts": 1},
            {"tool": "Write", "error": False, "file": "/project/another.py", "ts": 2},
            {"tool": "Write", "error": False, "file": "/project/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)

    def test_grep_counts_as_read_context(self):
        """Grep/Glob provide read context too."""
        log = [
            {"tool": "Grep", "error": False, "file": "/project/src/auth.py", "ts": 1},
            {"tool": "Glob", "error": False, "file": "/project/src/models.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 5},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)
