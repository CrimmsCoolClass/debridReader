from PySide6.QtCore import QObject, Signal, Slot

from timing import TimingSession


class PageWorker(QObject):

    finished = Signal(int, bytes)
    failed = Signal(int, str)

    def __init__(self, archive):
        super().__init__()

        self.archive = archive

    @Slot(int, str)
    def load_page(
        self,
        page_number,
        filename,
    ):

        timing = TimingSession(
            f"Page {page_number + 1}"
        )

        try:

            print(
                f"Loading page {page_number + 1}: "
                f"{filename}"
            )

            timing.mark(
                "request started"
            )

            # -------------------------------------------------
            # Get the underlying RemoteFile.
            # -------------------------------------------------

            remote_file = getattr(
                self.archive,
                "remote_file",
                None,
            )

            # -------------------------------------------------
            # Record RemoteFile statistics before the read.
            #
            # Use individual integer/float variables instead
            # of keeping a possibly-None dictionary around.
            # This also keeps the LSP happy.
            # -------------------------------------------------

            if remote_file is not None:

                before_range_requests = (
                    remote_file.get_cache_info()[
                        "range_requests"
                    ]
                )

                before_downloaded_bytes = (
                    remote_file.get_cache_info()[
                        "downloaded_bytes"
                    ]
                )

                before_request_time = (
                    remote_file.get_cache_info()[
                        "request_time"
                    ]
                )

            else:

                before_range_requests = 0
                before_downloaded_bytes = 0
                before_request_time = 0.0

            # -------------------------------------------------
            # Read the actual page.
            # -------------------------------------------------

            data = self.archive.read_file(
                filename
            )

            timing.mark(
                f"archive.read_file "
                f"({len(data) / 1024 / 1024:.2f} MiB)"
            )

            # -------------------------------------------------
            # Record RemoteFile statistics after the read.
            # -------------------------------------------------

            if remote_file is not None:

                after_info = (
                    remote_file.get_cache_info()
                )

                after_range_requests = (
                    after_info["range_requests"]
                )

                after_downloaded_bytes = (
                    after_info["downloaded_bytes"]
                )

                after_request_time = (
                    after_info["request_time"]
                )

                range_requests = (
                    after_range_requests
                    - before_range_requests
                )

                downloaded_bytes = (
                    after_downloaded_bytes
                    - before_downloaded_bytes
                )

                request_time = (
                    after_request_time
                    - before_request_time
                )

                print(
                    f"[REMOTE] Page {page_number + 1} | "
                    f"Range requests: "
                    f"{range_requests} | "
                    f"Downloaded: "
                    f"{downloaded_bytes / 1024 / 1024:.2f} MiB | "
                    f"HTTP time: "
                    f"{request_time * 1000:.2f} ms"
                )

            # -------------------------------------------------
            # Deliver the page to the reader.
            # -------------------------------------------------

            self.finished.emit(
                page_number,
                data,
            )

            timing.mark(
                "finished signal emitted"
            )

            timing.finish()

        except Exception as error:

            timing.mark(
                "ERROR"
            )

            timing.finish()

            self.failed.emit(
                page_number,
                str(error),
            )
