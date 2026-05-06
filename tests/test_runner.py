"""Tests for runner helpers (dirty-tree detection, etc).

Full end-to-end runner tests would require a real provider or extensive
mocking; that is intentionally out of scope. These tests cover the pure
helpers in runner.py.
"""

from __future__ import annotations

from bellwether.runner import DIRTY_IGNORE_UNTRACKED_PREFIXES, is_dirty_status


def test_is_dirty_empty_status_is_clean():
    assert not is_dirty_status("")


def test_is_dirty_only_untracked_results_is_clean():
    assert not is_dirty_status("?? results/2026-05-06/foo.json\n?? results/bar.json\n")


def test_is_dirty_only_untracked_docs_is_clean():
    assert not is_dirty_status("?? docs/index.html\n?? docs/methodology.html\n?? docs/.nojekyll\n")


def test_is_dirty_mixed_results_and_docs_is_clean():
    assert not is_dirty_status("?? results/foo.json\n?? docs/index.html\n")


def test_is_dirty_modified_source_is_dirty():
    assert is_dirty_status(" M src/bellwether/runner.py\n")


def test_is_dirty_staged_source_is_dirty():
    assert is_dirty_status("M  src/bellwether/runner.py\n")


def test_is_dirty_added_is_dirty():
    assert is_dirty_status("A  src/bellwether/new.py\n")


def test_is_dirty_deleted_is_dirty():
    assert is_dirty_status(" D src/bellwether/old.py\n")


def test_is_dirty_untracked_outside_artifact_dirs_is_dirty():
    assert is_dirty_status("?? src/bellwether/scratch.py\n")


def test_is_dirty_untracked_at_repo_root_is_dirty():
    assert is_dirty_status("?? scratch.py\n")


def test_is_dirty_mixed_artifact_and_real_dirt_is_dirty():
    """If there's any real dirt, ignored artifacts don't make it clean."""
    assert is_dirty_status("?? results/foo.json\n M src/bellwether/runner.py\n")


def test_is_dirty_artifact_dir_lookalike_is_dirty():
    """A path that starts with 'resultsfoo/' is NOT under 'results/' — must be dirty."""
    assert is_dirty_status("?? resultsfoo/bar.json\n")


def test_is_dirty_quoted_path_with_special_chars():
    """Git porcelain quotes paths with spaces or special chars; we strip the quotes."""
    assert not is_dirty_status('?? "results/with space/foo.json"\n')


def test_dirty_ignore_prefixes_is_documented_in_module():
    """Constant is exported so callers can introspect or extend in tests."""
    assert "results/" in DIRTY_IGNORE_UNTRACKED_PREFIXES
    assert "docs/" in DIRTY_IGNORE_UNTRACKED_PREFIXES
