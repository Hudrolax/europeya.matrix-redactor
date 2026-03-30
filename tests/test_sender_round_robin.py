from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from europeya_matrix_redactor.services.sender_round_robin import SenderRoundRobinScheduler


def test_sender_round_robin_scheduler_interleaves_senders() -> None:
    scheduler = SenderRoundRobinScheduler(max_concurrent_senders=1)

    results = scheduler.run(
        {
            "@alice:example.com": ["a1", "a2"],
            "@bob:example.com": ["b1", "b2"],
            "@carol:example.com": ["c1"],
        },
        lambda item: item,
    )

    assert results == ["a1", "b1", "c1", "a2", "b2"]


def test_sender_round_robin_scheduler_never_runs_same_sender_in_parallel() -> None:
    scheduler = SenderRoundRobinScheduler(max_concurrent_senders=3)
    active_by_sender: dict[str, int] = defaultdict(int)
    max_active_by_sender: dict[str, int] = defaultdict(int)
    lock = Lock()

    def worker(item: tuple[str, str]) -> tuple[str, str]:
        sender, value = item
        with lock:
            active_by_sender[sender] += 1
            max_active_by_sender[sender] = max(
                max_active_by_sender[sender],
                active_by_sender[sender],
            )
        time.sleep(0.02)
        with lock:
            active_by_sender[sender] -= 1
        return (sender, value)

    results = scheduler.run(
        {
            "@alice:example.com": [
                ("@alice:example.com", "a1"),
                ("@alice:example.com", "a2"),
                ("@alice:example.com", "a3"),
            ],
            "@bob:example.com": [("@bob:example.com", "b1")],
            "@carol:example.com": [("@carol:example.com", "c1")],
        },
        worker,
    )

    assert len(results) == 5
    assert max_active_by_sender["@alice:example.com"] == 1
