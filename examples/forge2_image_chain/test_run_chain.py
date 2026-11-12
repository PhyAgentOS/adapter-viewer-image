"""Regression for a real Dora zero-exit run that lost a transport reply."""
from run_chain import runtime_failures


def test_zero_exit_transport_warning_is_not_accepted():
    log = """2026-11-12T02:03:29 WARN dora_daemon::node_communication: failed to send NextEvent reply
Caused by:
   2: outgoing message size 90462638 exceeds maximum 67108864
10:03:31 INFO checker: checker finished successfully
"""
    assert len(runtime_failures(log)) == 2


def test_expected_drop_oldest_warning_is_not_a_transport_failure():
    assert runtime_failures("10:04:15 WARN scheduler Discarding event for input `image/rgb` due to queue size limit") == []
