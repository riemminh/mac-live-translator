"""Centralized dark theme stylesheet for native macOS appearance."""

from __future__ import annotations

DARK_THEME_QSS = """
QMainWindow, QWidget#rootWidget {
    background-color: #17151e;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
QSplitter::handle {
    background-color: #2a2538;
    width: 3px;
    margin: 2px 0px;
}
QSplitter::handle:hover {
    background-color: #7c3aed;
}
QFrame.cardFrame {
    background-color: #221e2c;
    border: 1px solid #342e42;
    border-radius: 10px;
}
QFrame.subCardFrame {
    background-color: #1b1723;
    border: 1px solid #302a3d;
    border-radius: 8px;
}
QLabel {
    color: #e2e8f0;
    font-size: 13px;
}
QLabel.sectionTitle {
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
}
QLabel.fieldLabel {
    font-size: 11px;
    font-weight: 600;
    color: #94a3b8;
}
QLineEdit {
    background-color: #1b1723;
    border: 1px solid #3d354e;
    border-radius: 6px;
    color: #ffffff;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: #7c3aed;
}
QLineEdit:focus {
    border: 1px solid #8b5cf6;
    background-color: #201b2a;
}
QLineEdit::placeholder {
    color: #64748b;
}
QTextEdit {
    background-color: #1b1723;
    border: 1px solid #302a3d;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 13px;
    padding: 6px;
    selection-background-color: #7c3aed;
}
QComboBox {
    background-color: #221e2c;
    border: 1px solid #3d354e;
    border-radius: 6px;
    color: #ffffff;
    padding: 4px 10px;
    font-size: 12px;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #5b4f73;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #221e2c;
    border: 1px solid #473e5c;
    selection-background-color: #4c1d95;
    color: #ffffff;
    outline: none;
    padding: 4px;
}
QPushButton {
    background-color: #2a2538;
    border: 1px solid #3d354e;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 12px;
    font-weight: 500;
    padding: 5px 12px;
}
QPushButton:hover {
    background-color: #37304a;
    border-color: #554a6c;
}
QPushButton:pressed {
    background-color: #201b2c;
}
QPushButton:disabled {
    background-color: #1b1723;
    border-color: #272233;
    color: #524b61;
}
QPushButton#primaryCopilotBtn {
    background-color: #6d28d9;
    border: 1px solid #8b5cf6;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 14px;
    border-radius: 6px;
}
QPushButton#primaryCopilotBtn:hover {
    background-color: #7c3aed;
    border-color: #a78bfa;
}
QPushButton#primaryCopilotBtn:disabled {
    background-color: #2e1d4d;
    border-color: #3d2666;
    color: #6d5b88;
}
QPushButton#stopBtn {
    background-color: #7f1d1d;
    border: 1px solid #ef4444;
    color: #fee2e2;
    font-weight: 700;
}
QPushButton#stopBtn:hover {
    background-color: #991b1b;
}
QPushButton#startBtn {
    background-color: #14532d;
    border: 1px solid #22c55e;
    color: #dcfce7;
    font-weight: 700;
}
QPushButton#startBtn:hover {
    background-color: #166534;
}
QCheckBox {
    color: #e2e8f0;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #4a3f60;
    border-radius: 4px;
    background-color: #1b1723;
}
QCheckBox::indicator:checked {
    background-color: #7c3aed;
    border-color: #a78bfa;
}
QScrollBar:vertical {
    border: none;
    background-color: #17151e;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background-color: #383049;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background-color: #554970;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
