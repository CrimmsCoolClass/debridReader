import io

import pypdfium2 as pdfium


class RemotePDFFile(io.RawIOBase):

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

    # ========================================================
    # Reading
    # ========================================================

    def read(
        self,
        size=-1,
    ):
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

    def readinto(
        self,
        buffer,
    ):
        data = self.read(
            len(buffer)
        )

        length = len(data)

        buffer[:length] = data

        return length

    # ========================================================
    # Seeking
    # ========================================================

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

        self.position = min(
            new_position,
            self.size,
        )

        return self.position

    def tell(self):
        return self.position

    def readable(self):
        return True

    def seekable(self):
        return True


class RemotePDF:

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

        self.document = pdfium.PdfDocument(
            self.file
        )

    # ========================================================
    # Information
    # ========================================================

    @property
    def page_count(self):
        return len(
            self.document
        )

    # ========================================================
    # Rendering
    # ========================================================

    def render_page(
        self,
        page_number,
        scale=1.5,
    ):
        if (
            page_number < 0
            or page_number >= self.page_count
        ):
            raise IndexError(
                "PDF page number out of range"
            )

        page = self.document[
            page_number
        ]

        bitmap = page.render(
            scale=scale
        )

        pil_image = bitmap.to_pil()

        output = io.BytesIO()

        pil_image.save(
            output,
            format="PNG",
        )

        return output.getvalue()

    # ========================================================
    # Closing
    # ========================================================

    def close(self):

        if self.document is not None:

            self.document.close()

            self.document = None

        self.file = None

    # ========================================================
    # Cache information
    # ========================================================

    def get_cache_info(self):

        return self.remote_file.get_cache_info()
