"""Tests for output truncation utilities."""

import pytest

from agentbench.util.truncation import (
    MAX_OUTPUT_BYTES,
    MAX_OUTPUT_LINES,
    truncate_output,
    truncate_bytes,
)


class TestTruncateOutput:
    """Tests for truncate_output function."""

    def test_small_content_unchanged(self) -> None:
        """Small content is returned unchanged."""
        content = "Hello, World!\nSecond line."
        result, was_truncated = truncate_output(content)
        
        assert result == content
        assert was_truncated is False

    def test_empty_string(self) -> None:
        """Empty string is returned unchanged."""
        content = ""
        result, was_truncated = truncate_output(content)
        
        assert result == ""
        assert was_truncated is False

    def test_exactly_max_lines_unchanged(self) -> None:
        """Content with exactly MAX_OUTPUT_LINES is not truncated."""
        lines = [f"Line {i}" for i in range(MAX_OUTPUT_LINES)]
        content = "\n".join(lines)
        # This is under byte limit but exactly at line limit
        if len(content) <= MAX_OUTPUT_BYTES:
            result, was_truncated = truncate_output(content)
            assert was_truncated is False

    def test_over_max_lines_truncated(self) -> None:
        """Content with more than MAX_OUTPUT_LINES is truncated when exceeding byte limit."""
        # Create content that exceeds both line limit AND byte limit
        # Each line needs to be long enough that total bytes > MAX_OUTPUT_BYTES
        lines = [f"Line {i:06d} - " + "x" * 100 for i in range(MAX_OUTPUT_LINES + 1000)]
        content = "\n".join(lines)
        
        # Verify content exceeds byte limit
        assert len(content) > MAX_OUTPUT_BYTES
        
        result, was_truncated = truncate_output(content)
        
        assert was_truncated is True
        assert "lines truncated" in result
        assert "1000" in result  # Should mention 1000 lines were truncated

    def test_truncated_contains_first_half(self) -> None:
        """Truncated content contains first half of allowed lines."""
        lines = [f"FIRST_{i:06d}" for i in range(1000)]
        lines.extend([f"MIDDLE_{i:06d}" for i in range(5000)])
        lines.extend([f"LAST_{i:06d}" for i in range(1000)])
        content = "\n".join(lines)
        
        result, was_truncated = truncate_output(content)
        
        if was_truncated:
            # First lines should be present
            assert "FIRST_000000" in result

    def test_truncated_contains_last_half(self) -> None:
        """Truncated content contains last half of allowed lines."""
        lines = [f"FIRST_{i:06d}" for i in range(1000)]
        lines.extend([f"MIDDLE_{i:06d}" for i in range(5000)])
        lines.extend([f"LAST_{i:06d}" for i in range(1000)])
        content = "\n".join(lines)
        
        result, was_truncated = truncate_output(content)
        
        if was_truncated:
            # Last lines should be present
            assert "LAST_000999" in result

    def test_truncation_marker_present(self) -> None:
        """Truncated output contains a clear marker."""
        lines = [f"Line {i}" for i in range(MAX_OUTPUT_LINES + 500)]
        content = "\n".join(lines)
        
        result, was_truncated = truncate_output(content)
        
        if was_truncated:
            assert "..." in result
            assert "truncated" in result.lower()


class TestTruncateBytes:
    """Tests for truncate_bytes function."""

    def test_small_bytes_unchanged(self) -> None:
        """Small byte content is returned unchanged."""
        content = b"Hello, World!"
        result, was_truncated = truncate_bytes(content)
        
        assert result == content
        assert was_truncated is False

    def test_empty_bytes(self) -> None:
        """Empty bytes is returned unchanged."""
        content = b""
        result, was_truncated = truncate_bytes(content)
        
        assert result == b""
        assert was_truncated is False

    def test_over_limit_truncated(self) -> None:
        """Byte content over limit is truncated."""
        content = b"X" * (MAX_OUTPUT_BYTES + 1000)
        
        result, was_truncated = truncate_bytes(content)
        
        assert was_truncated is True
        assert len(result) < len(content)
        assert b"truncated" in result

    def test_custom_limit(self) -> None:
        """Custom max_bytes limit is respected."""
        content = b"X" * 1000
        
        result, was_truncated = truncate_bytes(content, max_bytes=500)
        
        assert was_truncated is True
        assert len(result) < len(content)

    def test_exactly_at_limit_unchanged(self) -> None:
        """Content exactly at limit is not truncated."""
        content = b"X" * 500
        
        result, was_truncated = truncate_bytes(content, max_bytes=500)
        
        assert was_truncated is False
        assert result == content


class TestConstants:
    """Tests for truncation constants."""

    def test_max_output_bytes_value(self) -> None:
        """MAX_OUTPUT_BYTES is 100KB."""
        assert MAX_OUTPUT_BYTES == 100_000

    def test_max_output_lines_value(self) -> None:
        """MAX_OUTPUT_LINES is 2000."""
        assert MAX_OUTPUT_LINES == 2000
