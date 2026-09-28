from collections import OrderedDict
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

        # Reuse the same HTTP connection for all Range requests.
        #
        # requests.get() creates a temporary Session for each call.
        # A persistent Session lets requests reuse TCP/TLS connections.
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept-Encoding": "identity",
            }
        )

        # HTTP Range request statistics.
        self.range_requests = 0
        self.downloaded_bytes = 0
        self.request_time = 0.0

    def _download_block(self, block_number):
        start = block_number * self.block_size

        if start >= self.size:
            return b""

        end = min(
            start + self.block_size,
            self.size,
        ) - 1

        request_start = time.perf_counter()

        response = self.session.get(
            self.url,
            headers={
                "Range": f"bytes={start}-{end}",
            },
        )

        elapsed = time.perf_counter() - request_start

        response.raise_for_status()

        self.range_requests += 1
        self.downloaded_bytes += len(response.content)
        self.request_time += elapsed

        return response.content

    def _get_block(self, block_number):
        if block_number in self.cache:
            data = self.cache.pop(block_number)
            self.cache[block_number] = data
            return data

        data = self._download_block(block_number)

        self.cache[block_number] = data
        self.cached_bytes += len(data)

        while self.cached_bytes > self.cache_size:
            _, old_data = self.cache.popitem(last=False)
            self.cached_bytes -= len(old_data)

        return data

    def read(self, length=-1):
        if self.position >= self.size:
            return b""

        if length < 0:
            length = self.size - self.position

        length = min(
            length,
            self.size - self.position,
        )

        result = bytearray()

        while length > 0:
            block_number = (
                self.position // self.block_size
            )

            block_offset = (
                self.position % self.block_size
            )

            block = self._get_block(
                block_number
            )

            available = min(
                length,
                len(block) - block_offset,
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

    def seek(self, offset, whence=0):
        if whence == 0:
            new_position = offset
        elif whence == 1:
            new_position = self.position + offset
        elif whence == 2:
            new_position = self.size + offset
        else:
            raise ValueError("Invalid whence")

        if new_position < 0:
            raise ValueError("Negative seek position")

        self.position = new_position
        return self.position

    def tell(self):
        return self.position

    def get_cache_info(self):
        return {
            "blocks": len(self.cache),
            "bytes": self.cached_bytes,
            "limit": self.cache_size,
            "range_requests": self.range_requests,
            "downloaded_bytes": self.downloaded_bytes,
            "request_time": self.request_time,
        }

    def close(self):
        self.session.close()
