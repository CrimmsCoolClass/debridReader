import io

import fitz


class RemotePDFFile(io.RawIOBase):
    """
    Seekable view of a PDF stored inside a RemoteFile.

    offset:
        Absolute byte offset of the PDF data inside the outer RAR.

    size:
        Size of the PDF data.
    """

    def __init__(
        self,
        remote_file,
        offset,
        size,
    ):
        super().__init__()

        self.remote_file = remote_file
        self.offset = offset
        self.size = size
        self.position = 0

    def read(self, size=-1):
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

        data = self.remote_file.read(
            size
        )

        self.position += len(data)

        return data

    def seek(
        self,
        offset,
        whence=0,
    ):
        if whence == 0:
            new_position = offset

        elif whence == 1:
            new_position = (
                self.position + offset
            )

        elif whence == 2:
            new_position = (
                self.size + offset
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

    def readable(self):
        return True

    def seekable(self):
        return True


class RemotePDF:
    """
    PDF stored inside a remote RAR archive.

    The PDF is never downloaded as a complete file.
    PyMuPDF reads it through RemotePDFFile, which
    ultimately reads through RemoteFile's HTTP
    Range-request cache.
    """

    def __init__(
        self,
        remote_file,
        offset,
        size,
    ):
        self.remote_file = remote_file
        self.offset = offset
        self.size = size

        self.file = RemotePDFFile(
            remote_file,
            offset,
            size,
        )

        self.document = fitz.open(
            stream=self.file,
            filetype="pdf",
        )

    @property
    def page_count(self):
        return self.document.page_count

    def render_page(
        self,
        page_number,
        scale=1.5,
    ):
        """
        Render a PDF page and return PNG bytes.
        """

        if (
            page_number < 0
            or page_number >= self.page_count
        ):
            raise IndexError(
                "PDF page number out of range"
            )

        page = self.document.load_page(
            page_number
        )

        matrix = fitz.Matrix(
            scale,
            scale,
        )

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False,
        )

        return pixmap.tobytes(
            "png"
        )

    def close(self):
        self.document.close()

    def get_cache_info(self):
        return self.remote_file.get_cache_info()
