"""Unit tests for FailureReason taxonomy."""

import pytest

from agentbench.scoring.taxonomy import FailureReason


class TestFromPytestExitCode:
    """Tests for FailureReason.from_pytest_exit_code()."""

    def test_exit_code_0_returns_none(self):
        """Exit code 0 (success) should return None."""
        assert FailureReason.from_pytest_exit_code(0) is None

    def test_exit_code_1_returns_tests_failed(self):
        """Exit code 1 should return TESTS_FAILED."""
        assert (
            FailureReason.from_pytest_exit_code(1) == FailureReason.TESTS_FAILED
        )

    def test_exit_code_5_returns_no_tests_collected(self):
        """Exit code 5 should return NO_TESTS_COLLECTED."""
        assert (
            FailureReason.from_pytest_exit_code(5)
            == FailureReason.NO_TESTS_COLLECTED
        )

    def test_exit_code_124_returns_timeout(self):
        """Exit code 124 (GNU timeout) should return TIMEOUT."""
        assert FailureReason.from_pytest_exit_code(124) == FailureReason.TIMEOUT

    def test_exit_code_137_returns_timeout(self):
        """Exit code 137 (SIGKILL) should return TIMEOUT."""
        assert FailureReason.from_pytest_exit_code(137) == FailureReason.TIMEOUT

    def test_exit_code_2_returns_interrupted(self):
        """Exit code 2 should return INTERRUPTED."""
        assert (
            FailureReason.from_pytest_exit_code(2) == FailureReason.INTERRUPTED
        )

    def test_exit_code_3_returns_internal_error(self):
        """Exit code 3 should return INTERNAL_ERROR."""
        assert (
            FailureReason.from_pytest_exit_code(3)
            == FailureReason.INTERNAL_ERROR
        )

    def test_exit_code_4_returns_internal_error(self):
        """Exit code 4 should return INTERNAL_ERROR."""
        assert (
            FailureReason.from_pytest_exit_code(4)
            == FailureReason.INTERNAL_ERROR
        )

    def test_unknown_exit_code_returns_unknown(self):
        """Unknown exit codes should return UNKNOWN."""
        assert FailureReason.from_pytest_exit_code(99) == FailureReason.UNKNOWN


class TestFromStage:
    """Tests for FailureReason.from_stage()."""

    def test_setup_non_zero_returns_setup_failed(self):
        """Setup stage with non-zero exit code should return SETUP_FAILED."""
        assert (
            FailureReason.from_stage("setup", 1, None)
            == FailureReason.SETUP_FAILED
        )

    def test_setup_timeout_returns_setup_timeout(self):
        """Setup stage with exit code 124 should return SETUP_TIMEOUT."""
        result = FailureReason.from_stage("setup", 124, None)
        assert result == FailureReason.SETUP_TIMEOUT

    def test_baseline_run_exit_0_returns_baseline_not_failing(self):
        """Baseline run with exit code 0 should return BASELINE_NOT_FAILING."""
        assert (
            FailureReason.from_stage("baseline_run", 0, None)
            == FailureReason.BASELINE_NOT_FAILING
        )

    def test_baseline_run_exit_1_returns_none(self):
        """Baseline run with exit code 1 (tests failing) should return None (valid baseline)."""
        assert FailureReason.from_stage("baseline_run", 1, None) is None

    def test_git_clone_non_zero_returns_git_clone_failed(self):
        """Git clone with non-zero exit code should return GIT_CLONE_FAILED."""
        assert (
            FailureReason.from_stage("git_clone", 128, None)
            == FailureReason.GIT_CLONE_FAILED
        )

    def test_git_clone_timeout_returns_timeout(self):
        """Git clone with exit code 124 should return TIMEOUT (timeout takes precedence)."""
        result = FailureReason.from_stage("git_clone", 124, None)
        assert result == FailureReason.TIMEOUT

    def test_git_checkout_non_zero_returns_git_checkout_failed(self):
        """Git checkout with non-zero exit code should return GIT_CHECKOUT_FAILED."""
        assert (
            FailureReason.from_stage("git_checkout", 1, None)
            == FailureReason.GIT_CHECKOUT_FAILED
        )

    def test_setup_success_returns_none(self):
        """Setup with exit code 0 should return None."""
        assert FailureReason.from_stage("setup", 0, None) is None

    def test_git_clone_success_returns_none(self):
        """Git clone with exit code 0 should return None."""
        assert FailureReason.from_stage("git_clone", 0, None) is None

    def test_keyboard_interrupt_exception_returns_interrupted(self):
        """KeyboardInterrupt exception should return INTERRUPTED."""
        assert (
            FailureReason.from_stage("setup", 0, KeyboardInterrupt())
            == FailureReason.INTERRUPTED
        )

    def test_other_exception_returns_unknown(self):
        """Other exceptions should return UNKNOWN."""
        assert (
            FailureReason.from_stage("setup", 0, ValueError("test"))
            == FailureReason.UNKNOWN
        )

    def test_unknown_stage_raises_value_error(self):
        """Unknown stage should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown stage"):
            FailureReason.from_stage("invalid_stage", 0, None)

    def test_agent_run_delegates_to_pytest_exit_code(self):
        """Agent run stage should delegate to from_pytest_exit_code."""
        assert FailureReason.from_stage("agent_run", 0, None) is None
        assert (
            FailureReason.from_stage("agent_run", 1, None)
            == FailureReason.TESTS_FAILED
        )

    def test_final_test_delegates_to_pytest_exit_code(self):
        """Final test stage should delegate to from_pytest_exit_code."""
        assert FailureReason.from_stage("final_test", 0, None) is None
        assert (
            FailureReason.from_stage("final_test", 1, None)
            == FailureReason.TESTS_FAILED
        )


class TestPrecedence:
    """Tests for FailureReason.precedence property."""

    def test_precedence_ordering_is_deterministic(self):
        """Precedence values should be unique and consistently ordered."""
        precedence_values = [reason.precedence for reason in FailureReason]
        # Check all values are unique
        assert len(precedence_values) == len(set(precedence_values))

    def test_git_clone_has_highest_precedence(self):
        """GIT_CLONE_FAILED should have highest precedence (lowest value)."""
        assert FailureReason.GIT_CLONE_FAILED.precedence == 1
        for reason in FailureReason:
            if reason != FailureReason.GIT_CLONE_FAILED:
                assert (
                    FailureReason.GIT_CLONE_FAILED.precedence
                    < reason.precedence
                )

    def test_setup_failures_precede_runtime_failures(self):
        """Setup failures should have higher precedence than runtime failures."""
        assert (
            FailureReason.SETUP_FAILED.precedence
            < FailureReason.TESTS_FAILED.precedence
        )
        assert (
            FailureReason.SETUP_TIMEOUT.precedence
            < FailureReason.TIMEOUT.precedence
        )

    def test_precedence_follows_documented_order(self):
        """Precedence should follow the documented order in the docstring."""
        expected_order = [
            FailureReason.GIT_CLONE_FAILED,
            FailureReason.GIT_CHECKOUT_FAILED,
            FailureReason.SETUP_TIMEOUT,
            FailureReason.SETUP_FAILED,
            FailureReason.BASELINE_NOT_FAILING,
            FailureReason.SANDBOX_ERROR,
            FailureReason.LLM_ERROR,
            FailureReason.TOOL_ERROR,
            FailureReason.TIMEOUT,
            FailureReason.AGENT_GAVE_UP,
            FailureReason.TESTS_FAILED,
            FailureReason.NO_TESTS_COLLECTED,
            FailureReason.INTERNAL_ERROR,
            FailureReason.INTERRUPTED,
            FailureReason.UNKNOWN,
        ]
        for i in range(len(expected_order) - 1):
            assert (
                expected_order[i].precedence < expected_order[i + 1].precedence
            ), (
                f"{expected_order[i]} should have higher precedence than {expected_order[i + 1]}"
            )

    def test_can_sort_failures_by_precedence(self):
        """Should be able to sort failures by precedence to find primary failure."""
        failures = [
            FailureReason.TESTS_FAILED,
            FailureReason.SETUP_FAILED,
            FailureReason.GIT_CLONE_FAILED,
        ]
        sorted_failures = sorted(failures, key=lambda f: f.precedence)
        assert sorted_failures[0] == FailureReason.GIT_CLONE_FAILED
        assert sorted_failures[1] == FailureReason.SETUP_FAILED
        assert sorted_failures[2] == FailureReason.TESTS_FAILED
