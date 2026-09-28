import json
import os
import re
import time
from pathlib import Path
import threading

import requests
from PySide6.QtCore import QObject, Signal, Slot

from remotefile import RemoteFile
from remotezip import RemoteCBZArchive, RemoteRARArchive


class OpenVolumeWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)
    progress = Signal(str)

    RAR4_FILE_HEADER = 0x74

    FHD_LARGE = 0x0100
    FHD_UNICODE = 0x0200
    FHD_SALT = 0x0400
    FHD_VERSION = 0x0800
    FHD_EXTTIME = 0x1000

    def __init__(self, realdebrid):
        super().__init__()

        self.realdebrid = realdebrid

        self.rar_index_cache = {}

        self.rar_index_path = (
            Path.home()
            / ".cache"
            / "debrid-reader"
            / "rar-index.json"
        )

        self._thread_local = threading.local()

        self._load_rar_index_cache()

    # ------------------------------------------------------------------
    # Persistent RAR index
    # ------------------------------------------------------------------

    def _load_rar_index_cache(self):
        try:
            with self.rar_index_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                self.rar_index_cache = json.load(file)

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
        ):
            self.rar_index_cache = {}

    def _save_rar_index_cache(self):
        try:
            self.rar_index_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_path = (
                self.rar_index_path.with_suffix(".tmp")
            )

            with temporary_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    self.rar_index_cache,
                    file,
                    separators=(",", ":"),
                )

            temporary_path.replace(
                self.rar_index_path
            )

        except OSError:
            pass

    # ------------------------------------------------------------------
    # RAR parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _u16(data, offset):
        if offset + 2 > len(data):
            raise ValueError(
                "RAR header is truncated"
            )

        return int.from_bytes(
            data[offset:offset + 2],
            "little",
        )

    @staticmethod
    def _u32(data, offset):
        if offset + 4 > len(data):
            raise ValueError(
                "RAR header is truncated"
            )

        return int.from_bytes(
            data[offset:offset + 4],
            "little",
        )

    @staticmethod
    def _decode_filename(raw):
        return raw.decode(
            "cp1252",
            errors="replace",
        )

    def _parse_file_header(
        self,
        data,
        absolute_offset=0,
    ):
        """
        Parse a RAR4 file header.

        absolute_offset is the position of the RAR HEADER.

        The returned 'offset' is deliberately the position of the
        PACKED FILE DATA, because that is the convention used by
        RemoteRARArchive / RemoteCBZArchive.
        """

        if len(data) < 32:
            raise ValueError(
                "Not enough bytes for RAR4 file header"
            )

        head_type = data[2]
        flags = self._u16(data, 3)
        head_size = self._u16(data, 5)

        pack_size_low = self._u32(data, 7)
        unpack_size_low = self._u32(data, 11)

        name_size = self._u16(data, 26)

        if head_type != self.RAR4_FILE_HEADER:
            raise ValueError(
                "Not a RAR4 file header"
            )

        if head_size < 32:
            raise ValueError(
                "Invalid RAR4 header size"
            )

        name_offset = 32

        if flags & self.FHD_LARGE:
            name_offset += 8

        if (
            name_offset + name_size
            > len(data)
        ):
            raise ValueError(
                "RAR filename is truncated"
            )

        if head_size > len(data):
            raise ValueError(
                "RAR header is truncated"
            )

        pack_size = pack_size_low
        unpack_size = unpack_size_low

        if flags & self.FHD_LARGE:
            pack_high = self._u32(
                data,
                32,
            )

            unpack_high = self._u32(
                data,
                36,
            )

            pack_size |= (
                pack_high << 32
            )

            unpack_size |= (
                unpack_high << 32
            )

        raw_name = data[
            name_offset:
            name_offset + name_size
        ]

        filename = self._decode_filename(
            raw_name
        )

        data_offset = (
            absolute_offset
            + head_size
        )

        return {
            # Position of the actual CBZ data.
            "offset": data_offset,

            # Position of the RAR header.
            "header_offset": absolute_offset,

            "size": pack_size,
            "unpacked_size": unpack_size,
            "filename": filename,
            "flags": flags,
            "head_size": head_size,
            "name_size": name_size,
        }

    def _find_first_rar_entry(
        self,
        data,
        base_offset,
    ):
        for index in range(
            0,
            max(0, len(data) - 32),
        ):
            if data[index + 2] != self.RAR4_FILE_HEADER:
                continue

            try:
                return self._parse_file_header(
                    data[index:],
                    base_offset + index,
                )

            except ValueError:
                continue

        raise RuntimeError(
            "Could not identify the first RAR entry."
        )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get_session(self):
        session = getattr(
            self._thread_local,
            "session",
            None,
        )

        if session is None:
            session = requests.Session()

            session.headers.update(
                {
                    "Accept-Encoding": "identity",
                }
            )

            self._thread_local.session = session

        return session

    def _get_single_range(
        self,
        url,
        start,
        end,
    ):
        response = self._get_session().get(
            url,
            headers={
                "Range": (
                    f"bytes={start}-{end}"
                ),
                "Accept-Encoding": "identity",
            },
        )

        response.raise_for_status()

        if response.status_code != 206:
            raise RuntimeError(
                "Server did not honor Range request: "
                f"HTTP {response.status_code}"
            )

        return response.content

    def _parse_multipart_ranges(
        self,
        response,
    ):
        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        match = re.search(
            r"boundary=(?:\"([^\"]+)\"|([^;]+))",
            content_type,
            re.IGNORECASE,
        )

        if match is None:
            raise ValueError(
                "Response is not multipart/byteranges"
            )

        boundary = (
            match.group(1)
            if match.group(1) is not None
            else match.group(2).strip()
        ).encode("ascii")

        marker = (
            b"--"
            + boundary
        )

        result = {}

        for part in response.content.split(
            marker
        ):
            part = part.strip(
                b"\r\n-"
            )

            if not part:
                continue

            header_end = part.find(
                b"\r\n\r\n"
            )

            if header_end < 0:
                continue

            headers = part[
                :header_end
            ]

            body = part[
                header_end + 4:
            ]

            if body.endswith(
                b"\r\n"
            ):
                body = body[:-2]

            range_match = re.search(
                rb"Content-Range:\s*bytes\s+(\d+)-(\d+)/",
                headers,
                re.IGNORECASE,
            )

            if range_match is None:
                continue

            start = int(
                range_match.group(1)
            )

            result[start] = body

        if not result:
            raise ValueError(
                "Multipart response contained no ranges"
            )

        return result

    def _get_multipart_ranges(
        self,
        url,
        ranges,
    ):
        range_header = ",".join(
            f"{start}-{end}"
            for start, end in ranges
        )

        response = self._get_session().get(
            url,
            headers={
                "Range": (
                    f"bytes={range_header}"
                ),
                "Accept-Encoding": "identity",
            },
        )

        response.raise_for_status()

        if response.status_code != 206:
            raise RuntimeError(
                "Server did not honor multipart Range request: "
                f"HTTP {response.status_code}"
            )

        if (
            "multipart/byteranges"
            not in response.headers.get(
                "Content-Type",
                "",
            ).lower()
        ):
            raise RuntimeError(
                "Server did not return multipart/byteranges"
            )

        return self._parse_multipart_ranges(
            response
        )

    # ------------------------------------------------------------------
    # Optimized RAR scanner
    # ------------------------------------------------------------------

    def _optimized_rar_scan(
        self,
        url,
        file_size,
        torrent_files,
    ):
        """
        Discover the physical RAR order without assuming that the
        torrent API file order matches the RAR file order.

        For each entry:

            RAR header
            CBZ data

        Therefore the next RAR header begins exactly at:

            current_data_offset + current_data_size

        The returned 'offset' values point to CBZ data, not RAR headers.
        """

        cbz_files = []

        for file_info in torrent_files:
            path = file_info.get(
                "path",
                "",
            )

            if not path.lower().endswith(
                ".cbz"
            ):
                continue

            try:
                size = int(
                    file_info.get(
                        "bytes",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if size <= 0:
                continue

            cbz_files.append(
                {
                    "filename": path,
                    "basename": os.path.basename(
                        path
                    ),
                    "size": size,
                }
            )

        if not cbz_files:
            raise RuntimeError(
                "Torrent contains no CBZ files."
            )

        start_time = time.perf_counter()

        request_count = 0
        downloaded_bytes = 0

        # --------------------------------------------------------------
        # Find first RAR entry.
        # --------------------------------------------------------------

        first_probe_size = min(
            file_size,
            256 * 1024,
        )

        first_data = self._get_single_range(
            url,
            0,
            first_probe_size - 1,
        )

        request_count += 1
        downloaded_bytes += len(
            first_data
        )

        current = (
            self._find_first_rar_entry(
                first_data,
                0,
            )
        )

        # --------------------------------------------------------------
        # Match first physical entry against torrent metadata.
        # --------------------------------------------------------------

        current_match = None

        for file_info in cbz_files:
            if (
                file_info["size"]
                == current["size"]
                and
                file_info["basename"].lower()
                ==
                os.path.basename(
                    current["filename"]
                ).lower()
            ):
                current_match = file_info
                break

        if current_match is None:
            raise RuntimeError(
                "The first RAR entry does not match "
                "any CBZ reported by the torrent."
            )

        entries = [
            current
        ]

        remaining = [
            file_info
            for file_info in cbz_files
            if file_info is not current_match
        ]

        # --------------------------------------------------------------
        # Follow physical RAR order.
        # --------------------------------------------------------------

        while remaining:

            # 'offset' is the beginning of the CBZ data.
            #
            # Therefore the next RAR header starts exactly where this
            # CBZ's data ends.
            next_header_offset = (
                current["offset"]
                + current["size"]
            )

            if (
                next_header_offset
                >= file_size
            ):
                raise RuntimeError(
                    "RAR ended before all CBZ entries "
                    "were discovered."
                )

            # RAR headers in the tested archives are < 200 bytes.
            # 512 bytes gives substantial room for the complete header.
            probe_end = min(
                next_header_offset + 511,
                file_size - 1,
            )

            data = self._get_single_range(
                url,
                next_header_offset,
                probe_end,
            )

            request_count += 1
            downloaded_bytes += len(
                data
            )

            try:
                next_entry = (
                    self._parse_file_header(
                        data,
                        next_header_offset,
                    )
                )

            except ValueError as error:
                raise RuntimeError(
                    "Could not parse the RAR header "
                    f"at offset {next_header_offset}: "
                    f"{error}"
                )

            # ----------------------------------------------------------
            # Match physical entry to torrent metadata.
            # ----------------------------------------------------------

            matched = None

            for file_info in remaining:

                if (
                    file_info["size"]
                    != next_entry["size"]
                ):
                    continue

                if (
                    file_info["basename"].lower()
                    !=
                    os.path.basename(
                        next_entry["filename"]
                    ).lower()
                ):
                    continue

                matched = file_info
                break

            if matched is None:
                raise RuntimeError(
                    "RAR entry does not match any "
                    "remaining torrent file: "
                    f"{next_entry['filename']} "
                    f"({next_entry['size']} bytes)"
                )

            entries.append(
                next_entry
            )

            remaining.remove(
                matched
            )

            current = next_entry

        elapsed = (
            time.perf_counter()
            - start_time
        )

        message = (
            "RAR optimized scan: "
            f"{elapsed:.2f}s, "
            f"{request_count} Range requests, "
            f"{downloaded_bytes / (1024 * 1024):.2f} MiB downloaded"
        )

        print(
            message,
            flush=True,
        )

        self.progress.emit(
            message
        )

        return entries

    # ------------------------------------------------------------------
    # Main operation
    # ------------------------------------------------------------------

    @Slot(str, str)
    def open_volume(
        self,
        torrent_id,
        selected_name,
    ):
        archive = None

        try:
            self.progress.emit(
                "Getting torrent information..."
            )

            info = (
                self.realdebrid.get_torrent_info(
                    torrent_id
                )
            )

            links = info.get(
                "links",
                [],
            )

            if not links:
                raise RuntimeError(
                    "Torrent has no downloadable links."
                )

            self.progress.emit(
                "Getting download link..."
            )

            unrestricted = (
                self.realdebrid.unrestrict_link(
                    links[0]
                )
            )

            download_url = (
                unrestricted["download"]
            )

            filename = (
                unrestricted["filename"]
            )

            file_size = int(
                unrestricted["filesize"]
            )

            remote_file = RemoteFile(
                download_url,
                file_size,
                cache_size=500 * 1024 * 1024,
                block_size=4 * 1024 * 1024,
            )

            # ----------------------------------------------------------
            # Direct CBZ
            # ----------------------------------------------------------

            if filename.lower().endswith(
                ".cbz"
            ):

                self.progress.emit(
                    "Opening CBZ..."
                )

                archive = RemoteCBZArchive(
                    remote_file,
                    0,
                    file_size,
                )

            # ----------------------------------------------------------
            # CBZ inside RAR
            # ----------------------------------------------------------

            elif filename.lower().endswith(
                ".rar"
            ):

                cache_key = (
                    f"{torrent_id}|"
                    f"{filename}|"
                    f"{file_size}"
                )

                entries = (
                    self.rar_index_cache.get(
                        cache_key
                    )
                )

                if entries is None:

                    self.progress.emit(
                        "Scanning RAR archive..."
                    )

                    try:

                        entries = (
                            self._optimized_rar_scan(
                                download_url,
                                file_size,
                                info.get(
                                    "files",
                                    [],
                                ),
                            )
                        )

                        self.rar_index_cache[
                            cache_key
                        ] = entries

                        self._save_rar_index_cache()

                    except Exception as error:

                        print(
                            "RAR optimized scan failed; "
                            "falling back to sequential scanner: "
                            f"{error}",
                            flush=True,
                        )

                        self.progress.emit(
                            "Optimized RAR scan failed; "
                            "using compatibility scanner..."
                        )

                        scan_remote_file = RemoteFile(
                            download_url,
                            file_size,
                            cache_size=8 * 1024 * 1024,
                            block_size=256 * 1024,
                        )

                        scan_start = (
                            time.perf_counter()
                        )

                        rar = RemoteRARArchive(
                            scan_remote_file
                        )

                        entries = (
                            rar.list_cbzs()
                        )

                        scan_elapsed = (
                            time.perf_counter()
                            - scan_start
                        )

                        scan_stats = (
                            scan_remote_file.get_cache_info()
                        )

                        timing_message = (
                            "RAR scan: "
                            f"{scan_elapsed:.2f}s, "
                            f"{scan_stats['range_requests']} "
                            "Range requests, "
                            f"{scan_stats['downloaded_bytes'] / (1024 * 1024):.2f} MiB downloaded, "
                            f"{scan_stats['request_time']:.2f}s HTTP time"
                        )

                        print(
                            timing_message,
                            flush=True,
                        )

                        self.progress.emit(
                            timing_message
                        )

                else:

                    print(
                        "RAR index: using cached index "
                        "(no RAR scan)",
                        flush=True,
                    )

                    self.progress.emit(
                        "Using cached RAR index..."
                    )

                selected_basename = (
                    os.path.basename(
                        selected_name
                    ).lower()
                )

                selected_entry = None

                for entry in entries:

                    if (
                        os.path.basename(
                            entry["filename"]
                        ).lower()
                        == selected_basename
                    ):
                        selected_entry = entry
                        break

                if selected_entry is None:
                    raise RuntimeError(
                        "Could not find the selected "
                        "volume inside the RAR."
                    )

                self.progress.emit(
                    "Opening volume..."
                )

                # IMPORTANT:
                #
                # selected_entry["offset"] is the beginning of the
                # CBZ payload, NOT the RAR header.
                #
                # This is exactly what RemoteCBZArchive expects.
                archive = RemoteCBZArchive(
                    remote_file,
                    selected_entry["offset"],
                    selected_entry["size"],
                )

            else:

                raise RuntimeError(
                    "Unsupported remote archive type: "
                    f"{filename}"
                )

            self.progress.emit(
                "Reading page list..."
            )

            pages = archive.list_pages()

            if not pages:
                archive.close()
                archive = None

                raise RuntimeError(
                    "The selected volume contains "
                    "no image pages."
                )

            self.finished.emit(
                archive,
                pages,
            )

        except Exception as error:

            if archive is not None:
                try:
                    archive.close()
                except Exception:
                    pass

            self.failed.emit(
                str(error)
            )
