import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from agentbench.tools.patching import (
    parse_unified_diff,
    validate_patch,
    apply_patch,
    FilePatch,
    PatchHunk,
)
from agentbench.tools.contract import ApplyPatchParams, ToolStatus
from agentbench.schemas.events import Event, EventType


# Sample patches for testing
SIMPLE_PATCH = """\
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
 def foo():
+    print("hello")
     pass
"""

MULTI_FILE_PATCH = """\
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
 def foo():
+    print("hello")
     pass
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,2 +1,3 @@
 def bar():
+    return 42
     pass
"""

NEW_FILE_PATCH = """\
--- /dev/null
+++ b/src/new_file.py
@@ -0,0 +1,3 @@
+def new_func():
+    pass
+
"""

DELETE_FILE_PATCH = """\
--- a/src/old_file.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old_func():
-    pass
-
"""

PATH_ESCAPE_PATCH = """\
--- a/../../../etc/passwd
+++ b/../../../etc/passwd
@@ -1,1 +1,2 @@
 root:x:0:0
+hacked
"""


class TestParseUnifiedDiff:
    """Tests for parse_unified_diff function."""

    def test_parse_simple_patch(self):
        """Single file, single hunk."""
        patches = parse_unified_diff(SIMPLE_PATCH)
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch.old_path == "src/main.py"
        assert patch.new_path == "src/main.py"
        assert len(patch.hunks) == 1
        
        hunk = patch.hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_count == 3
        assert hunk.new_start == 1
        assert hunk.new_count == 4

    def test_parse_multi_file_patch(self):
        """Multiple files in one patch."""
        patches = parse_unified_diff(MULTI_FILE_PATCH)
        
        assert len(patches) == 2
        assert patches[0].old_path == "src/main.py"
        assert patches[1].old_path == "src/utils.py"

    def test_parse_new_file(self):
        """Patch creates a new file."""
        patches = parse_unified_diff(NEW_FILE_PATCH)
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch.old_path == "/dev/null"
        assert patch.new_path == "src/new_file.py"

    def test_parse_delete_file(self):
        """Patch deletes a file."""
        patches = parse_unified_diff(DELETE_FILE_PATCH)
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch.old_path == "src/old_file.py"
        assert patch.new_path == "/dev/null"


class TestValidatePatch:
    """Tests for validate_patch function."""

    def test_validate_path_escape(self):
        """Patch with ../ is rejected."""
        patches = parse_unified_diff(PATH_ESCAPE_PATCH)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            errors = validate_patch(workspace, patches)
            
            assert len(errors) > 0
            assert any("escapes" in err for err in errors)

    def test_validate_file_not_found(self):
        """Patch targets file that doesn't exist."""
        patches = parse_unified_diff(SIMPLE_PATCH)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            errors = validate_patch(workspace, patches)
            
            assert len(errors) > 0
            assert any("does not exist" in err for err in errors)

    def test_validate_context_mismatch(self):
        """Context lines don't match file content."""
        patches = parse_unified_diff(SIMPLE_PATCH)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            src_dir = workspace / "src"
            src_dir.mkdir()
            
            # Create file with different content
            (src_dir / "main.py").write_text("def bar():\n    return\n")
            
            errors = validate_patch(workspace, patches)
            
            assert len(errors) > 0
            assert any("context" in err.lower() or "does not match" in err for err in errors)


class TestApplyPatch:
    """Tests for apply_patch function."""

    def test_apply_clean_patch(self):
        """Patch applies successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            artifacts = workspace / "artifacts"
            artifacts.mkdir()
            src_dir = workspace / "src"
            src_dir.mkdir()
            
            # Create file with matching content
            (src_dir / "main.py").write_text("def foo():\n    pass\n")
            
            params = ApplyPatchParams(unified_diff=SIMPLE_PATCH)
            result = apply_patch(workspace, params, step_id=1, artifacts_dir=artifacts)
            
            assert result.status == ToolStatus.SUCCESS
            assert result.data is not None
            assert "changed_files" in result.data
            
            # Verify file was modified
            content = (src_dir / "main.py").read_text()
            assert 'print("hello")' in content

    def test_apply_context_mismatch_error(self):
        """Context lines don't match returns error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            artifacts = workspace / "artifacts"
            artifacts.mkdir()
            src_dir = workspace / "src"
            src_dir.mkdir()
            
            # Create file with different content
            (src_dir / "main.py").write_text("def bar():\n    return 42\n")
            
            params = ApplyPatchParams(unified_diff=SIMPLE_PATCH)
            result = apply_patch(workspace, params, step_id=1, artifacts_dir=artifacts)
            
            assert result.status == ToolStatus.ERROR
            assert result.error is not None
            assert result.error.error_type == "patch_hunk_fail"

    def test_apply_creates_artifact(self):
        """Patch file is saved to diffs/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            artifacts = workspace / "diffs"
            artifacts.mkdir()
            src_dir = workspace / "src"
            src_dir.mkdir()
            
            # Create file with matching content
            (src_dir / "main.py").write_text("def foo():\n    pass\n")
            
            params = ApplyPatchParams(unified_diff=SIMPLE_PATCH)
            result = apply_patch(workspace, params, step_id=1, artifacts_dir=artifacts)
            
            assert result.status == ToolStatus.SUCCESS
            
            # Check artifact was saved
            artifact_path = artifacts / "step_0001.patch"
            assert artifact_path.exists()
            assert artifact_path.read_text() == SIMPLE_PATCH


class TestApplyPatchEvents:
    """Tests for PATCH_APPLIED event emission."""
    
    def test_apply_emits_event(self):
        """PATCH_APPLIED event is logged with correct payload."""
        # Note: This test verifies the ToolResult contains the data needed for event emission
        # The actual event emission would be handled by the caller
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            artifacts = workspace / "diffs"
            artifacts.mkdir()
            src_dir = workspace / "src"
            src_dir.mkdir()
            
            (src_dir / "main.py").write_text("def foo():\n    pass\n")
            
            params = ApplyPatchParams(unified_diff=SIMPLE_PATCH)
            result = apply_patch(workspace, params, step_id=5, artifacts_dir=artifacts)
            
            assert result.status == ToolStatus.SUCCESS
            assert result.data is not None
            
            # Verify data contains fields needed for PATCH_APPLIED event
            assert "changed_files" in result.data
            assert "patch_size_bytes" in result.data
            assert isinstance(result.data["changed_files"], list)
            assert result.data["patch_size_bytes"] > 0
            
            # Verify we can construct an event from the result
            event = Event(
                event_type=EventType.PATCH_APPLIED,
                timestamp=datetime.now(),
                run_id="test_run",
                step_id=5,
                payload={
                    "step_id": 5,
                    "changed_files": result.data["changed_files"],
                    "patch_artifact_path": str(artifacts / "step_0005.patch"),
                    "patch_size_bytes": result.data["patch_size_bytes"],
                }
            )
            assert event.event_type == EventType.PATCH_APPLIED
