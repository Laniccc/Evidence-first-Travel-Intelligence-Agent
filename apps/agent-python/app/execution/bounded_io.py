"""Dedicated serial lanes. Cancellation never pretends to terminate a running thread."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Lock


class WorkerBusy(RuntimeError):
    pass


class BoundedIO:
    def __init__(self, *, capacity_per_lane: int = 2):
        if capacity_per_lane < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity_per_lane
        self._lock = Lock()
        self._pools = {}
        self._futures = {}
        self._closed = False

    def outstanding(self, lane: str) -> int:
        with self._lock:
            return len(self._futures.get(lane, ()))

    async def run(self, lane: str, function, *args, **kwargs):
        if lane not in {"lexical", "dense", "postfilter"}:
            raise ValueError("unknown I/O lane")
        with self._lock:
            if self._closed:
                raise WorkerBusy("worker_closed")
            pending = self._futures.setdefault(lane, set())
            if len(pending) >= self._capacity:
                raise WorkerBusy("worker_capacity_exhausted")
            if lane not in self._pools:
                self._pools[lane] = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"travel-{lane}")
            pool = self._pools[lane]
            future = pool.submit(partial(function, *args, **kwargs))
            pending.add(future)

        def completed(done):
            with self._lock:
                self._futures[lane].discard(done)

        future.add_done_callback(completed)
        wrapped = asyncio.wrap_future(future)
        # Consume eventual errors even if this caller is cancelled.
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(wrapped)

    async def aclose(self):
        with self._lock:
            self._closed = True
            pending = [f for values in self._futures.values() for f in values]
        if pending:
            await asyncio.gather(*(asyncio.wrap_future(f) for f in pending), return_exceptions=True)
        for pool in self._pools.values():
            pool.shutdown(wait=True)

    def close(self):
        # Only for synchronous owners; ASGI shutdown must await aclose first.
        with self._lock:
            self._closed = True
        for pool in self._pools.values():
            pool.shutdown(wait=True)
