from webapi.rate_limit import RateLimiter, FailedAuthTracker


def test_rate_limiter_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is False


def test_failed_auth_tracker_blocks_after_threshold():
    tracker = FailedAuthTracker(max_failures=3, window_seconds=60, block_seconds=300)
    assert tracker.is_blocked("1.2.3.4") is False
    tracker.record_failure("1.2.3.4")
    tracker.record_failure("1.2.3.4")
    assert tracker.is_blocked("1.2.3.4") is False
    tracker.record_failure("1.2.3.4")
    assert tracker.is_blocked("1.2.3.4") is True


def test_failed_auth_tracker_success_resets_failure_count():
    tracker = FailedAuthTracker(max_failures=3, window_seconds=60, block_seconds=300)
    tracker.record_failure("1.2.3.4")
    tracker.record_failure("1.2.3.4")
    tracker.record_success("1.2.3.4")
    tracker.record_failure("1.2.3.4")
    tracker.record_failure("1.2.3.4")
    assert tracker.is_blocked("1.2.3.4") is False  # only 2 failures since reset


def test_failed_auth_tracker_keys_are_independent():
    tracker = FailedAuthTracker(max_failures=1, window_seconds=60, block_seconds=300)
    tracker.record_failure("attacker")
    assert tracker.is_blocked("attacker") is True
    assert tracker.is_blocked("innocent") is False
