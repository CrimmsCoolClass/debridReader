import os

from PySide6.QtCore import (
    QThread,
    Signal,
    Qt,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reading_progress import ReadingProgress
from ui.pdf_reader_window import PDFReaderWindow
from ui.reader_window import ReaderWindow
from workers.open_pdf import OpenPDFWorker
from workers.open_volume import OpenVolumeWorker


class LibraryWindow(QMainWindow):

    # ========================================================
    # Worker signals
    # ========================================================

    open_volume_requested = Signal(
        str,
        str,
    )

    open_pdf_requested = Signal(
        str,
        str,
    )

    scan_pdfs_requested = Signal(
        str,
    )

    def __init__(self, realdebrid):
        super().__init__()

        self.realdebrid = realdebrid

        # ====================================================
        # Open-volume worker
        # ====================================================

        self.open_worker_thread = QThread(
            self
        )

        self.open_worker = OpenVolumeWorker(
            self.realdebrid
        )

        self.open_worker.moveToThread(
            self.open_worker_thread
        )

        self.open_volume_requested.connect(
            self.open_worker.open_volume,
            Qt.ConnectionType.QueuedConnection,
        )

        self.open_worker.finished.connect(
            self.volume_opened
        )

        self.open_worker.failed.connect(
            self.volume_open_failed
        )

        self.open_worker.progress.connect(
            self.volume_open_progress
        )

        self.open_worker_thread.start()

        # ====================================================
        # Open-PDF worker
        # ====================================================

        self.open_pdf_worker_thread = QThread(
            self
        )

        self.open_pdf_worker = OpenPDFWorker(
            self.realdebrid
        )

        self.open_pdf_worker.moveToThread(
            self.open_pdf_worker_thread
        )

        self.open_pdf_requested.connect(
            self.open_pdf_worker.open_pdf,
            Qt.ConnectionType.QueuedConnection,
        )

        self.scan_pdfs_requested.connect(
            self.open_pdf_worker.scan_pdfs,
            Qt.ConnectionType.QueuedConnection,
        )

        self.open_pdf_worker.finished.connect(
            self.pdf_opened
        )

        self.open_pdf_worker.failed.connect(
            self.pdf_open_failed
        )

        self.open_pdf_worker.progress.connect(
            self.pdf_open_progress
        )

        self.open_pdf_worker.pdfs_found.connect(
            self.pdfs_found
        )

        self.open_pdf_worker_thread.start()

        # ====================================================
        # State
        # ====================================================

        self.torrents = []

        self.current_torrent = None
        self.current_info = None
        self.current_volume_name = None
        self.current_pdf_name = None

        self.remote_file = None
        self.remote_rar = None

        self.current_view = "works"

        self.reading_progress = ReadingProgress()

        self.reader = None
        self.pdf_reader = None

        # When a volume reaches its final page, the reader
        # closes and this stores the next volume to open.
        self.pending_next_volume = None

        # ====================================================
        # Window
        # ====================================================

        self.setWindowTitle(
            "Debrid Reader"
        )

        self.resize(
            1200,
            700,
        )

        # ====================================================
        # Search
        # ====================================================

        self.search_box = QLineEdit()

        self.search_box.setPlaceholderText(
            "Search works..."
        )

        self.search_box.textChanged.connect(
            self.filter_torrents
        )

        # ====================================================
        # View buttons
        # ====================================================

        self.works_button = QPushButton(
            "Works"
        )

        self.currently_reading_button = (
            QPushButton(
                "Currently Reading"
            )
        )

        self.works_button.setCheckable(
            True
        )

        self.currently_reading_button.setCheckable(
            True
        )

        self.works_button.setChecked(
            True
        )

        self.works_button.clicked.connect(
            self.show_works
        )

        self.currently_reading_button.clicked.connect(
            self.show_currently_reading
        )

        view_button_layout = QHBoxLayout()

        view_button_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        view_button_layout.setSpacing(
            4
        )

        view_button_layout.addWidget(
            self.works_button
        )

        view_button_layout.addWidget(
            self.currently_reading_button
        )

        # ====================================================
        # Works list
        # ====================================================

        self.torrent_list = QListWidget()

        self.torrent_list.currentItemChanged.connect(
            self.torrent_selected
        )

        # ====================================================
        # Currently Reading tree
        # ====================================================

        self.currently_reading_tree = (
            QTreeWidget()
        )

        self.currently_reading_tree.setHeaderLabels(
            [
                "Currently Reading",
                "Page",
            ]
        )

        self.currently_reading_tree.setColumnCount(
            2
        )

        self.currently_reading_tree.setRootIsDecorated(
            True
        )

        self.currently_reading_tree.setAlternatingRowColors(
            True
        )

        self.currently_reading_tree.itemDoubleClicked.connect(
            self.currently_reading_double_clicked
        )

        # ====================================================
        # Volumes
        # ====================================================

        self.volume_list = QListWidget()

        self.volume_list.itemDoubleClicked.connect(
            self.volume_double_clicked
        )

        # ====================================================
        # Status
        # ====================================================

        self.status_label = QLabel(
            "Loading works..."
        )

        # ====================================================
        # Open button
        # ====================================================

        self.open_button = QPushButton(
            "Open Volume"
        )

        self.open_button.clicked.connect(
            self.open_selected_volume
        )

        # ====================================================
        # Left side
        # ====================================================

        left_layout = QVBoxLayout()

        left_layout.addLayout(
            view_button_layout
        )

        left_layout.addWidget(
            self.search_box
        )

        left_layout.addWidget(
            self.torrent_list
        )

        left_layout.addWidget(
            self.currently_reading_tree
        )

        # ====================================================
        # Right side
        # ====================================================

        right_layout = QVBoxLayout()

        right_layout.addWidget(
            QLabel("Volumes")
        )

        right_layout.addWidget(
            self.volume_list
        )

        right_layout.addWidget(
            self.open_button
        )

        # ====================================================
        # Main layout
        # ====================================================

        content_layout = QHBoxLayout()

        content_layout.addLayout(
            left_layout,
            1,
        )

        content_layout.addLayout(
            right_layout,
            2,
        )

        layout = QVBoxLayout()

        layout.addLayout(
            content_layout
        )

        layout.addWidget(
            self.status_label
        )

        central_widget = QWidget()

        central_widget.setLayout(
            layout
        )

        self.setCentralWidget(
            central_widget
        )

        # ====================================================
        # Initial UI state
        # ====================================================

        self.currently_reading_tree.hide()

        # ====================================================
        # Load torrents
        # ====================================================

        self.load_torrents()

    # ========================================================
    # View switching
    # ========================================================

    def show_works(self):

        self.current_view = "works"

        self.works_button.setChecked(
            True
        )

        self.currently_reading_button.setChecked(
            False
        )

        self.search_box.show()

        self.torrent_list.show()

        self.currently_reading_tree.hide()

        self.status_label.setText(
            f"{len(self.torrents)} works"
        )

    def show_currently_reading(self):

        self.current_view = (
            "currently_reading"
        )

        self.works_button.setChecked(
            False
        )

        self.currently_reading_button.setChecked(
            True
        )

        self.search_box.hide()

        self.torrent_list.hide()

        self.currently_reading_tree.show()

        self.populate_currently_reading()

    # ========================================================
    # Torrent list
    # ========================================================

    def load_torrents(self):

        try:

            self.torrents = (
                self.realdebrid.get_torrents()
            )

            self.populate_torrent_list()

            self.status_label.setText(
                f"{len(self.torrents)} works"
            )

        except Exception as error:

            self.status_label.setText(
                f"Failed to load works: {error}"
            )

    def populate_torrent_list(self):

        self.torrent_list.clear()

        search_text = (
            self.search_box.text()
            .strip()
            .lower()
        )

        for torrent in self.torrents:

            filename = torrent.get(
                "filename",
                "Unknown",
            )

            if (
                search_text
                and search_text
                not in filename.lower()
            ):
                continue

            item = QListWidgetItem(
                filename
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                torrent,
            )

            self.torrent_list.addItem(
                item
            )

    def filter_torrents(self):

        self.populate_torrent_list()

    # ========================================================
    # Currently Reading
    # ========================================================

    def populate_currently_reading(self):

        self.reading_progress = (
            ReadingProgress()
        )

        self.currently_reading_tree.clear()

        volumes = (
            self.reading_progress.data.get(
                "volumes",
                {}
            )
        )

        works = {}

        for key, progress in volumes.items():

            if not isinstance(
                progress,
                dict,
            ):
                continue

            torrent_id = progress.get(
                "torrent_id"
            )

            volume_name = progress.get(
                "volume"
            )

            page = progress.get(
                "page"
            )

            if not torrent_id:
                continue

            if not volume_name:
                continue

            if not isinstance(
                page,
                int,
            ):
                continue

            if page <= 0:
                continue

            work_name = self.get_work_name(
                torrent_id
            )

            if work_name is None:
                work_name = (
                    progress.get(
                        "work",
                        "Unknown Work",
                    )
                )

            if work_name not in works:

                works[work_name] = []

            works[work_name].append(
                {
                    "key": key,
                    "torrent_id": torrent_id,
                    "volume": volume_name,
                    "page": page,
                }
            )

        for work_name in sorted(
            works,
            key=str.lower,
        ):

            work_item = QTreeWidgetItem(
                self.currently_reading_tree
            )

            work_item.setText(
                0,
                work_name,
            )

            work_item.setFirstColumnSpanned(
                False
            )

            work_item.setExpanded(
                True
            )

            work_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                None,
            )

            for volume in sorted(
                works[work_name],
                key=lambda entry:
                    entry["volume"].lower(),
            ):

                volume_item = (
                    QTreeWidgetItem(
                        work_item
                    )
                )

                volume_item.setText(
                    0,
                    self.clean_volume_name(
                        volume["volume"]
                    ),
                )

                volume_item.setText(
                    1,
                    f"Page {volume['page'] + 1}",
                )

                volume_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    volume,
                )

        self.currently_reading_tree.resizeColumnToContents(
            0
        )

        self.currently_reading_tree.resizeColumnToContents(
            1
        )

        volume_count = sum(
            len(entries)
            for entries in works.values()
        )

        self.status_label.setText(
            f"{volume_count} volume"
            f"{'' if volume_count == 1 else 's'} "
            "currently reading"
        )

    def get_work_name(
        self,
        torrent_id,
    ):

        for torrent in self.torrents:

            if torrent.get("id") == torrent_id:

                filename = torrent.get(
                    "filename",
                    "",
                )

                return self.clean_work_name(
                    filename
                )

        return None

    def clean_work_name(
        self,
        filename,
    ):

        if not filename:
            return "Unknown Work"

        name = os.path.basename(
            filename
        )

        lower_name = name.lower()

        if lower_name.endswith(
            ".torrent"
        ):

            name = name[:-8]

        elif lower_name.endswith(
            ".rar"
        ):

            name = name[:-4]

        elif lower_name.endswith(
            ".cbz"
        ):

            name = name[:-4]

        elif lower_name.endswith(
            ".zip"
        ):

            name = name[:-4]

        elif lower_name.endswith(
            ".pdf"
        ):

            name = name[:-4]

        return name.strip()

    # ========================================================
    # Currently Reading selection
    # ========================================================

    def currently_reading_double_clicked(
        self,
        item,
        column,
    ):

        volume = item.data(
            0,
            Qt.ItemDataRole.UserRole,
        )

        if volume is None:
            return

        torrent_id = volume.get(
            "torrent_id"
        )

        volume_name = volume.get(
            "volume"
        )

        if not torrent_id or not volume_name:
            return

        torrent = None

        for candidate in self.torrents:

            if candidate.get(
                "id"
            ) == torrent_id:

                torrent = candidate
                break

        if torrent is None:

            QMessageBox.warning(
                self,
                "Work Not Found",
                "This work is no longer "
                "available in Real-Debrid.",
            )

            return

        self.current_torrent = torrent

        self.current_volume_name = (
            volume_name
        )

        self.open_volume_from_progress()

    def open_volume_from_progress(self):

        if self.current_torrent is None:
            return

        torrent_id = (
            self.current_torrent["id"]
        )

        if not self.current_volume_name:
            return

        self.pending_next_volume = None

        self.volume_list.setEnabled(
            False
        )

        self.open_button.setEnabled(
            False
        )

        self.status_label.setText(
            "Opening volume..."
        )

        self.open_volume_requested.emit(
            torrent_id,
            self.current_volume_name,
        )

    # ========================================================
    # Torrent selection
    # ========================================================

    def torrent_selected(
        self,
        current,
        previous,
    ):

        if current is None:
            return

        torrent = current.data(
            Qt.ItemDataRole.UserRole
        )

        if torrent is None:
            return

        self.current_torrent = torrent

        self.volume_list.clear()

        self.status_label.setText(
            "Loading volumes..."
        )

        try:

            torrent_id = torrent["id"]

            info = (
                self.realdebrid.get_torrent_info(
                    torrent_id
                )
            )

            self.current_info = info

            self.load_volumes(
                info
            )

        except Exception as error:

            self.status_label.setText(
                f"Failed to load volumes: {error}"
            )

    # ========================================================
    # Volume discovery
    # ========================================================

    def load_volumes(
        self,
        info,
    ):

        self.volume_list.clear()

        files = info.get(
            "files",
            [],
        )

        cbz_files = []

        for file_info in files:

            path = file_info.get(
                "path",
                "",
            )

            if path.lower().endswith(
                ".cbz"
            ):

                cbz_files.append(
                    file_info
                )

        if cbz_files:

            for file_info in cbz_files:

                path = file_info[
                    "path"
                ]

                item = QListWidgetItem(
                    self.clean_volume_name(
                        path
                    )
                )

                item.setData(
                    Qt.ItemDataRole.UserRole,
                    file_info,
                )

                item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    "torrent_file",
                )

                self.volume_list.addItem(
                    item
                )

        links = info.get(
            "links",
            [],
        )

        if links:

            self.status_label.setText(
                f"{len(cbz_files)} volumes — "
                "scanning for PDFs..."
            )

            if self.current_torrent is None:

                self.status_label.setText(
                    "Unable to determine current torrent."
                )

                return

            torrent_id = (
                self.current_torrent["id"]
            )

            self.scan_pdfs_requested.emit(
                torrent_id
            )

        else:

            self.status_label.setText(
                "No downloadable links"
            )

    # ========================================================
    # PDF discovery callback
    # ========================================================

    def pdfs_found(
        self,
        pdfs,
    ):

        if self.current_torrent is None:
            return

        for pdf in pdfs:

            filename = pdf.get(
                "filename",
                "",
            )

            if not filename:
                continue

            item = QListWidgetItem(
                self.clean_volume_name(
                    filename
                )
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "path": filename,
                    "pdf": pdf,
                },
            )

            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                "pdf",
            )

            self.volume_list.addItem(
                item
            )

        cbz_count = 0
        pdf_count = 0

        for index in range(
            self.volume_list.count()
        ):

            item = self.volume_list.item(
                index
            )

            item_type = item.data(
                Qt.ItemDataRole.UserRole + 1
            )

            if item_type == "torrent_file":
                cbz_count += 1

            elif item_type == "pdf":
                pdf_count += 1

        if pdf_count:

            self.status_label.setText(
                f"{cbz_count} volumes, "
                f"{pdf_count} PDFs"
            )

        else:

            self.status_label.setText(
                f"{cbz_count} volumes"
            )

    # ========================================================
    # Volume opening
    # ========================================================

    def open_selected_volume(self):

        item = (
            self.volume_list.currentItem()
        )

        if item is None:
            return

        self.open_volume(
            item
        )

    def volume_double_clicked(
        self,
        item,
    ):

        self.open_volume(
            item
        )

    # ========================================================
    # Open volume / PDF
    # ========================================================

    def open_volume(
        self,
        item,
    ):

        if self.current_torrent is None:
            return

        item_type = item.data(
            Qt.ItemDataRole.UserRole + 1
        )

        selected_file = item.data(
            Qt.ItemDataRole.UserRole
        )

        if selected_file is None:
            return

        selected_name = selected_file.get(
            "path",
            "",
        )

        if not selected_name:

            self.status_label.setText(
                "Unable to determine selected file."
            )

            return

        torrent_id = (
            self.current_torrent["id"]
        )

        self.pending_next_volume = None

        self.volume_list.setEnabled(
            False
        )

        self.open_button.setEnabled(
            False
        )

        # ====================================================
        # PDF
        # ====================================================

        if item_type == "pdf":

            self.current_pdf_name = (
                selected_name
            )

            self.status_label.setText(
                "Opening PDF..."
            )

            self.open_pdf_requested.emit(
                torrent_id,
                selected_name,
            )

            return

        # ====================================================
        # CBZ volume
        # ====================================================

        self.current_volume_name = (
            selected_name
        )

        self.status_label.setText(
            "Opening volume..."
        )

        self.open_volume_requested.emit(
            torrent_id,
            selected_name,
        )

    # ========================================================
    # Volume worker callbacks
    # ========================================================

    def volume_open_progress(
        self,
        message,
    ):

        self.status_label.setText(
            message
        )

    def volume_open_failed(
        self,
        error,
    ):

        self.volume_list.setEnabled(
            True
        )

        self.open_button.setEnabled(
            True
        )

        self.status_label.setText(
            f"Failed to open volume: {error}"
        )

        QMessageBox.critical(
            self,
            "Open Volume",
            str(error),
        )

    def volume_opened(
        self,
        archive,
        pages,
    ):

        self.volume_list.setEnabled(
            True
        )

        self.open_button.setEnabled(
            True
        )

        if (
            self.current_torrent is None
            or not self.current_volume_name
        ):

            archive.close()

            self.status_label.setText(
                "Unable to determine volume."
            )

            return

        torrent_id = (
            self.current_torrent["id"]
        )

        progress_key = (
            f"{torrent_id}|"
            f"{self.current_volume_name}"
        )

        self.reading_progress = (
            ReadingProgress()
        )

        initial_page = (
            self.reading_progress.get_page(
                progress_key
            )
        )

        # A completed volume should have been removed
        # from the progress file. This extra guard prevents
        # an invalid saved page from opening past the end.
        if initial_page >= len(pages):

            initial_page = 0

        reader = ReaderWindow(
            archive,
            pages,
            initial_page=initial_page,
            progress_key=progress_key,
            torrent_id=torrent_id,
            volume_name=self.current_volume_name,
        )

        reader.closed.connect(
            self.reader_closed
        )

        reader.volume_finished.connect(
            self.volume_finished
        )

        reader.show()

        self.reader = reader

        self.status_label.setText(
            "Volume opened"
        )

    # ========================================================
    # PDF worker callbacks
    # ========================================================

    def pdf_open_progress(
        self,
        message,
    ):

        self.status_label.setText(
            message
        )

    def pdf_open_failed(
        self,
        error,
    ):

        self.volume_list.setEnabled(
            True
        )

        self.open_button.setEnabled(
            True
        )

        self.status_label.setText(
            f"Failed to open PDF: {error}"
        )

        QMessageBox.critical(
            self,
            "Open PDF",
            str(error),
        )

    def pdf_opened(
        self,
        pdf,
    ):

        self.volume_list.setEnabled(
            True
        )

        self.open_button.setEnabled(
            True
        )

        reader = PDFReaderWindow(
            pdf
        )

        reader.closed.connect(
            self.pdf_reader_closed
        )

        reader.show()

        self.pdf_reader = reader

        self.status_label.setText(
            "PDF opened"
        )

    def pdf_reader_closed(self):

        self.pdf_reader = None

        self.current_pdf_name = None

        if (
            self.current_view
            == "currently_reading"
        ):

            self.populate_currently_reading()

        else:

            self.status_label.setText(
                "Ready"
            )

    # ========================================================
    # Volume completion / next volume
    # ========================================================

    def get_next_volume_name(self):

        if self.current_torrent is None:
            return None

        torrent_id = self.current_torrent.get(
            "id"
        )

        if not torrent_id:
            return None

        info = self.current_info

        if info is None:

            try:

                info = (
                    self.realdebrid.get_torrent_info(
                        torrent_id
                    )
                )

                self.current_info = info

            except Exception as error:

                print(
                    "Unable to get torrent info "
                    f"for next volume: {error}"
                )

                return None

        files = info.get(
            "files",
            [],
        )

        volume_names = []

        for file_info in files:

            path = file_info.get(
                "path",
                "",
            )

            if path.lower().endswith(
                ".cbz"
            ):

                volume_names.append(
                    path
                )

        if not volume_names:
            return None

        current_name = self.current_volume_name

        if not current_name:
            return None

        # Real-Debrid's logical file order is the order
        # we want for "next volume." Do not use physical
        # RAR order.
        current_index = None

        for index, name in enumerate(
            volume_names
        ):

            if name == current_name:

                current_index = index
                break

        # Some API responses can differ in path prefix,
        # so fall back to basename comparison.
        if current_index is None:

            current_base = os.path.basename(
                current_name
            ).lower()

            for index, name in enumerate(
                volume_names
            ):

                if (
                    os.path.basename(
                        name
                    ).lower()
                    == current_base
                ):

                    current_index = index
                    break

        if current_index is None:
            return None

        next_index = current_index + 1

        if next_index >= len(
            volume_names
        ):

            return None

        return volume_names[
            next_index
        ]

    def volume_finished(self):

        self.pending_next_volume = (
            self.get_next_volume_name()
        )

    # ========================================================
    # Reader closed
    # ========================================================

    def reader_closed(self):

        self.reading_progress = (
            ReadingProgress()
        )

        next_volume = (
            self.pending_next_volume
        )

        self.pending_next_volume = None

        self.reader = None

        if next_volume:

            if self.current_torrent is None:

                self.status_label.setText(
                    "Unable to open next volume."
                )

                return

            torrent_id = (
                self.current_torrent["id"]
            )

            self.current_volume_name = (
                next_volume
            )

            self.status_label.setText(
                "Opening next volume..."
            )

            self.open_volume_requested.emit(
                torrent_id,
                next_volume,
            )

            return

        if (
            self.current_view
            == "currently_reading"
        ):

            self.populate_currently_reading()

        else:

            self.status_label.setText(
                "Ready"
            )

    # ========================================================
    # Volume names
    # ========================================================

    def clean_volume_name(
        self,
        path,
    ):

        name = os.path.basename(
            path
        )

        lower_name = name.lower()

        if lower_name.endswith(
            ".cbz"
        ):

            name = name[:-4]

        elif lower_name.endswith(
            ".zip"
        ):

            name = name[:-4]

        elif lower_name.endswith(
            ".pdf"
        ):

            name = name[:-4]

        return name.strip()

    # ========================================================
    # Window close
    # ========================================================

    def closeEvent(
        self,
        event,
    ):

        self.open_worker_thread.quit()

        self.open_worker_thread.wait()

        self.open_pdf_worker_thread.quit()

        self.open_pdf_worker_thread.wait()

        event.accept()
