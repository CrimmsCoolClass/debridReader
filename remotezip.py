import io
import struct
import zipfile


class RemoteCBZ(io.RawIOBase):
    def __init__(self, remote_file, offset, size):
        self.remote_file = remote_file
        self.offset = offset
        self.size = size
        self.position = 0

    def read(self, size=-1):
        """Read bytes from the CBZ."""

        if self.position >= self.size:
            return b""

        if size < 0:
            size = self.size - self.position

        size = min(
            size,
            self.size - self.position,
        )

        self.remote_file.seek(
            self.offset + self.position
        )

        data = self.remote_file.read(size)

        self.position += len(data)

        return data

    def seek(self, offset, whence=0):
        """Move within the CBZ."""

        if whence == 0:
            new_position = offset

        elif whence == 1:
            new_position = self.position + offset

        elif whence == 2:
            new_position = self.size + offset

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
        """Return the current position."""

        return self.position

    def readable(self):
        return True

    def seekable(self):
        return True


class RemoteCBZArchive:
    def __init__(
        self,
        remote_file,
        offset,
        size,
    ):
        self.remote_file = remote_file
        self.offset = offset
        self.size = size

        self.file = RemoteCBZ(
            remote_file,
            offset,
            size,
        )

        self.zip = zipfile.ZipFile(
            self.file
        )

    def list_files(self):
        """Return the names of all files in the CBZ."""

        return self.zip.namelist()

    def list_pages(self):
        """Return image files in the CBZ."""

        pages = []

        for filename in self.zip.namelist():
            lower_name = filename.lower()

            if lower_name.endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            ):
                pages.append(filename)

        return pages

    def read_file(self, filename):
        """Read and decompress a file from the CBZ."""

        with self.zip.open(filename) as file:
            return file.read()

    def close(self):
        self.zip.close()


class RemoteRARArchive:
    """
    Lightweight RAR4 container scanner.

    This does not decompress RAR files.

    It only reads the RAR headers so we can locate
    files stored inside the RAR.
    """

    RAR4_SIGNATURE = (
        b"Rar!\x1a\x07\x00"
    )

    FILE_HEADER = 0x74
    END_HEADER = 0x7B

    FLAG_LARGE = 0x0100
    FLAG_UNICODE = 0x0200
    FLAG_SALT = 0x0400
    FLAG_LONG_BLOCK = 0x8000

    def __init__(self, remote_file):
        self.remote_file = remote_file
        self.entries = []

        self._scan()

    def _read_at(self, offset, size):
        """Read a section of the remote RAR."""

        self.remote_file.seek(offset)

        data = self.remote_file.read(size)

        if len(data) != size:
            raise IOError(
                "Unexpected end of remote RAR"
            )

        return data

    @staticmethod
    def _decode_filename(
        filename_data,
        unicode_flag,
    ):
        """
        Decode a RAR filename.

        Most modern comic archives use UTF-8-compatible
        names, so try UTF-8 first and then common fallbacks.
        """

        if not filename_data:
            return ""

        if unicode_flag:
            # RAR Unicode filenames contain an ANSI name
            # followed by RAR's Unicode encoding.

            zero = filename_data.find(
                b"\x00"
            )

            if zero >= 0:
                ansi_name = filename_data[
                    :zero
                ]

                try:
                    return ansi_name.decode(
                        "utf-8"
                    )
                except UnicodeDecodeError:
                    try:
                        return ansi_name.decode(
                            "cp437"
                        )
                    except UnicodeDecodeError:
                        return ansi_name.decode(
                            "latin-1",
                            errors="replace",
                        )

        for encoding in (
            "utf-8",
            "cp437",
            "latin-1",
        ):
            try:
                return filename_data.decode(
                    encoding
                )
            except UnicodeDecodeError:
                pass

        return filename_data.decode(
            "utf-8",
            errors="replace",
        )

    def _scan(self):
        """Scan the RAR headers."""

        signature = self._read_at(
            0,
            7,
        )

        if signature != self.RAR4_SIGNATURE:
            raise ValueError(
                "Remote file is not a RAR4 archive"
            )

        position = 7

        while position < self.remote_file.size:

            base_header = self._read_at(
                position,
                7,
            )

            (
                _head_crc,
                head_type,
                head_flags,
                head_size,
            ) = struct.unpack(
                "<HBHH",
                base_header,
            )

            if head_size < 7:
                raise ValueError(
                    "Invalid RAR header size"
                )

            header = self._read_at(
                position,
                head_size,
            )

            # ------------------------------------------------
            # RAR file entry
            # ------------------------------------------------

            if head_type == self.FILE_HEADER:

                pack_size = struct.unpack_from(
                    "<I",
                    header,
                    7,
                )[0]

                unpacked_size = struct.unpack_from(
                    "<I",
                    header,
                    11,
                )[0]

                name_size = struct.unpack_from(
                    "<H",
                    header,
                    26,
                )[0]

                data_offset = (
                    position + head_size
                )

                # Files larger than 4 GiB have high
                # size fields after ATTR.
                if head_flags & self.FLAG_LARGE:

                    high_pack_size = (
                        struct.unpack_from(
                            "<I",
                            header,
                            32,
                        )[0]
                    )

                    high_unpacked_size = (
                        struct.unpack_from(
                            "<I",
                            header,
                            36,
                        )[0]
                    )

                    pack_size |= (
                        high_pack_size << 32
                    )

                    unpacked_size |= (
                        high_unpacked_size << 32
                    )

                    name_offset = 40

                else:
                    name_offset = 32

                name_end = (
                    name_offset + name_size
                )

                if name_end > len(header):
                    raise ValueError(
                        "Invalid RAR filename"
                    )

                filename_data = header[
                    name_offset:name_end
                ]

                filename = self._decode_filename(
                    filename_data,
                    bool(
                        head_flags
                        & self.FLAG_UNICODE
                    ),
                )

                entry = {
                    "filename": filename,
                    "offset": data_offset,
                    "size": pack_size,
                    "unpacked_size": (
                        unpacked_size
                    ),
                    "flags": head_flags,
                }

                self.entries.append(entry)

                # RAR entries may be split across
                # multiple volumes. Those aren't usable
                # as standalone CBZ files.
                if head_flags & 0x0001:
                    entry["split_before"] = True
                else:
                    entry["split_before"] = False

                if head_flags & 0x0002:
                    entry["split_after"] = True
                else:
                    entry["split_after"] = False

                position = (
                    data_offset + pack_size
                )

                continue

            # ------------------------------------------------
            # End of archive
            # ------------------------------------------------

            if head_type == self.END_HEADER:
                break

            # ------------------------------------------------
            # Other RAR block types
            # ------------------------------------------------

            if head_flags & self.FLAG_LONG_BLOCK:

                additional_size = (
                    struct.unpack_from(
                        "<I",
                        header,
                        7,
                    )[0]
                )

                position += (
                    head_size
                    + additional_size
                )

            else:
                position += head_size

    def list_files(self):
        """Return all files in the RAR."""

        return list(self.entries)

    def list_cbzs(self):
        """Return CBZ files stored in the RAR."""

        result = []

        for entry in self.entries:

            filename = entry[
                "filename"
            ]

            if filename.lower().endswith(
                ".cbz"
            ):
                result.append(entry)

        return result

    def open_cbz(self, entry):
        """Open a CBZ stored inside the RAR."""

        return RemoteCBZArchive(
            self.remote_file,
            entry["offset"],
            entry["size"],
        )

    def close(self):
        """
        Close the underlying remote file.

        RemoteFile currently doesn't have a close
        operation, so this exists for symmetry.
        """
