from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget
from src.core.colors import Colors


class CurveChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve = {}
        self._anim_progress = 0.0
        self._anim = None
        self.setMinimumHeight(150)
        self.setMaximumHeight(190)

    def set_curve(self, curve: dict):
        self._curve = curve
        self._anim_progress = 0.0
        self._anim = QPropertyAnimation(self, b"animProgress")
        self._anim.setDuration(600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self.update)
        self._anim.start()

    def get_animProgress(self):
        return self._anim_progress

    def set_animProgress(self, v):
        self._anim_progress = v
        self.update()

    animProgress = property(get_animProgress, set_animProgress)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._curve:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "Build a deck to see the mana curve")
            return

        max_cmc = max(self._curve.keys(), default=7)
        max_count = max(self._curve.values(), default=1)
        if max_count == 0:
            return

        w, h = self.width(), self.height()
        n_bars = max_cmc + 1
        gap = 6
        total_gap = gap * (n_bars - 1)
        bar_w = max(14, min(42, (w - 40 - total_gap) // n_bars))
        x_start = (w - (bar_w * n_bars + total_gap)) // 2
        y_bottom = h - 26

        for cmc in range(n_bars):
            count = self._curve.get(cmc, 0)
            full_h = int((count / max_count) * (y_bottom - 24)) if max_count else 0
            bar_h = int(full_h * self._anim_progress)
            x = x_start + cmc * (bar_w + gap)
            y = y_bottom - bar_h

            if cmc <= 2:
                c1, c2 = QColor("#34d399"), QColor("#059669")
            elif cmc <= 4:
                c1, c2 = QColor("#e8b830"), QColor("#b89020")
            elif cmc <= 6:
                c1, c2 = QColor("#f87171"), QColor("#dc2626")
            else:
                c1, c2 = QColor("#a855f7"), QColor("#7c3aed")

            if bar_h > 0:
                grad = QLinearGradient(x, y, x, y_bottom)
                grad.setColorAt(0, c1)
                grad.setColorAt(1, c2)
                painter.setBrush(QBrush(grad))
                painter.setPen(QPen(c2.darker(120), 1))
                painter.drawRoundedRect(x, y, bar_w, bar_h, 4, 4)
                painter.setPen(QColor(Colors.TEXT))
                painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                painter.drawText(x, y - 14, bar_w, 14, Qt.AlignCenter, str(count))

            painter.setPen(QColor(Colors.TEXT_DIM) if count == 0 else QColor(Colors.TEXT))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(x, y_bottom + 4, bar_w, 18, Qt.AlignCenter, str(cmc))

        painter.end()
