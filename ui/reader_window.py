from PySide6.QtCore import (
    QThread,
    Qt,
    QEvent,
    Signal,
)
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QIntValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from reading_progress import ReadingProgress
from workers.page_loader import PageWorker


# ============================================================
# Image label
# ============================================================

class ImageLabel(QLabel):
    """
    QLabel used for displaying and dragging pages.
    """

    drag_started = Signal(object)
    drag_moved = Signal(object)
    drag_finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.drag_started.emit(
                event.position()
            )

            event.accept()

            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        self.drag_moved.emit(
            event.position()
        )

        event.accept()

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.drag_finished.emit(
                event.position()
            )

            event.accept()

            return

        super().mouseReleaseEvent(event)


# ============================================================
# Reader window
# ============================================================

class ReaderWindow(QMainWindow):

    page_requested = Signal(
        int,
        str,
    )

    closed = Signal()

    volume_finished = Signal()

    def __init__(
        self,
        archive,
        pages,
        initial_page=0,
        progress_key=None,
        torrent_id=None,
        volume_name=None,
        parent=None,
    ):
        super().__init__(parent)

        self.archive = archive
        self.pages = pages

        self.current_page = initial_page

        # ----------------------------------------------------
        # Reading progress
        # ----------------------------------------------------

        self.progress_key = progress_key
        self.torrent_id = torrent_id
        self.volume_name = volume_name

        self.progress = ReadingProgress()

        self.volume_completed = False

        # ----------------------------------------------------
        # Zoom
        # ----------------------------------------------------

        self.zoom_factor = 1.0
        self.min_zoom = 0.25
        self.max_zoom = 4.0

        # ----------------------------------------------------
        # Panning
        # ----------------------------------------------------

        self.dragging = False
        self.drag_start_position = None

        self.original_pixmap = None

        # ----------------------------------------------------
        # Window
        # ----------------------------------------------------

        self.setWindowTitle(
            "Debrid Reader"
        )

        self.resize(
            1200,
            900,
        )

        # ----------------------------------------------------
        # Image
        # ----------------------------------------------------

        self.image_label = ImageLabel()

        self.image_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.image_label.drag_started.connect(
            self.image_drag_started
        )

        self.image_label.drag_moved.connect(
            self.image_drag_moved
        )

        self.image_label.drag_finished.connect(
            self.image_drag_finished
        )

        # ----------------------------------------------------
        # Scroll area
        # ----------------------------------------------------

        self.scroll_area = QScrollArea()

        self.scroll_area.setWidget(
            self.image_label
        )

        self.scroll_area.setWidgetResizable(
            False
        )

        self.scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # ----------------------------------------------------
        # Page number editor
        # ----------------------------------------------------

        self.page_edit = QLineEdit()

        self.page_edit.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.page_edit.setFixedWidth(
            70
        )

        self.page_edit.returnPressed.connect(
            self.jump_to_page
        )

        self.page_total_label = QLabel()

        self.page_total_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # ----------------------------------------------------
        # Navigation layout
        # ----------------------------------------------------

        navigation_layout = QHBoxLayout()

        navigation_layout.addStretch()

        navigation_layout.addWidget(
            self.page_edit
        )

        navigation_layout.addWidget(
            self.page_total_label
        )

        navigation_layout.addStretch()

        layout = QVBoxLayout()

        layout.addWidget(
            self.scroll_area
        )

        layout.addLayout(
            navigation_layout
        )

        central_widget = QWidget()

        central_widget.setLayout(
            layout
        )

        self.setCentralWidget(
            central_widget
        )

        # ----------------------------------------------------
        # Worker
        # ----------------------------------------------------

        self.worker_thread = QThread(
            self
        )

        self.worker = PageWorker(
            self.archive
        )

        self.worker.moveToThread(
            self.worker_thread
        )

        self.page_requested.connect(
            self.worker.load_page,
            Qt.ConnectionType.QueuedConnection,
        )

        self.worker.finished.connect(
            self.page_loaded
        )

        self.worker.failed.connect(
            self.page_failed
        )

        self.worker_thread.start()

        # ----------------------------------------------------
        # Keyboard
        # ----------------------------------------------------

        app = QApplication.instance()

        if app is not None:

            app.installEventFilter(
                self
            )

        # ----------------------------------------------------
        # Restore reading position
        # ----------------------------------------------------

        if self.progress_key is not None:

            self.current_page = (
                self.progress.get_page(
                    self.progress_key
                )
            )

        # ----------------------------------------------------
        # Initial page
        # ----------------------------------------------------

        self.load_current_page()

    # ========================================================
    # Page navigation
    # ========================================================

    def load_current_page(self):

        if not self.pages:
            return

        self.current_page = max(
            0,
            min(
                self.current_page,
                len(self.pages) - 1,
            ),
        )

        self.update_page_label()

        filename = self.pages[
            self.current_page
        ]

        self.page_requested.emit(
            self.current_page,
            filename,
        )

    def next_page(self):

        # ----------------------------------------------------
        # Final image
        # ----------------------------------------------------

        if (
            self.current_page
            >= len(self.pages) - 1
        ):

            self.finish_volume()

            return

        # ----------------------------------------------------
        # Normal next page
        # ----------------------------------------------------

        self.current_page += 1

        self.save_reading_progress()

        self.load_current_page()

    def previous_page(self):

        if self.current_page > 0:

            self.current_page -= 1

            self.save_reading_progress()

            self.load_current_page()

    # ========================================================
    # Page jumping
    # ========================================================

    def jump_to_page(self):

        text = (
            self.page_edit.text()
            .strip()
        )

        try:
            page_number = int(text)

        except ValueError:
            self.update_page_label()
            return

        if page_number < 1:
            page_number = 1

        if page_number > len(self.pages):
            page_number = len(self.pages)

        self.current_page = (
            page_number - 1
        )

        self.save_reading_progress()

        self.load_current_page()

        self.page_edit.setFocus()

        self.page_edit.selectAll()

    # ========================================================
    # Reading progress
    # ========================================================

    def save_reading_progress(self):

        if self.volume_completed:
            return

        if self.progress_key is None:
            return

        if self.torrent_id is None:
            return

        if self.volume_name is None:
            return

        self.progress.save_page(
            self.progress_key,
            self.torrent_id,
            self.volume_name,
            self.current_page,
        )

    def finish_volume(self):

        if self.volume_completed:
            return

        self.volume_completed = True

        if self.progress_key is not None:

            self.progress.remove_volume(
                self.progress_key
            )

        print(
            "Volume completed: "
            f"{self.volume_name}",
            flush=True,
        )

        self.volume_finished.emit()

        self.close()

    # ========================================================
    # Page loading
    # ========================================================

    def page_loaded(
        self,
        page_number,
        data,
    ):

        if page_number != self.current_page:
            return

        image = QImage()

        if not image.loadFromData(data):

            self.page_failed(
                page_number,
                "Unable to decode image",
            )

            return

        self.original_pixmap = (
            QPixmap.fromImage(image)
        )

        self.update_image()

    def page_failed(
        self,
        page_number,
        error,
    ):

        if page_number != self.current_page:
            return

        self.page_total_label.setText(
            f"/ {len(self.pages)} — "
            f"Error: {error}"
        )

        self.page_edit.setText(
            str(page_number + 1)
        )

    def update_page_label(self):

        self.page_edit.setText(
            str(self.current_page + 1)
        )

        self.page_total_label.setText(
            f"/ {len(self.pages)}"
        )

        self.page_edit.setValidator(
            QIntValidator(
                1,
                max(1, len(self.pages)),
                self.page_edit,
            )
        )

    # ========================================================
    # Image
    # ========================================================

    def update_image(self):

        if self.original_pixmap is None:
            return

        pixmap = self.original_pixmap

        viewport_size = (
            self.scroll_area.viewport().size()
        )

        if (
            viewport_size.width() <= 0
            or viewport_size.height() <= 0
        ):
            return

        fit_pixmap = pixmap.scaled(
            viewport_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        width = int(
            fit_pixmap.width()
            * self.zoom_factor
        )

        height = int(
            fit_pixmap.height()
            * self.zoom_factor
        )

        if width <= 0 or height <= 0:
            return

        scaled_pixmap = pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_label.setPixmap(
            scaled_pixmap
        )

        self.image_label.resize(
            scaled_pixmap.size()
        )

        if self.zoom_factor > 1.0:

            self.image_label.setCursor(
                Qt.CursorShape.OpenHandCursor
            )

        else:

            self.image_label.setCursor(
                Qt.CursorShape.ArrowCursor
            )

    # ========================================================
    # Zoom
    # ========================================================

    def set_zoom(
        self,
        zoom,
    ):

        self.zoom_factor = max(
            self.min_zoom,
            min(
                zoom,
                self.max_zoom,
            ),
        )

        self.update_image()

    def zoom_in(self):

        self.set_zoom(
            self.zoom_factor * 1.25
        )

    def zoom_out(self):

        self.set_zoom(
            self.zoom_factor / 1.25
        )

    def reset_zoom(self):

        self.set_zoom(
            1.0
        )

    def wheelEvent(self, event):

        if (
            event.modifiers()
            & Qt.KeyboardModifier.ControlModifier
        ):

            if event.angleDelta().y() > 0:

                self.zoom_in()

            elif event.angleDelta().y() < 0:

                self.zoom_out()

            event.accept()

            return

        super().wheelEvent(event)

    # ========================================================
    # Panning
    # ========================================================

    def image_drag_started(
        self,
        position,
    ):

        if self.zoom_factor <= 1.0:
            return

        self.dragging = True

        self.drag_start_position = (
            position
        )

        self.image_label.setCursor(
            Qt.CursorShape.ClosedHandCursor
        )

    def image_drag_moved(
        self,
        position,
    ):

        if not self.dragging:
            return

        if self.drag_start_position is None:
            return

        delta = (
            position
            - self.drag_start_position
        )

        horizontal_scrollbar = (
            self.scroll_area.horizontalScrollBar()
        )

        vertical_scrollbar = (
            self.scroll_area.verticalScrollBar()
        )

        horizontal_scrollbar.setValue(
            horizontal_scrollbar.value()
            - int(delta.x())
        )

        vertical_scrollbar.setValue(
            vertical_scrollbar.value()
            - int(delta.y())
        )

        self.drag_start_position = position

    def image_drag_finished(
        self,
        position,
    ):

        if not self.dragging:
            return

        self.dragging = False

        self.drag_start_position = None

        if self.zoom_factor > 1.0:

            self.image_label.setCursor(
                Qt.CursorShape.OpenHandCursor
            )

        else:

            self.image_label.setCursor(
                Qt.CursorShape.ArrowCursor
            )

    # ========================================================
    # Keyboard
    # ========================================================

    def eventFilter(
        self,
        watched,
        event,
    ):

        if event.type() == QEvent.Type.KeyPress:

            # Let the page number editor handle its own
            # keyboard input.
            if watched is self.page_edit:
                return super().eventFilter(
                    watched,
                    event,
                )

            key = event.key()

            if key == Qt.Key.Key_Right:

                self.next_page()

                return True

            if key == Qt.Key.Key_Left:

                self.previous_page()

                return True

            if key == Qt.Key.Key_Escape:

                self.close()

                return True

            if (
                key == Qt.Key.Key_0
                and (
                    event.modifiers()
                    & Qt.KeyboardModifier.ControlModifier
                )
            ):

                self.reset_zoom()

                return True

        return super().eventFilter(
            watched,
            event,
        )

    # ========================================================
    # Window events
    # ========================================================

    def resizeEvent(
        self,
        event,
    ):

        super().resizeEvent(
            event
        )

        self.update_image()

    def closeEvent(
        self,
        event,
    ):

        app = QApplication.instance()

        if app is not None:

            app.removeEventFilter(
                self
            )

        # Don't save the final page after the volume
        # was explicitly completed.
        self.save_reading_progress()

        self.worker_thread.quit()

        self.worker_thread.wait()

        self.archive.close()

        event.accept()

        self.closed.emit()
