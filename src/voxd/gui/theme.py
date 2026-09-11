"""Shared dark theme for VOXD windows and dialogs.

Parented dialogs inherit the main window's `color: white` cascade while
their background follows the system (often light) theme, rendering
white-on-white text. Applying this stylesheet explicitly keeps every
dialog readable regardless of the system theme.
"""

DARK_DIALOG_STYLE = """
QWidget {
    background-color: #2e2e2e;
    color: white;
    font-size: 10pt;
}
QLabel {
    background-color: transparent;
    color: white;
}
QLabel:disabled {
    color: #888;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
    background-color: #1e1e1e;
    color: white;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: #FF4500;
}
QComboBox {
    background-color: #1e1e1e;
    color: white;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 3px 6px;
}
QComboBox QAbstractItemView {
    background-color: #1e1e1e;
    color: white;
    selection-background-color: #FF4500;
    border: 1px solid #555;
}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: #242424;
    color: #888;
}
QPushButton {
    background-color: #444;
    color: white;
    border: 1px solid #555;
    border-radius: 5px;
    padding: 5px 12px;
}
QPushButton:hover {
    background-color: #555;
}
QPushButton:pressed {
    background-color: #666;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #888;
}
QDialogButtonBox QPushButton {
    min-width: 70px;
}
QCheckBox {
    background-color: transparent;
    color: white;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #777;
    border-radius: 3px;
    background-color: #555;
}
QCheckBox::indicator:checked {
    background-color: #E03D00;
}
QGroupBox {
    border: 1px solid #555;
    border-radius: 6px;
    margin-top: 12px;
    color: white;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
}
QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background-color: #2e2e2e;
    width: 12px;
}
QScrollBar::handle:vertical {
    background-color: #555;
    border-radius: 6px;
    min-height: 20px;
}
QTableWidget {
    background-color: #1e1e1e;
    color: white;
    gridline-color: #444;
    selection-background-color: #FF4500;
}
QHeaderView::section {
    background-color: #3a3a3a;
    color: white;
    border: 1px solid #555;
    padding: 4px;
}
QProgressBar {
    background-color: #1e1e1e;
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background-color: #FF4500;
    border-radius: 3px;
}
QMenu {
    background-color: #2e2e2e;
    color: white;
    border: 1px solid #555;
}
QMenu::item:selected {
    background-color: #444;
}
"""


def apply_dark_theme(widget) -> None:
    """Apply the shared dark stylesheet to a dialog or window."""
    try:
        widget.setStyleSheet(DARK_DIALOG_STYLE)
    except Exception:
        pass
