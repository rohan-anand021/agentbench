"""Output truncation utilities for large outputs (stdout, stderr, file contents)."""

# Truncation limits
MAX_OUTPUT_BYTES = 100_000  # 100KB
MAX_OUTPUT_LINES = 2000


def truncate_output(content: str) -> tuple[str, bool]:
    """
    Truncate large output, keeping first and last portions.
    
    This is used to prevent excessive memory usage and disk space consumption
    when dealing with large stdout/stderr outputs or large file contents.
    
    The function preserves the beginning and end of the content, which are
    typically the most useful parts for debugging (initial context and final
    errors/results).
    
    Args:
        content: The string content to potentially truncate
    
    Returns:
        A tuple of (truncated_content, was_truncated)
        - truncated_content: The original or truncated content
        - was_truncated: True if content was truncated, False otherwise
    
    Example:
        >>> content = "line1\\nline2\\n" * 3000  # 6000 lines
        >>> truncated, was_truncated = truncate_output(content)
        >>> was_truncated
        True
        >>> "lines truncated" in truncated
        True
    """
    # First check byte limit
    if len(content) <= MAX_OUTPUT_BYTES:
        return content, False
    
    # Then check line limit
    lines = content.splitlines(keepends=True)
    if len(lines) <= MAX_OUTPUT_LINES:
        return content, False
    
    # Truncate by keeping first half and last half of allowed lines
    half = MAX_OUTPUT_LINES // 2
    first_lines = lines[:half]
    last_lines = lines[-half:]
    
    truncated_count = len(lines) - MAX_OUTPUT_LINES
    
    truncated = (
        "".join(first_lines) +
        f"\n\n... [{truncated_count} lines truncated] ...\n\n" +
        "".join(last_lines)
    )
    return truncated, True


def truncate_bytes(content: bytes, max_bytes: int = MAX_OUTPUT_BYTES) -> tuple[bytes, bool]:
    """
    Truncate large byte content, keeping first and last portions.
    
    Similar to truncate_output but for bytes. Useful for binary-safe truncation
    when the content encoding is unknown.
    
    Args:
        content: The byte content to potentially truncate
        max_bytes: Maximum size in bytes (default: MAX_OUTPUT_BYTES)
    
    Returns:
        A tuple of (truncated_content, was_truncated)
    """
    if len(content) <= max_bytes:
        return content, False
    
    half = max_bytes // 2
    marker = b"\n\n... [content truncated] ...\n\n"
    
    truncated = content[:half] + marker + content[-half:]
    return truncated, True
