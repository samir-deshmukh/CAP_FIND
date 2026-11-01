from backend.admin.state import JobStatus, TERMINAL_STATUSES, can_transition


def test_valid_and_invalid_transitions():
    assert can_transition(JobStatus.RECEIVED, JobStatus.SECURITY_CHECK.value)
    assert can_transition("REVIEW_REQUIRED", "APPROVED")
    assert not can_transition("COMPLETED", "RECEIVED")
    assert not can_transition("UNKNOWN", "RECEIVED")


def test_terminal_statuses_are_explicit():
    assert JobStatus.COMPLETED.value in TERMINAL_STATUSES
    assert JobStatus.FAILED.value in TERMINAL_STATUSES
    assert JobStatus.ROLLED_BACK.value in TERMINAL_STATUSES
    assert JobStatus.REVIEW_REQUIRED.value not in TERMINAL_STATUSES
