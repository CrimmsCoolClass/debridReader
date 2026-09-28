from typing import Optional

from PySide6.QtCore import (
    QEvent,
    Qt,
    Signal,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from remotepdf import RemotePDF


# ============================================================
# Image label
# ============================================================

class ImageLabel(QLabel):
    """
    QLabel used for displaying and dragging PDF pages.
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
# PDF reader window
# ============================================================

class PDFReaderWindow(QMainWindow):

    closed = Signal()

    def __init__(
        self,
        pdf: RemotePDF,
        initial_page: int = 0,
        parent=None,
    ):
        super().__init__(parent)

        self.pdf: Optional[RemotePDF] = pdf

        self.current_page = max(
            0,
            min(
                initial_page,
                pdf.page_count - 1,
            ),
        )

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
            "PDF Reader"
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
        # Page navigation
        # ----------------------------------------------------

        self.previous_button = QPushButton(
            "Previous"
        )

        self.next_button = QPushButton(
            "Next"
        )

        self.page_number_label = QLabel()

        self.previous_button.clicked.connect(
            self.previous_page
        )

        self.next_button.clicked.connect(
            self.next_page
        )

        navigation_layout = QHBoxLayout()

        navigation_layout.addStretch()

        navigation_layout.addWidget(
            self.previous_button
        )

        navigation_layout.addWidget(
            self.page_number_label
        )

        navigation_layout.addWidget(
            self.next_button
        )

        navigation_layout.addStretch()

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

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
        # Keyboard
        # ----------------------------------------------------

        app = QApplication.instance()

        if app is not None:
            app.installEventFilter(
                self
            )

        # ----------------------------------------------------
        # Initial page
        # ----------------------------------------------------

        self.update_page()

    # ========================================================
    # Page navigation
    # ========================================================

    def previous_page(self):

        if self.current_page <= 0:
            return

        self.current_page -= 1

        self.update_page()

    def next_page(self):

        pdf = self.pdf

        if pdf is None:
            return

        if (
            self.current_page
            >= pdf.page_count - 1
        ):
            return

        self.current_page += 1

        self.update_page()

    def update_page(self):

        pdf = self.pdf

        if pdf is None:
            return

        # Reset zoom when changing pages.
        self.zoom_factor = 1.0

        self.original_pixmap = None

        png_data = pdf.render_page(
            self.current_page,
            scale=1.5,
        )

        pixmap = QPixmap()

        if not pixmap.loadFromData(
            png_data
        ):
            return

        self.original_pixmap = pixmap

        self.update_image()

        self.page_number_label.setText(
            f"Page {self.current_page + 1} / "
            f"{pdf.page_count}"
        )

        self.previous_button.setEnabled(
            self.current_page > 0
        )

        self.next_button.setEnabled(
            self.current_page
            < pdf.page_count - 1
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

        # Fit the page to the available viewport first.
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

        # Apply zoom to the fitted dimensions.
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

        pdf = self.pdf

        self.pdf = None

        if pdf is not None:

            pdf.close()

        self.closed.emit()

        event.accept()
