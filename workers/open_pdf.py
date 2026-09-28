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
    """
    Worker responsible for opening a PDF stored inside
    a Real-Debrid RAR archive.

    This is intentionally separate from OpenVolumeWorker
    so the existing CBZ code does not need to know about
    PDFs.
    """

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, realdebrid):
        super().__init__()

        self.realdebrid = realdebrid

    @Slot(str, str)
    def open_pdf(
        self,
        torrent_id,
        selected_name,
    ):
        remote_file = None
        pdf = None

        try:
            # --------------------------------------------------
            # Get torrent information
            # --------------------------------------------------

            self.progress.emit(
                "Getting torrent information..."
            )

            info = self.realdebrid.get_torrent_info(
                torrent_id
            )

            links = info.get(
                "links",
                [],
            )

            if not links:
                raise RuntimeError(
                    "Torrent has no downloadable links."
                )

            # --------------------------------------------------
            # Get Real-Debrid download link
            # --------------------------------------------------

            self.progress.emit(
                "Getting download link..."
            )

            unrestricted = (
                self.realdebrid.unrestrict_link(
                    links[0]
                )
            )

            download_url = unrestricted[
                "download"
            ]

            filename = unrestricted[
                "filename"
            ]

            file_size = int(
                unrestricted[
                    "filesize"
                ]
            )

            # --------------------------------------------------
            # Make the outer RAR remotely accessible
            # --------------------------------------------------

            remote_file = RemoteFile(
                download_url,
                file_size,
                cache_size=500 * 1024 * 1024,
                block_size=4 * 1024 * 1024,
            )

            # --------------------------------------------------
            # Verify that Real-Debrid gave us a RAR
            # --------------------------------------------------

            if not filename.lower().endswith(
                ".rar"
            ):
                raise RuntimeError(
                    "Expected a RAR download from "
                    "Real-Debrid, but received: "
                    f"{filename}"
                )

            # --------------------------------------------------
            # Scan the RAR
            #
            # This uses the existing lightweight RAR scanner.
            # It only reads RAR headers and does not download
            # the PDF contents.
            # --------------------------------------------------

            self.progress.emit(
                "Scanning RAR archive..."
            )

            rar = RemoteRARArchive(
                remote_file
            )

            entries = rar.entries

            # --------------------------------------------------
            # Find the requested PDF
            # --------------------------------------------------

            selected_basename = (
                os.path.basename(
                    selected_name
                ).lower()
            )

            selected_entry = None

            for entry in entries:

                entry_filename = os.path.basename(
                    entry["filename"]
                ).lower()

                if (
                    entry_filename
                    == selected_basename
                    and entry_filename.endswith(
                        ".pdf"
                    )
                ):
                    selected_entry = entry
                    break

            # --------------------------------------------------
            # If the exact filename wasn't found, try matching
            # by filename alone. This is useful if the caller
            # supplied a path while the RAR stores only a
            # basename.
            # --------------------------------------------------

            if selected_entry is None:

                for entry in entries:

                    entry_filename = os.path.basename(
                        entry["filename"]
                    ).lower()

                    if (
                        entry_filename
                        == selected_basename
                    ):
                        selected_entry = entry
                        break

            if selected_entry is None:
                raise RuntimeError(
                    "Could not find the selected "
                    f"PDF inside the RAR: "
                    f"{selected_name}"
                )

            # --------------------------------------------------
            # Open the PDF directly from its RAR byte range
            # --------------------------------------------------

            self.progress.emit(
                "Opening PDF..."
            )

            pdf = RemotePDF(
                remote_file,
                selected_entry["offset"],
                selected_entry["size"],
            )

            # --------------------------------------------------
            # Make sure PyMuPDF successfully opened it
            # --------------------------------------------------

            page_count = pdf.page_count

            if page_count <= 0:
                raise RuntimeError(
                    "The PDF contains no pages."
                )

            self.progress.emit(
                f"PDF opened: {page_count} pages"
            )

            # --------------------------------------------------
            # Return the PDF object.
            #
            # The worker deliberately does NOT close
            # remote_file here because RemotePDF needs it
            # while the document remains open.
            # --------------------------------------------------

            self.finished.emit(
                pdf
            )

            pdf = None
            remote_file = None

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
