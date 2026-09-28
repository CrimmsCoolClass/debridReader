# timing.py

import time


class TimingSession:

    def __init__(self, name):
        self.name = name
        self.start_time = time.perf_counter()
        self.last_time = self.start_time

    def mark(self, name):
        now = time.perf_counter()

        step_ms = (now - self.last_time) * 1000
        total_ms = (now - self.start_time) * 1000

        print(
            f"[TIMING] {self.name} | "
            f"{name}: +{step_ms:.2f} ms "
            f"(total {total_ms:.2f} ms)"
        )

        self.last_time = now

    def finish(self):
        now = time.perf_counter()
        total_ms = (now - self.start_time) * 1000

        print(
            f"[TIMING] {self.name} | "
            f"TOTAL: {total_ms:.2f} ms"
        )

        return total_ms
