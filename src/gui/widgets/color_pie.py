from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget
from src.core.colors import Colors


class ColorPieWidget(QWidget):
    """Small donut chart showing colour distribution."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = {}
        self.setMinimumSize(100, 100)
        self.setMaximumSize(160, 160)

    def set_counts(self, counts: dict):
        self._counts = counts
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._counts or sum(self._counts.values()) == 0:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignCenter, "No color data")
            return

        total = sum(self._counts.values())
        w, h = self.width(), self.height()
        side = min(w, h) - 16
        x, y = (w - side) // 2, (h - side) // 2
        rect = QRect(x, y, side, side)

        start_angle = 90 * 16
        for color in "WUBRG":
            count = self._counts.get(color, 0)
            if count <= 0:
                continue
            span = int(360 * 16 * count / total)
            mc = Colors.MANA.get(color, {})
            painter.setBrush(QBrush(QColor(mc.get("bg", "#888"))))
            painter.setPen(QPen(QColor(Colors.BG), 2))
            painter.drawPie(rect, start_angle, span)
            start_angle += span

        painter.setBrush(QBrush(QColor(Colors.BG)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect.center(), side // 5, side // 5)
        painter.end()
