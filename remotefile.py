from collections import OrderedDict
import threading
import time

import requests


class RemoteFile:
    def __init__(
        self,
        url,
        size,
        cache_size=64 * 1024 * 1024,
        block_size=1024 * 1024,
    ):
        self.url = url
        self.size = size
        self.position = 0

        self.cache_size = cache_size
        self.block_size = block_size

        self.cache = OrderedDict()
        self.cached_bytes = 0

        self.session = requests.Session()
        self.session.headers.update(
            {"Accept-Encoding": "identity"}
        )

        # Multiple background prefetch threads can access
        # the cache while the reader is using it.
        self.cache_lock = threading.RLock()

        # Blocks currently being prefetched.
        self.prefetching = set()

        # Events allow a normal read to wait for an existing
        # prefetch instead of downloading the same block again.
        self.prefetch_events = {}

        self.range_requests = 0
        self.downloaded_bytes = 0
        self.request_time = 0.0

    def _download_block(
        self,
        block_number,
        session=None,
    ):
        start = (
            block_number
            * self.block_size
        )

        if start >= self.size:
            return b""

        end = min(
            start + self.block_size,
            self.size,
        ) - 1

        if session is None:
            session = self.session

        request_start = time.perf_counter()

        response = session.get(
            self.url,
            headers={
                "Range": f"bytes={start}-{end}"
            },
        )

        elapsed = (
            time.perf_counter()
            - request_start
        )

        response.raise_for_status()

        data = response.content

        with self.cache_lock:
            self.range_requests += 1
            self.downloaded_bytes += len(data)
            self.request_time += elapsed

        return data

    def _cache_block(
        self,
        block_number,
        data,
    ):
        if not data:
            return

        with self.cache_lock:
            # Another thread may have inserted this block
            # while this thread was downloading it.
            old_data = self.cache.pop(
                block_number,
                None,
            )

            if old_data is not None:
                self.cached_bytes -= len(
                    old_data
                )

            self.cache[
                block_number
            ] = data

            self.cached_bytes += len(data)

            while (
                self.cached_bytes
                > self.cache_size
            ):
                (
                    _old_block,
                    old_data,
                ) = self.cache.popitem(
                    last=False
                )

                self.cached_bytes -= len(
                    old_data
                )

    def _get_block(
        self,
        block_number,
    ):
        # First check whether the block is already cached.
        with self.cache_lock:
            if block_number in self.cache:
                data = self.cache.pop(
                    block_number
                )

                self.cache[
                    block_number
                ] = data

                return data

            # If a background prefetch is already downloading
            # this block, wait for that download instead of
            # starting another HTTP request.
            prefetch_event = (
                self.prefetch_events.get(
                    block_number
                )
            )

        if prefetch_event is not None:
            prefetch_event.wait()

            with self.cache_lock:
                if block_number in self.cache:
                    data = self.cache.pop(
                        block_number
                    )

                    self.cache[
                        block_number
                    ] = data

                    return data

        # No usable prefetch exists, so download normally.
        data = self._download_block(
            block_number
        )

        self._cache_block(
            block_number,
            data,
        )

        return data

    def _prefetch_worker(
        self,
        block_number,
        event,
    ):
        session = requests.Session()

        try:
            session.headers.update(
                {"Accept-Encoding": "identity"}
            )

            # It is possible that the block became cached
            # after the prefetch was scheduled.
            with self.cache_lock:
                already_cached = (
                    block_number
                    in self.cache
                )

            if not already_cached:
                data = self._download_block(
                    block_number,
                    session=session,
                )

                self._cache_block(
                    block_number,
                    data,
                )

        except Exception as error:
            # Prefetch is only an optimization.
            # A failed prefetch must never break normal
            # page loading.
            print(
                f"[PREFETCH] Block "
                f"{block_number} failed: "
                f"{error}"
            )

        finally:
            with self.cache_lock:
                self.prefetching.discard(
                    block_number
                )

                self.prefetch_events.pop(
                    block_number,
                    None,
                )

                event.set()

            session.close()

    def prefetch_block(
        self,
        block_number,
    ):
        """
        Download one RemoteFile block in the background.

        Does nothing if the block is already cached or
        another prefetch is already downloading it.
        """

        if block_number < 0:
            return

        start = (
            block_number
            * self.block_size
        )

        if start >= self.size:
            return

        with self.cache_lock:
            if block_number in self.cache:
                return

            if block_number in self.prefetching:
                return

            event = threading.Event()

            self.prefetching.add(
                block_number
            )

            self.prefetch_events[
                block_number
            ] = event

        thread = threading.Thread(
            target=self._prefetch_worker,
            args=(
                block_number,
                event,
            ),
            daemon=True,
        )

        thread.start()

    def prefetch_blocks(
        self,
        block_numbers,
    ):
        """
        Start background downloads for multiple blocks.
        """

        for block_number in block_numbers:
            self.prefetch_block(
                block_number
            )

    def read(
        self,
        length=-1,
    ):
        if self.position >= self.size:
            return b""

        if length < 0:
            length = (
                self.size
                - self.position
            )

        length = min(
            length,
            self.size - self.position,
        )

        result = bytearray()

        while length > 0:
            block_number = (
                self.position
                // self.block_size
            )

            block_offset = (
                self.position
                % self.block_size
            )

            block = self._get_block(
                block_number
            )

            available = min(
                length,
                len(block)
                - block_offset,
            )

            if available <= 0:
                break

            result.extend(
                block[
                    block_offset:
                    block_offset + available
                ]
            )

            self.position += available
            length -= available

        return bytes(result)

    def seek(
        self,
        offset,
        whence=0,
    ):
        if whence == 0:
            new_position = offset

        elif whence == 1:
            new_position = (
                self.position
                + offset
            )

        elif whence == 2:
            new_position = (
                self.size
                + offset
            )

        else:
            raise ValueError(
                "Invalid whence"
            )

        if new_position < 0:
            raise ValueError(
                "Negative seek position"
            )

        self.position = new_position

        return self.position

    def tell(self):
        return self.position

    def get_cache_info(self):
        with self.cache_lock:
            return {
                "blocks": len(self.cache),
                "bytes": self.cached_bytes,
                "limit": self.cache_size,
                "range_requests": self.range_requests,
                "downloaded_bytes": (
                    self.downloaded_bytes
                ),
                "request_time": (
                    self.request_time
                ),
                "prefetching": len(
                    self.prefetching
                ),
            }

    def close(self):
        self.session.close()
