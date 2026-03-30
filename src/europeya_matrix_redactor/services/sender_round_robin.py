from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


class SenderRoundRobinScheduler:
    def __init__(self, max_concurrent_senders: int) -> None:
        if max_concurrent_senders <= 0:
            raise ValueError("max_concurrent_senders must be greater than zero")
        self.max_concurrent_senders = max_concurrent_senders

    def run(
        self,
        items_by_sender: Mapping[str, Sequence[T]],
        worker: Callable[[T], R],
    ) -> list[R]:
        return list(self.iter_results(items_by_sender, worker))

    def iter_results(
        self,
        items_by_sender: Mapping[str, Sequence[T]],
        worker: Callable[[T], R],
    ) -> Iterator[R]:
        sender_queues = {
            sender: deque(items)
            for sender, items in items_by_sender.items()
            if items
        }
        if not sender_queues:
            return

        max_workers = min(self.max_concurrent_senders, len(sender_queues))
        ready_senders = deque(sender_queues.keys())
        in_flight: dict[Future[R], str] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            self._fill_worker_pool(
                pool,
                worker,
                sender_queues,
                ready_senders,
                in_flight,
                max_workers=max_workers,
            )

            while in_flight:
                completed, _ = wait(tuple(in_flight.keys()), return_when=FIRST_COMPLETED)
                for future in completed:
                    sender = in_flight.pop(future)
                    yield future.result()
                    if sender_queues[sender]:
                        ready_senders.append(sender)

                self._fill_worker_pool(
                    pool,
                    worker,
                    sender_queues,
                    ready_senders,
                    in_flight,
                    max_workers=max_workers,
                )

    @staticmethod
    def _fill_worker_pool(
        pool: ThreadPoolExecutor,
        worker: Callable[[T], R],
        sender_queues: Mapping[str, deque[T]],
        ready_senders: deque[str],
        in_flight: dict[Future[R], str],
        *,
        max_workers: int,
    ) -> None:
        while ready_senders and len(in_flight) < max_workers:
            sender = ready_senders.popleft()
            queue = sender_queues[sender]
            if not queue:
                continue
            future = pool.submit(worker, queue.popleft())
            in_flight[future] = sender
