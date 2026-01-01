"""Unit tests for path utilities."""

from pathlib import Path

import pytest

from agentbench.util.paths import ensure_dir


class TestEnsureDir:
    """Tests for ensure_dir function."""

    def test_ensure_dir_creates_new_directory(self, tmp_path: Path):
        """ensure_dir creates directory if it doesn't exist."""
        new_dir = tmp_path / "new_directory"
        assert not new_dir.exists()

        result = ensure_dir(new_dir)

        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir

    def test_ensure_dir_creates_nested_directories(self, tmp_path: Path):
        """ensure_dir creates nested directories."""
        nested_dir = tmp_path / "a" / "b" / "c" / "d"
        assert not nested_dir.exists()

        result = ensure_dir(nested_dir)

        assert nested_dir.exists()
        assert nested_dir.is_dir()
        assert result == nested_dir

    def test_ensure_dir_handles_existing_directory(self, tmp_path: Path):
        """ensure_dir succeeds for existing directory."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        assert existing_dir.exists()

        result = ensure_dir(existing_dir)

        assert existing_dir.exists()
        assert result == existing_dir

    def test_ensure_dir_returns_path(self, tmp_path: Path):
        """ensure_dir returns the Path object."""
        new_dir = tmp_path / "new_dir"

        result = ensure_dir(new_dir)

        assert isinstance(result, Path)
        assert result == new_dir

    def test_ensure_dir_with_file_path_raises_error(self, tmp_path: Path):
        """ensure_dir raises error when path is a file."""
        file_path = tmp_path / "existing_file.txt"
        file_path.write_text("content")

        with pytest.raises((FileExistsError, NotADirectoryError)):
            ensure_dir(file_path)

    def test_ensure_dir_is_idempotent(self, tmp_path: Path):
        """Calling ensure_dir multiple times succeeds."""
        new_dir = tmp_path / "idempotent_dir"

        result1 = ensure_dir(new_dir)
        result2 = ensure_dir(new_dir)
        result3 = ensure_dir(new_dir)

        assert result1 == result2 == result3 == new_dir
        assert new_dir.exists()
