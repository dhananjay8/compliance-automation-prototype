"""Standalone RQ worker process for the distributed job queue.

Run with:

    ENABLE_QUEUE=1 REDIS_URL=redis://localhost:6381/0 PYTHONPATH=prototype \
        python -m queue_worker

Multiple instances of this process can run concurrently (different hosts or
containers) to horizontally scale sync/test execution, which is what the
Phase 4 roadmap item "distributed queue/worker architecture" calls for.
"""

from __future__ import annotations

import os
import sys

from queue_backend import QUEUE_NAME, REDIS_URL


def main() -> None:
    import redis
    from rq import Queue, Worker

    conn = redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=conn)
    worker = Worker([queue], connection=conn)
    print(f"[queue_worker] listening on '{QUEUE_NAME}' at {REDIS_URL}")
    worker.work()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    main()
