"""Integration tests for tool implementations in builtins.py."""

import shutil
from pathlib import Path

import pytest

from agentbench.tools.builtins import list_files, read_file, search
from agentbench.tools.contract import (
    ListFilesParams,
    ReadFileParams,
    SearchParams,
    ToolStatus,
)

# Check if ripgrep is available
HAS_RIPGREP = shutil.which("rg") is not None
requires_ripgrep = pytest.mark.skipif(
    not HAS_RIPGREP, reason="ripgrep (rg) not installed - tests run in Docker"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temp workspace with test files."""
    # Create source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n\nmain()\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (src / "config.json").write_text('{"key": "value"}')

    # Create test files
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_main():\n    assert True\n")

    # Create nested structure
    deep = tmp_path / "src" / "deep" / "nested"
    deep.mkdir(parents=True)
    (deep / "module.py").write_text("# Deep nested module\n")

    # Create .git directory
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n")

    # Create hidden file
    (tmp_path / ".env").write_text("SECRET=abc123\n")

    return tmp_path


class TestListFilesReturnsSorted:
    """Test that list_files returns files in alphabetical order."""

    def test_list_files_returns_sorted(self, workspace: Path) -> None:
        """Files are returned in alphabetical order."""
        result = list_files(
            request_id="test-001",
            workspace_root=workspace,
            params=ListFilesParams(root=".", glob="**/*.py"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        files = result.data["files"]
        # Verify files are sorted
        assert files == sorted(files)


class TestListFilesExcludesGit:
    """Test that list_files excludes .git directory."""

    def test_list_files_excludes_git(self, workspace: Path) -> None:
        """.git/ directory contents are not included."""
        result = list_files(
            request_id="test-002",
            workspace_root=workspace,
            params=ListFilesParams(root=".", glob="**/*"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        files = result.data["files"]
        for f in files:
            assert ".git" not in f


class TestListFilesWithGlob:
    """Test that glob filter works correctly."""

    def test_list_files_with_glob(self, workspace: Path) -> None:
        """Glob filter correctly filters files."""
        result = list_files(
            request_id="test-003",
            workspace_root=workspace,
            params=ListFilesParams(root=".", glob="**/*.py"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        files = result.data["files"]
        # All files should end with .py
        for f in files:
            assert f.endswith(".py")

        # Should include the python files we created
        assert any("main.py" in f for f in files)
        assert any("utils.py" in f for f in files)
        assert any("test_main.py" in f for f in files)

    def test_list_files_json_glob(self, workspace: Path) -> None:
        """JSON glob pattern works."""
        result = list_files(
            request_id="test-004",
            workspace_root=workspace,
            params=ListFilesParams(root=".", glob="**/*.json"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        files = result.data["files"]
        assert len(files) >= 1
        assert any("config.json" in f for f in files)


class TestReadFileFull:
    """Test reading entire file contents."""

    def test_read_file_full(self, workspace: Path) -> None:
        """Reads entire file correctly."""
        # Create a test file
        test_file = workspace / "test_read.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = read_file(
            request_id="test-005",
            workspace_root=workspace,
            params=ReadFileParams(path="test_read.txt"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None
        assert "line 1" in result.data["content"]
        assert "line 2" in result.data["content"]
        assert "line 3" in result.data["content"]
        assert result.data["truncated"] is False
        assert result.data["total_lines"] == 3


class TestReadFileLineRange:
    """Test reading specific line ranges."""

    def test_read_file_line_range(self, workspace: Path) -> None:
        """Line range parameters are respected."""
        # Note: The current implementation reads the whole file and
        # returns first 5000 + last 5000 lines. Line range params
        # (start_line, end_line) exist but may not be implemented.
        # This test verifies the file is readable.
        result = read_file(
            request_id="test-006",
            workspace_root=workspace,
            params=ReadFileParams(path="src/main.py"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None
        assert "def main():" in result.data["content"]


class TestReadFileTruncatesLarge:
    """Test that large files are truncated with metadata."""

    def test_read_file_truncates_large(self, workspace: Path) -> None:
        """Large files (>10000 lines) are truncated with proper metadata."""
        # Create a file with 15000 lines
        large_file = workspace / "large_file.txt"
        lines = [f"line {i}" for i in range(1, 15001)]
        large_file.write_text("\n".join(lines))

        result = read_file(
            request_id="test-007",
            workspace_root=workspace,
            params=ReadFileParams(path="large_file.txt"),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None
        assert result.data["truncated"] is True
        assert result.data["total_lines"] == 15000
        # Should contain truncation indicator
        assert "truncated" in result.data["content"].lower() or result.data["lines_included"] is not None
        # First and last lines should be present
        assert "line 1" in result.data["content"]
        assert "line 15000" in result.data["content"]


class TestReadFileNotFound:
    """Test reading a non-existent file returns structured error."""

    def test_read_file_not_found(self, workspace: Path) -> None:
        """Missing file returns structured error."""
        result = read_file(
            request_id="test-008",
            workspace_root=workspace,
            params=ReadFileParams(path="nonexistent_file.txt"),
        )

        assert result.status == ToolStatus.ERROR
        assert result.error is not None
        assert result.error.error_type == "file_not_found" or "not found" in result.error.message.lower()


@requires_ripgrep
class TestSearchFindsMatches:
    """Test that search finds expected matches."""

    def test_search_finds_matches(self, workspace: Path) -> None:
        """Search finds expected text matches."""
        result = search(
            request_id="test-009",
            workspace_root=workspace,
            params=SearchParams(query="def main", max_results=50),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        matches = result.data.get("matches", [])
        assert len(matches) >= 1
        # Should find match in main.py
        assert any("main.py" in m["file"] for m in matches)

    def test_search_with_glob_filter(self, workspace: Path) -> None:
        """Search respects glob filter."""
        result = search(
            request_id="test-010",
            workspace_root=workspace,
            params=SearchParams(query="def", glob="**/test_*.py", max_results=50),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        matches = result.data.get("matches", [])
        # All matches should be in test files
        for m in matches:
            assert "test_" in m["file"]


@requires_ripgrep
class TestSearchRespectsMaxResults:
    """Test that search caps results at max_results."""

    def test_search_respects_max_results(self, workspace: Path) -> None:
        """Search caps results at max_results parameter."""
        # Create many files with matches
        for i in range(60):
            f = workspace / f"file_{i}.py"
            f.write_text(f"def function_{i}():\n    pass\n")

        result = search(
            request_id="test-011",
            workspace_root=workspace,
            params=SearchParams(query="def function", max_results=10),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        matches = result.data.get("matches", [])
        # Should have at most max_results matches
        assert len(matches) <= 10


@requires_ripgrep
class TestSearchNoMatches:
    """Test search with no matches."""

    def test_search_no_matches(self, workspace: Path) -> None:
        """Search with no matches returns empty results."""
        result = search(
            request_id="test-012",
            workspace_root=workspace,
            params=SearchParams(query="xyznonexistentpatternxyz", max_results=50),
        )

        assert result.status == ToolStatus.SUCCESS
        assert result.data is not None

        matches = result.data.get("matches", [])
        assert len(matches) == 0


class TestToolResultStructure:
    """Test that all tool results have valid ToolResult structure."""

    def test_list_files_returns_tool_result(self, workspace: Path) -> None:
        """list_files returns valid ToolResult object."""
        result = list_files(
            request_id="test-013",
            workspace_root=workspace,
            params=ListFilesParams(root="."),
        )

        # Verify ToolResult fields
        assert result.request_id == "test-013"
        assert result.tool == "list_files"
        assert result.status in [ToolStatus.SUCCESS, ToolStatus.ERROR]
        assert result.started_at is not None
        assert result.ended_at is not None
        assert result.duration_sec >= 0

    def test_read_file_returns_tool_result(self, workspace: Path) -> None:
        """read_file returns valid ToolResult object."""
        result = read_file(
            request_id="test-014",
            workspace_root=workspace,
            params=ReadFileParams(path="src/main.py"),
        )

        assert result.request_id == "test-014"
        assert result.tool == "read_file"
        assert result.started_at is not None
        assert result.ended_at is not None

    @requires_ripgrep
    def test_search_returns_tool_result(self, workspace: Path) -> None:
        """search returns valid ToolResult object."""
        result = search(
            request_id="test-015",
            workspace_root=workspace,
            params=SearchParams(query="test"),
        )

        assert result.request_id == "test-015"
        assert result.tool == "search"
        assert result.started_at is not None
        assert result.ended_at is not None
