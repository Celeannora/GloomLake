from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from src.core.colors import Colors


class SummaryCard(QFrame):
    def __init__(self, label: str, value: str, color: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
            }}
        """)
        self._color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self.val_label = QLabel(value)
        self.val_label.setStyleSheet(
            f"color: {color}; font-size: 22px; font-weight: 700; border: none;"
        )
        self.val_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.val_label)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 10px; border: none;"
        )
        self.lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl)

    def set_value(self, value: str, color: str | None = None):
        c = color or self._color
        self.val_label.setText(str(value))
        self.val_label.setStyleSheet(
            f"color: {c}; font-size: 22px; font-weight: 700; border: none;"
        )


def make_panel(title: str, subtitle: str = "") -> QFrame:
    from PySide6.QtWidgets import QVBoxLayout
    frame = QFrame()
    frame.setObjectName("glassPanel")
    frame.setStyleSheet(f"""
        #glassPanel {{
            background: {Colors.CARD};
            border: 1px solid {Colors.CARD_BORDER};
            border-radius: 12px;
        }}
    """)
    v = QVBoxLayout(frame)
    v.setContentsMargins(16, 12, 16, 14)
    v.setSpacing(6)

    head = QLabel(title)
    head.setStyleSheet(
        f"color: {Colors.ACCENT}; font-weight: 700; font-size: 13px; border: none;"
    )
    v.addWidget(head)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; border: none; margin-bottom: 2px;"
        )
        v.addWidget(sub)

    return frame
