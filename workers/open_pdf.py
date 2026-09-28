import os

from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

from remotefile import RemoteFile
from remotepdf import RemotePDF
from remotezip import RemoteRARArchive


class OpenPDFWorker(QObject):

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    pdfs_found = Signal(object)

    def __init__(self, realdebrid):
        super().__init__()
        self.realdebrid = realdebrid

    @Slot(str, str)
    def open_pdf(self, torrent_id, selected_name):
        remote_file = None
        pdf = None

        try:
            self.progress.emit(
                "Getting torrent information..."
            )

            info = self.realdebrid.get_torrent_info(
                torrent_id
            )

            links = info.get("links", [])

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

            download_url = unrestricted["download"]
            filename = unrestricted["filename"]
            file_size = int(
                unrestricted["filesize"]
            )

            remote_file = RemoteFile(
                download_url,
                file_size,
                cache_size=500 * 1024 * 1024,
                block_size=4 * 1024 * 1024,
            )

            lower_filename = filename.lower()

            # --------------------------------------------------
            # Case 1:
            # Real-Debrid gave us a standalone PDF.
            # --------------------------------------------------

            if lower_filename.endswith(".pdf"):

                self.progress.emit(
                    "Opening PDF..."
                )

                pdf = RemotePDF(
                    remote_file,
                    0,
                    file_size,
                )

                page_count = pdf.page_count

                if page_count <= 0:
                    raise RuntimeError(
                        "The PDF contains no pages."
                    )

                self.progress.emit(
                    f"PDF opened: {page_count} pages"
                )

                self.finished.emit(pdf)

                # Ownership has now been transferred
                # to the PDF reader.
                pdf = None
                remote_file = None

                return

            # --------------------------------------------------
            # Case 2:
            # Real-Debrid gave us a RAR containing the PDF.
            # --------------------------------------------------

            if lower_filename.endswith(".rar"):

                self.progress.emit(
                    "Scanning RAR archive..."
                )

                rar = RemoteRARArchive(
                    remote_file
                )

                entries = rar.entries

                selected_basename = (
                    os.path.basename(
                        selected_name
                    ).lower()
                )

                selected_entry = None

                for entry in entries:
                    entry_filename = (
                        os.path.basename(
                            entry["filename"]
                        ).lower()
                    )

                    if (
                        entry_filename
                        == selected_basename
                        and entry_filename.endswith(
                            ".pdf"
                        )
                    ):
                        selected_entry = entry
                        break

                # If an exact basename match was not
                # found, try the complete stored name.
                if selected_entry is None:
                    selected_name_lower = (
                        selected_name.lower()
                    )

                    for entry in entries:
                        entry_filename = (
                            entry["filename"]
                            .lower()
                        )

                        if (
                            entry_filename
                            == selected_name_lower
                        ):
                            selected_entry = entry
                            break

                if selected_entry is None:
                    raise RuntimeError(
                        "Could not find the selected PDF "
                        "inside the RAR: "
                        f"{selected_name}"
                    )

                self.progress.emit(
                    "Opening PDF..."
                )

                pdf = RemotePDF(
                    remote_file,
                    selected_entry["offset"],
                    selected_entry["size"],
                )

                page_count = pdf.page_count

                if page_count <= 0:
                    raise RuntimeError(
                        "The PDF contains no pages."
                    )

                self.progress.emit(
                    f"PDF opened: {page_count} pages"
                )

                self.finished.emit(pdf)

                # Ownership has now been transferred
                # to the PDF reader.
                pdf = None
                remote_file = None

                return

            # --------------------------------------------------
            # Unsupported download type.
            # --------------------------------------------------

            raise RuntimeError(
                "Unsupported Real-Debrid download type: "
                f"{filename}"
            )

        except Exception as error:

            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass

            if remote_file is not None:
                try:
                    remote_file.close()
                except Exception:
                    pass

            self.failed.emit(
                str(error)
            )

    @Slot(str)
    def scan_pdfs(self, torrent_id):
        remote_file = None

        try:
            self.progress.emit(
                "Getting torrent information..."
            )

            info = self.realdebrid.get_torrent_info(
                torrent_id
            )

            links = info.get("links", [])

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

            download_url = unrestricted["download"]
            filename = unrestricted["filename"]
            file_size = int(
                unrestricted["filesize"]
            )

            remote_file = RemoteFile(
                download_url,
                file_size,
                cache_size=500 * 1024 * 1024,
                block_size=4 * 1024 * 1024,
            )

            lower_filename = filename.lower()

            # --------------------------------------------------
            # Standalone PDF
            # --------------------------------------------------

            if lower_filename.endswith(".pdf"):

                pdfs = [
                    {
                        "filename": filename,
                        "offset": 0,
                        "size": file_size,
                    }
                ]

                self.pdfs_found.emit(
                    pdfs
                )

                remote_file.close()

                return

            # --------------------------------------------------
            # PDF(s) inside RAR
            # --------------------------------------------------

            if lower_filename.endswith(".rar"):

                self.progress.emit(
                    "Scanning RAR for PDFs..."
                )

                rar = RemoteRARArchive(
                    remote_file
                )

                pdfs = []

                for entry in rar.entries:

                    name = entry.get(
                        "filename",
                        "",
                    )

                    if name.lower().endswith(
                        ".pdf"
                    ):
                        pdfs.append(
                            {
                                "filename": name,
                                "offset": entry["offset"],
                                "size": entry["size"],
                            }
                        )

                self.pdfs_found.emit(
                    pdfs
                )

                remote_file.close()

                return

            raise RuntimeError(
                "Unsupported Real-Debrid download type: "
                f"{filename}"
            )

        except Exception as error:

            if remote_file is not None:
                try:
                    remote_file.close()
                except Exception:
                    pass

            self.failed.emit(
                str(error)
            )
