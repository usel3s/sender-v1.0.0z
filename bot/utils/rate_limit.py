import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, dict[int, deque[float]]] = defaultdict(lambda: defaultdict(deque))

    def check(self, action: str, user_id: int, limit: int, window_sec: int) -> tuple[bool, int]:
        now = time.time()
        bucket = self._events[action][user_id]
        while bucket and now - bucket[0] > window_sec:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window_sec - (now - bucket[0])) + 1
            return False, retry_after
        bucket.append(now)
        return True, 0


rate_limiter = RateLimiter()

LIMITS = {
    "add_account_start": (3, 600),
    "request_code": (3, 900),
    "code_entry": (5, 900),
    "tdata_import": (3, 600),
}
